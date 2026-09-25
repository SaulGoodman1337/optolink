#!/opt/optolink/venv/bin/python
"""Bounded read-only KBUS_VIRTUAL_READ (0x5F) semantic gate for WB2A/VDensHO1.

Purpose
-------
Vitosoft v6 contains source-backed KBUS_VIRTUAL_READ objects outside the exact
VDensHO1 event tree. This helper tests only two temperature anchors for local
20C2 applicability, with ordinary VDensHO1 Virtual_READ controls:

  outside temperature:
    control  0x01 / 0x5525 / 2  (signed LE, 0.1 C/LSB)
    KBus     0x5F / 0x2508 / 1  (signed byte, 0.5 C/LSB)

  A1 flow actual temperature:
    control  0x01 / 0x0810 / 2  (signed LE, 0.1 C/LSB)
    KBus     0x5F / 0x2D08 / 1  (signed byte, 0.5 C/LSB)

The KBus objects are source-backed Vitosoft definitions with BlockLength=1 and
Div2 conversion. PrefixRead metadata equals the respective address, but the
recovered host serializer does not append PrefixRead to ordinary non-RPC read
requests. Therefore this probe sends standard P300 read frames with no extra
request data.

Every research sample uses a fresh P300 session. Fixed order per anchor:
control, KBus, KBus, control.

Production remains permanent VS1/KW. The helper stops only the known serial
owners, performs only the fixed allowlisted reads, restores all services that
were previously active, and verifies VS1 restoration.

No write function exists. No arbitrary address/function arguments exist.
"""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import fcntl
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import termios
import time

VERSION = "1.0.0"
SPLITTER = "optolink-splitter.service"
PARTY = "optolink-party-emulator.service"
SCHEDULE = "optolink-schedule-manager.service"
SETTINGS = Path("/opt/optolink/settings_ini.py")
LOCK = "/run/lock/wb2a-kbus-virtual-read-probe.lock"
ABORT_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)

IDENT_EXPECTED = bytes.fromhex("20 c2 00 03 00 00 01 03")
ORDER = ("C", "K", "K", "C")
MATCH_TOLERANCE_C = 1.5

ANCHORS = (
    {
        "label": "outside_temperature",
        "control": (0x01, 0x5525, 2),
        "kbus": (0x5F, 0x2508, 1),
    },
    {
        "label": "a1_flow_actual_temperature",
        "control": (0x01, 0x0810, 2),
        "kbus": (0x5F, 0x2D08, 1),
    },
)

ALLOWED_REQUESTS = {
    (0x01, 0x00F8, 8),
    (0x01, 0x5525, 2),
    (0x5F, 0x2508, 1),
    (0x01, 0x0810, 2),
    (0x5F, 0x2D08, 1),
}


class ProbeError(RuntimeError):
    pass


class Log:
    def __init__(self, path: Path):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        self.file = os.fdopen(fd, "w", encoding="utf-8", buffering=1)
        self.path = path

    def __call__(self, message: str):
        line = dt.datetime.now().astimezone().isoformat(timespec="milliseconds") + " " + message
        try:
            self.file.write(line + "\n")
        except OSError:
            pass
        try:
            print(line, flush=True)
        except (BrokenPipeError, OSError):
            pass

    def close(self):
        self.file.close()


def read_settings(path: Path) -> str:
    names = {"port_optolink", "port_vitoconnect", "vs1protocol"}
    values = {}
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in names:
                if target.id in values:
                    raise ProbeError("Ambiguous duplicate setting: " + target.id)
                try:
                    values[target.id] = ast.literal_eval(node.value)
                except (ValueError, TypeError) as exc:
                    raise ProbeError("Setting is not a literal: " + target.id) from exc

    if values.get("vs1protocol") is not True:
        raise ProbeError("Require permanent production vs1protocol=True.")
    if values.get("port_vitoconnect") is not None:
        raise ProbeError("Require port_vitoconnect=None.")
    port = values.get("port_optolink")
    if not isinstance(port, str) or not port.startswith("/dev/"):
        raise ProbeError("Require literal local /dev/ port_optolink.")
    return port


def checksum(body: bytes) -> int:
    if not body or body[0] != 0x41:
        raise ValueError("P300 frame must start with 0x41.")
    return sum(body[1:]) & 0xFF


