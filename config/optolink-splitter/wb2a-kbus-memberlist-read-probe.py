#!/opt/optolink/venv/bin/python
"""Bounded read-only KBUS_MEMBERLIST_READ (0x5D) gate for WB2A/VDensHO1.

Source basis
------------
The verified Vitosoft-v6 KBus read slice contains exactly one
KBUS_MEMBERLIST_READ definition:

  event 2756
  "Teilnehmer 00 am Viessmann-2-Draht-BUS"
  function 0x5D
  address  0x0000
  length   3
  PrefixRead empty

The event belongs to legacy DEKATEL/VCOM300 profiles, not VDensHO1. Therefore
this helper tests only whether that exact source-backed request shape has a
stable local response. A successful return does NOT prove the meaning of its
three bytes.

Fixed live sequence, each in a fresh P300 session:

  1. 0x01 / 0x00F8 / 8 identity control
  2. 0x5D / 0x0000 / 3
  3. 0x5D / 0x0000 / 3
  4. 0x5D / 0x0000 / 3
  5. 0x01 / 0x00F8 / 8 identity control

No writes, no arbitrary function/address/length arguments and no address sweep.

The helper can run unprivileged when the caller has serial-device access.
Service stop/start uses only the already allowlisted sudo systemctl commands.
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
LOCK = "/tmp/wb2a-kbus-memberlist-read-probe.lock"
ABORT_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)

IDENT_EXPECTED = bytes.fromhex("20 c2 00 03 00 00 01 03")
IDENT_REQUEST = (0x01, 0x00F8, 8)
MEMBER_REQUEST = (0x5D, 0x0000, 3)
TRIALS = 3

ALLOWED_REQUESTS = {IDENT_REQUEST, MEMBER_REQUEST}


class ProbeError(RuntimeError):
    pass


class Log:
    def __init__(self):
        base = Path(os.environ.get("WB2A_PROBE_LOG_DIR", str(Path.home())))
        base.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        path = base / f"wb2a-kbus-memberlist-read-{stamp}-{os.getpid()}.log"
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


IDENT_FRAME = request_frame(*IDENT_REQUEST)
MEMBER_FRAME = request_frame(*MEMBER_REQUEST)
ALLOWED_TX = frozenset({b"\x04", b"\x16\x00\x00", b"\x06", IDENT_FRAME, MEMBER_FRAME})


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
    def state(unit):
        p = subprocess.run(
            ["/usr/bin/systemctl", "show", unit, "-p", "LoadState", "-p", "ActiveState", "-p", "SubState"],
            capture_output=True, text=True, timeout=15, check=False,
        )
        if p.returncode:
            raise ProbeError("systemctl show failed: " + p.stderr.strip())
        return dict(line.split("=", 1) for line in p.stdout.splitlines() if "=" in line)

    @staticmethod
    def change(action: str, unit: str):
        if action not in {"start", "stop"}:
            raise ProbeError("Blocked service action: " + action)
        base = ["/usr/bin/systemctl", action, unit]
        cmd = base if os.geteuid() == 0 else ["sudo", "-n", *base]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=25, check=False)
        if p.returncode:
            raise ProbeError("service action failed: " + " ".join(cmd) + ": " + p.stderr.strip())

    def stop(self, unit):
        self.change("stop", unit)
        if self.state(unit).get("ActiveState") != "inactive":
            raise ProbeError("Service did not stop: " + unit)

    def start(self, unit):
        self.change("start", unit)
        time.sleep(2)
        st = self.state(unit)
        if st.get("ActiveState") != "active" or st.get("SubState") != "running":
            raise ProbeError("Service did not stay running: " + unit)

    @staticmethod
    def journal_since(epoch):
        p = subprocess.run(
            ["/usr/bin/journalctl", "-u", SPLITTER, "--since", "@" + str(int(epoch)),
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
        raise ProbeError("Serial port still open by visible PID(s): " + ",".join(owners))


def open_port(port, serial_module):
    check_port_owners(port)
    s = serial_module.Serial(
        port=port, baudrate=4800, bytesize=8, parity="E", stopbits=2,
        timeout=0.05, write_timeout=2, xonxoff=False, rtscts=False,
        dsrdtr=False, exclusive=True,
    )
    try:
        fcntl.ioctl(s.fileno(), termios.TIOCEXCL)
    except BaseException:
        s.close()
        raise
    return s


def one_fresh_session(wire: Wire, frame: bytes) -> dict:
    wire.enter_p300()
    try:
        return wire.transact(frame)
    finally:
        wire.leave()
        time.sleep(0.15)


def classify_member_results(results: list[dict]) -> str:
    if len(results) != TRIALS:
        return "INCOMPLETE"

    if all(r["status"] == "SUCCESS" for r in results):
        for r in results:
            validate_success(r, *MEMBER_REQUEST)
        values = {r["data"] for r in results}
        return "STABLE_SUCCESS_UNKNOWN_SEMANTICS" if len(values) == 1 else "DYNAMIC_SUCCESS_UNKNOWN_SEMANTICS"

    if all(r["status"] == "ERROR_MESSAGE" for r in results):
        values = {(r["command"], r["address"], r["length"], r["data"]) for r in results}
        return "STABLE_ERROR_RESPONSE" if len(values) == 1 else "DYNAMIC_ERROR_RESPONSE"

    if all(r["status"] == "NACK" for r in results):
        return "STABLE_NACK"

    return "MIXED_OR_INCONCLUSIVE"


def identity_control(wire: Wire, label: str, log):
    result = one_fresh_session(wire, IDENT_FRAME)
    validate_success(result, *IDENT_REQUEST)
    if result["data"] != IDENT_EXPECTED:
        raise ProbeError(label + " identity mismatch: " + result["data"].hex())
    log(label + "_IDENTITY_CONTROL=PASS data=" + result["data"].hex())


def run_guarded(log, serial_module):
    services = Services()
    split = services.state(SPLITTER)
    if (split.get("LoadState"), split.get("ActiveState"), split.get("SubState")) != (
        "loaded", "active", "running"
    ):
        raise ProbeError("Require running splitter.")

    party = services.state(PARTY)
    party_active = party.get("LoadState") == "loaded" and party.get("ActiveState") == "active"
    schedule = services.state(SCHEDULE)
    schedule_active = schedule.get("LoadState") == "loaded" and schedule.get("ActiveState") == "active"

    port = read_settings(SETTINGS)
    log(f"Configured port: {port}; resolved: {os.path.realpath(port)}; 4800 8E2.")

    changed = []
    wire = None
    failures = []
    member_results = []
    restart_epoch = None

    try:
        stop_order = []
        if schedule_active:
            stop_order.append(SCHEDULE)
        if party_active:
            stop_order.append(PARTY)
        stop_order.append(SPLITTER)

        for unit in stop_order:
            log("Stopping " + unit)
            services.stop(unit)
            changed.append(unit)

        wire = Wire(open_port(port, serial_module), log)

        identity_control(wire, "PRE", log)

        for n in range(1, TRIALS + 1):
            result = one_fresh_session(wire, MEMBER_FRAME)
            if result["status"] == "SUCCESS":
                validate_success(result, *MEMBER_REQUEST)
            member_results.append(result)
            log(
                f"TRIAL n={n} function=0x5d address=0x0000 len=3 "
                f"status={result['status']} data={result['data'].hex() if result['data'] else '-'}"
            )

        identity_control(wire, "POST", log)

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

    classification = classify_member_results(member_results)
    values = [
        f"{r['status']}:{r['data'].hex() if r['data'] else '-'}"
        for r in member_results
    ]
    log("MEMBERLIST_VALUES=" + ",".join(values))
    log("CLASSIFICATION=" + classification)

    completed = len(member_results) == TRIALS and not failures
    log("EXECUTION_RESULT=" + ("PASS" if completed else "FAIL"))
    for error in failures:
        log("ERROR: " + error)
    return 0 if completed else 1


def self_test():
    import unittest

    class Tests(unittest.TestCase):
        def test_identity_frame(self):
            self.assertEqual(IDENT_FRAME.hex(), "4105000100f80806")

        def test_member_frame(self):
            self.assertEqual(MEMBER_FRAME.hex(), "4105005d00000365")

        def test_error_response_decode(self):
            r = decode_response(bytes.fromhex("4106035d000003056e"))
            self.assertEqual(r["status"], "ERROR_MESSAGE")
            self.assertEqual(r["command"], 0x5D)
            self.assertEqual(r["address"], 0x0000)
            self.assertEqual(r["length"], 3)
            self.assertEqual(r["data"], b"\x05")

        def test_stable_error_classification(self):
            r = {
                "status": "ERROR_MESSAGE", "command": 0x5D,
                "address": 0, "length": 3, "data": b"\x05",
            }
            self.assertEqual(classify_member_results([r, dict(r), dict(r)]), "STABLE_ERROR_RESPONSE")

        def test_stable_success_classification(self):
            r = {
                "status": "SUCCESS", "command": 0x5D,
                "address": 0, "length": 3, "data": bytes.fromhex("010203"),
            }
            self.assertEqual(
                classify_member_results([r, dict(r), dict(r)]),
                "STABLE_SUCCESS_UNKNOWN_SEMANTICS",
            )

        def test_write_and_unknown_blocked(self):
            with self.assertRaises(ValueError):
                request_frame(0x5E, 0x0000, 3)
            with self.assertRaises(ValueError):
                request_frame(0x5D, 0x0001, 3)
            with self.assertRaises(ValueError):
                request_frame(0x5D, 0x0000, 4)

    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
    )
    if result.wasSuccessful():
        print("KBUS_MEMBERLIST_READ_PROBE_TESTS=6/6")
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
            f"WB2A KBUS_MEMBERLIST_READ gate {VERSION}: "
            "plan only; no action without --execute."
        )
        return 0

    log = None
    lock_fd = None
    previous = {}
    try:
        import serial

        lock_fd = os.open(LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

        log = Log()
        log(f"WB2A KBUS_MEMBERLIST_READ gate {VERSION}; LOG={log.path}")
        log("READ_ONLY=yes; FUNCTION=0x5D; ADDRESS=0x0000; LEN=3")
        log("PREFIXREAD=empty; TRIALS=3; FRESH_P300_SESSION_PER_SAMPLE=yes")
        log("ARBITRARY_REQUESTS=no; WRITES_IMPLEMENTED=no")
        log("EUID=" + str(os.geteuid()))

        def abort(signum, _frame):
            raise ProbeError("Interrupted by signal " + str(signum))

        previous = {sig: signal.signal(sig, abort) for sig in ABORT_SIGNALS}
        return run_guarded(log, serial)

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
