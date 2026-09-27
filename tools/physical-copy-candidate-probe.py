#!/opt/optolink/venv/bin/python
"""Fixed read-only probe for two ROM-to-RAM-shaped RAM tuples.

Candidate A: RAM 0x1DE5 = src3,dst3,count2.
Candidate B: RAM 0x1E6A = dst3,src3,count2.
No writes and no arbitrary address input.
"""
from __future__ import annotations
import argparse, fcntl, importlib.util, os, signal, time
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("physical_ram_snapshot",HERE/"physical-ram-snapshot.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

COUNT=16

def parse_a(d:bytes):
    o=0x1DE5-0x1DE0
    return (int.from_bytes(d[o:o+3],"little"),
            int.from_bytes(d[o+3:o+6],"little"),
            int.from_bytes(d[o+6:o+8],"little"))

def parse_b(d:bytes):
    o=0x1E6A-0x1E60
    return (int.from_bytes(d[o+3:o+6],"little"),
            int.from_bytes(d[o:o+3],"little"),
            int.from_bytes(d[o+6:o+8],"little"))
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--execute",action="store_true")
    ap.add_argument("--self-test",action="store_true")
    args=ap.parse_args()
    if args.self_test:
        a=bytes.fromhex("00"*5+"ab a2 0e 01 33 00 1d 00"+"00"*19)
        b=bytes.fromhex("00"*10+"05 07 00 7d b2 0f 07 00"+"00"*14)
        assert parse_a(a)==(0xEA2AB,0x3301,29)
        assert parse_b(b)==(0xFB27D,0x0705,7)
        print("SELFTEST=PASS"); return 0
    if not args.execute:
        print("plan only; use --execute for fixed read-only candidate probe"); return 0

    fd=os.open(m.LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    states={u:m.active(u) for u in (m.SCHEDULE,m.PARTY,m.SPLITTER)}
    if not states[m.SPLITTER]:
        raise m.ProbeError("splitter not running before probe")
    changed=[]; w=None
    previous={sig:signal.getsignal(sig) for sig in m.ABORT}
    for sig in m.ABORT:
        signal.signal(sig,lambda s,f: (_ for _ in ()).throw(m.ProbeError(f"signal {s}")))
    log=lambda s: print(time.strftime("%H:%M:%S"),s,flush=True)
    try:
        for unit in (m.SCHEDULE,m.PARTY,m.SPLITTER):
            if states[unit]:
                m.svc("stop",unit); changed.append(unit); log("STOPPED "+unit)
        w=m.Wire(m.read_port(),log); w.enter()
        ident=w.request(0x01,*m.IDENT)
        if ident["status"]!="SUCCESS" or ident["data"]!=bytes.fromhex("20 c2"):
            raise m.ProbeError("20C2 identity failed")
        base=m.monitor_snapshot(w)
        if base[0x5738]!=b"\x00" or base[0xA132][28]!=0:
            raise m.ProbeError("baseline active fault")

        seen_a={}; seen_b={}
        for n in range(COUNT):
            a=w.request(0x03,0x1DE0,32)["data"]
            b=w.request(0x03,0x1E60,32)["data"]
            ca=parse_a(a); cb=parse_b(b)
            seen_a[ca]=seen_a.get(ca,0)+1
            seen_b[cb]=seen_b.get(cb,0)+1
            log(f"COPY n={n:02d} A=src:{ca[0]:05x},dst:{ca[1]:05x},cnt:{ca[2]} "
                f"B=src:{cb[0]:05x},dst:{cb[1]:05x},cnt:{cb[2]}")
            if (n+1)%4==0: m.guard_current(w)
            time.sleep(0.08)
        log("A_UNIQUE="+str(seen_a))
        log("B_UNIQUE="+str(seen_b))
        after=m.monitor_snapshot(w)
        if after[0x5738]!=b"\x00" or after[0xA132][28]!=0:
            raise m.ProbeError("final active fault")
        for addr in m.HISTORY:
            if after[addr]!=base[addr]:
                raise m.ProbeError(f"fault history changed at 0x{addr:04x}")
        log("FAULT_GUARD=PASS")
        w.leave(); return 0
    finally:
        if w:
            try: w.close()
            except Exception: pass
        for unit in reversed(changed):
            try: m.svc("start",unit); log("RESTORED "+unit)
            except Exception as exc: log("RESTORE_ERROR "+str(exc))
        for sig,h in previous.items(): signal.signal(sig,h)
        os.close(fd)

if __name__=="__main__":
    raise SystemExit(main())