def request_frame(function: int, address: int, length: int) -> bytes:
    if (function, address, length) not in ALLOWED_REQUESTS:
        raise ValueError(
            f"Request outside fixed allowlist: function=0x{function:02x} "
            f"address=0x{address:04x} len={length}"
        )
    body = bytes((0x41, 0x05, 0x00, function, address >> 8, address & 0xFF, length))
    return body + bytes((checksum(body),))


CONTROL_FRAME = request_frame(0x01, 0x00F8, 8)
READ_FRAMES = {key: request_frame(*key) for key in ALLOWED_REQUESTS}
ALLOWED_TX = frozenset(
    {b"\x04", b"\x16\x00\x00", b"\x06"} | set(READ_FRAMES.values())
)


def decode_response(msg: bytes) -> dict:
    if len(msg) < 4 or msg[0] != 0x41 or len(msg) != msg[1] + 3:
        raise ProbeError("Bad P300 response length: " + msg.hex(" "))
    if checksum(msg[:-1]) != msg[-1]:
        raise ProbeError("Bad P300 response checksum: " + msg.hex(" "))

    mtype = msg[2] & 0x0F
    status = (
        "SUCCESS" if mtype == 0x01
        else "ERROR_MESSAGE" if mtype == 0x03
        else f"MESSAGE_TYPE_{mtype:02X}"
    )
    return {
        "status": status,
        "message_type": mtype,
        "command": msg[3],
        "address": int.from_bytes(msg[4:6], "big") if len(msg) >= 7 else None,
        "length": msg[6] if len(msg) >= 7 else None,
        "data": msg[7:-1] if len(msg) >= 8 else b"",
        "frame": msg.hex(),
    }


def decode_control_temperature(data: bytes) -> float:
    if len(data) != 2:
        raise ProbeError("Control temperature must be exactly 2 bytes.")
    return int.from_bytes(data, "little", signed=True) / 10.0


def decode_kbus_temperature(data: bytes) -> float:
    if len(data) != 1:
        raise ProbeError("KBus temperature must be exactly 1 byte.")
    return int.from_bytes(data, "big", signed=True) / 2.0


def validate_success(result: dict, function: int, address: int, length: int):
    if (
        result["status"] != "SUCCESS"
        or result["command"] != function
        or result["address"] != address
        or result["length"] != length
        or len(result["data"]) != length
    ):
        raise ProbeError(
            f"Unexpected successful result shape for function=0x{function:02x} "
            f"address=0x{address:04x}: {result}"
        )


class Wire:
    def __init__(self, port, log):
        self.port = port
        self.log = log

    def send(self, data: bytes):
        if data not in ALLOWED_TX:
            raise ProbeError("TX blocked by fixed read-only allowlist: " + data.hex(" "))
        self.log("TX " + data.hex(" "))
        if self.port.write(data) != len(data):
            raise ProbeError("Partial serial write.")

    def exact(self, count: int, timeout: float = 2.5) -> bytes:
        until = time.monotonic() + timeout
        out = bytearray()
        while len(out) < count and time.monotonic() < until:
            out.extend(self.port.read(count - len(out)))
        if out:
            self.log("RX " + out.hex(" "))
        if len(out) != count:
            raise ProbeError(f"RX timeout expected {count}, got {len(out)}.")
        return bytes(out)

    def control(self, expected: int, timeout: float = 5.0):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            b = self.port.read(1)
            if not b:
                continue
            self.log("RX control " + b.hex(" "))
            if b == bytes((expected,)):
                return
            if expected == 0x05 and b in (b"\x06", b"\x15"):
                continue
            if expected == 0x06 and b == b"\x05":
                continue
            raise ProbeError(f"Unexpected control byte {b.hex()}, expected {expected:02x}.")
        raise ProbeError(f"Timeout waiting for control {expected:02x}.")

    def discard_stale(self):
        size = self.port.in_waiting
        if size > 4096:
            raise ProbeError("Excessive queued serial traffic.")
        if size:
            self.log("RX stale/discard " + self.port.read(size).hex(" "))

    def enter_p300(self):
        self.discard_stale()
        self.send(b"\x04")
        self.control(0x05)
        self.send(b"\x16\x00\x00")
        self.control(0x06)
        self.log("P300_INITIALIZED=yes")

    def leave(self):
        self.send(b"\x04")
        self.log("P300_SESSION_ENDED=yes")

    def transact(self, frame: bytes) -> dict:
        self.send(frame)
        first = self.exact(1)
        if first == b"\x15":
            result = {
                "status": "NACK", "message_type": None, "command": None,
                "address": None, "length": None, "data": b"", "frame": "15",
            }
            self.log("P300_RESULT status=NACK")
            return result
        if first != b"\x06":
            raise ProbeError("Expected ACK/NACK, got " + first.hex(" "))

        hdr = self.exact(2)
        if hdr[0] != 0x41 or not 1 <= hdr[1] <= 64:
            raise ProbeError("Bad response header: " + hdr.hex(" "))
        msg = hdr + self.exact(hdr[1] + 1)
        result = decode_response(msg)
        self.log(
            f"P300_RESULT status={result['status']} "
            f"command={('-' if result['command'] is None else f'0x{result['command']:02x}')} "
            f"address={('-' if result['address'] is None else f'0x{result['address']:04x}')} "
            f"len={result['length']} "
            f"data={result['data'].hex() if result['data'] else '-'} "
            f"frame={result['frame']}"
        )
        self.send(b"\x06")
        return result


