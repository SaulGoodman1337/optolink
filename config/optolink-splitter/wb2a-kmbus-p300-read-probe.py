#!/usr/bin/env python3
"""Read-only WB2A KMBUS/P300 correlation probe while production remains VS1.

Production prerequisite:
  - permanent splitter is running VS1/KW (vs1protocol=True)
  - normal F7 Virtual_READ + GFA 6B polling is the production mode

Live action with --execute:
  1. stop Party if active
  2. stop optolink-splitter.service (release the single serial owner)
  3. open Optolink directly at 4800 8E2
  4. explicitly initialize P300/VS2
  5. compare P300 Virtual_READ 0x01 with KMBUS_RAM_READ 0x41 on a fixed allowlist
  6. leave interface in detection state, close serial
  7. restart splitter and Party if they were active
  8. require restored splitter journal to show "VS1/KW protocol initialized"

No controller write function is implemented.
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
LOCK = "/run/lock/wb2a-kmbus-p300-read-probe.lock"
ABORT_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)

TARGETS = (
    ("identity", 0x00F8, 8),
    ("pump_final_command", 0x0A3C, 1),
    ("internal_pump_runtime", 0x7660, 2),
    ("a1_pump_request", 0x7663, 2),
    ("internal_pump_identity", 0x5730, 1),
    ("internal_pump_sw_block", 0x0A54, 4),
    ("a1_remote_identity", 0x27A0, 1),
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
        raise ValueError("P300 frame must start with 0x41")
    return sum(frame_without_crc[1:]) & 0xFF


def request_frame(function: int, address: int, length: int) -> bytes:
    if function not in (0x01, 0x41):
        raise ValueError("Only read functions 0x01 and 0x41 are allowed.")
    if not any(address == a and length == l for _, a, l in TARGETS):
        raise ValueError("Address/length outside fixed allowlist.")
    body = bytes((0x41, 0x05, 0x00, function, address >> 8, address & 0xFF, length))
    return body + bytes((checksum(body),))


ALLOWED_FRAMES = frozenset(
    request_frame(function, address, length)
    for function in (0x01, 0x41)
    for _, address, length in TARGETS
)
ALLOWED_TX = frozenset({b"\x04", b"\x16\x00\x00", b"\x06"} | set(ALLOWED_FRAMES))


def decode_response(frame: bytes, address: int, length: int) -> tuple[int, int, bytes]:
    if len(frame) < 8 or frame[0] != 0x41 or len(frame) != frame[1] + 3:
        raise ProbeError("P300 response boundary/length mismatch: " + frame.hex(" "))
    if checksum(frame[:-1]) != frame[-1]:
        raise ProbeError("P300 response checksum mismatch: " + frame.hex(" "))

    msg_type = frame[2] & 0x0F
    command_byte = frame[3]
    got_addr = int.from_bytes(frame[4:6], "big")
    got_len = frame[6]
    data = frame[7:-1]

    if msg_type == 0x03:
        raise ProbeError("P300 Error Message: " + frame.hex(" "))
    if msg_type != 0x01:
        raise ProbeError(f"Unexpected P300 message type 0x{msg_type:02x}: " + frame.hex(" "))
    if got_addr != address:
        raise ProbeError(f"P300 response address mismatch 0x{got_addr:04x} != 0x{address:04x}")
    if got_len != length or len(data) != length:
        raise ProbeError(
            f"P300 response length mismatch field={got_len} payload={len(data)} expected={length}"
        )
    return msg_type, command_byte, data


class Wire:
    def __init__(self, port, log, clock=time.monotonic):
        self.port = port
        self.log = log
        self.clock = clock
        self.touched = False

    def send(self, data: bytes):
        if data not in ALLOWED_TX:
            raise ProbeError("TX blocked by fixed read-only allowlist: " + data.hex(" "))
        self.log("TX " + data.hex(" "))
        self.touched = True
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

    def request(self, function: int, address: int, length: int) -> bytes:
        frame = request_frame(function, address, length)
        self.send(frame)
        if self.exact(1) != b"\x06":
            raise ProbeError("P300 request was not acknowledged.")
        header = self.exact(2)
        if header[0] != 0x41 or not 5 <= header[1] <= 64:
            raise ProbeError("Invalid P300 response header: " + header.hex(" "))
        response = header + self.exact(header[1] + 1)
        _, command_byte, data = decode_response(response, address, length)
        self.log(
            f"P300_READ function=0x{function:02x} response_command=0x{command_byte:02x} "
            f"address=0x{address:04x} len={length} data={data.hex()}"
        )
        self.send(b"\x06")
        return data

    def leave_detection(self):
        self.send(b"\x04")
        self.log("INTERFACE_LEFT_IN_DETECTION_STATE=yes")


class Services:
    @staticmethod
    def command(*args: str, timeout: int = 25) -> str:
        try:
            proc = subprocess.run(
                ["systemctl", "--no-pager", "--no-ask-password", *args],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ProbeError("systemctl timeout: " + " ".join(args)) from exc
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
            [
                "journalctl", "-u", SPLITTER, "--since", "@" + str(int(epoch)),
                "--no-pager", "-o", "cat"
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
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
        port=port,
        baudrate=4800,
        bytesize=8,
        parity="E",
        stopbits=2,
        timeout=0.05,
        write_timeout=2,
        xonxoff=False,
        rtscts=False,
        dsrdtr=False,
        exclusive=True,
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
    if party.get("ActiveState") in ("activating", "deactivating", "reloading"):
        raise ProbeError("Party emulator is in transition.")
    party_active = party.get("LoadState") == "loaded" and party.get("ActiveState") == "active"

    changed = []
    wire = None
    failures = []
    pairs = {}
    restart_epoch = None

    try:
        for unit in ([PARTY] if party_active else []) + [SPLITTER]:
            changed.append(unit)
            log("Stopping " + unit)
            services.stop(unit)

        wire = Wire(opener(), log)
        wire.enter_p300()

        control = wire.request(0x01, 0x00F8, 8)
        if control != IDENT_EXPECTED:
            raise ProbeError(
                "P300 identity control mismatch: "
                + control.hex()
                + " != "
                + IDENT_EXPECTED.hex()
            )
        log("P300_IDENTITY_CONTROL=PASS")

        for name, address, length in TARGETS:
            normal = wire.request(0x01, address, length)
            kmbus = wire.request(0x41, address, length)
            if normal == kmbus:
                cls = "IDENTICAL"
            else:
                cls = "DIFFERENT"
            pairs[name] = (address, length, normal, kmbus, cls)
            log(
                f"PAIR {name} address=0x{address:04x} len={length} "
                f"virtual={normal.hex()} kmbus41={kmbus.hex()} class={cls}"
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

    log("PAIR_COUNT=" + str(len(pairs)))
    log("RESULT=" + ("PASS" if len(pairs) == len(TARGETS) and not failures else "FAIL"))
    for failure in failures:
        log("ERROR: " + failure)
    return 0 if len(pairs) == len(TARGETS) and not failures else 1


def self_test() -> int:
    import unittest

    class Tests(unittest.TestCase):
        def test_known_frames(self):
            self.assertEqual(request_frame(0x01, 0x00F8, 8).hex(), "4105000100f80806")
            self.assertEqual(request_frame(0x41, 0x00F8, 8).hex(), "4105004100f80846")

        def test_write_codes_blocked(self):
            for f in (0x02, 0x42, 0x43, 0x56):
                with self.assertRaises(ValueError):
                    request_frame(f, 0x00F8, 8)

        def test_unknown_target_blocked(self):
            with self.assertRaises(ValueError):
                request_frame(0x41, 0x1234, 1)

        def test_good_response_decode(self):
            body = bytes.fromhex("41 0d 01 01 00 f8 08 20 c2 00 03 00 00 01 03")
            frame = body + bytes((checksum(body),))
            _, command, data = decode_response(frame, 0x00F8, 8)
            self.assertEqual(command, 0x01)
            self.assertEqual(data, IDENT_EXPECTED)

        def test_bad_checksum(self):
            body = bytes.fromhex("41 06 01 01 00 f8 01 20")
            frame = body + bytes(((checksum(body) ^ 1),))
            with self.assertRaises(ProbeError):
                decode_response(frame, 0x00F8, 1)

    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
    )
    if result.wasSuccessful():
        print("KMBUS_P300_READ_PROBE_TESTS=5/5")
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
            f"WB2A KMBUS/P300 read probe {VERSION}: plan only; no action without --execute.\n"
            "Requires permanent production vs1protocol=True. Live execution pauses the VS1 "
            "serial owner, explicitly enters P300, performs only fixed 0x01/0x41 reads, "
            "then restores and verifies permanent VS1."
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
        log = Log(Path("/root") / f"wb2a-kmbus-p300-read-{stamp}-{os.getpid()}.log")
        log(f"WB2A KMBUS/P300 read-only probe {VERSION}; LOG={log.path}")
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
