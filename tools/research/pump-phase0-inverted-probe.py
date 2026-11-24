#!/opt/optolink/venv/bin/python
"""Phase 0: supervised feasibility test of the INVERTED E7 RAM override.

Idea: E7 (0x27E7) is persistently 100 %. The probe holds the volatile E7
working copy at physical RAM 0x20A5 at LOW (30) by re-writing it whenever the
firmware reloads 100, then stops and measures how fast the firmware returns to
100 on its own (the fail-safe path).

Strict allowlists: only the reads below, Physical_WRITE only 0x20A5 in {30,100},
Virtual_WRITE only E7 in {30,100} (used only if E7 is found at 30). Inert
without --execute. Requires root (systemctl, serial port, probe lock).
"""
from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
import time

APP_DIR = "/opt/optolink"
sys.path.insert(0, APP_DIR)

RAM_BLOCK, RAM_E7 = 0x20A0, 0x20A5
LOW, HIGH = 30, 100
READS = {
    "ident": (0x01, 0x00F8, 2),
    "sw": (0x01, 0x778C, 2),
    "e6": (0x01, 0x27E6, 1),
    "e7": (0x01, 0x27E7, 1),
    "ww": (0x01, 0x650A, 1),
    "gfa": (0x01, 0x55D3, 11),
    "fault": (0x01, 0x5738, 1),
    "alarm": (0x01, 0xA132, 29),
    "valve": (0x01, 0x0A10, 1),
    "pump": (0x01, 0x7660, 2),
    "a1": (0x01, 0x7663, 2),
    "a3c": (0x01, 0x0A3C, 1),
    "kessel": (0x01, 0x0810, 2),
    "ram": (0x03, RAM_BLOCK, 32),
    "cand_0f20": (0x03, 0x0F20, 32),
    "cand_1c60": (0x03, 0x1C60, 32),
}
ALLOWED_READ = set(READS.values())
LOCK = "/run/lock/physical-ram-snapshot.lock"
SPLITTER = "optolink-splitter.service"
WRITERS = (
    "optolink-schedule-manager.service",
    "optolink-party-emulator.service",
    "optolink-service-programs.service",
    "optolink-room-control.service",
)
HOLD_SECONDS = 180.0
RELEASE_SECONDS = 20.0
OUT = f"/tmp/pump-phase0-{time.strftime('%Y%m%dT%H%M%S')}.jsonl"
T0 = time.monotonic()


def cs(b: bytes) -> int:
    return sum(b[1:]) & 0xFF


def read_frame(fc: int, addr: int, n: int) -> bytes:
    if (fc, addr, n) not in ALLOWED_READ:
        raise RuntimeError(f"blocked read {fc:02X}/{addr:04X}/{n}")
    b = bytes((0x41, 0x05, 0x00, fc, addr >> 8, addr & 0xFF, n))
    return b + bytes((cs(b),))


def pwrite_frame(value: int) -> bytes:
    if value not in (LOW, HIGH):
        raise RuntimeError(f"blocked RAM value {value}")
    b = bytes((0x41, 0x06, 0x00, 0x04, RAM_E7 >> 8, RAM_E7 & 0xFF, 1, value))
    return b + bytes((cs(b),))


def vwrite_e7_frame(value: int) -> bytes:
    if value not in (LOW, HIGH):
        raise RuntimeError(f"blocked E7 value {value}")
    b = bytes((0x41, 0x06, 0x00, 0x02, 0x27, 0xE7, 1, value))
    return b + bytes((cs(b),))


def rec(fh, kind, **kw):
    kw.update(t=round(time.monotonic() - T0, 3), kind=kind)
    fh.write(json.dumps(kw) + "\n")
    fh.flush()


