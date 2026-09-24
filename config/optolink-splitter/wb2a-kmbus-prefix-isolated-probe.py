#!/opt/optolink/venv/bin/python
"""Isolated-session PrefixRead discriminator for local KMBUS_EEPROM_READ 0x43.

Purpose
-------
Confirm the clean 0x0001/1 PrefixRead effect observed in the first P-N-P run:

  prefixed   -> 0x88
  no-prefix  -> 0x87
  prefixed   -> 0x88

The earlier comparison occurred inside one continuous P300 session. This helper
removes session carry-over as a confounder by opening a fresh P300 protocol
session before EVERY 0x43 request.

Balanced deterministic order:
  P, N, N, P, N, P, P, N

where:
  P = 0x43 / 0x0001 / len 1 / PrefixRead 03 00 00 00 01 01
  N = 0x43 / 0x0001 / len 1 / no extra bytes

A separate identity-only P300 session is performed first. Production remains
permanent VS1/KW. The helper pauses the single serial owner, performs read-only
tests only, then restores VS1/Party.

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
from collections import Counter

VERSION = "1.0.0"
SPLITTER = "optolink-splitter.service"
PARTY = "optolink-party-emulator.service"
SETTINGS = Path("/opt/optolink/settings_ini.py")
LOCK = "/run/lock/wb2a-kmbus-prefix-isolated-probe.lock"
ABORT_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)

IDENT_EXPECTED = bytes.fromhex("20 c2 00 03 00 00 01 03")
PREFIX = bytes.fromhex("03 00 00 00 01 01")
ORDER = ("P", "N", "N", "P", "N", "P", "P", "N")
ADDRESS = 0x0001
LENGTH = 1


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
        raise ValueError("P300 body must start with 0x41.")
    return sum(body[1:]) & 0xFF


def request_frame(function: int, address: int, length: int, extra: bytes = b"") -> bytes:
    if function == 0x01:
        if (address, length, extra) != (0x00F8, 8, b""):
            raise ValueError("0x01 allowed only for identity control.")
    elif function == 0x43:
        if (address, length) != (ADDRESS, LENGTH):
            raise ValueError("0x43 allowed only for 0x0001/1.")
        if extra not in (b"", PREFIX):
            raise ValueError("Only exact PrefixRead or empty extra data allowed.")
    else:
        raise ValueError("Only read functions 0x01 and 0x43 are allowed.")

    body = bytes(
        (0x41, 5 + len(extra), 0x00, function, address >> 8, address & 0xFF, length)
    ) + extra
    return body + bytes((checksum(body),))


CONTROL_FRAME = request_frame(0x01, 0x00F8, 8)
P_FRAME = request_frame(0x43, ADDRESS, LENGTH, PREFIX)
N_FRAME = request_frame(0x43, ADDRESS, LENGTH, b"")
ALLOWED_TX = frozenset({b"\x04", b"\x16\x00\x00", b"\x06", CONTROL_FRAME, P_FRAME, N_FRAME})


def decode_response(msg: bytes) -> dict:
    if len(msg) < 4 or msg[0] != 0x41 or len(msg) != msg[1] + 3:
        raise ProbeError("Bad P300 response length: " + msg.hex(" "))
    if checksum(msg[:-1]) != msg[-1]:
        raise ProbeError("Bad P300 response checksum: " + msg.hex(" "))

    mtype = msg[2] & 0x0F
    status = "SUCCESS" if mtype == 0x01 else ("ERROR_MESSAGE" if mtype == 0x03 else f"MESSAGE_TYPE_{mtype:02X}")
    return {
        "status": status,
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
            raise ProbeError("TX blocked by read-only allowlist: " + data.hex(" "))
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
            raise ProbeError(f"Unexpected control byte {b.hex()}.")
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

    def leave_detection(self):
        self.send(b"\x04")
        self.log("P300_SESSION_ENDED=yes")

    def transact(self, frame: bytes) -> dict:
        self.send(frame)
        first = self.exact(1)
        if first == b"\x15":
            return {"status":"NACK","command":None,"address":None,"length":None,"data":b"","frame":"15"}
        if first != b"\x06":
            raise ProbeError("Expected ACK/NACK, got " + first.hex(" "))

        hdr = self.exact(2)
        if hdr[0] != 0x41 or not 1 <= hdr[1] <= 64:
            raise ProbeError("Bad response header: " + hdr.hex(" "))
        msg = hdr + self.exact(hdr[1] + 1)
        r = decode_response(msg)
        self.log(
            f"P300_RESULT status={r['status']} command="
            f"{'-' if r['command'] is None else f'0x{r['command']:02x}'} "
            f"address={'-' if r['address'] is None else f'0x{r['address']:04x}'} "
            f"len={r['length']} data={r['data'].hex() if r['data'] else '-'} "
            f"frame={r['frame']}"
        )
        self.send(b"\x06")
        return r


class Services:
    @staticmethod
    def cmd(*args, timeout=25):
        p = subprocess.run(
            ["systemctl","--no-pager","--no-ask-password",*args],
            capture_output=True,text=True,timeout=timeout,check=False
        )
        if p.returncode:
            raise ProbeError("systemctl failed: " + p.stderr.strip())
        return p.stdout

    def state(self, unit):
        out = self.cmd("show",unit,"-p","LoadState","-p","ActiveState","-p","SubState")
        return dict(line.split("=",1) for line in out.splitlines() if "=" in line)

    def stop(self, unit):
        self.cmd("stop",unit)
        if self.state(unit).get("ActiveState") != "inactive":
            raise ProbeError("Service did not stop: " + unit)

    def start(self, unit):
        self.cmd("start",unit)
        time.sleep(2)
        st = self.state(unit)
        if st.get("ActiveState")!="active" or st.get("SubState")!="running":
            raise ProbeError("Service did not stay running: " + unit)

    @staticmethod
    def journal_since(epoch):
        p = subprocess.run(
            ["journalctl","-u",SPLITTER,"--since","@"+str(int(epoch)),
             "--no-pager","-o","cat"],
            capture_output=True,text=True,timeout=20,check=False
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
            fds = list((proc/"fd").iterdir())
        except (FileNotFoundError,PermissionError):
            continue
        for fd in fds:
            try:
                st = fd.stat()
            except (FileNotFoundError,PermissionError):
                continue
            if stat.S_ISCHR(st.st_mode) and st.st_rdev == dev.st_rdev:
                owners.append(proc.name)
                break
    if owners:
        raise ProbeError("Serial port still open by PID(s): " + ",".join(owners))


def open_port(port, serial):
    check_port_owners(port)
    s = serial.Serial(
        port=port, baudrate=4800, bytesize=8, parity="E", stopbits=2,
        timeout=0.05, write_timeout=2, xonxoff=False, rtscts=False,
        dsrdtr=False, exclusive=True
    )
    try:
        fcntl.ioctl(s.fileno(), termios.TIOCEXCL)
        check_port_owners(port)
    except BaseException:
        s.close()
        raise
    return s


def validate_success(result: dict, expected_function: int, address: int, length: int):
    if (
        result["status"] != "SUCCESS"
        or result["command"] != expected_function
        or result["address"] != address
        or result["length"] != length
        or len(result["data"]) != length
    ):
        raise ProbeError(
            f"Unexpected result for function 0x{expected_function:02x} "
            f"address=0x{address:04x}: {result}"
        )


def one_fresh_session(wire: Wire, frame: bytes, label: str) -> dict:
    wire.enter_p300()
    try:
        r = wire.transact(frame)
        validate_success(r, 0x43, ADDRESS, LENGTH)
        wire.log(f"ISOLATED_RESULT label={label} data={r['data'].hex()}")
        return r
    finally:
        wire.leave_detection()
        time.sleep(0.15)


def run_guarded(services, opener, log):
    split = services.state(SPLITTER)
    if (split.get("LoadState"),split.get("ActiveState"),split.get("SubState")) != ("loaded","active","running"):
        raise ProbeError("Require running splitter.")
    party = services.state(PARTY)
    party_active = party.get("LoadState")=="loaded" and party.get("ActiveState")=="active"

    changed=[]; wire=None; failures=[]; observations=[]; restart_epoch=None
    try:
        for unit in ([PARTY] if party_active else []) + [SPLITTER]:
            changed.append(unit)
            log("Stopping " + unit)
            services.stop(unit)

        wire = Wire(opener(), log)

        # Separate identity-only session so no test result shares its P300 session.
        wire.enter_p300()
        ident = wire.transact(CONTROL_FRAME)
        validate_success(ident, 0x01, 0x00F8, 8)
        if ident["data"] != IDENT_EXPECTED:
            raise ProbeError("20C2 identity mismatch: " + ident["data"].hex())
        log("P300_IDENTITY_CONTROL=PASS")
        wire.leave_detection()
        time.sleep(0.15)

        for index, label in enumerate(ORDER, 1):
            test_frame = P_FRAME if label == "P" else N_FRAME
            result = one_fresh_session(wire, test_frame, label)
            observations.append((label, result["data"]))
            log(f"TRIAL n={index} label={label} data={result['data'].hex()}")

    except BaseException as exc:
        failures.append(str(exc) or type(exc).__name__)
        log("PROBE FAILED: " + failures[-1])
    finally:
        previous={sig:signal.signal(sig,signal.SIG_IGN) for sig in ABORT_SIGNALS}
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
                        restart_epoch=time.time()
                    log("Restoring running state: " + unit)
                    services.start(unit)
                    log("SERVICE_RESTORED=" + unit + " running")
                except Exception as exc:
                    failures.append("Restart failed: " + unit + ": " + str(exc))
        finally:
            for sig,h in previous.items():
                signal.signal(sig,h)

    if restart_epoch is not None and SPLITTER in changed:
        try:
            restored = "VS1/KW protocol initialized" in services.journal_since(restart_epoch-0.25)
            log("VS1_RESTORED=" + ("yes" if restored else "NOT_CONFIRMED"))
            if not restored:
                failures.append("VS1 restore not confirmed.")
        except Exception as exc:
            failures.append("VS1 verification failed: " + str(exc))

    p_values=[d.hex() for label,d in observations if label=="P"]
    n_values=[d.hex() for label,d in observations if label=="N"]
    p_counts=Counter(p_values)
    n_counts=Counter(n_values)
    log("P_VALUES=" + ",".join(p_values))
    log("N_VALUES=" + ",".join(n_values))
    log("P_COUNTS=" + ",".join(f"{k}:{v}" for k,v in sorted(p_counts.items())))
    log("N_COUNTS=" + ",".join(f"{k}:{v}" for k,v in sorted(n_counts.items())))

    if len(p_values)==4 and len(n_values)==4:
        if len(p_counts)==1 and len(n_counts)==1 and set(p_counts) != set(n_counts):
            classification="ISOLATED_PREFIX_EFFECT_REPRODUCED"
        elif p_counts == n_counts:
            classification="NO_ISOLATED_PREFIX_EFFECT"
        else:
            classification="ISOLATED_DYNAMIC_OR_MIXED"
    else:
        classification="INCOMPLETE"

    log("CLASSIFICATION=" + classification)
    completed=len(observations)==len(ORDER) and not failures
    log("EXECUTION_RESULT=" + ("PASS" if completed else "FAIL"))
    for e in failures:
        log("ERROR: " + e)
    return 0 if completed else 1


def self_test():
    import unittest

    class T(unittest.TestCase):
        def test_control(self):
            self.assertEqual(CONTROL_FRAME.hex(),"4105000100f80806")

        def test_prefixed(self):
            self.assertEqual(P_FRAME.hex(),"410b004300010103000000010155")

        def test_unprefixed(self):
            self.assertEqual(N_FRAME.hex(),"410500430001014a")

        def test_balanced_order(self):
            self.assertEqual(ORDER.count("P"),4)
            self.assertEqual(ORDER.count("N"),4)

        def test_write_blocked(self):
            with self.assertRaises(ValueError):
                request_frame(0x44,0x0001,1,b"")

    result=unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(T)
    )
    if result.wasSuccessful():
        print("KMBUS_PREFIX_ISOLATED_PROBE_TESTS=5/5")
        return 0
    return 1


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    g=ap.add_mutually_exclusive_group()
    g.add_argument("--execute",action="store_true")
    g.add_argument("--self-test",action="store_true")
    args=ap.parse_args()

    if args.self_test:
        return self_test()
    if not args.execute:
        print(
            f"WB2A isolated-session PrefixRead probe {VERSION}: plan only; "
            "no action without --execute."
        )
        return 0
    if os.geteuid()!=0:
        print("ERROR: --execute requires root.",file=sys.stderr)
        return 1

    log=None; lock_fd=None; previous={}
    try:
        import serial
        port=read_settings(SETTINGS)
        lock_fd=os.open(LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        fcntl.flock(lock_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)

        stamp=dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        log=Log(Path("/root")/f"wb2a-kmbus-prefix-isolated-{stamp}-{os.getpid()}.log")
        log(f"WB2A isolated-session PrefixRead probe {VERSION}; LOG={log.path}")
        log(f"Configured port: {port}; resolved: {os.path.realpath(port)}; 4800 8E2.")
        log("READ_ONLY=yes; ADDRESS=0x0001; LEN=1; PREFIX=030000000101")
        log("ORDER=" + "".join(ORDER) + "; FRESH_P300_SESSION_PER_TRIAL=yes")

        def abort(signum,_frame):
            raise ProbeError("Interrupted by signal " + str(signum))

        previous={sig:signal.signal(sig,abort) for sig in ABORT_SIGNALS}
        return run_guarded(Services(),lambda:open_port(port,serial),log)

    except Exception as exc:
        if log:
            log("ERROR: " + str(exc))
        else:
            print("ERROR: " + str(exc),file=sys.stderr)
        return 1
    finally:
        for sig,h in previous.items():
            signal.signal(sig,h)
        if lock_fd is not None:
            os.close(lock_fd)
        if log:
            log("LOG=" + str(log.path))
            log.close()


if __name__=="__main__":
    raise SystemExit(main())
