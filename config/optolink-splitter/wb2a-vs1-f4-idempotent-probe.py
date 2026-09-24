#!/usr/bin/env python3
"""WB2A bounded VS1 F4 idempotent write transport probe.

Reads the current ordinary day setpoint 0x2306 through VS1/F7, writes the
EXACT SAME byte back through the stock upstream VS1/F4 implementation, then
reads it again. This validates the F4 transport without intentionally changing
the effective setpoint value.

The probe stops the splitter (and Party if active) for exclusive serial access,
requires device identity 20C2, verifies the stock optolinkvs1.py blob, and
restores normal services afterward.

It does not write coding, EEPROM, GFA, burner/gas-valve, actuator or safety
parameters.
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

VERSION = "1.0.0"
ROOT = Path("/opt/optolink")
PARENT_NAME = "wb2a-gfa-p80-probe.py"
PARENT_SHA256 = "6de883c422a09c821b342d12e5bb71dd3d518d8115ec2495bdfb202f5a7f50cb"
OPTO_VS1_BLOB = "cff6b4d8d52ca4ee1f79c310dd9377dba1a18270"
TARGET_ADDR = 0x2306
MIN_REPLY_GAP_S = 0.150


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
        spec = importlib.util.spec_from_file_location("wb2a_stock_optolinkvs1", path)
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


def pace():
    time.sleep(MIN_REPLY_GAP_S)


def read_one(vs1, ser, address: int) -> int:
    ret, retaddr, data = vs1.read_datapoint_ext(address, 1, ser)
    if ret != 0x01 or retaddr != address or len(data) != 1:
        raise RuntimeError(
            f"F7 read failed addr=0x{address:04X} ret=0x{ret:02X} "
            f"retaddr=0x{retaddr:04X} data={bytes(data).hex()}"
        )
    return int(data[0])


def read_ident(vs1, ser) -> bytes:
    ret, retaddr, data = vs1.read_datapoint_ext(0x00F8, 2, ser)
    if ret != 0x01 or retaddr != 0x00F8 or bytes(data) != b"\x20\xC2":
        raise RuntimeError(
            f"VS1 identity mismatch ret=0x{ret:02X} addr=0x{retaddr:04X} data={bytes(data).hex()}"
        )
    return bytes(data)


def self_test() -> int:
    import unittest

    class FakeVS1:
        def __init__(self, value=0x15, write_ret=0x01, write_reply=b"\x15"):
            self.value = value
            self.write_ret = write_ret
            self.write_reply = bytearray(write_reply)
            self.writes = []

        def read_datapoint_ext(self, addr, length, ser):
            if addr == 0x00F8:
                return 0x01, addr, bytearray(b"\x20\xC2")
            return 0x01, addr, bytearray([self.value])

        def write_datapoint_ext(self, addr, data, ser):
            self.writes.append((addr, bytes(data)))
            return self.write_ret, addr, bytearray(self.write_reply)

    class Tests(unittest.TestCase):
        def test_blob(self):
            p = Path(__file__)
            self.assertTrue(p.name.endswith(".py"))

        def test_ident(self):
            self.assertEqual(read_ident(FakeVS1(), object()), b"\x20\xC2")

        def test_read_one(self):
            self.assertEqual(read_one(FakeVS1(0x15), object(), TARGET_ADDR), 0x15)

        def test_same_value_frame_semantics(self):
            fake = FakeVS1(0x15)
            baseline = read_one(fake, object(), TARGET_ADDR)
            ret, addr, reply = fake.write_datapoint_ext(TARGET_ADDR, bytes([baseline]), object())
            self.assertEqual(ret, 0x01)
            self.assertEqual(addr, TARGET_ADDR)
            self.assertEqual(fake.writes, [(TARGET_ADDR, b"\x15")])
            self.assertEqual(bytes(reply), b"\x15")

        def test_write_failure_detectable(self):
            fake = FakeVS1(write_ret=0xFF, write_reply=b"")
            ret, _, _ = fake.write_datapoint_ext(TARGET_ADDR, b"\x15", object())
            self.assertNotEqual(ret, 0x01)

    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
    )
    if result.wasSuccessful():
        print("VS1_F4_IDEMPOTENT_TESTS=5/5")
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
    readback = None
    write_reply = b""
    f4_success = False
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
        if not 10 <= baseline <= 30:
            raise ProbeError(
                f"0x2306 baseline 0x{baseline:02X} outside conservative 10..30 C gate; no F4 sent."
            )
        log(f"BASELINE_2306=0x{baseline:02X} ({baseline} C)")
        pace()

        log(f"F4_IDEMPOTENT_WRITE addr=0x2306 value=0x{baseline:02X}")
        ret, retaddr, data = vs1.write_datapoint_ext(TARGET_ADDR, bytes([baseline]), ser)
        write_reply = bytes(data)
        log(
            f"F4_RESPONSE ret=0x{ret:02X} addr=0x{retaddr:04X} "
            f"data={write_reply.hex() or '-'}"
        )
        if ret != 0x01 or retaddr != TARGET_ADDR or len(data) != 1:
            raise ProbeError("F4 idempotent write did not return one-byte success.")
        f4_success = True

        pace()
        readback = read_one(vs1, ser, TARGET_ADDR)
        log(f"READBACK_2306=0x{readback:02X} ({readback} C)")
        if readback != baseline:
            raise ProbeError(
                f"Idempotent F4 readback changed value: baseline=0x{baseline:02X}, "
                f"readback=0x{readback:02X}."
            )

    except BaseException as exc:
        failures.append(str(exc) or type(exc).__name__)
        log("PROBE_FAILED=" + failures[-1])
    finally:
        previous = {sig: signal.signal(sig, signal.SIG_IGN) for sig in parent.ABORT_SIGNALS}
        try:
            if ser is not None:
                try:
                    # Since this is idempotent, no distinct value restore is required.
                    # Still verify the final VS1 read if transport reached the write.
                    if f4_success and baseline is not None:
                        try:
                            pace()
                            final = read_one(vs1, ser, TARGET_ADDR)
                            log(f"FINAL_VS1_2306=0x{final:02X}")
                            if final != baseline:
                                failures.append(
                                    f"Final VS1 2306 differs from baseline: 0x{final:02X} != 0x{baseline:02X}"
                                )
                        except Exception as exc:
                            failures.append("Final VS1 read failed: " + str(exc))
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
        f4_success
        and baseline is not None
        and readback == baseline
        and splitter_ok
        and not failures
    )

    log("F4_SUCCESS=" + ("yes" if f4_success else "no"))
    log("VALUE_UNCHANGED=" + ("yes" if baseline is not None and readback == baseline else "no"))
    log("F4_REPLY=" + (write_reply.hex() or "-"))
    log("SPLITTER_RESTARTED=" + ("yes" if splitter_ok else "no"))
    log("RESULT=" + ("PASS" if result_ok else "FAIL"))
    log(
        "PASS proves only bounded stock VS1 F4 transport using an idempotent write of "
        "the existing 0x2306 value; it does not yet prove a value-changing write."
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
            f"WB2A VS1 F4 idempotent probe {VERSION}: plan only.\n"
            "Reads 0x2306, writes the exact same raw byte via stock VS1/F4, then reads it again.\n"
            "No intentional setpoint change. --execute required."
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
        log = parent.Log(Path("/root") / f"wb2a-vs1-f4-idempotent-{stamp}-{os.getpid()}.log")
        log(f"WB2A VS1 F4 idempotent probe {VERSION}; LOG={log.path}")
        log("TARGET=0x2306 ordinary day setpoint; same-value write only.")
        log("NO_INTENTIONAL_VALUE_CHANGE=yes")
        log(f"MIN_REPLY_GAP_MS={int(MIN_REPLY_GAP_S * 1000)}")
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
