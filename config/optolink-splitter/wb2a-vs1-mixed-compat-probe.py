#!/usr/bin/env python3
"""Read-only WB2A mixed VS1 compatibility probe.

Purpose:
  Verify on the exact VDensHO1 / 20C2 appliance that stable Virtual_READ
  datapoints can be read via VS1 F7 while direct GFA_READ 6B requests are
  interleaved in the same persistent VS1 session.

The probe compares fixed, stable Virtual_READ values across:
  P300 baseline -> mixed VS1 session -> P300 post-check.

No write command is implemented. No controller setpoint, coding, process,
GFA, actuator, or safety value is changed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import os
from pathlib import Path
import signal
import stat
import sys
import time
import types

VERSION = "1.0.0"
PARENT_NAME = "wb2a-gfa-p80-probe.py"
PARENT_SHA256 = "6de883c422a09c821b342d12e5bb71dd3d518d8115ec2495bdfb202f5a7f50cb"
MIN_REPLY_GAP_S = 0.150

# Stable Virtual_READ values chosen from already established production/profile data.
STABLE = (
    ("device_id", 0x00F8, 2),
    ("device_sw_index", 0x00FB, 1),
    ("day_setpoint", 0x2306, 1),
    ("operating_mode", 0x2323, 1),
    ("dhw_setpoint", 0x6300, 1),
    ("circulation_interval", 0x6773, 1),
    ("controller_sw_raw", 0x778C, 2),
)
STABLE_BY_ADDR = {addr: (name, length) for name, addr, length in STABLE}

GFA = (
    ("P80", 0x4050),
    ("P06", 0x4006),
    ("P09", 0x4009),
    ("P87", 0x4057),
)
GFA_BY_ADDR = {addr: name for name, addr in GFA}


def crc_p300(frame_without_crc: bytes) -> int:
    if len(frame_without_crc) < 2 or frame_without_crc[0] != 0x41:
        raise ValueError("P300 frame must begin with 0x41.")
    return sum(frame_without_crc[1:]) & 0xFF


def p300_read_frame(address: int, length: int) -> bytes:
    if address not in STABLE_BY_ADDR or STABLE_BY_ADDR[address][1] != length:
        raise ValueError("P300 read outside fixed stable allowlist.")
    body = bytes((0x41, 0x05, 0x00, 0x01, address >> 8, address & 0xFF, length))
    return body + bytes((crc_p300(body),))


def vs1_virtual_frame(address: int, length: int, *, stx: bool = False) -> bytes:
    if address not in STABLE_BY_ADDR or STABLE_BY_ADDR[address][1] != length:
        raise ValueError("VS1 Virtual_READ outside fixed stable allowlist.")
    body = bytes((0xF7, address >> 8, address & 0xFF, length))
    return (b"\x01" + body) if stx else body


def gfa_frame(address: int, *, stx: bool = False) -> bytes:
    if address not in GFA_BY_ADDR:
        raise ValueError("GFA_READ outside fixed allowlist.")
    body = bytes((0x6B, address >> 8, address & 0xFF, 0x01))
    return (b"\x01" + body) if stx else body


def decode_p300_read(frame: bytes, address: int, length: int) -> bytes:
    if len(frame) < 8 or frame[0] != 0x41 or len(frame) != frame[1] + 3:
        raise ValueError("P300 response boundary/length mismatch: " + frame.hex(" "))
    if sum(frame[1:-1]) & 0xFF != frame[-1]:
        raise ValueError("P300 response checksum mismatch: " + frame.hex(" "))
    if frame[2] != 0x01 or (frame[3] & 0x1F) != 0x01:
        raise ValueError("P300 response is not successful Virtual_READ.")
    if int.from_bytes(frame[4:6], "big") != address:
        raise ValueError("P300 response address mismatch.")
    if frame[6] != length:
        raise ValueError("P300 response data-length field mismatch.")
    data = frame[7:-1]
    if len(data) != length:
        raise ValueError("P300 response payload length mismatch.")
    return data


def load_parent():
    path = Path(__file__).resolve().with_name(PARENT_NAME)
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != PARENT_SHA256:
        raise RuntimeError(f"P80 helper hash mismatch ({digest}); no service/serial operation.")
    module = types.ModuleType("wb2a_gfa_p80_pinned")
    module.__file__ = str(path)
    exec(compile(data, str(path), "exec"), module.__dict__)
    return module


def make_runtime(base):
    ProbeError = base.ProbeError

    p300_frames = {p300_read_frame(addr, length) for _, addr, length in STABLE}
    vs1_frames = {vs1_virtual_frame(addr, length) for _, addr, length in STABLE}
    vs1_first_frames = {vs1_virtual_frame(addr, length, stx=True) for _, addr, length in STABLE}
    gfa_frames = {gfa_frame(addr) for _, addr in GFA}
    gfa_first_frames = {gfa_frame(addr, stx=True) for _, addr in GFA}
    allowed = frozenset(
        {b"\x04", b"\x16\x00\x00", b"\x06", base.IDENT_REQUEST}
        | p300_frames | vs1_frames | vs1_first_frames | gfa_frames | gfa_first_frames
    )

    class Wire(base.Wire):
        def __init__(self, serial_port, log, clock=time.monotonic, sleeper=time.sleep):
            super().__init__(serial_port, log, clock)
            self.sleeper = sleeper
            self.vs1_active = False
            self.last_reply = 0.0

        def send(self, data: bytes):
            if data not in allowed:
                raise ProbeError("TX blocked by fixed read-only mixed-session allowlist.")
            self.log("TX " + data.hex(" "))
            self.touched = True
            if self.port.write(data) != len(data):
                raise ProbeError("Partial serial write; no automatic retransmission.")

        def exact_timed(self, count: int, timeout: float = 2.0) -> bytes:
            data = self.exact(count, timeout)
            self.last_reply = self.clock()
            return data

        def no_tail(self):
            tail = self.port.read(1)
            if tail:
                self.log("RX unexpected trailing " + tail.hex(" "))
                raise ProbeError("Unexpected trailing data in VS1 response.")

        def pace(self):
            target = self.last_reply + MIN_REPLY_GAP_S
            while self.clock() < target:
                self.sleeper(min(0.020, target - self.clock()))

        def p300_read(self, address: int, length: int) -> bytes:
            self.vs1_active = False
            self.send(p300_read_frame(address, length))
            if self.exact(1) != b"\x06":
                raise ProbeError("P300 Virtual_READ request was not acknowledged.")
            header = self.exact(2)
            if header[0] != 0x41 or not 5 <= header[1] <= 64:
                raise ProbeError("Invalid P300 response header: " + header.hex(" "))
            frame = header + self.exact(header[1] + 1)
            try:
                data = decode_p300_read(frame, address, length)
            except ValueError as exc:
                raise ProbeError(str(exc)) from exc
            self.send(b"\x06")
            name = STABLE_BY_ADDR[address][0]
            self.log(f"P300_READ {name} address=0x{address:04x} data={data.hex()}")
            return data

        def enter_vs1(self):
            self.discard_stale()
            self.send(b"\x04")
            self.control(5)
            self.log("Waiting for fresh VS1 synchronization ENQ.")
            self.control(5)
            self.vs1_active = True
            self.last_reply = self.clock()

        def vs1_virtual_read(self, address: int, length: int, *, first: bool = False) -> bytes:
            if not self.vs1_active:
                raise ProbeError("VS1 Virtual_READ attempted outside active VS1 session.")
            if not first:
                self.pace()
            frame = vs1_virtual_frame(address, length, stx=first)
            self.send(frame)
            data = self.exact_timed(length)
            self.no_tail()
            name = STABLE_BY_ADDR[address][0]
            self.log(
                f"VS1_F7 {name} address=0x{address:04x} data={data.hex()} "
                f"first={'yes' if first else 'no'}"
            )
            return data

        def vs1_gfa_read(self, address: int) -> int:
            if not self.vs1_active:
                raise ProbeError("GFA_READ attempted outside active VS1 session.")
            self.pace()
            self.send(gfa_frame(address))
            value = self.exact_timed(1)[0]
            self.no_tail()
            name = GFA_BY_ADDR[address]
            if value == 0xFF:
                raise ProbeError(f"Suspect FF from {name}/0x{address:04x}; mixed session rejected.")
            if address == 0x4050 and value != 0x20:
                raise ProbeError(f"P80 changed to 0x{value:02x}; expected local GFA 0x20.")
            self.log(f"VS1_GFA {name} address=0x{address:04x} raw=0x{value:02x}")
            return value

    def read_p300_set(wire, *, initial: bool) -> dict[int, bytes]:
        values = {}
        ident = wire.p300_ident()
        if ident != b"\x20\xc2":
            label = "Baseline" if initial else "Post-check"
            raise ProbeError(f"{label} P300 identity is not 20C2.")
        values[0x00F8] = ident
        for _, address, length in STABLE:
            if address == 0x00F8:
                continue
            values[address] = wire.p300_read(address, length)
        return values

    def run_probe(services, opener, log, wire_factory=None) -> int:
        state = services.state(base.SPLITTER)
        if (state.get("LoadState"), state.get("ActiveState"), state.get("SubState")) != (
            "loaded", "active", "running"
        ):
            raise ProbeError("Require splitter loaded and running before this test.")
        party = services.state(base.PARTY)
        if party.get("ActiveState") in ("activating", "deactivating", "reloading"):
            raise ProbeError("Party emulator is in transition; no service change performed.")
        party_active = party.get("LoadState") == "loaded" and party.get("ActiveState") == "active"
        to_stop = ([base.PARTY] if party_active else []) + [base.SPLITTER]

        changed = []
        restarted = set()
        failures = []
        wire = None
        baseline = {}
        vs1_values = {}
        post = {}
        gfa_values = {}
        p300_restored = False

        try:
            for unit in to_stop:
                changed.append(unit)
                log("Stopping " + unit)
                services.stop(unit)
            connection = opener()
            factory = wire_factory or (lambda c, l: Wire(c, l))
            wire = factory(connection, log)

            baseline = read_p300_set(wire, initial=True)
            log("BASELINE_COMPLETE=" + ",".join(
                f"0x{addr:04x}:{data.hex()}" for addr, data in baseline.items()
            ))

            wire.enter_vs1()
            vs1_values[0x00F8] = wire.vs1_virtual_read(0x00F8, 2, first=True)
            if vs1_values[0x00F8] != b"\x20\xc2":
                raise ProbeError("VS1 F7 identity is not 20C2.")

            sequence = (
                ("v", 0x00FB),
                ("g", 0x4050),
                ("v", 0x2306),
                ("g", 0x4006),
                ("v", 0x2323),
                ("g", 0x4009),
                ("v", 0x6300),
                ("g", 0x4057),
                ("v", 0x6773),
                ("v", 0x778C),
                ("g", 0x4050),
            )
            p80_values = []
            for kind, address in sequence:
                if kind == "v":
                    name, length = STABLE_BY_ADDR[address]
                    value = wire.vs1_virtual_read(address, length)
                    vs1_values[address] = value
                    if value != baseline[address]:
                        raise ProbeError(
                            f"Stable value mismatch P300->VS1 for {name}/0x{address:04x}: "
                            f"{baseline[address].hex()} != {value.hex()}"
                        )
                else:
                    value = wire.vs1_gfa_read(address)
                    gfa_values.setdefault(address, []).append(value)
                    if address == 0x4050:
                        p80_values.append(value)

            if p80_values != [0x20, 0x20]:
                raise ProbeError("Two in-session P80 guards were not both 0x20.")
            if set(vs1_values) != set(baseline):
                raise ProbeError("VS1 stable-read coverage is incomplete.")
            log("MIXED_VS1_COMPLETE=yes")
        except BaseException as exc:
            failures.append(str(exc) or type(exc).__name__)
            log("MIXED PROBE FAILED: " + failures[-1])
        finally:
            previous = {sig: signal.signal(sig, signal.SIG_IGN) for sig in base.ABORT_SIGNALS}
            try:
                if wire is not None:
                    try:
                        if wire.touched:
                            try:
                                post = read_p300_set(wire, initial=False)
                                p300_restored = True
                                if baseline:
                                    for address, before in baseline.items():
                                        after = post.get(address)
                                        if after != before:
                                            name = STABLE_BY_ADDR[address][0]
                                            failures.append(
                                                f"Stable value changed baseline->post for {name}/0x{address:04x}: "
                                                f"{before.hex()} != {(after or b'').hex()}"
                                            )
                            except Exception as exc:
                                failures.append("P300 post-check/restoration failed: " + str(exc))
                    finally:
                        try:
                            wire.port.close()
                            log("Serial port closed.")
                        except Exception as exc:
                            failures.append("Serial close failed: " + str(exc))

                for unit in reversed(changed):
                    try:
                        log("Restoring running state: " + unit)
                        services.start(unit)
                        restarted.add(unit)
                        log("SERVICE_RESTORED=" + unit + " running")
                    except Exception as exc:
                        failures.append("Restart failed: " + unit + ": " + str(exc))
            finally:
                for sig, handler in previous.items():
                    signal.signal(sig, handler)

        exact_match = bool(baseline and vs1_values and post)
        if exact_match:
            exact_match = baseline == vs1_values == post
        splitter_ok = base.SPLITTER in restarted
        result_ok = exact_match and p300_restored and splitter_ok and not failures

        for name, address, _ in STABLE:
            log(
                f"COMPARE {name} 0x{address:04x} "
                f"p300_before={baseline.get(address, b'').hex() or '-'} "
                f"vs1_f7={vs1_values.get(address, b'').hex() or '-'} "
                f"p300_after={post.get(address, b'').hex() or '-'}"
            )
        for name, address in GFA:
            vals = gfa_values.get(address, [])
            if vals:
                log(f"GFA_SAMPLE {name} 0x{address:04x}=" + ",".join(f"0x{x:02x}" for x in vals))
        log("STABLE_VALUES_MATCH=" + ("yes" if exact_match else "no"))
        log("P300_RESTORED=" + ("yes" if p300_restored else "NOT_VERIFIED"))
        log("SPLITTER_RESTARTED=" + ("yes" if splitter_ok else "NOT_VERIFIED"))
        log("RESULT=" + ("PASS" if result_ok else "FAIL"))
        log("PASS proves only this bounded read-only mixed F7/6B compatibility test, not production readiness.")
        for failure in failures:
            log("ERROR: " + failure)
        return 0 if result_ok else 1

    return ProbeError, Wire, run_probe


def self_test() -> int:
    import unittest

    class FrameTests(unittest.TestCase):
        def test_known_p300_frames(self):
            self.assertEqual(p300_read_frame(0x2306, 1).hex(), "4105000123060130")
            self.assertEqual(p300_read_frame(0x00FB, 1).hex(), "4105000100fb0102")

        def test_vs1_virtual_frames(self):
            self.assertEqual(vs1_virtual_frame(0x00F8, 2, stx=True).hex(), "01f700f802")
            self.assertEqual(vs1_virtual_frame(0x2306, 1).hex(), "f7230601")

        def test_gfa_frames(self):
            self.assertEqual(gfa_frame(0x4050).hex(), "6b405001")
            self.assertEqual(gfa_frame(0x4057).hex(), "6b405701")

        def test_unknown_addresses_blocked(self):
            with self.assertRaises(ValueError):
                p300_read_frame(0x1234, 1)
            with self.assertRaises(ValueError):
                vs1_virtual_frame(0x1234, 1)
            with self.assertRaises(ValueError):
                gfa_frame(0x1234)

        def test_decode_p300(self):
            frame = bytes.fromhex("41 06 01 01 23 06 01 15 47")
            self.assertEqual(decode_p300_read(frame, 0x2306, 1), b"\x15")

        def test_decode_bad_checksum(self):
            frame = bytearray.fromhex("41 06 01 01 23 06 01 15 47")
            frame[-1] ^= 1
            with self.assertRaises(ValueError):
                decode_p300_read(bytes(frame), 0x2306, 1)

        def test_no_write_function_in_fixed_frames(self):
            frames = [p300_read_frame(a, l) for _, a, l in STABLE]
            frames += [vs1_virtual_frame(a, l) for _, a, l in STABLE]
            frames += [gfa_frame(a) for _, a in GFA]
            self.assertTrue(all(not (f and f[0] in (0xF4, 0x68, 0x78)) for f in frames))

        def test_expected_targets(self):
            self.assertEqual(STABLE_BY_ADDR[0x00F8], ("device_id", 2))
            self.assertEqual(STABLE_BY_ADDR[0x778C], ("controller_sw_raw", 2))
            self.assertEqual(GFA_BY_ADDR[0x4050], "P80")
            self.assertEqual(GFA_BY_ADDR[0x4057], "P87")

    local = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(FrameTests)
    )
    if not local.wasSuccessful():
        return 1

    try:
        parent = load_parent()
    except Exception as exc:
        print("PARENT_CHAIN_TESTS=SKIPPED: " + str(exc))
        print("LOCAL_MIXED_TESTS=8/8")
        return 0
    parent_rc = parent.self_test()
    if parent_rc:
        return 1
    make_runtime(parent)
    print("LOCAL_MIXED_TESTS=8/8; PARENT_P80_TESTS=23/23")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--execute", action="store_true")
    action.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if not args.execute:
        print(
            f"WB2A mixed VS1 compatibility probe {VERSION}: plan only; no device/service access.\n"
            "Read-only test: P300 stable Virtual_READ baseline -> one persistent VS1 session with\n"
            "interleaved F7 Virtual_READ and 6B GFA_READ -> P300 stable post-check.\n"
            "No write command is implemented. --execute required."
        )
        return 0
    if os.geteuid() != 0:
        print("ERROR: --execute requires root.", file=sys.stderr)
        return 1

    parent = load_parent()
    ProbeError, Wire, run_probe = make_runtime(parent)
    port = parent.read_settings(parent.SETTINGS)
    if not stat.S_ISCHR(os.stat(port).st_mode):
        print("ERROR: configured port is not a character device.", file=sys.stderr)
        return 1

    lock_fd = None
    log = None
    result = 1
    previous = {}
    try:
        lock_fd = os.open(
            "/run/lock/wb2a-gfa-p80-probe.lock",
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
            0o600,
        )
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        log = parent.Log(Path("/root") / f"wb2a-vs1-mixed-compat-{stamp}-{os.getpid()}.log")
        log(f"WB2A mixed VS1 compatibility probe {VERSION}; LOG={log.path}")
        log("READ_ONLY=yes; stable P300/F7 comparison plus interleaved GFA 6B reads.")
        log("No write function, setpoint change, coding change, GFA_WRITE, PROCESS_WRITE or actuator command.")
        log(f"MIN_REPLY_GAP_MS={int(MIN_REPLY_GAP_S * 1000)}")

        def abort(signum, _frame):
            raise ProbeError("Interrupted by signal " + str(signum) + "; entering cleanup.")

        previous = {sig: signal.signal(sig, abort) for sig in parent.ABORT_SIGNALS}
        import serial
        result = run_probe(
            parent.Services(),
            lambda: parent.open_port(port, serial),
            log,
        )
    except BaseException as exc:
        if log:
            log("ERROR: " + (str(exc) or type(exc).__name__))
        else:
            print("ERROR: " + (str(exc) or type(exc).__name__), file=sys.stderr)
        result = 1
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        if log:
            log("LOG=" + str(log.path))
            log.close()
        if lock_fd is not None:
            os.close(lock_fd)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