class Wire:
    def __init__(self, port):
        import serial
        self.s = serial.Serial(port=port, baudrate=4800, bytesize=8, parity="E",
                               stopbits=2, timeout=0.05, write_timeout=2, exclusive=True)

    def exact(self, n, timeout=3.0):
        end, out = time.monotonic() + timeout, bytearray()
        while len(out) < n and time.monotonic() < end:
            out.extend(self.s.read(n - len(out)))
        if len(out) != n:
            raise RuntimeError(f"serial timeout {len(out)}/{n}")
        return bytes(out)

    def send(self, d):
        if self.s.write(d) != len(d):
            raise RuntimeError("partial write")

    def enter(self):
        time.sleep(1.0)
        self.s.reset_input_buffer()
        self.send(b"\x04")
        end = time.monotonic() + 6
        while time.monotonic() < end:
            if self.s.read(1) == b"\x05":
                break
        else:
            raise RuntimeError("no 0x05 sync")
        self.s.reset_input_buffer()
        self.send(b"\x16\x00\x00")
        end = time.monotonic() + 4
        while time.monotonic() < end:
            b = self.s.read(1)
            if b == b"\x06":
                return
            if b and b != b"\x05":
                raise RuntimeError(f"bad P300 init byte {b.hex()}")
        raise RuntimeError("P300 init timeout")

    def leave(self):
        try:
            self.send(b"\x04")
        except Exception:
            pass

    def _xfer(self, req, fc, addr):
        self.send(req)
        first = self.exact(1)
        if first != b"\x06":
            raise RuntimeError(f"no ACK ({first.hex()}) for fc {fc:02X} {addr:04X}")
        head = self.exact(2)
        if head[0] != 0x41 or not 1 <= head[1] <= 64:
            raise RuntimeError("bad header")
        msg = head + self.exact(head[1] + 1)
        if cs(msg[:-1]) != msg[-1]:
            raise RuntimeError("bad checksum")
        self.send(b"\x06")
        if msg[3] != fc or int.from_bytes(msg[4:6], "big") != addr:
            raise RuntimeError("fc/address mismatch")
        if (msg[2] & 0x0F) != 1:
            raise RuntimeError(f"controller error fc {fc:02X} {addr:04X}: {msg.hex()}")
        return msg[7:-1]

    def read(self, name):
        fc, addr, n = READS[name]
        data = self._xfer(read_frame(fc, addr, n), fc, addr)
        if len(data) != n:
            raise RuntimeError(f"short read {name}")
        return data

    def ram(self):
        return self.read("ram")[RAM_E7 - RAM_BLOCK]

    def pwrite(self, v):
        self._xfer(pwrite_frame(v), 0x04, RAM_E7)

    def vwrite_e7(self, v):
        self._xfer(vwrite_e7_frame(v), 0x02, 0x27E7)


def state(w):
    g = w.read("gfa")
    return dict(ww=w.read("ww")[0], flame=bool(g[5] & 0x20), lockout=bool(g[5] & 0x40),
                gg1=g[5:8].hex(), valve=w.read("valve")[0])


def fault_clear(w):
    return w.read("fault")[0] == 0 and w.read("alarm")[28] == 0


def runtime(w):
    p, a1 = w.read("pump"), w.read("a1")
    return dict(pump_on=p[0], pump=p[1], a1_on=a1[0], a1=a1[1], a3c=w.read("a3c")[0])


def systemctl(action, unit):
    r = subprocess.run(["systemctl", action, unit], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"systemctl {action} {unit}: {r.stderr.strip()}")


def is_active(unit):
    return subprocess.run(["systemctl", "is-active", "--quiet", unit]).returncode == 0


