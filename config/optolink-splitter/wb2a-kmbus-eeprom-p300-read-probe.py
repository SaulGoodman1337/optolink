#!/opt/optolink/venv/bin/python
"""Read-only prefixed KMBUS_EEPROM_READ 0x43 probe in a temporary P300 window.

This helper reconstructs one exact Vitosoft-v6 request shape:

  event 578
  source profile: GWG_BT2
  source label: Kennung (Prog1)
  function: KMBUS_EEPROM_READ (0x43)
  address: 0x0001
  block length: 1
  PrefixRead: 03 00 00 00 01 01

The source semantics are NOT assumed to apply to the local WB2A / VDensHO1.
The purpose is only to determine whether the local 20C2 controller accepts and
routes an exact source-defined prefixed 0x43 request.

Production remains permanent VS1/KW. With --execute this helper pauses the
single serial owner, initializes P300 explicitly, performs the identity control
and exactly one fixed 0x43 read, then restores VS1/Party.

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
LOCK = "/run/lock/wb2a-kmbus-eeprom-p300-read-probe.lock"
ABORT_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)

IDENT_EXPECTED = bytes.fromhex("20 c2 00 03 00 00 01 03")
PREFIX = bytes.fromhex("03 00 00 00 01 01")
TARGET_ADDRESS = 0x0001
TARGET_LENGTH = 1


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


def request_frame(function: int, address: int, length: int, data: bytes = b"") -> bytes:
    if function == 0x01:
        if (address, length, data) != (0x00F8, 8, b""):
            raise ValueError("0x01 is allowed only for the fixed identity control.")
    elif function == 0x43:
        if (address, length, data) != (TARGET_ADDRESS, TARGET_LENGTH, PREFIX):
            raise ValueError("0x43 request outside the exact source-derived allowlist.")
    else:
        raise ValueError("Only read functions 0x01 and 0x43 are allowed.")

    payload_len = 5 + len(data)
    body = bytes(
        (0x41, payload_len, 0x00, function, address >> 8, address & 0xFF, length)
    ) + data
    return body + bytes((checksum(body),))


CONTROL_FRAME = request_frame(0x01, 0x00F8, 8)
EEPROM_FRAME = request_frame(0x43, TARGET_ADDRESS, TARGET_LENGTH, PREFIX)
ALLOWED_TX = frozenset({b"\x04", b"\x16\x00\x00", b"\x06", CONTROL_FRAME, EEPROM_FRAME})


def decode_response(frame: bytes) -> dict:
    if len(frame) < 4 or frame[0] != 0x41 or len(frame) != frame[1] + 3:
        raise ProbeError("P300 response boundary/length mismatch: " + frame.hex(" "))
    if checksum(frame[:-1]) != frame[-1]:
        raise ProbeError("P300 response checksum mismatch: " + frame.hex(" "))

    msg_type = frame[2] & 0x0F
    command = frame[3]
    address = int.from_bytes(frame[4:6], "big") if len(frame) >= 7 else None
    length = frame[6] if len(frame) >= 7 else None
    data = frame[7:-1] if len(frame) >= 8 else b""

    if msg_type == 0x01:
        status = "SUCCESS"
    elif msg_type == 0x03:
        status = "ERROR_MESSAGE"
    else:
        status = f"MESSAGE_TYPE_{msg_type:02X}"

    return {
        "status": status,
        "message_type": msg_type,
        "command": command,
        "address": address,
        "length": length,
        "data": data,
        "frame": frame.hex(),
    }


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

    def transact(self, frame: bytes) -> dict:
        self.send(frame)
        first = self.exact(1)
        if first == b"\x15":
            result = {
                "status": "NACK",
                "message_type": None,
                "command": None,
                "address": None,
                "length": None,
                "data": b"",
                "frame": "15",
            }
            self.log("P300_RESULT status=NACK")
            return result
        if first != b"\x06":
            raise ProbeError("P300 request was neither ACK nor NACK: " + first.hex(" "))

        header = self.exact(2)
        if header[0] != 0x41 or not 1 <= header[1] <= 64:
            raise ProbeError("Invalid P300 response header: " + header.hex(" "))
        full = header + self.exact(header[1] + 1)
        result = decode_response(full)
        self.log(
            f"P300_RESULT status={result['status']} "
            f"response_command={('-' if result['command'] is None else f'0x{result['command']:02x}')} "
            f"address={('-' if result['address'] is None else f'0x{result['address']:04x}')} "
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
    eeprom_result = None
    restart_epoch = None

    try:
        for unit in ([PARTY] if party_active else []) + [SPLITTER]:
            changed.append(unit)
            log("Stopping " + unit)
            services.stop(unit)

        wire = Wire(opener(), log)
        wire.enter_p300()

        ident = wire.transact(CONTROL_FRAME)
        if (
            ident["status"] != "SUCCESS"
            or ident["command"] != 0x01
            or ident["address"] != 0x00F8
            or ident["data"] != IDENT_EXPECTED
        ):
            raise ProbeError("P300 20C2 identity control failed.")
        log("P300_IDENTITY_CONTROL=PASS")

        log(
            "SOURCE_EVENT=578 function=0x43 address=0x0001 len=1 "
            "prefix=030000000101 source_profile=GWG_BT2 local_semantics=UNPROVEN"
        )
        eeprom_result = wire.transact(EEPROM_FRAME)

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

    if eeprom_result is None:
        capability = "NOT_TESTED"
    elif eeprom_result["status"] == "SUCCESS":
        capability = "PREFIXED_SOURCE_REQUEST_SUCCEEDED"
    elif eeprom_result["status"] == "ERROR_MESSAGE":
        capability = "PREFIXED_SOURCE_REQUEST_ERROR_MESSAGE"
    else:
        capability = eeprom_result["status"]

    completed = eeprom_result is not None and not failures
    log("KMBUS_EEPROM_CAPABILITY=" + capability)
    log("EXECUTION_RESULT=" + ("PASS" if completed else "FAIL"))
    for failure in failures:
        log("ERROR: " + failure)
    return 0 if completed else 1


def self_test() -> int:
    import unittest

    class Tests(unittest.TestCase):
        def test_identity_frame(self):
            self.assertEqual(CONTROL_FRAME.hex(), "4105000100f80806")

        def test_exact_prefixed_frame(self):
            self.assertEqual(
                EEPROM_FRAME.hex(),
                "410b004300010103000000010155"
            )

        def test_wrong_prefix_blocked(self):
            with self.assertRaises(ValueError):
                request_frame(0x43, 0x0001, 1, bytes.fromhex("030000000100"))

        def test_other_address_blocked(self):
            with self.assertRaises(ValueError):
                request_frame(0x43, 0x000A, 5, PREFIX)

        def test_write_blocked(self):
            with self.assertRaises(ValueError):
                request_frame(0x44, 0x0001, 1, PREFIX)

    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
    )
    if result.wasSuccessful():
        print("KMBUS_EEPROM_P300_READ_PROBE_TESTS=5/5")
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
            f"WB2A prefixed KMBUS EEPROM/P300 read probe {VERSION}: plan only; "
            "no action without --execute.\n"
            "Sends exactly one source-derived read-only 0x43 request after a "
            "20C2 P300 identity control, then restores permanent VS1/KW."
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
        log = Log(Path("/root") / f"wb2a-kmbus-eeprom-p300-read-{stamp}-{os.getpid()}.log")
        log(f"WB2A prefixed KMBUS EEPROM/P300 read-only probe {VERSION}; LOG={log.path}")
        log(f"Configured port: {port}; resolved: {os.path.realpath(port)}; 4800 8E2.")
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
