#!/opt/optolink/venv/bin/python
"""Bounded read-only probe for the mapped Physical_READ communication descriptors.

Fixed targets only: 0x18F8/32 and 0x1A70/32. No write path and no arbitrary address input.
"""
from __future__ import annotations
import argparse, fcntl, importlib.util, os, signal, time
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("physical_ram_snapshot",HERE/"physical-ram-snapshot.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

TARGETS=(0x18F8,0x1A70)
COUNT=16

def u32(d:bytes,off:int)->int:
    return int.from_bytes(d[off:off+4],"little")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--execute",action="store_true")
    ap.add_argument("--self-test",action="store_true")
    args=ap.parse_args()
    if args.self_test:
        for a in TARGETS:
            assert m.frame(0x03,a,m.CHUNK)[3]==0x03
        sample=bytes.fromhex("00"*13+"28 5c 0f 00"+"00"*15)
        assert u32(sample,13)==0x0F5C28
        print("SELFTEST=PASS"); return 0
    if not args.execute:
        print("plan only; use --execute for fixed read-only descriptor probe"); return 0

    fd=os.open(m.LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    log=lambda s: print(time.strftime("%H:%M:%S"),s,flush=True)
    states={u:m.active(u) for u in (m.SCHEDULE,m.PARTY,m.SPLITTER)}
    if not states[m.SPLITTER]: raise m.ProbeError("splitter not running before probe")
    changed=[]; w=None
    prev={sig:signal.getsignal(sig) for sig in m.ABORT}
    for sig in m.ABORT:
        signal.signal(sig,lambda s,f: (_ for _ in ()).throw(m.ProbeError(f"signal {s}")))
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
        ptr_rows=[]
        for n in range(COUNT):
            a=w.request(0x03,0x18F8,m.CHUNK)["data"]
            b=w.request(0x03,0x1A70,m.CHUNK)["data"]
            ptrs=(u32(a,0),u32(a,11),u32(a,22),u32(b,13))
            ptr_rows.append(ptrs)
            log("DESC n=%02d p0=%05x p1=%05x p2=%05x callback=%05x target16=%04x raw=%s" %
                (n,*ptrs,int.from_bytes(b[9:11],"little"),b.hex()))
            if (n+1)%4==0: m.guard_current(w)
            time.sleep(0.08)

        cols=list(zip(*ptr_rows))
        log("POINTER_STABILITY="+",".join("stable" if len(set(c))==1 else "varying" for c in cols))
        after=m.monitor_snapshot(w)
        if after[0x5738]!=b"\x00" or after[0xA132][28]!=0:
            raise m.ProbeError("final active fault")
        for a in m.HISTORY:
            if after[a]!=base[a]: raise m.ProbeError(f"fault history changed at 0x{a:04x}")
        log("FAULT_GUARD=PASS")
        w.leave(); return 0
    finally:
        if w:
            try: w.close()
            except Exception: pass
        for unit in reversed(changed):
            try: m.svc("start",unit); log("RESTORED "+unit)
            except Exception as exc: log("RESTORE_ERROR "+str(exc))
        for sig,h in prev.items(): signal.signal(sig,h)
        os.close(fd)

if __name__=="__main__":
    raise SystemExit(main())