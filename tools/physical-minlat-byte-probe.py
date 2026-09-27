#!/opt/optolink/venv/bin/python
"""Read-only minimal-latency V/P byte discriminator on fixed RAM windows."""
from __future__ import annotations
import argparse, collections, fcntl, importlib.util, os, signal, time
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("physical_ram_snapshot", HERE/"physical-ram-snapshot.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
VIRTUAL=(0x01,0x00F8,2)
PHYSICAL=(0x03,0x0400,32)
RANGES=((0x1E00,0x20),(0x1E60,0x20))
ROUNDS=6
ORIG_FRAME=m.frame

def fixed_frame(function:int,address:int,length:int)->bytes:
    if function==0x01 and (function,address,length)==VIRTUAL:
        b=bytes((0x41,0x05,0x00,0x01,address>>8,address&0xff,length))
        return b+bytes((m.checksum(b),))
    if function==0x03 and length==1 and any(base <= address < base+n for base,n in RANGES):
        b=bytes((0x41,0x05,0x00,0x03,address>>8,address&0xff,1))
        return b+bytes((m.checksum(b),))
    return ORIG_FRAME(function,address,length)
m.frame=fixed_frame

def one_pair(w, addr:int):
    out={}
    for label,stim in (("V",VIRTUAL),("P",PHYSICAL)):
        r=w.request(*stim)
        if r["status"]!="SUCCESS": raise m.ProbeError(f"stimulus {label} failed")
        t0=time.monotonic()
        q=w.request(0x03,addr,1)
        if q["status"]!="SUCCESS" or len(q["data"])!=1:
            raise m.ProbeError(f"byte sample failed 0x{addr:04x}")
        out[label]=(q["data"][0],(time.monotonic()-t0)*1000.0)
    return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--execute",action="store_true"); ap.add_argument("--self-test",action="store_true")
    args=ap.parse_args()
    if args.self_test:
        assert fixed_frame(*VIRTUAL).hex()=="4105000100f80200"
        assert fixed_frame(0x03,0x1E00,1)[3:7]==bytes.fromhex("03 1e 00 01")
        assert fixed_frame(0x03,0x1E7F,1)[3:7]==bytes.fromhex("03 1e 7f 01")
        print("SELFTEST=PASS"); return 0
    if not args.execute:
        print("plan only; use --execute for fixed read-only byte discriminator"); return 0
    fd=os.open(m.LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600); fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    log=lambda s: print(time.strftime("%H:%M:%S"),s,flush=True)
    states={u:m.active(u) for u in (m.SCHEDULE,m.PARTY,m.SPLITTER)}
    if not states[m.SPLITTER]: raise m.ProbeError("splitter not running before probe")
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
        for base_addr,nbytes in RANGES:
            for off in range(nbytes):
                addr=base_addr+off; vals={"V":collections.Counter(),"P":collections.Counter()}; delays={"V":[],"P":[]}
                for n in range(ROUNDS):
                    pair=one_pair(w,addr)
                    for label,(value,delay) in pair.items(): vals[label][value]+=1; delays[label].append(delay)
                    if (n+1)%8==0: m.guard_current(w)
                disjoint=set(vals["V"]).isdisjoint(set(vals["P"]))
                row=(addr,vals,delays,disjoint); rows.append(row)
                log(f"BYTE 0x{addr:04x} V={dict(vals['V'])} P={dict(vals['P'])} disjoint={int(disjoint)} "
                    f"vmed={sorted(delays['V'])[len(delays['V'])//2]:.1f}ms pmed={sorted(delays['P'])[len(delays['P'])//2]:.1f}ms")
            log(f"RANGE_DONE=0x{base_addr:04x}")
        hits=[r for r in rows if r[3]]
        log("DISJOINT_COUNT="+str(len(hits)))
        for addr,vals,delays,_ in hits:
            log(f"HIT 0x{addr:04x} V={dict(vals['V'])} P={dict(vals['P'])}")
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