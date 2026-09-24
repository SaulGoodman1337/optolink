#!/opt/optolink/venv/bin/python
"""Read-only PrefixRead A/B discriminator for KMBUS_EEPROM_READ 0x43.

Purpose:
  Determine whether the six source-derived PrefixRead bytes
  03 00 00 00 01 01 materially affect the local 0x43 transaction.

For each of four fixed source-derived address/length pairs the helper sends:
  P = prefixed 0x43 request
  N = otherwise identical 0x43 request without PrefixRead bytes
  P = prefixed 0x43 request again

P-N-P controls for short-term drift while keeping the experiment bounded.

Production remains permanent VS1/KW. The helper temporarily pauses the single
serial owner, initializes P300, performs only read operations, then restores
VS1/Party. No write function is implemented.
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
LOCK = "/run/lock/wb2a-kmbus-prefix-ab-probe.lock"
ABORT_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)

IDENT_EXPECTED = bytes.fromhex("20 c2 00 03 00 00 01 03")
PREFIX = bytes.fromhex("03 00 00 00 01 01")
TARGETS = (
    ("low_id", 0x0001, 1),
    ("low_parameter_block", 0x000A, 5),
    ("repetition_block", 0x0078, 8),
    ("fault_code_block", 0x00A0, 10),
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
                values[target.id] = ast.literal_eval(node.value)

    if values.get("vs1protocol") is not True:
        raise ProbeError("Require permanent production vs1protocol=True.")
    if values.get("port_vitoconnect") is not None:
        raise ProbeError("Require port_vitoconnect=None.")
    port = values.get("port_optolink")
    if not isinstance(port, str) or not port.startswith("/dev/"):
        raise ProbeError("Require literal local /dev/ port_optolink.")
    return port


def checksum(body: bytes) -> int:
    return sum(body[1:]) & 0xFF


def frame(function: int, address: int, length: int, extra: bytes = b"") -> bytes:
    if function == 0x01:
        if (address, length, extra) != (0x00F8, 8, b""):
            raise ValueError("0x01 allowed only for identity control.")
    elif function == 0x43:
        if (address, length) not in {(a, l) for _, a, l in TARGETS}:
            raise ValueError("0x43 address/length outside fixed allowlist.")
        if extra not in (b"", PREFIX):
            raise ValueError("Only empty extra data or exact source PrefixRead allowed.")
    else:
        raise ValueError("Only read functions 0x01 and 0x43 are allowed.")

    body = bytes((0x41, 5 + len(extra), 0x00, function,
                  address >> 8, address & 0xFF, length)) + extra
    return body + bytes((checksum(body),))


CONTROL = frame(0x01, 0x00F8, 8)
ALLOWED_FRAMES = {CONTROL}
for _, a, l in TARGETS:
    ALLOWED_FRAMES.add(frame(0x43, a, l, b""))
    ALLOWED_FRAMES.add(frame(0x43, a, l, PREFIX))
ALLOWED_TX = frozenset({b"\x04", b"\x16\x00\x00", b"\x06"} | ALLOWED_FRAMES)


def decode_response(msg: bytes) -> dict:
    if len(msg) < 4 or msg[0] != 0x41 or len(msg) != msg[1] + 3:
        raise ProbeError("Bad P300 response length: " + msg.hex(" "))
    if checksum(msg[:-1]) != msg[-1]:
        raise ProbeError("Bad P300 response checksum: " + msg.hex(" "))
    mtype = msg[2] & 0x0F
    return {
        "status": "SUCCESS" if mtype == 1 else ("ERROR_MESSAGE" if mtype == 3 else f"MESSAGE_TYPE_{mtype:02X}"),
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
        raise ProbeError(f"Timeout waiting for {expected:02x}.")

    def enter_p300(self):
        if self.port.in_waiting:
            stale = self.port.read(self.port.in_waiting)
            self.log("RX stale/discard " + stale.hex(" "))
        self.send(b"\x04")
        self.control(0x05)
        self.send(b"\x16\x00\x00")
        self.control(0x06)
        self.log("P300_INITIALIZED=yes")

    def transact(self, tx: bytes) -> dict:
        self.send(tx)
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

    def leave(self):
        self.send(b"\x04")
        self.log("INTERFACE_LEFT_IN_DETECTION_STATE=yes")


class Services:
    @staticmethod
    def cmd(*args, timeout=25):
        p = subprocess.run(["systemctl","--no-pager","--no-ask-password",*args],
                           capture_output=True,text=True,timeout=timeout,check=False)
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
        st=self.state(unit)
        if st.get("ActiveState")!="active" or st.get("SubState")!="running":
            raise ProbeError("Service did not stay running: " + unit)

    @staticmethod
    def journal_since(epoch):
        p=subprocess.run(["journalctl","-u",SPLITTER,"--since","@"+str(int(epoch)),
                          "--no-pager","-o","cat"],capture_output=True,text=True,
                         timeout=20,check=False)
        if p.returncode:
            raise ProbeError("journalctl failed: " + p.stderr.strip())
        return p.stdout


def check_port_owners(port):
    dev=os.stat(port)
    owners=[]
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit() or int(proc.name)==os.getpid():
            continue
        try:
            fds=list((proc/"fd").iterdir())
        except (FileNotFoundError,PermissionError):
            continue
        for fd in fds:
            try:
                st=fd.stat()
            except (FileNotFoundError,PermissionError):
                continue
            if stat.S_ISCHR(st.st_mode) and st.st_rdev==dev.st_rdev:
                owners.append(proc.name); break
    if owners:
        raise ProbeError("Serial port still open by PID(s): " + ",".join(owners))


def open_port(port, serial):
    check_port_owners(port)
    s=serial.Serial(port=port,baudrate=4800,bytesize=8,parity="E",stopbits=2,
                    timeout=0.05,write_timeout=2,xonxoff=False,rtscts=False,
                    dsrdtr=False,exclusive=True)
    try:
        fcntl.ioctl(s.fileno(),termios.TIOCEXCL)
        check_port_owners(port)
    except BaseException:
        s.close(); raise
    return s


def classify(p1, n, p2):
    key=lambda r:(r["status"],r["data"])
    if key(p1)==key(p2)==key(n):
        return "NO_PREFIX_EFFECT_OBSERVED"
    if key(p1)==key(p2) and key(n)!=key(p1):
        return "PREFIX_EFFECT_OBSERVED"
    return "DYNAMIC_OR_INCONCLUSIVE"


def run_guarded(services, opener, log):
    split=services.state(SPLITTER)
    if (split.get("LoadState"),split.get("ActiveState"),split.get("SubState")) != ("loaded","active","running"):
        raise ProbeError("Require running splitter.")
    party=services.state(PARTY)
    party_active=party.get("LoadState")=="loaded" and party.get("ActiveState")=="active"

    changed=[]; wire=None; failures=[]; results=[]; restart_epoch=None
    try:
        for unit in ([PARTY] if party_active else [])+[SPLITTER]:
            changed.append(unit); log("Stopping "+unit); services.stop(unit)

        wire=Wire(opener(),log); wire.enter_p300()
        ident=wire.transact(CONTROL)
        if ident["status"]!="SUCCESS" or ident["command"]!=0x01 or ident["address"]!=0x00F8 or ident["data"]!=IDENT_EXPECTED:
            raise ProbeError("P300 identity control failed.")
        log("P300_IDENTITY_CONTROL=PASS")

        for name,a,l in TARGETS:
            p1=wire.transact(frame(0x43,a,l,PREFIX))
            time.sleep(0.20)
            n=wire.transact(frame(0x43,a,l,b""))
            time.sleep(0.20)
            p2=wire.transact(frame(0x43,a,l,PREFIX))
            cls=classify(p1,n,p2)
            results.append((name,a,l,p1,n,p2,cls))
            log(
                f"AB {name} address=0x{a:04x} len={l} "
                f"P1={p1['status']}:{p1['data'].hex()} "
                f"N={n['status']}:{n['data'].hex()} "
                f"P2={p2['status']}:{p2['data'].hex()} class={cls}"
            )
        wire.leave()
    except BaseException as exc:
        failures.append(str(exc) or type(exc).__name__); log("PROBE FAILED: "+failures[-1])
    finally:
        previous={sig:signal.signal(sig,signal.SIG_IGN) for sig in ABORT_SIGNALS}
        try:
            if wire is not None:
                try:
                    wire.port.close(); log("Serial port closed.")
                except Exception as exc:
                    failures.append("Serial close failed: "+str(exc))
            for unit in reversed(changed):
                try:
                    if unit==SPLITTER: restart_epoch=time.time()
                    log("Restoring running state: "+unit); services.start(unit)
                    log("SERVICE_RESTORED="+unit+" running")
                except Exception as exc:
                    failures.append("Restart failed: "+unit+": "+str(exc))
        finally:
            for sig,h in previous.items(): signal.signal(sig,h)

    if restart_epoch is not None and SPLITTER in changed:
        try:
            restored="VS1/KW protocol initialized" in services.journal_since(restart_epoch-0.25)
            log("VS1_RESTORED="+("yes" if restored else "NOT_CONFIRMED"))
            if not restored: failures.append("VS1 restore not confirmed.")
        except Exception as exc:
            failures.append("VS1 verification failed: "+str(exc))

    effect=sum(1 for *_,cls in results if cls=="PREFIX_EFFECT_OBSERVED")
    none=sum(1 for *_,cls in results if cls=="NO_PREFIX_EFFECT_OBSERVED")
    inc=sum(1 for *_,cls in results if cls=="DYNAMIC_OR_INCONCLUSIVE")
    log(f"PREFIX_EFFECT_COUNT={effect}")
    log(f"NO_PREFIX_EFFECT_COUNT={none}")
    log(f"INCONCLUSIVE_COUNT={inc}")
    completed=len(results)==len(TARGETS) and not failures
    log("EXECUTION_RESULT="+("PASS" if completed else "FAIL"))
    for e in failures: log("ERROR: "+e)
    return 0 if completed else 1


def self_test():
    import unittest
    class T(unittest.TestCase):
        def test_control(self):
            self.assertEqual(CONTROL.hex(),"4105000100f80806")
        def test_prefixed(self):
            self.assertEqual(frame(0x43,0x0001,1,PREFIX).hex(),"410b004300010103000000010155")
        def test_unprefixed(self):
            self.assertEqual(frame(0x43,0x0001,1,b"").hex(),"410500430001014a")
        def test_bad_extra(self):
            with self.assertRaises(ValueError):
                frame(0x43,0x0001,1,b"\x00")
        def test_write_blocked(self):
            with self.assertRaises(ValueError):
                frame(0x44,0x0001,1,b"")
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(T))
    if result.wasSuccessful():
        print("KMBUS_PREFIX_AB_PROBE_TESTS=5/5"); return 0
    return 1


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    g=ap.add_mutually_exclusive_group()
    g.add_argument("--execute",action="store_true")
    g.add_argument("--self-test",action="store_true")
    args=ap.parse_args()

    if args.self_test: return self_test()
    if not args.execute:
        print(f"WB2A KMBUS PrefixRead A/B probe {VERSION}: plan only; no action without --execute.")
        return 0
    if os.geteuid()!=0:
        print("ERROR: --execute requires root.",file=sys.stderr); return 1

    log=None; lock_fd=None; previous={}
    try:
        import serial
        port=read_settings(SETTINGS)
        lock_fd=os.open(LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        fcntl.flock(lock_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        stamp=dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        log=Log(Path("/root")/f"wb2a-kmbus-prefix-ab-{stamp}-{os.getpid()}.log")
        log(f"WB2A KMBUS PrefixRead A/B probe {VERSION}; LOG={log.path}")
        log(f"Configured port: {port}; resolved: {os.path.realpath(port)}; 4800 8E2.")
        log("READ_ONLY=yes; PREFIX=030000000101; ORDER=P-N-P")
        def abort(signum,_frame):
            raise ProbeError("Interrupted by signal "+str(signum))
        previous={sig:signal.signal(sig,abort) for sig in ABORT_SIGNALS}
        return run_guarded(Services(),lambda:open_port(port,serial),log)
    except Exception as exc:
        if log: log("ERROR: "+str(exc))
        else: print("ERROR: "+str(exc),file=sys.stderr)
        return 1
    finally:
        for sig,h in previous.items(): signal.signal(sig,h)
        if lock_fd is not None: os.close(lock_fd)
        if log:
            log("LOG="+str(log.path)); log.close()


if __name__=="__main__":
    raise SystemExit(main())
