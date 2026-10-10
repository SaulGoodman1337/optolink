"""Pure offline deterministic protocol tests. No serial/USB or services."""
from __future__ import annotations

import sys
import tempfile
import threading
import subprocess
import os
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from handover_acceleration.coordinator import (
    ACK, DEVICE_ID, EOT, GFA, P300_ID, P300_SOFTWARE, SOFTWARE,
    STX, VS1_ID, VS1_SOFTWARE, BusyError, HandoverCoordinator,
    Mode, WirePhase, PortLease, ProtocolError, RestoreError,
)


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += max(seconds, 0)


class FakePort:
    """Only enqueues RX after the exact expected TX; no spontaneous replies."""
    def __init__(self, script):
        self.script = list(script)
        self.buf = bytearray()
        self.writes = []
        self.closed = False
        self.resets = 0

    def write(self, data):
        if self.closed:
            raise AssertionError("closed port")
        if self.buf:
            raise AssertionError("request before earlier response drained")
        if not self.script:
            raise AssertionError("unexpected TX " + data.hex())
        expected, reply = self.script.pop(0)
        if expected != data:
            raise AssertionError(f"expected TX {expected.hex()}, got {data.hex()}")
        self.writes.append(data)
        self.buf += reply
        return len(data)

    def read(self, count):
        ret = bytes(self.buf[:count])
        del self.buf[:count]
        return ret

    def reset_input_buffer(self):
        self.resets += 1
        self.buf.clear()

    def close(self):
        self.closed = True


class StallP300FramePort(FakePort):
    """Deliver request ACK but withhold STX beyond a single frame deadline."""
    def __init__(self, script, clock):
        super().__init__(script)
        self.clock = clock
        self.pending = None
        self.release_at = None

    def write(self, data):
        if data == P300_ID and self.pending is None:
            expected, reply = self.script.pop(0)
            if expected != data or not reply.startswith(ACK):
                raise AssertionError('invalid delayed P300 script')
            self.writes.append(data)
            self.buf.extend(ACK)
            self.pending = reply[1:]
            self.release_at = self.clock.now + 4.0
            return len(data)
        return super().write(data)

    def read(self, count):
        if self.pending is not None and self.clock.now >= self.release_at:
            self.buf.extend(self.pending)
            self.pending = None
        return super().read(count)

    def reset_input_buffer(self):
        self.pending = None
        super().reset_input_buffer()


def expect_vs1(enqs=2, *, device=DEVICE_ID, software=SOFTWARE, p80=b"\x20", p06=b"\x00"):
    return [
        (EOT, b"\x05" * enqs),
        (STX + VS1_ID, device),
        (VS1_SOFTWARE, software),
        (GFA["P80"], p80),
        (GFA["P06"], p06),
    ]


def expect_attached_vs1(*, device=DEVICE_ID, software=SOFTWARE,
                        p80=b"\x20", p06=b"\x00"):
    """Already initialized original splitter: NO second STX, EOT or ENQ."""
    from handover_acceleration.coordinator import VS1_ID
    return [
        (VS1_ID, device),
        (VS1_SOFTWARE, software),
        (GFA["P80"], p80),
        (GFA["P06"], p06),
    ]


def p300_reply(address, data, *, bad_crc=False, wrong_addr=False):
    if wrong_addr:
        address ^= 1
    b = bytes([1, 1, address >> 8, address & 255, len(data)]) + data
    crc = (7 + sum(b)) & 255
    if bad_crc:
        crc ^= 0xff
    return ACK + bytes([0x41, 7]) + b + bytes([crc])


def expect_p300(*, bad_crc=False, wrong_addr=False, ack=ACK):
    return [
        (EOT, b"\x05"),
        (b"\x16\x00\x00", ack),
        (P300_ID, p300_reply(0xf8, DEVICE_ID, bad_crc=bad_crc, wrong_addr=wrong_addr)),
        (ACK, b""),
        (P300_SOFTWARE, p300_reply(0x778c, SOFTWARE)),
        (ACK, b""),
    ]


class OfflineHandoverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.lock_path = Path(self.temp.name) / "serial.lock"
        self.clock = FakeClock()

    def manager(self, script):
        port = FakePort(script)
        coordinator = HandoverCoordinator(lambda: port, PortLease(self.lock_path),
                                           clock=self.clock.monotonic, sleep=self.clock.sleep)
        return coordinator, port

    def test_full_single_enq_roundtrip_and_gfa(self):
        m, p = self.manager(expect_vs1() + expect_p300() +
                            [(P300_ID, p300_reply(0xf8, DEVICE_ID)), (ACK, b"")] +
                            expect_vs1(1) + [(GFA["P06"], b"\x17")])
        with m:
            answer = m.p300_window(lambda x: x.p300_identity())
            self.assertEqual(answer, DEVICE_ID)
            self.assertEqual(m.mode, Mode.VS1_VERIFIED)
            self.assertEqual(m.gfa_read("P06"), b"\x17")
            self.assertEqual(m.history, [("vs1", "verified:2"),
                                         ("p300", "verified"),
                                         ("vs1", "verified:1")])
        self.assertEqual(p.script, [])
        self.assertEqual(p.writes.count(EOT), 3)
        self.assertTrue(p.closed)

    def test_reuses_current_verified_vs1_without_handshake(self):
        m, p = self.manager(expect_vs1() + [(GFA["P80"], b"\x20")])
        with m:
            self.assertEqual(m.gfa_read("P80"), b"\x20")
            self.assertEqual(m.mode, Mode.VS1_VERIFIED)
        self.assertEqual(p.writes.count(EOT), 1)
        self.assertEqual(p.script, [])

    def test_p300_id_read_only_when_verified(self):
        m, p = self.manager(expect_vs1() + expect_p300() +
            [(P300_ID, p300_reply(0xf8, DEVICE_ID)), (ACK, b"")] + expect_vs1(1))
        with m:
            with self.assertRaises(ProtocolError):
                m.p300_identity()
            m.to_p300()
            self.assertEqual(m.p300_identity(), DEVICE_ID)
            m.to_vs1_fast()
        self.assertEqual(p.script, [])

    def test_rejects_p300_bad_crc_and_conservatively_recovers(self):
        # No ACK may be sent for the corrupt response.
        script = expect_vs1() + expect_p300(bad_crc=True)[:3] + expect_vs1(2)
        m, p = self.manager(script)
        with self.assertRaises(ProtocolError):
            with m:
                m.p300_window(lambda x: x.p300_identity())
        self.assertEqual(p.script, [])
        self.assertEqual(m.history[-1], ("vs1", "verified:2"))
        self.assertNotIn(("p300", "verified"), m.history)

    def test_rejects_wrong_p300_address(self):
        script = expect_vs1() + expect_p300(wrong_addr=True)[:3] + expect_vs1(2)
        m, p = self.manager(script)
        with self.assertRaises(ProtocolError):
            with m:
                m.to_p300()
        self.assertEqual(p.script, [])
        self.assertIn(("p300", "failed"), m.history)

    def test_single_enq_wrong_identity_never_silent_fallback(self):
        script = expect_vs1() + expect_p300() + [
            (EOT, b"\x05"), (STX + VS1_ID, b"\x00\x00")
        ] + expect_vs1(2)
        m, p = self.manager(script)
        with self.assertRaisesRegex(ProtocolError, "VS1 device identity mismatch"):
            with m:
                m.p300_window(lambda x: 1)
        self.assertEqual(p.script, [])
        self.assertEqual(m.history[-2:], [("vs1", "failed"),
                                          ("vs1", "verified:2")])
        self.assertEqual(p.writes.count(EOT), 4)

    def test_wrong_software_initialisation_has_no_success(self):
        m, p = self.manager(expect_vs1(2, software=b"\x00\x00"))
        with self.assertRaisesRegex(ProtocolError, "VS1 software"):
            with m:
                pass
        self.assertTrue(p.closed)
        self.assertIn(("vs1", "failed"), m.history)
        self.assertNotIn(("vs1", "verified:2"), m.history)

    def test_wrong_p80_aborts_before_exposing_gfa(self):
        m, p = self.manager(expect_vs1(2, p80=b"\x21"))
        with self.assertRaisesRegex(ProtocolError, "P80"):
            with m:
                pass
        self.assertTrue(p.closed)

    def test_ff_p06_never_presented_as_actual_rpm(self):
        m, p = self.manager(expect_vs1(2, p06=b"\xff"))
        with self.assertRaisesRegex(ProtocolError, "P06 invalid FF"):
            with m:
                pass
        self.assertTrue(p.closed)

    def test_no_gfa_in_p300_and_no_unknown_opcode(self):
        m, p = self.manager(expect_vs1() + expect_p300() + expect_vs1(2))
        with m:
            m.to_p300()
            with self.assertRaises(ProtocolError):
                m.gfa_read("P06")
            with self.assertRaises(ProtocolError):
                m.to_p300()
            self.assertEqual(m.mode, Mode.P300_VERIFIED)
            m.restore_vs1()
            with self.assertRaises(ProtocolError):
                m.gfa_read("C9")
        self.assertEqual(p.script, [])

    def test_failed_auto_restore_marks_failure_and_closes(self):
        script = expect_vs1() + expect_p300() + [(EOT, b"\x05"),
                (STX + VS1_ID, b"\x00\x00"), (EOT, b"")]
        m, p = self.manager(script)
        with self.assertRaises(RestoreError):
            with m:
                m.p300_window(lambda x: None)
        self.assertTrue(p.closed)
        self.assertEqual(m.mode, Mode.FAILED_CLOSED)
        self.assertEqual(p.writes.count(EOT), 4)  # no unbounded retry

    def test_missing_enq_timeout_causes_fail_closed(self):
        m, p = self.manager([(EOT, b"")])
        with self.assertRaisesRegex(ProtocolError, "RX deadline"):
            with m:
                pass
        self.assertGreaterEqual(self.clock.now, 6.0)
        self.assertTrue(p.closed)

    def test_port_lease_blocks_second_owner_before_open(self):
        a, p1 = self.manager(expect_vs1())
        opened = []
        b = HandoverCoordinator(lambda: opened.append(1), PortLease(self.lock_path),
                                clock=self.clock.monotonic, sleep=self.clock.sleep)
        with a:
            with self.assertRaises(BusyError):
                with b:
                    pass
            self.assertEqual(opened, [])
        self.assertTrue(p1.closed)

    def test_window_serializes_a_competing_request(self):
        # Different threads cannot inject an interleaving VS1 GFA read.
        m, p = self.manager(expect_vs1() + expect_p300() + expect_vs1(1) +
                            [(GFA["P09"], b"\x01")])
        entered = threading.Event()
        release = threading.Event()
        out = []
        def window(c):
            entered.set()
            self.assertTrue(release.wait(timeout=2))
            return "done"
        def reader():
            self.assertTrue(entered.wait(timeout=2))
            out.append(m.gfa_read("P09"))
        with m:
            t1 = threading.Thread(target=lambda: out.append(m.p300_window(window)))
            t2 = threading.Thread(target=reader)
            t1.start(); t2.start()
            self.assertTrue(entered.wait(timeout=2))
            release.set()
            t1.join(timeout=3); t2.join(timeout=3)
            self.assertFalse(t1.is_alive() or t2.is_alive())
        self.assertCountEqual(out, [b"\x01", "done"])
        self.assertEqual(p.script, [])

    def test_p300_start_nack_triggers_separate_two_enq_recovery(self):
        m, p = self.manager(expect_vs1() + expect_p300(ack=b"\x15")[:2] + expect_vs1(2))
        with self.assertRaisesRegex(ProtocolError, "unexpected control"):
            with m:
                m.p300_window(lambda x: None)
        self.assertEqual(p.script, [])
        self.assertEqual(m.history[-1], ("vs1", "verified:2"))

    def test_p300_software_identity_mismatch_blocks_activation(self):
        script = expect_vs1() + expect_p300()[:4] + [
            (P300_SOFTWARE, p300_reply(0x778c, b"\x00\x00"))
        ] + expect_vs1(2)
        m, p = self.manager(script)
        with self.assertRaisesRegex(ProtocolError, "P300 identity mismatch"):
            with m:
                m.to_p300()
        self.assertEqual(p.script, [])
        self.assertNotIn(("p300", "verified"), m.history)

    def test_p300_enq_timeout_restore_conservatively(self):
        script = expect_vs1() + [(EOT, b"")] + expect_vs1(2)
        m, p = self.manager(script)
        with self.assertRaisesRegex(ProtocolError, "RX deadline"):
            with m:
                m.p300_window(lambda x: 1)
        self.assertEqual(p.script, [])
        self.assertEqual(m.history[-1], ("vs1", "verified:2"))

    def test_p300_frame_stall_has_one_absolute_deadline(self):
        script = expect_vs1() + expect_p300()[:3] + expect_vs1(2)
        p = StallP300FramePort(script, self.clock)
        m = HandoverCoordinator(lambda: p, PortLease(self.lock_path),
                                clock=self.clock.monotonic, sleep=self.clock.sleep)
        with self.assertRaisesRegex(ProtocolError, 'RX deadline'):
            with m:
                m.to_p300()
        # P300 ACK is immediate. Its late STX must not grant more than 3 s.
        self.assertLess(self.clock.now, 3.5)
        self.assertEqual(m.history[-1], ('vs1', 'verified:2'))
        self.assertEqual(p.script, [])

    def test_application_callback_error_restores_fast_vs1(self):
        m, p = self.manager(expect_vs1() + expect_p300() + expect_vs1(1))
        def application_error(_):
            raise ValueError('offline callback failure')
        with self.assertRaisesRegex(ValueError, 'offline callback failure'):
            with m:
                m.p300_window(application_error)
        self.assertEqual(m.history[-1], ('vs1', 'verified:1'))
        self.assertEqual(p.script, [])

    def test_runtime_gfa_ff_invalidates_session_before_recovery(self):
        script = expect_vs1() + [(GFA["P06"], b"\xff")] + expect_vs1(2)
        m, p = self.manager(script)
        with self.assertRaisesRegex(ProtocolError, "invalid GFA response"):
            with m:
                try:
                    m.gfa_read("P06")
                finally:
                    self.assertEqual(m.mode, Mode.FAILED_CLOSED)
                    self.assertEqual(m.wire.phase, WirePhase.FAILED_CLOSED)
        self.assertEqual(p.script, [])
        self.assertIn(("vs1", "verified:2"), m.history)

    def test_raw_wire_rejects_gfa_and_resync_during_p300(self):
        m, p = self.manager(expect_vs1() + expect_p300() + expect_vs1(1))
        with m:
            m.to_p300()
            self.assertEqual(m.wire.phase, WirePhase.P300_VERIFIED)
            with self.assertRaisesRegex(ProtocolError, "not permitted in phase"):
                m.wire.tx(GFA["P06"])
            with self.assertRaisesRegex(ProtocolError, "not permitted in phase"):
                m.wire.tx(EOT)
            self.assertEqual(m.mode, Mode.P300_VERIFIED)
            m.to_vs1_fast()
        self.assertEqual(p.script, [])

    def test_raw_wire_rejects_p300_frames_during_vs1(self):
        m, p = self.manager(expect_vs1() + [(GFA["P87"], b"\x01")])
        with m:
            self.assertEqual(m.wire.phase, WirePhase.VS1_VERIFIED)
            with self.assertRaisesRegex(ProtocolError, "not permitted in phase"):
                m.wire.tx(P300_ID)
            self.assertEqual(m.gfa_read("P87"), b"\x01")
        self.assertEqual(p.script, [])

    def test_bad_lock_permissions_refuse_before_port_open(self):
        self.lock_path.write_bytes(b"")
        os.chmod(self.lock_path, 0o666)
        opened = []
        m = HandoverCoordinator(lambda: opened.append(1), PortLease(self.lock_path))
        with self.assertRaises(BusyError):
            with m:
                pass
        self.assertEqual(opened, [])

    def test_lock_symlink_refused_before_port_open(self):
        target = Path(self.temp.name) / "other.lock"
        target.write_bytes(b"")
        self.lock_path.symlink_to(target)
        opened = []
        m = HandoverCoordinator(lambda: opened.append(1), PortLease(self.lock_path))
        with self.assertRaises(BusyError):
            with m:
                pass
        self.assertEqual(opened, [])

    def test_cross_process_port_lock_rejects_second_owner(self):
        # Real OS-level flock in an independent process; no serial device.
        script = ("import fcntl, os, sys; "
                  "fd=os.open(sys.argv[1],os.O_CREAT|os.O_RDWR,0o600); "
                  "fcntl.flock(fd,fcntl.LOCK_EX); "
                  "print('LOCKED',flush=True); sys.stdin.readline(); os.close(fd)")
        proc = subprocess.Popen([sys.executable, "-c", script, str(self.lock_path)],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(proc.stdout.readline().strip(), "LOCKED")
            with self.assertRaises(BusyError):
                PortLease(self.lock_path).acquire()
        finally:
            proc.stdin.write("\n")
            proc.stdin.flush()
            proc.communicate(timeout=5)
        lease = PortLease(self.lock_path)
        lease.acquire()
        lease.release()

    def test_unknown_session_rejects_gfa_and_early_identity(self):
        m, p = self.manager(expect_vs1())
        self.assertEqual(m.mode, Mode.DETACHED)
        with self.assertRaises(ProtocolError):
            m.gfa_read("P80")
        with self.assertRaises(ProtocolError):
            m.p300_identity()
        self.assertEqual(p.writes, [])

    def test_fast_return_rejects_a_second_unsupported_enq_count(self):
        m, p = self.manager(expect_vs1() + expect_p300() + expect_vs1(1))
        with m:
            m.to_p300()
            with self.assertRaises(ProtocolError):
                m.wire.sync(2)  # never resync outside an explicit transition
            m.to_vs1_fast()
        self.assertEqual(p.writes.count(EOT), 3)
        self.assertEqual(p.script, [])

    def test_no_port_import_or_serial_device_dependency(self):
        # This check is structural: package imports without pyserial and /dev.
        import inspect
        import handover_acceleration.coordinator as c
        source = inspect.getsource(c)
        self.assertNotIn("import serial", source)
        self.assertNotIn("systemctl", source)
        self.assertNotIn("/dev/", source)


if __name__ == "__main__":
    unittest.main()

class VerifiedSnapshotTests(unittest.TestCase):
    """Only session-local GFA acquired inside fresh VS1 handshake is reusable."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clock = FakeClock()

    def coordinator(self, script):
        return HandoverCoordinator(lambda: FakePort(script),
                PortLease(Path(self.tmp.name) / 'port.lock'),
                clock=self.clock.monotonic, sleep=self.clock.sleep)

    def test_stored_gfa_was_read_during_verified_vs1_not_a_cache(self):
        m = self.coordinator(expect_vs1(2, p06=b'\x12') +
                    expect_p300() + expect_vs1(1, p06=b'\x23'))
        with m:
            self.assertEqual(m.verified_gfa_snapshot(), {'P80':b'\x20','P06':b'\x12'})
            m.to_p300()
            with self.assertRaisesRegex(ProtocolError, 'verified VS1'):
                m.verified_gfa_snapshot()
            m.to_vs1_fast()
            self.assertEqual(m.verified_gfa_snapshot(), {'P80':b'\x20','P06':b'\x23'})

    def test_snapshot_rejected_if_too_old(self):
        m = self.coordinator(expect_vs1())
        with m:
            self.clock.sleep(.76)
            with self.assertRaisesRegex(ProtocolError, 'stale'):
                m.verified_gfa_snapshot()

    def test_unbounded_freshness_limit_rejected(self):
        m = self.coordinator(expect_vs1())
        with m:
            with self.assertRaisesRegex(ProtocolError, 'missing or unbounded'):
                m.verified_gfa_snapshot(max_age=10)

    def test_bad_identity_cannot_publish_snapshot(self):
        m = self.coordinator(expect_vs1(2, p80=b'\x21'))
        with self.assertRaisesRegex(ProtocolError, 'P80'):
            with m:
                pass
        self.assertNotEqual(m.mode, Mode.VS1_VERIFIED)
