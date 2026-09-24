#!/opt/optolink/venv/bin/python
"""Read-only WB2A XRAM_READ 0x31 probe in a temporary P300 maintenance window.

The source-derived targets come from the verified Vitosoft-v6 All-Devices
metadata. All 12 XRAM_READ event definitions use no PrefixRead and collapse to
six unique address/length shapes:

  0x0000 / 1
  0x003A / 2
  0x003D / 2
  0x0040 / 2
  0x0042 / 2
  0x0088 / 2

Those Vitosoft events belong to GWG-family profiles, not VDensHO1. This helper
therefore treats any local result only as protocol-capability evidence and
preserves raw bytes without importing cross-profile semantics.

Live action with --execute:
  - requires permanent production vs1protocol=True
  - pauses Party and the VS1 splitter
  - explicitly initializes P300
  - verifies local 20C2 identity via Virtual_READ
  - sends only fixed read-only 0x31 XRAM_READ requests
  - optionally compares same address/length via 0x01 Virtual_READ
  - restores permanent VS1/Party and verifies VS1/KW re-initialization

No write function is implemented.
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
SETTINGS = Path("/opt/optolink/settings_ini.py")
LOCK = "/run/lock/wb2a-xram-p300-read-probe.lock"
ABORT_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)

TARGETS = (
    ("external_request_or_lockout_slot", 0x0000, 1),
    ("runon_timer_slot", 0x003A, 2),
    ("one_minute_timer_slot", 0x003D, 2),
    ("seven_minute_timer_slot", 0x0040, 2),
    ("thirteen_minute_timer_slot", 0x0042, 2),
    ("water_pressure_slot", 0x0088, 2),
)
IDENT_EXPECTED = bytes.fromhex("20 c2 00 03 00 00 01 03")


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
        raise ProbeError("Require permanent production vs1protocol = True; settings are never modified.")
    if values.get("port_vitoconnect") is not None:
        raise ProbeError("Require port_vitoconnect = None for single-owner direct probe.")
    port = values.get("port_optolink")
    if not isinstance(port, str) or not port.startswith("/dev/"):
        raise ProbeError("Require a literal local /dev/ port_optolink path.")
    return port


def checksum(frame_without_crc: bytes) -> int:
    if len(frame_without_crc) < 2 or frame_without_crc[0] != 0x41:
        raise ValueError("P300 frame must start with 0x41.")
    return sum(frame_without_crc[1:]) & 0xFF


def request_frame(function: int, address: int, length: int) -> bytes:
    if function not in (0x01, 0x31):
        raise ValueError("Only read functions 0x01 and 0x31 are allowed.")
    allowed = {(0x00F8, 8)} | {(a, l) for _, a, l in TARGETS}
    if (address, length) not in allowed:
        raise ValueError("Address/length outside fixed allowlist.")
    body = bytes((0x41, 0x05, 0x00, function, address >> 8, address & 0xFF, length))
    return body + bytes((checksum(body),))


ALLOWED_FRAMES = frozenset(
    [request_frame(0x01, 0x00F8, 8)]
    + [request_frame(f, a, l) for f in (0x01, 0x31) for _, a, l in TARGETS]
)
ALLOWED_TX = frozenset({b"\x04", b"\x16\x00\x00", b"\x06"} | set(ALLOWED_FRAMES))


def decode_response(frame: bytes, expected_address: int) -> dict:
    if len(frame) < 4 or frame[0] != 0x41 or len(frame) != frame[1] + 3:
        raise ProbeError("P300 response boundary/length mismatch: " + frame.hex(" "))
    if checksum(frame[:-1]) != frame[-1]:
        raise ProbeError("P300 response checksum mismatch: " + frame.hex(" "))

    msg_type = frame[2] & 0x0F
    command = frame[3]
    result = {
        "message_type": msg_type,
        "command": command,
        "frame": frame.hex(),
        "status": "UNKNOWN",
        "address": None,
        "length": None,
        "data": b"",
    }

    if len(frame) >= 7:
        result["address"] = int.from_bytes(frame[4:6], "big")
        result["length"] = frame[6]
        result["data"] = frame[7:-1]

    if msg_type == 0x01:
        if result["address"] != expected_address:
            raise ProbeError(
                f"P300 response address mismatch 0x{result['address']:04x} != 0x{expected_address:04x}"
            )
        result["status"] = "SUCCESS"
    elif msg_type == 0x03:
        result["status"] = "ERROR_MESSAGE"
    else:
        result["status"] = f"MESSAGE_TYPE_{msg_type:02X}"
    return result


class Wire:
    def __init__(self, port, log, clock=time.monotonic):
        self.port = port
        self.log = log
        self.clock = clock

    def send(self, data: bytes):
        if data not in ALLOWED_TX:
            raise ProbeError("TX blocked by fixed read-only allowlist: " + data.hex(" "))
        self.log("TX " + data.hex(" "))
        if self.port.write(data) != len(data):
            raise ProbeError("Partial serial write; no automatic retransmission.")

    def exact(self, count: int, timeout: float = 2.5) -> bytes:
        until = self.clock() + timeout
        out = bytearray()
        while len(out) < count and self.clock() < until:
            out.extend(self.port.read(count - len(out)))
        if out:
            self.log("RX " + out.hex(" "))
        if len(out) != count:
            raise ProbeError(f"RX timeout: expected {count} byte(s), got {len(out)}.")
        return bytes(out)

    def control(self, expected: int, timeout: float = 5.0):
        until = self.clock() + timeout
        while self.clock() < until:
            data = self.port.read(1)
            if not data:
                continue
            self.log("RX control " + data.hex(" "))
            if data == bytes((expected,)):
                return
            if expected == 0x05 and data in (b"\x06", b"\x15"):
                continue
            if expected == 0x06 and data == b"\x05":
                continue
            raise ProbeError(
                f"Unexpected control byte {data.hex()}, expected {expected:02x}."
            )
        raise ProbeError(f"Timeout waiting for control {expected:02x}.")

    def discard_stale(self):
        size = self.port.in_waiting
        if size > 4096:
            raise ProbeError("Excessive queued serial traffic; aborting.")
        if size:
            self.log("RX stale/discard " + self.port.read(size).hex(" "))

    def enter_p300(self):
        self.discard_stale()
        self.send(b"\x04")
        self.control(0x05)
        self.send(b"\x16\x00\x00")
        self.control(0x06)
        self.log("P300_INITIALIZED=yes")

    def request(self, function: int, address: int, length: int) -> dict:
        self.send(request_frame(function, address, length))
        first = self.exact(1)
        if first == b"\x15":
            return {
                "status": "NACK",
                "command": function,
                "address": address,
                "length": 0,
                "data": b"",
                "frame": "15",
            }
        if first != b"\x06":
            raise ProbeError("P300 request was neither ACK nor NACK: " + first.hex(" "))

        header = self.exact(2)
        if header[0] != 0x41 or not 1 <= header[1] <= 64:
            raise ProbeError("Invalid P300 response header: " + header.hex(" "))
        frame = header + self.exact(header[1] + 1)
        result = decode_response(frame, address)
        self.log(
            f"P300_RESULT function=0x{function:02x} address=0x{address:04x} "
            f"status={result['status']} response_command=0x{result['command']:02x} "
            f"data={result['data'].hex() if result['data'] else '-'} "
            f"frame={result['frame']}"
        )
        self.send(b"\x06")
        return result

    def leave_detection(self):
        self.send(b"\x04")
        self.log("INTERFACE_LEFT_IN_DETECTION_STATE=yes")


class Services:
    @staticmethod
    def command(*args: str, timeout: int = 25) -> str:
        proc = subprocess.run(
            ["systemctl", "--no-pager", "--no-ask-password", *args],
            capture_output=True, text=True, timeout=timeout, check=False
        )
        if proc.returncode:
            raise ProbeError(
                "systemctl failed: " + " ".join(args) + ": " + proc.stderr.strip()
            )
        return proc.stdout

    def state(self, unit: str) -> dict[str, str]:
        output = self.command(
            "show", unit, "-p", "LoadState", "-p", "ActiveState", "-p", "SubState"
        )
        return dict(line.split("=", 1) for line in output.splitlines() if "=" in line)

    def stop(self, unit: str):
        self.command("stop", unit)
        if self.state(unit).get("ActiveState") != "inactive":
            raise ProbeError("Service did not become inactive: " + unit)

    def start(self, unit: str):
        self.command("start", unit)
        time.sleep(2)
        state = self.state(unit)
        if state.get("ActiveState") != "active" or state.get("SubState") != "running":
            raise ProbeError("Service did not stay running: " + unit)

    @staticmethod
    def journal_since(epoch: float) -> str:
        proc = subprocess.run(
            ["journalctl", "-u", SPLITTER, "--since", "@" + str(int(epoch)),
             "--no-pager", "-o", "cat"],
            capture_output=True, text=True, timeout=20, check=False
        )
        if proc.returncode:
            raise ProbeError("journalctl failed: " + proc.stderr.strip())
        return proc.stdout


def check_port_owners(port: str):
    device = os.stat(port)
    if not stat.S_ISCHR(device.st_mode):
        raise ProbeError("Serial path is not a character device: " + port)
    owners = []
    for process in Path("/proc").iterdir():
        if not process.name.isdigit() or int(process.name) == os.getpid():
            continue
        try:
            descriptors = list((process / "fd").iterdir())
        except (FileNotFoundError, PermissionError):
            continue
        for descriptor in descriptors:
            try:
                info = descriptor.stat()
            except (FileNotFoundError, PermissionError):
                continue
            if stat.S_ISCHR(info.st_mode) and info.st_rdev == device.st_rdev:
                owners.append(process.name)
                break
    if owners:
        raise ProbeError("Serial port still open by PID(s): " + ", ".join(owners))


def open_port(port: str, serial_module):
    check_port_owners(port)
    connection = serial_module.Serial(
        port=port, baudrate=4800, bytesize=8, parity="E", stopbits=2,
        timeout=0.05, write_timeout=2, xonxoff=False, rtscts=False,
        dsrdtr=False, exclusive=True
    )
    try:
        fcntl.ioctl(connection.fileno(), termios.TIOCEXCL)
        check_port_owners(port)
    except BaseException:
        connection.close()
        raise
    return connection


def run_guarded(services, opener, log) -> int:
    split = services.state(SPLITTER)
    if (split.get("LoadState"), split.get("ActiveState"), split.get("SubState")) != (
        "loaded", "active", "running"
    ):
        raise ProbeError("Require running permanent splitter before probe.")

    party = services.state(PARTY)
    party_active = party.get("LoadState") == "loaded" and party.get("ActiveState") == "active"
    changed = []
    wire = None
    failures = []
    results = []
    restart_epoch = None

    try:
        for unit in ([PARTY] if party_active else []) + [SPLITTER]:
            changed.append(unit)
            log("Stopping " + unit)
            services.stop(unit)

        wire = Wire(opener(), log)
        wire.enter_p300()

        ident = wire.request(0x01, 0x00F8, 8)
        if ident["status"] != "SUCCESS" or ident["data"] != IDENT_EXPECTED:
            raise ProbeError("P300 20C2 identity control failed.")
        log("P300_IDENTITY_CONTROL=PASS")

        for name, address, length in TARGETS:
            virtual = wire.request(0x01, address, length)
            xram = wire.request(0x31, address, length)
            row = {
                "name": name,
                "address": address,
                "length": length,
                "virtual": virtual,
                "xram": xram,
            }
            results.append(row)
            log(
                f"PAIR {name} address=0x{address:04x} len={length} "
                f"virtual_status={virtual['status']} "
                f"virtual_data={virtual['data'].hex() if virtual['data'] else '-'} "
                f"xram_status={xram['status']} "
                f"xram_data={xram['data'].hex() if xram['data'] else '-'}"
            )

        wire.leave_detection()

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
            journal = services.journal_since(restart_epoch - 0.25)
            restored_vs1 = "VS1/KW protocol initialized" in journal
            log("VS1_RESTORED=" + ("yes" if restored_vs1 else "NOT_CONFIRMED"))
            if not restored_vs1:
                failures.append("Restored splitter did not show VS1/KW protocol initialized.")
        except Exception as exc:
            failures.append("VS1 restore verification failed: " + str(exc))

    success_count = sum(1 for row in results if row["xram"]["status"] == "SUCCESS")
    completed = len(results) == len(TARGETS) and not failures
    log(f"XRAM_SUCCESS_COUNT={success_count}/{len(TARGETS)}")
    log("XRAM_CAPABILITY=" + ("SOURCE_TARGET_SUCCESS" if success_count else "NO_SOURCE_TARGET_SUCCEEDED"))
    log("EXECUTION_RESULT=" + ("PASS" if completed else "FAIL"))
    for failure in failures:
        log("ERROR: " + failure)
    return 0 if completed else 1


def self_test() -> int:
    import unittest

    class Tests(unittest.TestCase):
        def test_known_xram_frame(self):
            self.assertEqual(request_frame(0x31, 0x003A, 2).hex(), "41050031003a0272")

        def test_identity_frame(self):
            self.assertEqual(request_frame(0x01, 0x00F8, 8).hex(), "4105000100f80806")

        def test_write_codes_blocked(self):
            for f in (0x02, 0x32, 0x42, 0x43):
                with self.assertRaises(ValueError):
                    request_frame(f, 0x003A, 2)

        def test_unknown_target_blocked(self):
            with self.assertRaises(ValueError):
                request_frame(0x31, 0x1234, 1)

        def test_source_targets(self):
            self.assertEqual(
                {(a, l) for _, a, l in TARGETS},
                {(0x0000,1),(0x003A,2),(0x003D,2),(0x0040,2),(0x0042,2),(0x0088,2)}
            )

    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
    )
    if result.wasSuccessful():
        print("XRAM_P300_READ_PROBE_TESTS=5/5")
        return 0
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--execute", action="store_true")
    group.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if not args.execute:
        print(
            f"WB2A XRAM/P300 read probe {VERSION}: plan only; no action without --execute.\n"
            "Runs only source-derived read-only 0x31 targets in a temporary P300 window, "
            "then restores permanent VS1/KW."
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
        if not stat.S_ISCHR(os.stat(port).st_mode):
            raise ProbeError("Configured port is not a character device.")

        lock_fd = os.open(LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        log = Log(Path("/root") / f"wb2a-xram-p300-read-{stamp}-{os.getpid()}.log")
        log(f"WB2A XRAM/P300 read-only probe {VERSION}; LOG={log.path}")
        log(f"Configured port: {port}; resolved: {os.path.realpath(port)}; 4800 8E2.")
        log("SOURCE_TARGETS=Vitosoft-v6 GWG-family XRAM; LOCAL_SEMANTICS=UNPROVEN")
        log("PRODUCTION_EXPECTED=VS1/KW; NO_SETTINGS_EDITS=yes; READ_ONLY=yes")

        def abort(signum, _frame):
            raise ProbeError("Interrupted by signal " + str(signum) + "; entering cleanup.")

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