class Services:
    @staticmethod
    def cmd(*args, timeout=25):
        p = subprocess.run(
            ["systemctl", "--no-pager", "--no-ask-password", *args],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
        if p.returncode:
            raise ProbeError("systemctl failed: " + p.stderr.strip())
        return p.stdout

    def state(self, unit):
        out = self.cmd("show", unit, "-p", "LoadState", "-p", "ActiveState", "-p", "SubState")
        return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)

    def stop(self, unit):
        self.cmd("stop", unit)
        if self.state(unit).get("ActiveState") != "inactive":
            raise ProbeError("Service did not stop: " + unit)

    def start(self, unit):
        self.cmd("start", unit)
        time.sleep(2)
        st = self.state(unit)
        if st.get("ActiveState") != "active" or st.get("SubState") != "running":
            raise ProbeError("Service did not stay running: " + unit)

    @staticmethod
    def journal_since(epoch):
        p = subprocess.run(
            ["journalctl", "-u", SPLITTER, "--since", "@" + str(int(epoch)),
             "--no-pager", "-o", "cat"],
            capture_output=True, text=True, timeout=20, check=False,
        )
        if p.returncode:
            raise ProbeError("journalctl failed: " + p.stderr.strip())
        return p.stdout


def check_port_owners(port):
    dev = os.stat(port)
    if not stat.S_ISCHR(dev.st_mode):
        raise ProbeError("Serial path is not a character device.")
    owners = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            fds = list((proc / "fd").iterdir())
        except (FileNotFoundError, PermissionError):
            continue
        for fd in fds:
            try:
                st = fd.stat()
            except (FileNotFoundError, PermissionError):
                continue
            if stat.S_ISCHR(st.st_mode) and st.st_rdev == dev.st_rdev:
                owners.append(proc.name)
                break
    if owners:
        raise ProbeError("Serial port still open by PID(s): " + ",".join(owners))


def open_port(port, serial_module):
    check_port_owners(port)
    s = serial_module.Serial(
        port=port, baudrate=4800, bytesize=8, parity="E", stopbits=2,
        timeout=0.05, write_timeout=2, xonxoff=False, rtscts=False,
        dsrdtr=False, exclusive=True,
    )
    try:
        fcntl.ioctl(s.fileno(), termios.TIOCEXCL)
        check_port_owners(port)
    except BaseException:
        s.close()
        raise
    return s


def one_fresh_session(wire: Wire, function: int, address: int, length: int) -> dict:
    wire.enter_p300()
    try:
        result = wire.transact(request_frame(function, address, length))
        if result["status"] == "SUCCESS":
            validate_success(result, function, address, length)
        return result
    finally:
        wire.leave()
        time.sleep(0.15)


def classify_anchor(observations):
    controls = [value for kind, _result, value in observations if kind == "C"]
    kbus_rows = [(result, value) for kind, result, value in observations if kind == "K"]

    if len(controls) != 2 or len(kbus_rows) != 2:
        return "INCOMPLETE"
    successes = [(r, v) for r, v in kbus_rows if r["status"] == "SUCCESS"]
    if not successes:
        return "KBUS_REJECTED_OR_ERROR"
    if len(successes) != len(kbus_rows):
        return "KBUS_MIXED_OR_INCONCLUSIVE"

    low = min(controls) - MATCH_TOLERANCE_C
    high = max(controls) + MATCH_TOLERANCE_C
    if all(low <= value <= high for _result, value in successes):
        return "SEMANTIC_MATCH"
    return "DATA_BUT_NO_SEMANTIC_MATCH"


