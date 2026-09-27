#!/opt/optolink/venv/bin/python
"""Read-only probe of the Physical_READ/P300 communication-ring metadata.

Reads only 0x1a60/32 repeatedly after the normal 20C2 identity and fault guard.
No write function and no arbitrary address input.
"""
from __future__ import annotations
import argparse, fcntl, importlib.util, os, signal, time
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("physical_ram_snapshot",HERE/"physical-ram-snapshot.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
TARGET=0x1A60
COUNT=24

def word(data:bytes,absolute:int)->int:
    off=absolute-TARGET
    return int.from_bytes(data[off:off+2],"little")

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--execute",action="store_true"); ap.add_argument("--self-test",action="store_true")
    args=ap.parse_args()
    if args.self_test:
        f=m.frame(0x03,TARGET,m.CHUNK)
        assert f[:7]==bytes.fromhex("41 05 00 03 1a 60 20")
        assert word(bytes(range(32)),0x1A6E)==0x0F0E
        print("SELFTEST=PASS"); return 0
    if not args.execute:
        print("plan only; use --execute for the fixed read-only ring probe"); return 0
    lock_fd=os.open(m.LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600); fcntl.flock(lock_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    log=lambda s: print(time.strftime("%H:%M:%S"),s,flush=True)
    states={u:m.active(u) for u in (m.SCHEDULE,m.PARTY,m.SPLITTER)}
    if not states[m.SPLITTER]: raise m.ProbeError("splitter not running before ring probe")
    changed=[]; w=None; prev={sig:signal.getsignal(sig) for sig in m.ABORT}
    for sig in m.ABORT: signal.signal(sig,lambda s,f: (_ for _ in ()).throw(m.ProbeError(f"signal {s}")))
    try:
        for u in (m.SCHEDULE,m.PARTY,m.SPLITTER):
            if states[u]: m.svc("stop",u); changed.append(u); log("STOPPED "+u)
        w=m.Wire(m.read_port(),log); w.enter()
        ident=w.request(0x01,*m.IDENT)
        if ident["status"]!="SUCCESS" or ident["data"]!=bytes.fromhex("20 c2"): raise m.ProbeError("20C2 identity failed")
        base=m.monitor_snapshot(w)
        if base[0x5738]!=b"\x00" or base[0xA132][28]!=0: raise m.ProbeError("baseline active fault")
        rows=[]
        for n in range(COUNT):
            r=w.request(0x03,TARGET,m.CHUNK)
            if r["status"]!="SUCCESS" or len(r["data"])!=m.CHUNK: raise m.ProbeError("ring read failed")
            d=r["data"]
            a=word(d,0x1A6E); b=word(d,0x1A70); baseptr=word(d,0x1A72)
            rows.append((a,b,baseptr))
            log(f"RING n={n:02d} p1=0x{a:04x} p2=0x{b:04x} base=0x{baseptr:04x} delta={(a-b)&0xffff} raw={d.hex()}")
            if (n+1)%8==0: m.guard_current(w)
            time.sleep(0.08)
        after=m.monitor_snapshot(w)
        if after[0x5738]!=b"\x00" or after[0xA132][28]!=0: raise m.ProbeError("final active fault")
        for a in m.HISTORY:
            if after[a]!=base[a]: raise m.ProbeError(f"fault history changed at 0x{a:04x}")
        log("RING_UNIQUE="+str(len(set(rows))))
        log("FAULT_GUARD=PASS")
        w.leave(); return 0
    finally:
        if w:
            try: w.close()
            except Exception: pass
        for u in reversed(changed):
            try: m.svc("start",u); log("RESTORED "+u)
            except Exception as e: log("RESTORE_ERROR "+str(e))
        for sig,h in prev.items(): signal.signal(sig,h)
        os.close(lock_fd)

if __name__=="__main__": raise SystemExit(main())