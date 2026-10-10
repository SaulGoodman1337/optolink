"""Kernel flock isolation of multi-request writers from P300 windows; offline."""
from __future__ import annotations

from pathlib import Path
import os
import stat
import subprocess
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from handover_acceleration.coordinator import PortLease, EOT
from handover_acceleration.phase_planner import Budget
from handover_acceleration.runtime_admission import RuntimeAdmissionGate, DispatcherSnapshot
from handover_acceleration.producer_fence import (
    ProducerFenceRejected, writer_transaction, p300_window,
    fenced_readonly_batch, LEASE_PATH, COOPERATIVE_SERVICES,
)
from test_handover_acceleration import FakePort, FakeClock, expect_vs1, expect_attached_vs1, expect_p300, p300_reply, P300_ID, ACK, DEVICE_ID
from test_handover_fc03_fixed import response


class ProducerFenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name)
        self.path=self.folder/'writer-epoch.lock'
        self.path.write_bytes(b'')
        self.path.chmod(0o600)

    def test_missing_provisioning_must_fail_closed(self):
        with self.assertRaisesRegex(ProducerFenceRejected, 'missing'):
            with p300_window(path=self.folder/'absent'):
                self.fail('no file should be auto-created')
        self.assertFalse((self.folder/'absent').exists())

    def test_refuse_invalid_writers_and_weak_producer_lease(self):
        self.assertEqual(COOPERATIVE_SERVICES,
                         frozenset({'party','schedule','maintenance',
                                    'service-programs','clock-sync','mqtt-direct',
                                    'tcp-direct'}))
        with self.assertRaises(ProducerFenceRejected):
            with writer_transaction('unregistered-writer', path=self.path):
                pass
        self.path.chmod(0o666)
        with self.assertRaisesRegex(ProducerFenceRejected, 'unsafe'):
            with p300_window(path=self.path):
                pass
        with self.assertRaisesRegex(ProducerFenceRejected, 'unsafe'):
            with writer_transaction('schedule',path=self.path):
                pass

    def test_symlink_and_hardlink_refused(self):
        link=self.folder/'link'
        link.symlink_to(self.path)
        with self.assertRaises(ProducerFenceRejected):
            with p300_window(path=link):
                pass
        hard=self.folder/'hard'
        os.link(self.path,hard)
        with self.assertRaisesRegex(ProducerFenceRejected, 'unsafe'):
            with p300_window(path=self.path):
                pass
        hard.unlink()

    def test_p300_crash_marker_blocks_new_controller_writers(self):
        with self.assertRaisesRegex(RuntimeError, 'artificial abort'):
            with p300_window(path=self.path) as proof:
                proof.begin()
                self.assertEqual(self.path.read_bytes(),b'P300_ACTIVE')
                raise RuntimeError('artificial abort')
        self.assertEqual(self.path.read_bytes(),b'P300_FAILED')
        with self.assertRaisesRegex(ProducerFenceRejected,'P300 was interrupted'):
            with writer_transaction('party',path=self.path):
                self.fail('cannot write during unresolved P300 session')
        with self.assertRaisesRegex(ProducerFenceRejected,'unverified or interrupted'):
            with p300_window(path=self.path):
                pass

    def test_successfully_verified_p300_window_clears_persistent_marker(self):
        with p300_window(path=self.path) as proof:
            proof.begin()
            self.assertEqual(self.path.read_bytes(),b'P300_ACTIVE')
            proof.confirm_verified_vs1()
        self.assertEqual(self.path.read_bytes(),b'')
        with writer_transaction('party',path=self.path):
            pass

    def test_one_party_transaction_blocks_entire_p300_window(self):
        with writer_transaction('party',path=self.path):
            with self.assertRaisesRegex(ProducerFenceRejected, 'external writer'):
                with p300_window(path=self.path):
                    self.fail('P300 between write and rollback')
        with p300_window(path=self.path):
            pass

    def test_p300_batch_prevents_new_writer_until_return(self):
        with p300_window(path=self.path):
            with self.assertRaisesRegex(ProducerFenceRejected, 'timeout'):
                with writer_transaction('schedule',path=self.path,max_wait_s=0.055):
                    self.fail('schedule writer interrupted P300')
        with writer_transaction('schedule',path=self.path,max_wait_s=0.05):
            pass

    def test_exception_releases_writer_lock_without_reporting_success(self):
        with self.assertRaisesRegex(RuntimeError,'controller rollback failed'):
            with writer_transaction('maintenance',path=self.path):
                raise RuntimeError('controller rollback failed')
        # An exception persists FAILED on disk even after flock was freed.
        with self.assertRaisesRegex(ProducerFenceRejected, 'unverified or interrupted'):
            with p300_window(path=self.path):
                self.fail('ambiguous previous write must not permit P300')

    def test_nested_transaction_uses_one_exclusive_flop_and_clears_marker(self):
        with writer_transaction('schedule',path=self.path):
            self.assertNotEqual(self.path.read_bytes(), b'')
            with writer_transaction('schedule',path=self.path):
                with self.assertRaises(ProducerFenceRejected):
                    with p300_window(path=self.path): pass
            self.assertTrue(self.path.read_bytes())
        self.assertEqual(self.path.read_bytes(), b'')
        with p300_window(path=self.path): pass

    def test_failed_inner_transaction_latches_even_when_outer_swallows(self):
        with writer_transaction('schedule',path=self.path):
            try:
                with writer_transaction('schedule',path=self.path):
                    raise ValueError('readback failed')
            except ValueError:
                pass
        self.assertTrue(self.path.read_bytes().startswith(b'FAILED:'))
        with self.assertRaises(ProducerFenceRejected):
            with p300_window(path=self.path): pass

    def test_real_separate_process_owns_exclusive_writer_lock(self):
        script = (
            'import sys,time; '
            'sys.path.insert(0,sys.argv[1]); '
            'from handover_acceleration.producer_fence import writer_transaction; '
            'from pathlib import Path; '
            'with writer_transaction("party",path=Path(sys.argv[2])): '
            ' print("LOCKED",flush=True); time.sleep(2)'
        )
        # A compound with statement cannot follow a semicolon in Python;
        # use a multiline script as the actual subprocess entrypoint.
        script = script.replace(
            '; with writer_transaction', '\nwith writer_transaction').replace(
            ':  print', ':\n print')
        tool=str(Path(__file__).resolve().parents[1]/'tools')
        child=subprocess.Popen([sys.executable,'-c',script,tool,str(self.path)],
                               stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            banner=child.stdout.readline().strip()
            self.assertEqual(banner,'LOCKED',
                             child.stderr.read() if child.poll() is not None else '')
            with self.assertRaises(ProducerFenceRejected):
                with p300_window(path=self.path):
                    self.fail('second process won a locked port')
        finally:
            child.terminate()
            child.communicate(timeout=3)
        # SIGTERM may kill the writer mid-readback. The OS releases flock,
        # but its durable ACTIVE marker must bar a new P300 window.
        with self.assertRaisesRegex(ProducerFenceRejected, 'unverified or interrupted'):
            with p300_window(path=self.path):
                pass

    def test_sigkill_during_p300_active_remains_blocked_after_new_process(self):
        """Nur Prozess-/Dateitest: niemals an den realen Optolink-Port."""
        import signal
        import time
        tool=str(Path(__file__).resolve().parents[1]/"tools")
        child_code=(
            "import sys,time\n"
            "from pathlib import Path\n"
            "sys.path.insert(0,sys.argv[1])\n"
            "from handover_acceleration.producer_fence import p300_window\n"
            "with p300_window(path=Path(sys.argv[2])) as proof:\n"
            "    proof.begin()\n"
            "    print('P300_ACTIVE',flush=True)\n"
            "    time.sleep(30)\n"
        )
        process=subprocess.Popen(
            [sys.executable,"-c",child_code,tool,str(self.path)],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            first=process.stdout.readline().strip()
            self.assertEqual(first,"P300_ACTIVE")
            self.assertEqual(self.path.read_bytes(),b"P300_ACTIVE")
            os.kill(process.pid,signal.SIGKILL)
            process.wait(timeout=5)
            self.assertEqual(process.returncode,-signal.SIGKILL)
            # flock was forcibly released, but marker persists on disk.
            self.assertEqual(self.path.read_bytes(),b"P300_ACTIVE")
            with self.assertRaises(ProducerFenceRejected):
                with writer_transaction("party",path=self.path): pass
            # Simulate a *freshly started* process after reboot/crash:
            fresh_code=(
                "import sys\n"
                "from pathlib import Path\n"
                "sys.path.insert(0,sys.argv[1])\n"
                "from handover_acceleration.producer_fence import p300_window\n"
                "try:\n"
                "    with p300_window(path=Path(sys.argv[2])): pass\n"
                "except Exception as exc:\n"
                "    print(type(exc).__name__)\n"
                "    raise SystemExit(0)\n"
                "raise SystemExit(9)\n"
            )
            new_process=subprocess.run(
                [sys.executable,"-c",fresh_code,tool,str(self.path)],
                capture_output=True,text=True,timeout=5)
            self.assertEqual(new_process.returncode,0,new_process.stderr)
            self.assertIn("ProducerFenceRejected",new_process.stdout)
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=3)

    def test_fenced_batch_refuses_writer_before_any_fake_serial_tx(self):
        class FailPort:
            def write(self, raw):
                raise AssertionError('must never transmit')
        clock=FakeClock()
        gate=RuntimeAdmissionGate(clock=clock.monotonic)
        snapshot=DispatcherSnapshot(
            mqtt_pending=0,tcp_pending=0,forced_polls_pending=0,
            pending_readbacks=0,frame_idle=True,
            external_writers_quiesced=True,queue_admission_paused=True,
            legacy_vs1_verified=True,nearest_writer_deadline_ms=12000)
        calls=[]
        with writer_transaction('party',path=self.path):
            with self.assertRaisesRegex(ProducerFenceRejected,'external writer'):
                fenced_readonly_batch(
                    gate, lambda:calls.append('snapshot') or snapshot, Budget(),
                    lock_path=self.path,port=FailPort(),
                    legacy_dispatch=lambda *_:self.fail('no legacy'),
                    resume_vs1=lambda:None,
                    serial_lease=PortLease(self.folder/'serial.lease'))
        self.assertFalse(calls)
        self.assertFalse((self.folder/'serial.lease').exists())

    def test_fenced_batch_holds_writer_lease_until_real_vs1_gfa_check(self):
        clock=FakeClock()
        port=FakePort(
            expect_attached_vs1() + expect_p300() +
            [(P300_ID,p300_reply(0xf8,DEVICE_ID)),(ACK,b'')] +
            response('ram_0f20_32') + response('ram_1c60_32') +
            expect_vs1(1))
        gate=RuntimeAdmissionGate(clock=clock.monotonic)
        budget=Budget(max_vs1_unavailable_ms=8000.0,max_p06_age_ms=9000.0)
        snapshot=DispatcherSnapshot(
            mqtt_pending=0,tcp_pending=0,forced_polls_pending=0,
            pending_readbacks=0,frame_idle=True,
            external_writers_quiesced=True,queue_admission_paused=True,
            legacy_vs1_verified=True,nearest_writer_deadline_ms=12000.0)
        observations=[]
        def read_legacy(req,ser):
            with self.assertRaisesRegex(ProducerFenceRejected,'external writer'):
                with p300_window(path=self.path):
                    pass
            observations.append(req)
            return (1,bytearray(b'\x20' if '4050' in req else b'\x53'),
                    'raw','1;0x4050;20')
        def get_snapshot():
            with self.assertRaisesRegex(ProducerFenceRejected,'external writer'):
                with p300_window(path=self.path):
                    pass
            observations.append('snapshot')
            return snapshot
        result=fenced_readonly_batch(
            gate,get_snapshot,budget,lock_path=self.path,port=port,
            legacy_dispatch=read_legacy,
            resume_vs1=lambda:observations.append('vs1-resume'),
            serial_lease=PortLease(self.folder/'serial.lease'),
            clock=clock.monotonic,sleep=clock.sleep)
        self.assertTrue(result.verified_vs1)
        self.assertEqual(result.p300_windows,1)
        self.assertEqual(port.writes.count(EOT),2)
        self.assertFalse(port.closed)
        self.assertEqual(observations[0],'snapshot')
        self.assertEqual(observations[-1], 'gfaread;0x4006;1;raw;False')
        with p300_window(path=self.path):
            pass


if __name__=='__main__':
    unittest.main()