def run_guarded(services, opener, log):
    split = services.state(SPLITTER)
    if (split.get("LoadState"), split.get("ActiveState"), split.get("SubState")) != (
        "loaded", "active", "running"
    ):
        raise ProbeError("Require running splitter.")

    party = services.state(PARTY)
    party_active = party.get("LoadState") == "loaded" and party.get("ActiveState") == "active"
    schedule = services.state(SCHEDULE)
    schedule_active = schedule.get("LoadState") == "loaded" and schedule.get("ActiveState") == "active"

    changed = []
    wire = None
    failures = []
    anchor_results = []
    restart_epoch = None

    try:
        stop_order = []
        if schedule_active:
            stop_order.append(SCHEDULE)
        if party_active:
            stop_order.append(PARTY)
        stop_order.append(SPLITTER)

        for unit in stop_order:
            changed.append(unit)
            log("Stopping " + unit)
            services.stop(unit)

        wire = Wire(opener(), log)

        ident = one_fresh_session(wire, 0x01, 0x00F8, 8)
        validate_success(ident, 0x01, 0x00F8, 8)
        if ident["data"] != IDENT_EXPECTED:
            raise ProbeError("20C2 identity mismatch: " + ident["data"].hex())
        log("P300_IDENTITY_CONTROL=PASS")

        for anchor in ANCHORS:
            label = anchor["label"]
            observations = []
            log(
                f"ANCHOR_START label={label} order={''.join(ORDER)} "
                f"control=0x{anchor['control'][1]:04x}/{anchor['control'][2]} "
                f"kbus=0x{anchor['kbus'][1]:04x}/{anchor['kbus'][2]}"
            )
            for n, kind in enumerate(ORDER, 1):
                function, address, length = anchor["control"] if kind == "C" else anchor["kbus"]
                result = one_fresh_session(wire, function, address, length)

                if kind == "C":
                    validate_success(result, function, address, length)
                    value = decode_control_temperature(result["data"])
                elif result["status"] == "SUCCESS":
                    value = decode_kbus_temperature(result["data"])
                else:
                    value = None

                observations.append((kind, result, value))
                log(
                    f"TRIAL anchor={label} n={n} kind={kind} "
                    f"function=0x{function:02x} address=0x{address:04x} "
                    f"status={result['status']} raw={result['data'].hex() if result['data'] else '-'} "
                    f"temp_c={('-' if value is None else f'{value:.2f}')}"
                )

            classification = classify_anchor(observations)
            anchor_results.append((label, observations, classification))
            log(f"ANCHOR_RESULT label={label} class={classification}")

    except BaseException as exc:
        failures.append(str(exc) or type(exc).__name__)
        log("PROBE FAILED: " + failures[-1])
    finally:
        previous = {sig: signal.signal(sig, signal.SIG_IGN) for sig in ABORT_SIGNALS}
        try:
            if wire is not None:
                try:
                    wire.port.close()
                    log("Serial port closed.")
                except Exception as exc:
                    failures.append("Serial close failed: " + str(exc))
            for unit in reversed(changed):
                try:
                    if unit == SPLITTER:
                        restart_epoch = time.time()
                    log("Restoring running state: " + unit)
                    services.start(unit)
                    log("SERVICE_RESTORED=" + unit + " running")
                except Exception as exc:
                    failures.append("Restart failed: " + unit + ": " + str(exc))
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)

    if restart_epoch is not None and SPLITTER in changed:
        try:
            restored = "VS1/KW protocol initialized" in services.journal_since(restart_epoch - 0.25)
            log("VS1_RESTORED=" + ("yes" if restored else "NOT_CONFIRMED"))
            if not restored:
                failures.append("VS1 restore not confirmed.")
        except Exception as exc:
            failures.append("VS1 verification failed: " + str(exc))

    classes = []
    for label, observations, classification in anchor_results:
        classes.append(classification)
        values = []
        for kind, result, value in observations:
            values.append(
                f"{kind}:{result['status']}:{result['data'].hex() if result['data'] else '-'}:"
                f"{'-' if value is None else f'{value:.2f}C'}"
            )
        log(f"SUMMARY label={label} values=" + ",".join(values))
        log(f"SUMMARY label={label} class={classification}")

    if classes and all(c == "SEMANTIC_MATCH" for c in classes):
        overall = "LOCAL_KBUS_VIRTUAL_SEMANTICS_SUPPORTED"
    elif classes and all(c == "KBUS_REJECTED_OR_ERROR" for c in classes):
        overall = "NO_LOCAL_KBUS_VIRTUAL_SUCCESS_ON_TESTED_ANCHORS"
    else:
        overall = "INCONCLUSIVE_OR_PARTIAL"
    log("CLASSIFICATION=" + overall)

    completed = len(anchor_results) == len(ANCHORS) and not failures
    log("EXECUTION_RESULT=" + ("PASS" if completed else "FAIL"))
    for error in failures:
        log("ERROR: " + error)
    return 0 if completed else 1


