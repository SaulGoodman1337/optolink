#!/opt/optolink/venv/bin/python
"""Bounded read-only source-derived KMBUS_EEPROM_READ 0x43 map probe.

Prerequisite already proven locally:
  0x43 / 0x0001 / len 1 / PrefixRead 030000000101
  -> SUCCESS, raw byte 0x88

This helper expands only to exact Vitosoft-v6 GWG_BT2 block shapes that use the
same PrefixRead. It does NOT sweep a contiguous EEPROM range and it does NOT
transfer GWG_BT2/LGM27 semantics to the local WB2A.

Production remains permanent VS1/KW. With --execute the helper pauses the
single serial owner, explicitly initializes P300, verifies the local 20C2
identity, performs only fixed allowlisted 0x43 reads, then restores VS1/Party.

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
LOCK = "/run/lock/wb2a-kmbus-eeprom-map-probe.lock"
ABORT_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)

IDENT_EXPECTED = bytes.fromhex("20 c2 00 03 00 00 01 03")
PREFIX = bytes.fromhex("03 00 00 00 01 01")

# Exact source-derived block shapes observed in the verified v6 event slice for
# GWG_BT2 with KMBUS_EEPROM_READ and PrefixRead=030000000101.
TARGETS = (
    ("id_prog1",             0x0001, 1),
    ("device_parameter_set", 0x000A, 5),
    ("gas_modulation_block", 0x000F, 8),
    ("min_burner_pause",     0x0064, 2),
    ("temperature_block",    0x006A, 6),
    ("limits_block",         0x0070, 7),
    ("flue_threshold_block", 0x0078, 5),
    ("switch_diff_block",    0x0078, 8),
    ("timing_block",         0x0083, 4),
    ("dhw_runon_block",      0x0091, 1),
    ("fault_code_block",     0x00A0, 10),
    ("fault_diag_block",     0x00AA, 10),
    ("fault_phase_block",    0x00B4, 10),
)


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
        if data != PREFIX or (address, length) not in {(a, l) for _, a, l in TARGETS}:
            raise ValueError("0x43 request outside fixed source-derived allowlist.")
    else:
        raise ValueError("Only read functions 0x01 and 0x43 are allowed.")

    payload_len = 5 + len(data)
    body = bytes(
        (0x41, payload_len, 0x00, function, address >> 8, address & 0xFF, length)
    ) + data
    return body + bytes((checksum(body),))


CONTROL_FRAME = request_frame(0x01, 0x00F8, 8)
TARGET_FRAMES = {
    (address, length): request_frame(0x43, address, length, PREFIX)
    for _, address, length in TARGETS
}
ALLOWED_TX = frozenset(
    {b"\x04", b"\x16\x00\x00", b"\x06", CONTROL_FRAME} | set(TARGET_FRAMES.values())
)


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
    status = "SUCCESS" if msg_type == 0x01 else ("ERROR_MESSAGE" if msg_type == 0x03 else f"MESSAGE_TYPE_{msg_type:02X}")
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
            raise ProbeError(f"Unexpected control byte {data.hex()}, expected {expected:02x}.")
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
            result = {"status":"NACK","message_type":None,"command":None,"address":None,"length":None,"data":b"","frame":"15"}
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
            f"len={result['length']} data={result['data'].hex() if result['data'] else '-'} "
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
            raise ProbeError("systemctl failed: " + " ".join(args) + ": " + proc.stderr.strip())
        return proc.stdout

    def state(self, unit: str) -> dict[str, str]:
        output = self.command("show", unit, "-p", "LoadState", "-p", "ActiveState", "-p", "SubState")
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
            ["journalctl", "-u", SPLITTER, "--since", "@" + str(int(epoch)), "--no-pager", "-o", "cat"],
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
    if (split.get("LoadState"), split.get("ActiveState"), split.get("SubState")) != ("loaded","active","running"):
        raise ProbeError("Require running permanent splitter before probe.")
    party = services.state(PARTY)
    party_active = party.get("LoadState") == "loaded" and party.get("ActiveState") == "active"

    changed=[]; wire=None; failures=[]; results=[]; restart_epoch=None
    try:
        for unit in ([PARTY] if party_active else []) + [SPLITTER]:
            changed.append(unit); log("Stopping " + unit); services.stop(unit)

        wire=Wire(opener(),log); wire.enter_p300()
        ident=wire.transact(CONTROL_FRAME)
        if ident["status"]!="SUCCESS" or ident["command"]!=0x01 or ident["address"]!=0x00F8 or ident["data"]!=IDENT_EXPECTED:
            raise ProbeError("P300 20C2 identity control failed.")
        log("P300_IDENTITY_CONTROL=PASS")

        # Repeat the already proven minimal request three times to establish stability.
        id_values=[]
        for repeat in range(1,4):
            result=wire.transact(TARGET_FRAMES[(0x0001,1)])
            id_values.append(result)
            log(f"REPEAT id_prog1 n={repeat} status={result['status']} data={result['data'].hex() if result['data'] else '-'}")

        for name,address,length in TARGETS:
            if (address,length)==(0x0001,1):
                continue
            result=wire.transact(TARGET_FRAMES[(address,length)])
            results.append((name,address,length,result))
            log(
                f"BLOCK {name} address=0x{address:04x} len={length} "
                f"status={result['status']} data={result['data'].hex() if result['data'] else '-'}"
            )

        results.insert(0,("id_prog1",0x0001,1,id_values[-1]))
        stable_id = all(r["status"]=="SUCCESS" and r["data"]==id_values[0]["data"] for r in id_values)
        log("ID_REPEAT_STABLE=" + ("yes" if stable_id else "no"))

        wire.leave_detection()
    except BaseException as exc:
        failures.append(str(exc) or type(exc).__name__); log("PROBE FAILED: " + failures[-1])
    finally:
        previous={sig:signal.signal(sig,signal.SIG_IGN) for sig in ABORT_SIGNALS}
        try:
            if wire is not None:
                try:
                    wire.port.close(); log("Serial port closed.")
                except Exception as exc:
                    failures.append("Serial close failed: " + str(exc))
            for unit in reversed(changed):
                try:
                    if unit==SPLITTER: restart_epoch=time.time()
                    log("Restoring running state: " + unit); services.start(unit)
                    log("SERVICE_RESTORED=" + unit + " running")
                except Exception as exc:
                    failures.append("Restart failed: " + unit + ": " + str(exc))
        finally:
            for sig,handler in previous.items(): signal.signal(sig,handler)

    if restart_epoch is not None and SPLITTER in changed:
        try:
            journal=services.journal_since(restart_epoch-0.25)
            restored="VS1/KW protocol initialized" in journal
            log("VS1_RESTORED=" + ("yes" if restored else "NOT_CONFIRMED"))
            if not restored: failures.append("Restored splitter did not show VS1/KW protocol initialized.")
        except Exception as exc:
            failures.append("VS1 restore verification failed: " + str(exc))

    success_count=sum(1 for _,_,_,r in results if r["status"]=="SUCCESS")
    error_count=sum(1 for _,_,_,r in results if r["status"]=="ERROR_MESSAGE")
    log(f"KMBUS_EEPROM_SUCCESS_COUNT={success_count}/{len(TARGETS)}")
    log(f"KMBUS_EEPROM_ERROR_COUNT={error_count}/{len(TARGETS)}")
    completed=len(results)==len(TARGETS) and not failures
    log("EXECUTION_RESULT=" + ("PASS" if completed else "FAIL"))
    for failure in failures: log("ERROR: " + failure)
    return 0 if completed else 1


def self_test() -> int:
    import unittest
    class Tests(unittest.TestCase):
        def test_identity_frame(self):
            self.assertEqual(CONTROL_FRAME.hex(),"4105000100f80806")
        def test_known_minimal_frame(self):
            self.assertEqual(TARGET_FRAMES[(0x0001,1)].hex(),"410b004300010103000000010155")
        def test_fault_block_frame_is_read(self):
            frame=TARGET_FRAMES[(0x00A0,10)]
            self.assertEqual(frame[3],0x43)
            self.assertEqual(frame[4:6],bytes.fromhex("00a0"))
            self.assertEqual(frame[6],10)
            self.assertEqual(frame[7:13],PREFIX)
        def test_unknown_target_blocked(self):
            with self.assertRaises(ValueError):
                request_frame(0x43,0x1234,1,PREFIX)
        def test_write_blocked(self):
            with self.assertRaises(ValueError):
                request_frame(0x44,0x0001,1,PREFIX)

    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    if result.wasSuccessful():
        print("KMBUS_EEPROM_MAP_PROBE_TESTS=5/5")
        return 0
    return 1


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group()
    group.add_argument("--execute",action="store_true")
    group.add_argument("--self-test",action="store_true")
    args=parser.parse_args()

    if args.self_test: return self_test()
    if not args.execute:
        print(
            f"WB2A source-derived KMBUS EEPROM map probe {VERSION}: plan only; no action without --execute.\n"
            "Uses only exact v6 source-defined 0x43 block shapes with the already proven prefix."
        )
        return 0
    if os.geteuid()!=0:
        print("ERROR: --execute requires root.",file=sys.stderr); return 1

    log=None; lock_fd=None; previous={}
    try:
        import serial
        port=read_settings(SETTINGS)
        if not stat.S_ISCHR(os.stat(port).st_mode):
            raise ProbeError("Configured port is not a character device.")
        lock_fd=os.open(LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        fcntl.flock(lock_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        stamp=dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        log=Log(Path("/root")/f"wb2a-kmbus-eeprom-map-{stamp}-{os.getpid()}.log")
        log(f"WB2A source-derived KMBUS EEPROM map probe {VERSION}; LOG={log.path}")
        log(f"Configured port: {port}; resolved: {os.path.realpath(port)}; 4800 8E2.")
        log("PREFIX=030000000101; LOCAL_SEMANTICS=UNPROVEN; READ_ONLY=yes")

        def abort(signum,_frame):
            raise ProbeError("Interrupted by signal " + str(signum) + "; entering cleanup.")
        previous={sig:signal.signal(sig,abort) for sig in ABORT_SIGNALS}
        return run_guarded(Services(),lambda:open_port(port,serial),log)
    except Exception as exc:
        if log: log("ERROR: " + str(exc))
        else: print("ERROR: " + str(exc),file=sys.stderr)
        return 1
    finally:
        for sig,handler in previous.items(): signal.signal(sig,handler)
        if lock_fd is not None: os.close(lock_fd)
        if log:
            log("LOG=" + str(log.path)); log.close()


if __name__=="__main__":
    raise SystemExit(main())