def main():
    if "--self-test" in sys.argv:
        assert pwrite_frame(30).hex() == "4106000420a5011eee"
        assert pwrite_frame(100).hex() == "4106000420a5016434"
        assert read_frame(0x03, 0x20A0, 32).hex() == "4105000320a020e8"
        assert vwrite_e7_frame(100).hex()[:14] == "41060002" + "27e7" + "01"
        for bad in (lambda: pwrite_frame(50), lambda: vwrite_e7_frame(0),
                    lambda: read_frame(0x03, 0x20C0, 32)):
            try:
                bad()
                raise AssertionError("allowlist failed")
            except RuntimeError:
                pass
        print("SELFTEST=PASS")
        return 0
    if "--execute" not in sys.argv:
        print("inert: pass --execute to run the supervised hardware test")
        return 0
    if os.geteuid() != 0:
        raise SystemExit("must run as root")

    from c_settings_adapter import settings  # type: ignore
    port = settings.port_optolink
    fh = open(OUT, "w")
    print(f"log {OUT}", flush=True)
    lock = os.open(LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if is_active("optolink-pump-override.service"):
        raise SystemExit("legacy pump-override service active")
    was_active = {u: is_active(u) for u in (SPLITTER,) + WRITERS}
    rec(fh, "services_before", **was_active)
    if not was_active[SPLITTER]:
        raise SystemExit("splitter not active")
    stopped = []
    w = None
    e7_found = None
    e7_written = False
    summary = {}
    try:
        for u in WRITERS + (SPLITTER,):
            if is_active(u):
                systemctl("stop", u)
                stopped.append(u)
        rec(fh, "stopped", units=stopped)
        w = Wire(port)
        w.enter()
        ident, sw = w.read("ident"), w.read("sw")
        rec(fh, "ident", ident=ident.hex(), sw=sw.hex())
        if ident != bytes.fromhex("20c2"):
            raise RuntimeError(f"identity {ident.hex()}")
        if not fault_clear(w):
            raise RuntimeError("fault/alarm active")
        st = state(w)
        e6, e7_found, ram0 = w.read("e6")[0], w.read("e7")[0], w.ram()
        rec(fh, "precheck", e6=e6, e7=e7_found, ram=ram0, **st, **runtime(w))
        if st["ww"] != 0 or st["flame"] or st["lockout"]:
            raise RuntimeError(f"unsafe window {st}")
        if e6 != 100 or e7_found not in (LOW, HIGH):
            raise RuntimeError(f"unexpected e6={e6} e7={e7_found}")
        if e7_found == LOW:
            w.vwrite_e7(HIGH)
            e7_written = True
            if w.read("e7")[0] != HIGH:
                raise RuntimeError("E7 readback after write != 100")
            rec(fh, "e7_written", value=HIGH)
        # baseline at E7=100 for 8 s
        end = time.monotonic() + 8
        while time.monotonic() < end:
            rec(fh, "baseline", ram=w.ram(), **runtime(w))
            time.sleep(0.3)
        # inverted hold
        repairs, writes, gaps = [], 0, []
        w.pwrite(LOW)
        writes += 1
        last_write = time.monotonic()
        hold_end = time.monotonic() + HOLD_SECONDS
        rot, next_state, next_fault, ended = 0, time.monotonic() + 5, time.monotonic() + 15, "time"
        while time.monotonic() < hold_end:
            ram = w.ram()
            if ram == HIGH:
                td = time.monotonic()
                w.pwrite(LOW)
                writes += 1
                repairs.append(round(td - T0, 3))
                gaps.append(round(td - last_write, 3))
                last_write = time.monotonic()
                rec(fh, "repair", since_last_write=gaps[-1])
            elif ram != LOW:
                raise RuntimeError(f"unexpected RAM {ram}")
            rot += 1
            if rot % 2 == 0:
                rec(fh, "hold", ram=ram, **runtime(w))
            now = time.monotonic()
            if now >= next_state:
                st = state(w)
                rec(fh, "hold_state", **st)
                if st["ww"] or st["flame"] or st["lockout"]:
                    ended = f"stopped_by_state {st}"
                    break
                next_state = now + 5
            if now >= next_fault:
                if not fault_clear(w):
                    ended = "fault"
                    break
                next_fault = now + 15
        summary["hold"] = dict(ended=ended, writes=writes, repairs=len(repairs),
                               repair_interval_s=gaps)
        # release: stop writing, measure the fail-safe return
        t_rel = time.monotonic()
        back_ram = back_a3c = back_pump = None
        while time.monotonic() - t_rel < RELEASE_SECONDS:
            r = w.ram()
            rt = runtime(w)
            dt = round(time.monotonic() - t_rel, 3)
            rec(fh, "release", ram=r, dt=dt, **rt)
            if back_ram is None and r == HIGH:
                back_ram = dt
            if back_a3c is None and rt["a3c"] == HIGH:
                back_a3c = dt
            if back_pump is None and rt["pump"] >= 98:
                back_pump = dt
        summary["release"] = dict(ram_100_after_s=back_ram, a3c_100_after_s=back_a3c,
                                  pump_ge98_after_s=back_pump,
                                  since_last_write_s=round(t_rel - last_write, 3))
        for c in ("cand_0f20", "cand_1c60"):
            summary[c] = w.read(c).hex()
    except Exception as exc:
        summary["error"] = str(exc)
        print(f"ERROR {exc}", flush=True)
    finally:
        if w is not None:
            try:
                if e7_written:
                    w.vwrite_e7(LOW)
                    summary["e7_restored"] = w.read("e7")[0]
                e7_now = w.read("e7")[0]
                t = time.monotonic()
                while w.ram() != e7_now and time.monotonic() - t < 5:
                    time.sleep(0.2)
                if w.ram() != e7_now:
                    w.pwrite(e7_now if e7_now in (LOW, HIGH) else HIGH)
                summary["final"] = dict(e7=e7_now, ram=w.ram(), fault_clear=fault_clear(w), **runtime(w))
            except Exception as exc:
                summary["restore_error"] = str(exc)
            w.leave()
            try:
                w.s.close()
            except Exception:
                pass
        for u in (SPLITTER,) + tuple(x for x in WRITERS if x in stopped):
            if u in stopped:
                try:
                    systemctl("start", u)
                except Exception as exc:
                    summary.setdefault("service_errors", []).append(str(exc))
        summary["services_after"] = {u: is_active(u) for u in (SPLITTER,) + WRITERS}
        summary["e7_found"] = e7_found
        rec(fh, "summary", **summary)
        print("SUMMARY " + json.dumps(summary), flush=True)
        os.close(lock)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