def self_test():
    import unittest

    class Tests(unittest.TestCase):
        def test_identity_frame(self):
            self.assertEqual(CONTROL_FRAME.hex(), "4105000100f80806")

        def test_control_frames(self):
            self.assertEqual(request_frame(0x01, 0x5525, 2).hex(), "4105000155250282")
            self.assertEqual(request_frame(0x01, 0x0810, 2).hex(), "4105000108100220")

        def test_kbus_frames_are_prefixless_standard_reads(self):
            self.assertEqual(request_frame(0x5F, 0x2508, 1).hex(), "4105005f25080192")
            self.assertEqual(request_frame(0x5F, 0x2D08, 1).hex(), "4105005f2d08019a")

        def test_temperature_decoders(self):
            self.assertEqual(decode_control_temperature(bytes.fromhex("9100")), 14.5)
            self.assertEqual(decode_kbus_temperature(bytes.fromhex("1d")), 14.5)
            self.assertEqual(decode_control_temperature(bytes.fromhex("9cff")), -10.0)
            self.assertEqual(decode_kbus_temperature(bytes.fromhex("ec")), -10.0)

        def test_semantic_match(self):
            c1 = {"status": "SUCCESS"}
            k1 = {"status": "SUCCESS"}
            observations = [
                ("C", c1, 14.5), ("K", k1, 14.5),
                ("K", k1, 15.0), ("C", c1, 14.6),
            ]
            self.assertEqual(classify_anchor(observations), "SEMANTIC_MATCH")

        def test_semantic_mismatch(self):
            c1 = {"status": "SUCCESS"}
            k1 = {"status": "SUCCESS"}
            observations = [
                ("C", c1, 14.5), ("K", k1, 30.0),
                ("K", k1, 30.0), ("C", c1, 14.6),
            ]
            self.assertEqual(classify_anchor(observations), "DATA_BUT_NO_SEMANTIC_MATCH")

        def test_write_and_unknown_blocked(self):
            with self.assertRaises(ValueError):
                request_frame(0x60, 0x2508, 1)
            with self.assertRaises(ValueError):
                request_frame(0x5F, 0x1234, 1)

    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
    )
    if result.wasSuccessful():
        print("KBUS_VIRTUAL_READ_PROBE_TESTS=7/7")
        return 0
    return 1


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--execute", action="store_true")
    g.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if not args.execute:
        print(
            f"WB2A KBUS_VIRTUAL_READ semantic gate {VERSION}: "
            "plan only; no action without --execute."
        )
        return 0
    if os.geteuid() != 0:
        print("ERROR: --execute requires root.", file=sys.stderr)
        return 1

    log = None
    lock_fd = None
    previous = {}
    try:
        import serial

        port = read_settings(SETTINGS)
        lock_fd = os.open(LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        log = Log(Path("/root") / f"wb2a-kbus-virtual-read-{stamp}-{os.getpid()}.log")
        log(f"WB2A KBUS_VIRTUAL_READ semantic gate {VERSION}; LOG={log.path}")
        log(f"Configured port: {port}; resolved: {os.path.realpath(port)}; 4800 8E2.")
        log("READ_ONLY=yes; FUNCTION=0x5F; ARBITRARY_REQUESTS=no")
        log("PREFIXREAD_APPENDED=no; FRESH_P300_SESSION_PER_SAMPLE=yes")
        log("ALLOWLIST=0x2508/1,0x2D08/1 plus fixed Virtual_READ controls")

        def abort(signum, _frame):
            raise ProbeError("Interrupted by signal " + str(signum))

        previous = {sig: signal.signal(sig, abort) for sig in ABORT_SIGNALS}
        return run_guarded(Services(), lambda: open_port(port, serial), log)

    except Exception as exc:
        if log:
            log("ERROR: " + str(exc))
        else:
            print("ERROR: " + str(exc), file=sys.stderr)
        return 1
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        if lock_fd is not None:
            os.close(lock_fd)
        if log:
            log("LOG=" + str(log.path))
            log.close()


if __name__ == "__main__":
    raise SystemExit(main())
