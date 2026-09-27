#!/opt/optolink/venv/bin/python
"""Read-only order-controlled V/P check for DMA1 and timer SFR candidates."""
from __future__ import annotations
import argparse, collections, fcntl, importlib.util, os, signal, time
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("physical_ram_snapshot",HERE/"physical-ram-snapshot.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
VIRTUAL=(0x01,0x00F8,2); PHYSICAL=(0x03,0x0400,32)
TARGETS=(("dma1",0x0030,16),("timerA",0x0380,16),("timerB",0x0390,16)); ROUNDS=16
ORIG=m.frame

def frame(function:int,address:int,length:int)->bytes:
    allowed={VIRTUAL,PHYSICAL}|{(0x03,a,l) for _,a,l in TARGETS}
    if (function,address,length) in allowed:
        b=bytes((0x41,0x05,0x00,function,address>>8,address&0xff,length)); return b+bytes((m.checksum(b),))
    return ORIG(function,address,length)
m.frame=frame

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--execute",action="store_true"); ap.add_argument("--self-test",action="store_true"); args=ap.parse_args()
    if args.self_test:
        assert frame(0x03,0x0380,16)[3:7]==bytes.fromhex("03 03 80 10"); print("SELFTEST=PASS"); return 0
    if not args.execute: print("plan only; use --execute"); return 0
    fd=os.open(m.LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600); fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    log=lambda s: print(time.strftime("%H:%M:%S"),s,flush=True)
    states={u:m.active(u) for u in (m.SCHEDULE,m.PARTY,m.SPLITTER)}
    if not states[m.SPLITTER]: raise m.ProbeError("splitter not running")
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
        for name,addr,length in TARGETS:
            vals={"V":[],"P":[]}
            for n in range(ROUNDS):
                order=(("V",VIRTUAL),("P",PHYSICAL)) if n%2==0 else (("P",PHYSICAL),("V",VIRTUAL))
                for label,stim in order:
                    if w.request(*stim)["status"]!="SUCCESS": raise m.ProbeError("stimulus failed")
                    q=w.request(0x03,addr,length)
                    if q["status"]!="SUCCESS": raise m.ProbeError(f"sample {name} failed")
                    vals[label].append(q["data"])
            dis=[]
            for off in range(length):
                if {x[off] for x in vals['V']}.isdisjoint({x[off] for x in vals['P']}): dis.append(off)
            log(f"ORDER {name} dis={dis}")
            log("  V="+str(collections.Counter(x.hex() for x in vals['V'])))
            log("  P="+str(collections.Counter(x.hex() for x in vals['P'])))
            m.guard_current(w)
        after=m.monitor_snapshot(w)
        if after[0x5738]!=b"\x00" or after[0xA132][28]!=0: raise m.ProbeError("final active fault")
        for a in m.HISTORY:
            if after[a]!=base[a]: raise m.ProbeError(f"fault history changed at 0x{a:04x}")
        log("FAULT_GUARD=PASS"); w.leave(); return 0
    finally:
        if w:
            try:w.close()
            except Exception:pass
        for u in reversed(changed):
            try:m.svc("start",u); log("RESTORED "+u)
            except Exception as e: log("RESTORE_ERROR "+str(e))
        for sig,h in prev.items(): signal.signal(sig,h)
        os.close(fd)

if __name__=="__main__": raise SystemExit(main())