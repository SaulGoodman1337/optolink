#!/usr/bin/env python3
"""WB2A bounded VS1 F4 value-changing write/restore probe.

Target: ordinary day room setpoint 0x2306, one byte.

Sequence:
  1. Stop Party (if active) and splitter for exclusive serial access.
  2. Initialize stock upstream VS1 and verify device identity 20C2.
  3. Read baseline 0x2306 with F7.
  4. Choose target baseline +1 C (or -1 C at the upper gate).
  5. Write target through stock VS1/F4.
  6. Verify target through F7.
  7. Restore the exact original byte through stock VS1/F4.
  8. Verify restored byte through F7.
  9. Return to P300 and verify both identity 20C2 and restored 0x2306.
 10. Restore services.

The cleanup path attempts the original-value restore whenever the change write
was attempted, even if a later validation step fails.

No coding, EEPROM, GFA, process, burner/gas-valve, actuator or safety write is
implemented.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import importlib.util
import os
from pathlib import Path
import signal
import stat
import sys
import time
import types

VERSION = "1.0.1"
ROOT = Path("/opt/optolink")
PARENT_NAME = "wb2a-gfa-p80-probe.py"
PARENT_SHA256 = "6de883c422a09c821b342d12e5bb71dd3d518d8115ec2495bdfb202f5a7f50cb"
OPTO_VS1_BLOB = "cff6b4d8d52ca4ee1f79c310dd9377dba1a18270"
TARGET_ADDR = 0x2306
MIN_REPLY_GAP_S = 0.150
READBACK_DELAY_S = 0.250
BASELINE_MIN_C = 10
BASELINE_MAX_C = 30


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


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


def load_stock_vs1():
    path = ROOT / "optolinkvs1.py"
    blob = git_blob_sha(path)
    if blob != OPTO_VS1_BLOB:
        raise RuntimeError(f"optolinkvs1.py is not pinned stock runtime: {blob} != {OPTO_VS1_BLOB}")

    old_cwd = os.getcwd()
    inserted = False
    try:
        os.chdir(ROOT)
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
            inserted = True
        spec = importlib.util.spec_from_file_location("wb2a_stock_optolinkvs1_change", path)
        if spec is None or spec.loader is None:
            raise RuntimeError("Cannot import stock optolinkvs1.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        os.chdir(old_cwd)
        if inserted:
            try:
                sys.path.remove(str(ROOT))
            except ValueError:
                pass


def pace(delay: float = MIN_REPLY_GAP_S):
    time.sleep(delay)


def read_ext(vs1, ser, address: int, length: int) -> bytes:
    ret, retaddr, data = vs1.read_datapoint_ext(address, length, ser)
    if ret != 0x01 or retaddr != address or len(data) != length:
        raise RuntimeError(
            f"F7 read failed addr=0x{address:04X} ret=0x{ret:02X} "
            f"retaddr=0x{retaddr:04X} data={bytes(data).hex()}"
        )
    return bytes(data)


def read_one(vs1, ser, address: int) -> int:
    return read_ext(vs1, ser, address, 1)[0]


def read_ident(vs1, ser) -> bytes:
    ident = read_ext(vs1, ser, 0x00F8, 2)
    if ident != b"\x20\xC2":
        raise RuntimeError("VS1 identity is not 20C2: " + ident.hex())
    return ident


def write_one(vs1, ser, address: int, value: int) -> bytes:
    ret, retaddr, data = vs1.write_datapoint_ext(address, bytes([value]), ser)
    if ret != 0x01 or retaddr != address or len(data) != 1:
        raise RuntimeError(
            f"F4 write failed addr=0x{address:04X} value=0x{value:02X} "
            f"ret=0x{ret:02X} retaddr=0x{retaddr:04X} data={bytes(data).hex()}"
        )
    return bytes(data)


def target_for(baseline: int) -> int:
    if not BASELINE_MIN_C <= baseline <= BASELINE_MAX_C:
        raise RuntimeError(
            f"baseline {baseline} C outside conservative {BASELINE_MIN_C}..{BASELINE_MAX_C} C gate"
        )
    return baseline + 1 if baseline < BASELINE_MAX_C else baseline - 1


def p300_read_one(parent, wire, address: int) -> int:
    # Fixed post-restore allowlist: ordinary day setpoint 0x2306/1 only.
    if address != TARGET_ADDR:
        raise parent.ProbeError(f"P300 post-restore address blocked: 0x{address:04X}")

    body = bytes((0x41, 0x05, 0x00, 0x01, 0x23, 0x06, 0x01))
    frame = body + bytes((sum(body[1:]) & 0xFF,))
    if frame != bytes.fromhex("41 05 00 01 23 06 01 30"):
        raise parent.ProbeError("Internal fixed P300 2306 frame mismatch.")

    wire.log("TX " + frame.hex(" "))
    if wire.port.write(frame) != len(frame):
        raise parent.ProbeError("Partial P300 2306 request write.")
    if wire.exact(1) != b"\x06":
        raise parent.ProbeError("P300 post-restore read was not acknowledged.")
    header = wire.exact(2)
    if header[0] != 0x41 or not 5 <= header[1] <= 64:
        raise parent.ProbeError("Invalid P300 post-restore header: " + header.hex(" "))
    response = header + wire.exact(header[1] + 1)
    if len(response) != response[1] + 3:
        raise parent.ProbeError("P300 post-restore frame length mismatch.")
    if (sum(response[1:-1]) & 0xFF) != response[-1]:
        raise parent.ProbeError("P300 post-restore checksum mismatch.")
    if response[2] != 0x01 or (response[3] & 0x1F) != 0x01:
        raise parent.ProbeError("P300 post-restore response is not successful Virtual_READ.")
    if int.from_bytes(response[4:6], "big") != TARGET_ADDR or response[6] != 1:
        raise parent.ProbeError("P300 post-restore address/length mismatch.")
    data = response[7:-1]
    if len(data) != 1:
        raise parent.ProbeError("P300 post-restore payload length mismatch.")

    wire.log("TX 06")
    if wire.port.write(b"\x06") != 1:
        raise parent.ProbeError("Partial P300 post-restore ACK write.")
    return data[0]


def self_test() -> int:
    import unittest

    class FakeVS1:
        def __init__(self, value=21):
            self.value = value
            self.writes = []

        def read_datapoint_ext(self, addr, length, ser):
            if addr == 0x00F8:
                return 0x01, addr, bytearray(b"\x20\xC2")
            return 0x01, addr, bytearray([self.value])

        def write_datapoint_ext(self, addr, data, ser):
            self.writes.append((addr, bytes(data)))
            self.value = data[0]
            return 0x01, addr, bytearray(b"\x00")

    class Tests(unittest.TestCase):
        def test_target_up(self):
            self.assertEqual(target_for(21), 22)

        def test_target_down_at_upper_gate(self):
            self.assertEqual(target_for(30), 29)

        def test_target_refuses_outside_gate(self):
            for value in (9, 31):
                with self.assertRaises(RuntimeError):
                    target_for(value)

        def test_change_and_restore(self):
            fake = FakeVS1(21)
            baseline = read_one(fake, object(), TARGET_ADDR)
            target = target_for(baseline)
            self.assertEqual(write_one(fake, object(), TARGET_ADDR, target), b"\x00")
            self.assertEqual(read_one(fake, object(), TARGET_ADDR), target)
            self.assertEqual(write_one(fake, object(), TARGET_ADDR, baseline), b"\x00")
            self.assertEqual(read_one(fake, object(), TARGET_ADDR), baseline)
            self.assertEqual(fake.writes, [(TARGET_ADDR, b"\x16"), (TARGET_ADDR, b"\x15")])

        def test_ident(self):
            self.assertEqual(read_ident(FakeVS1(), object()), b"\x20\xC2")

        def test_fixed_p300_2306_frame(self):
            body = bytes((0x41, 0x05, 0x00, 0x01, 0x23, 0x06, 0x01))
            frame = body + bytes((sum(body[1:]) & 0xFF,))
            self.assertEqual(frame.hex(), "4105000123060130")

    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
    )
    if result.wasSuccessful():
        print("VS1_F4_CHANGE_RESTORE_TESTS=6/6")
        return 0
    return 1


def run_probe(parent, vs1, services, opener, log) -> int:
    ProbeError = parent.ProbeError
    state = services.state(parent.SPLITTER)
    if (state.get("LoadState"), state.get("ActiveState"), state.get("SubState")) != (
        "loaded", "active", "running"
    ):
        raise ProbeError("Require splitter loaded and running before test.")

    party = services.state(parent.PARTY)
    if party.get("ActiveState") in ("activating", "deactivating", "reloading"):
        raise ProbeError("Party emulator is in transition; no service change performed.")
    party_active = party.get("LoadState") == "loaded" and party.get("ActiveState") == "active"
    to_stop = ([parent.PARTY] if party_active else []) + [parent.SPLITTER]

    changed = []
    failures = []
    ser = None
    baseline = None
    target = None
    target_attempted = False
    target_verified = False
    restore_verified = False
    target_reply = b""
    restore_reply = b""
    p300_restored = False
    p300_value_verified = False
    restarted = set()

    try:
        for unit in to_stop:
            changed.append(unit)
            log("Stopping " + unit)
            services.stop(unit)

        ser = opener()
        if not vs1.init_protocol(ser):
            raise ProbeError("Stock VS1 init_protocol failed.")
        pace()

        ident = read_ident(vs1, ser)
        log("VS1_IDENTITY=" + ident.hex())
        pace()

        baseline = read_one(vs1, ser, TARGET_ADDR)
        target = target_for(baseline)
        log(f"BASELINE_2306=0x{baseline:02X} ({baseline} C)")
        log(f"TARGET_2306=0x{target:02X} ({target} C)")

        pace()
        target_attempted = True
        log(f"F4_CHANGE_WRITE addr=0x2306 value=0x{target:02X}")
        target_reply = write_one(vs1, ser, TARGET_ADDR, target)
        log("F4_CHANGE_REPLY=" + target_reply.hex())

        pace(READBACK_DELAY_S)
        changed_value = read_one(vs1, ser, TARGET_ADDR)
        log(f"CHANGED_READBACK_2306=0x{changed_value:02X} ({changed_value} C)")
        if changed_value != target:
            raise ProbeError(
                f"Changed readback mismatch: target=0x{target:02X}, got=0x{changed_value:02X}"
            )
        target_verified = True

    except BaseException as exc:
        failures.append(str(exc) or type(exc).__name__)
        log("PROBE_FAILED=" + failures[-1])
    finally:
        previous = {sig: signal.signal(sig, signal.SIG_IGN) for sig in parent.ABORT_SIGNALS}
        try:
            if ser is not None:
                try:
                    if target_attempted and baseline is not None:
                        restored = False
                        for attempt in range(1, 3):
                            try:
                                pace()
                                log(
                                    f"F4_RESTORE_WRITE attempt={attempt} "
                                    f"addr=0x2306 value=0x{baseline:02X}"
                                )
                                restore_reply = write_one(vs1, ser, TARGET_ADDR, baseline)
                                log("F4_RESTORE_REPLY=" + restore_reply.hex())
                                pace(READBACK_DELAY_S)
                                restored_value = read_one(vs1, ser, TARGET_ADDR)
                                log(
                                    f"RESTORED_READBACK_2306=0x{restored_value:02X} "
                                    f"({restored_value} C)"
                                )
                                if restored_value != baseline:
                                    raise ProbeError(
                                        f"restore readback mismatch 0x{restored_value:02X} "
                                        f"!= baseline 0x{baseline:02X}"
                                    )
                                restored = True
                                restore_verified = True
                                break
                            except Exception as exc:
                                log(f"Restore attempt {attempt} failed: {exc}")
                        if not restored:
                            failures.append("Original 0x2306 value could not be restored/verified via VS1.")

                    try:
                        log("Restoring P300 and verifying 00F8/2 plus 2306/1.")
                        p300_wire = parent.Wire(ser, log)
                        p300_restored = p300_wire.p300_ident() == b"\x20\xC2"
                        if not p300_restored:
                            failures.append("P300 identity after F4 probe is not 20C2.")
                        elif baseline is not None:
                            p300_value = p300_read_one(parent, p300_wire, TARGET_ADDR)
                            log(f"P300_POST_2306=0x{p300_value:02X} ({p300_value} C)")
                            p300_value_verified = p300_value == baseline
                            if not p300_value_verified:
                                failures.append(
                                    f"P300 post-check 2306 is 0x{p300_value:02X}, "
                                    f"expected baseline 0x{baseline:02X}."
                                )
                    except Exception as exc:
                        failures.append("P300 restoration/post-check failed: " + str(exc))
                finally:
                    try:
                        ser.close()
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

    splitter_ok = parent.SPLITTER in restarted
    result_ok = (
        target_attempted
        and target_verified
        and restore_verified
        and p300_restored
        and p300_value_verified
        and splitter_ok
        and not failures
    )

    log("TARGET_WRITE_VERIFIED=" + ("yes" if target_verified else "no"))
    log("RESTORE_VERIFIED=" + ("yes" if restore_verified else "no"))
    log("TARGET_F4_REPLY=" + (target_reply.hex() or "-"))
    log("RESTORE_F4_REPLY=" + (restore_reply.hex() or "-"))
    log("P300_RESTORED=" + ("yes" if p300_restored else "no"))
    log("P300_VALUE_RESTORED=" + ("yes" if p300_value_verified else "no"))
    log("SPLITTER_RESTARTED=" + ("yes" if splitter_ok else "no"))
    log("RESULT=" + ("PASS" if result_ok else "FAIL"))
    log(
        "PASS proves bounded stock VS1/F4 value mutation and exact restoration for "
        "ordinary one-byte setpoint 0x2306 on this appliance."
    )
    for failure in failures:
        log("ERROR: " + failure)
    return 0 if result_ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--self-test", action="store_true")
    action.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if not args.execute:
        print(
            f"WB2A VS1 F4 change/restore probe {VERSION}: plan only.\n"
            "Changes ordinary 0x2306 by exactly 1 C, verifies via F7, restores the exact baseline,\n"
            "then verifies the restored value again via F7 and P300. --execute required."
        )
        return 0
    if os.geteuid() != 0:
        print("ERROR: --execute requires root.", file=sys.stderr)
        return 1

    parent = load_parent()
    vs1 = load_stock_vs1()
    port = parent.read_settings(parent.SETTINGS)
    if not stat.S_ISCHR(os.stat(port).st_mode):
        print("ERROR: configured port is not a character device.", file=sys.stderr)
        return 1

    lock_fd = None
    log = None
    previous = {}
    result = 1
    try:
        lock_fd = os.open(
            "/run/lock/wb2a-gfa-p80-probe.lock",
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
            0o600,
        )
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        log = parent.Log(Path("/root") / f"wb2a-vs1-f4-change-restore-{stamp}-{os.getpid()}.log")
        log(f"WB2A VS1 F4 change/restore probe {VERSION}; LOG={log.path}")
        log("TARGET=0x2306 ordinary day setpoint; bounded +/-1 C temporary change.")
        log("RESTORE_POLICY=always attempt exact baseline after any change-write attempt.")
        log(f"MIN_REPLY_GAP_MS={int(MIN_REPLY_GAP_S * 1000)}")
        log(f"READBACK_DELAY_MS={int(READBACK_DELAY_S * 1000)}")
        log(f"OPTO_VS1_BLOB={OPTO_VS1_BLOB}")

        def abort(signum, _frame):
            raise parent.ProbeError("Interrupted by signal " + str(signum) + "; entering cleanup.")

        previous = {sig: signal.signal(sig, abort) for sig in parent.ABORT_SIGNALS}

        import serial
        result = run_probe(
            parent,
            vs1,
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
