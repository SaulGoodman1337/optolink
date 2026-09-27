#!/opt/optolink/venv/bin/python
"""Read-only paired V/P scan of fixed M16C SFR space 0x0000..0x03ff."""
from __future__ import annotations
import argparse, collections, fcntl, importlib.util, os, signal, time
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("physical_ram_snapshot",HERE/"physical-ram-snapshot.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
VIRTUAL=(0x01,0x00F8,2); PHYSICAL=(0x03,0x0400,32)
BLOCKS=tuple(range(0x0000,0x0400,0x10)); ROUNDS=4; LEN=16
ORIG=m.frame

def frame(function:int,address:int,length:int)->bytes:
    if (function,address,length)==VIRTUAL or (function,address,length)==PHYSICAL or (function==0x03 and address in BLOCKS and length==LEN):
        b=bytes((0x41,0x05,0x00,function,address>>8,address&0xff,length))
        return b+bytes((m.checksum(b),))
    return ORIG(function,address,length)
m.frame=frame

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--execute",action="store_true"); ap.add_argument("--self-test",action="store_true")
    args=ap.parse_args()
    if args.self_test:
        assert len(BLOCKS)==64 and BLOCKS[0]==0 and BLOCKS[-1]==0x03F0
        assert frame(0x03,0x0000,16)[3:7]==bytes.fromhex("03 00 00 10")
        assert frame(0x03,0x03F0,16)[3:7]==bytes.fromhex("03 03 f0 10")
        print("SELFTEST=PASS"); return 0
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
        hits=[]; failures=[]
        for bi,addr in enumerate(BLOCKS):
            vals={"V":[],"P":[]}
            ok=True
            for n in range(ROUNDS):
                for label,stim in (("V",VIRTUAL),("P",PHYSICAL)):
                    if w.request(*stim)["status"]!="SUCCESS": raise m.ProbeError("stimulus failed")
                    q=w.request(0x03,addr,LEN)
                    if q["status"]!="SUCCESS" or len(q["data"])!=LEN:
                        failures.append((addr,label,q["status"])); ok=False; break
                    vals[label].append(q["data"])
                if not ok: break
            if ok:
                dis=[]; stable=[]
                for off in range(LEN):
                    sv={x[off] for x in vals["V"]}; sp={x[off] for x in vals["P"]}
                    if sv.isdisjoint(sp): dis.append(off)
                    if len(sv)==1 and len(sp)==1 and sv!=sp: stable.append(off)
                if dis or stable:
                    hits.append((addr,dis,stable,vals)); log(f"HIT block=0x{addr:04x} dis={dis} stable={stable}")
            if (bi+1)%8==0:
                m.guard_current(w); log(f"PROGRESS={bi+1}/64")
        log(f"SUMMARY hits={len(hits)} failures={len(failures)}")
        for addr,dis,stable,vals in hits:
            log(f"DETAIL 0x{addr:04x} dis={dis} stable={stable} V={[x.hex() for x in vals['V']]} P={[x.hex() for x in vals['P']]}")
        if failures: log("FAILURES="+str(failures))
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