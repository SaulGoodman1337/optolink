#!/opt/optolink/venv/bin/python
"""Bounded read-only Physical_READ 0x03 vs KMBUS_EEPROM_READ 0x43 discriminator.

Research question
-----------------
Recovered Vitosoft response code puts command byte 0x43 in the same generic
read-conversion class as 0x03 because both have low five bits 0x03. This does
NOT prove that the controller aliases those full command bytes.

This helper tests that question locally without sweeping addresses.

Every research sample uses a fresh P300 session. Fixed trials:

  positive control, 0x00F8/2:
    0x01, 0x41, 0x41, 0x01

  discriminator, 0x00F8/2:
    0x03, 0x43, 0x43, 0x03

  discriminator, 0x0001/1:
    0x03, 0x43, 0x43, 0x03

The first group re-checks the already established 0x01/0x41 mirror. The other
two groups compare 0x03 against 0x43.

Production remains permanent VS1/KW. With --execute the helper pauses the
single serial owner, initializes P300 for each sample, performs only fixed
allowlisted reads, then restores splitter/Party and verifies VS1 restoration.

No write function is implemented.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
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

VERSION = "1.2.0"
SPLITTER = "optolink-splitter.service"
PARTY = "optolink-party-emulator.service"
SCHEDULE = "optolink-schedule-manager.service"
SETTINGS = Path("/opt/optolink/settings_ini.py")
LOCK = "/run/lock/wb2a-physical-vs-kmbus-eeprom-probe.lock"
ABORT_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)

IDENT_EXPECTED = bytes.fromhex("20 c2 00 03 00 00 01 03")

# Bytewise high-address discriminator. Physical_READ catalog definitions are
# byte-sized, so this deliberately avoids the earlier 16-byte block request.
BYTEWISE_HIGH_ADDRESSES = (
    tuple(range(0xF000, 0xF010))
    + tuple(range(0xFFF0, 0x10000))
)

# label, address, length, balanced function order
GROUPS = (
    ("virtual_vs_kmbus_ram_control", 0x00F8, 2, (0x01, 0x41, 0x41, 0x01)),
    ("physical_vs_kmbus_eeprom_f8",  0x00F8, 2, (0x03, 0x43, 0x43, 0x03)),
    ("physical_vs_kmbus_eeprom_0001",0x0001, 1, (0x03, 0x43, 0x43, 0x03)),
    # M16C/62P memory-map discriminators. These are valid mapped regions on
    # the M30624FG working hypothesis; no reserved address is touched.
    ("m16c_sfr_0004",               0x0004, 4, (0x03, 0x43, 0x43, 0x03)),
    ("m16c_ram_start_0400",         0x0400,16, (0x03, 0x43, 0x43, 0x03)),
    ("m16c_ram_end_53f0",           0x53F0,16, (0x03, 0x43, 0x43, 0x03)),
    ("m16c_dataflash_start_f000",   0xF000,16, (0x03, 0x43, 0x43, 0x03)),
    ("m16c_dataflash_end_fff0",     0xFFF0,16, (0x03, 0x43, 0x43, 0x03)),
)

ALLOWED_REQUESTS = {
    (0x01, 0x00F8, 8),
    (0x01, 0x00F8, 2),
    (0x41, 0x00F8, 2),
    (0x03, 0x00F8, 2),
    (0x43, 0x00F8, 2),
    (0x03, 0x0001, 1),
    (0x43, 0x0001, 1),
    (0x03, 0x0004, 4),
    (0x43, 0x0004, 4),
    (0x03, 0x0400,16),
    (0x43, 0x0400,16),
    (0x03, 0x53F0,16),
    (0x43, 0x53F0,16),
    (0x03, 0xF000,16),
    (0x43, 0xF000,16),
    (0x03, 0xFFF0,16),
    (0x43, 0xFFF0,16),
}
ALLOWED_REQUESTS.update((0x03, address, 1) for address in BYTEWISE_HIGH_ADDRESSES)


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
    body = bytes(
        (0x41, 0x05, 0x00, function, address >> 8, address & 0xFF, length)
    )
    return body + bytes((checksum(body),))


CONTROL_FRAME = request_frame(0x01, 0x00F8, 8)
RESEARCH_FRAMES = {
    key: request_frame(*key)
    for key in ALLOWED_REQUESTS
    if key != (0x01, 0x00F8, 8)
}
ALLOWED_TX = frozenset(
    {b"\x04", b"\x16\x00\x00", b"\x06", CONTROL_FRAME}
    | set(RESEARCH_FRAMES.values())
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


def result_key(result: dict):
    # Compare semantic response outcome, not the echoed request command.
    # 0x01 vs 0x41 and 0x03 vs 0x43 are expected to echo different command
    # bytes even when their status/address/length/payload are identical.
    return (
        result["status"],
        result["address"],
        result["length"],
        result["data"].hex(),
    )


def classify_pair(observations, f_a: int, f_b: int) -> str:
    a = [result_key(r) for f, r in observations if f == f_a]
    b = [result_key(r) for f, r in observations if f == f_b]
    if len(a) != 2 or len(b) != 2:
        return "INCOMPLETE"
    ca, cb = Counter(a), Counter(b)
    if len(ca) == 1 and len(cb) == 1:
        return "STABLE_SAME" if next(iter(ca)) == next(iter(cb)) else "STABLE_DISTINCT"
    if ca == cb:
        return "DYNAMIC_SAME_DISTRIBUTION"
    return "DYNAMIC_OR_INCONCLUSIVE"


def one_session(wire: Wire, function: int, address: int, length: int, log) -> dict:
    wire.enter_p300()
    try:
        result = wire.transact(request_frame(function, address, length))
        log(
            f"ISOLATED_RESULT function=0x{function:02x} "
            f"address=0x{address:04x} len={length} "
            f"status={result['status']} data={result['data'].hex() if result['data'] else '-'}"
        )
        return result
    finally:
        wire.leave()
        time.sleep(0.15)


def run_guarded(services, opener, log, bytewise_high=False):
    split = services.state(SPLITTER)
    if (split.get("LoadState"), split.get("ActiveState"), split.get("SubState")) != ("loaded", "active", "running"):
        raise ProbeError("Require running splitter.")
    party = services.state(PARTY)
    party_active = party.get("LoadState") == "loaded" and party.get("ActiveState") == "active"
    schedule = services.state(SCHEDULE)
    schedule_active = (
        schedule.get("LoadState") == "loaded"
        and schedule.get("ActiveState") == "active"
    )

    changed = []
    wire = None
    failures = []
    group_results = []
    bytewise_runs = []
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

        # Separate identity-only session.
        wire.enter_p300()
        ident = wire.transact(CONTROL_FRAME)
        if (
            ident["status"] != "SUCCESS"
            or ident["command"] != 0x01
            or ident["address"] != 0x00F8
            or ident["data"] != IDENT_EXPECTED
        ):
            raise ProbeError("20C2 identity control failed.")
        log("P300_IDENTITY_CONTROL=PASS")
        wire.leave()
        time.sleep(0.15)

        if bytewise_high:
            log(
                "BYTEWISE_HIGH_START ranges=0xf000-0xf00f,0xfff0-0xffff "
                "function=0x03 len=1 passes=2"
            )
            for pass_no in (1, 2):
                values = {}
                wire.enter_p300()
                try:
                    for address in BYTEWISE_HIGH_ADDRESSES:
                        result = wire.transact(request_frame(0x03, address, 1))
                        if (
                            result["status"] != "SUCCESS"
                            or result["command"] != 0x03
                            or result["address"] != address
                            or len(result["data"]) != 1
                        ):
                            raise ProbeError(
                                f"Bytewise read failed at 0x{address:04x}: {result}"
                            )
                        values[address] = result["data"][0]
                        log(
                            f"BYTEWISE pass={pass_no} address=0x{address:04x} "
                            f"data={result['data'].hex()}"
                        )
                finally:
                    wire.leave()
                    time.sleep(0.15)
                bytewise_runs.append(values)
                for base in (0xF000, 0xFFF0):
                    block = bytes(values[base + i] for i in range(16))
                    log(
                        f"BYTEWISE_BLOCK pass={pass_no} base=0x{base:04x} "
                        f"data={block.hex()}"
                    )
        else:
            for label, address, length, order in GROUPS:
                observations = []
                log(
                    f"GROUP_START label={label} address=0x{address:04x} "
                    f"len={length} order=" + ",".join(f"0x{x:02x}" for x in order)
                )
                for n, function in enumerate(order, 1):
                    result = one_session(wire, function, address, length, log)
                    observations.append((function, result))
                    log(
                        f"TRIAL group={label} n={n} function=0x{function:02x} "
                        f"status={result['status']} data={result['data'].hex() if result['data'] else '-'}"
                    )

                f_a, f_b = order[0], order[1]
                classification = classify_pair(observations, f_a, f_b)
                group_results.append((label, f_a, f_b, observations, classification))
                log(
                    f"GROUP_RESULT label={label} compare=0x{f_a:02x}:0x{f_b:02x} "
                    f"class={classification}"
                )

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

    for label, f_a, f_b, observations, classification in group_results:
        for function in (f_a, f_b):
            vals = [
                f"{r['status']}:{r['data'].hex() if r['data'] else '-'}"
                for f, r in observations if f == function
            ]
            log(
                f"SUMMARY label={label} function=0x{function:02x} "
                f"values=" + ",".join(vals)
            )
        log(f"SUMMARY label={label} class={classification}")

    if bytewise_high:
        if len(bytewise_runs) == 2:
            stable = [
                address for address in BYTEWISE_HIGH_ADDRESSES
                if bytewise_runs[0].get(address) == bytewise_runs[1].get(address)
            ]
            changed = [
                address for address in BYTEWISE_HIGH_ADDRESSES
                if bytewise_runs[0].get(address) != bytewise_runs[1].get(address)
            ]
            log(
                f"BYTEWISE_SUMMARY stable={len(stable)}/{len(BYTEWISE_HIGH_ADDRESSES)} "
                "changed=" + ",".join(f"0x{x:04x}" for x in changed)
            )
            for base in (0xF000, 0xFFF0):
                a = bytes(bytewise_runs[0][base + i] for i in range(16))
                b = bytes(bytewise_runs[1][base + i] for i in range(16))
                log(
                    f"BYTEWISE_COMPARE base=0x{base:04x} "
                    f"pass1={a.hex()} pass2={b.hex()} equal={a == b}"
                )
        completed = len(bytewise_runs) == 2 and not failures
    else:
        completed = len(group_results) == len(GROUPS) and not failures
    log("EXECUTION_RESULT=" + ("PASS" if completed else "FAIL"))
    for e in failures:
        log("ERROR: " + e)
    return 0 if completed else 1


def self_test():
    import unittest

    class Tests(unittest.TestCase):
        def test_identity_frame(self):
            self.assertEqual(CONTROL_FRAME.hex(), "4105000100f80806")

        def test_virtual_control_frame(self):
            self.assertEqual(request_frame(0x01, 0x00F8, 2).hex(), "4105000100f80200")

        def test_kmbus_ram_frame(self):
            self.assertEqual(request_frame(0x41, 0x00F8, 2).hex(), "4105004100f80240")

        def test_physical_and_43_frames(self):
            self.assertEqual(request_frame(0x03, 0x00F8, 2).hex(), "4105000300f80202")
            self.assertEqual(request_frame(0x43, 0x00F8, 2).hex(), "4105004300f80242")
            self.assertEqual(request_frame(0x03, 0xF000, 16).hex(), "41050003f0001008")
            self.assertEqual(request_frame(0x03, 0xFFF0, 16).hex(), "41050003fff01007")

        def test_classification_ignores_echoed_command(self):
            a = {
                "status": "SUCCESS", "command": 0x01, "address": 0x00F8,
                "length": 2, "data": bytes.fromhex("20c2"),
            }
            b = dict(a)
            b["command"] = 0x41
            observations = [(0x01, a), (0x41, b), (0x41, b), (0x01, a)]
            self.assertEqual(classify_pair(observations, 0x01, 0x41), "STABLE_SAME")

        def test_bytewise_high_allowlist(self):
            self.assertEqual(request_frame(0x03, 0xF000, 1).hex(), "41050003f00001f9")
            self.assertEqual(request_frame(0x03, 0xFFFF, 1).hex(), "41050003ffff0107")
            with self.assertRaises(ValueError):
                request_frame(0x03, 0xF010, 1)

        def test_write_and_unknown_blocked(self):
            with self.assertRaises(ValueError):
                request_frame(0x04, 0x00F8, 2)
            with self.assertRaises(ValueError):
                request_frame(0x43, 0x1234, 1)

    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
    )
    if result.wasSuccessful():
        print("PHYSICAL_VS_KMBUS_EEPROM_PROBE_TESTS=7/7")
        return 0
    return 1


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--execute", action="store_true")
    g.add_argument(
        "--bytewise-high",
        action="store_true",
        help="read-only bytewise Physical_READ at 0xF000..0xF00F and 0xFFF0..0xFFFF",
    )
    g.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if not args.execute and not args.bytewise_high:
        print(
            f"WB2A Physical_READ vs KMBUS_EEPROM_READ probe {VERSION}: "
            "plan only; no action without --execute or --bytewise-high."
        )
        return 0
    if os.geteuid() != 0:
        print("ERROR: live execution requires root.", file=sys.stderr)
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
        log = Log(Path("/root") / f"wb2a-physical-vs-kmbus-eeprom-{stamp}-{os.getpid()}.log")
        log(f"WB2A Physical_READ vs KMBUS_EEPROM_READ probe {VERSION}; LOG={log.path}")
        log(f"Configured port: {port}; resolved: {os.path.realpath(port)}; 4800 8E2.")
        log(
            "READ_ONLY=yes; FRESH_P300_SESSION_PER_TRIAL=yes; BROAD_SWEEP=no; "
            f"BYTEWISE_HIGH={'yes' if args.bytewise_high else 'no'}"
        )

        def abort(signum, _frame):
            raise ProbeError("Interrupted by signal " + str(signum))

        previous = {sig: signal.signal(sig, abort) for sig in ABORT_SIGNALS}
        return run_guarded(
            Services(),
            lambda: open_port(port, serial),
            log,
            bytewise_high=args.bytewise_high,
        )

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
