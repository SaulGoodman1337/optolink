#!/opt/optolink/venv/bin/python
"""Fixed read-only V/P discriminator for DMA/UART SFR blocks."""
from __future__ import annotations
import argparse, collections, fcntl, importlib.util, os, signal, time
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("physical_ram_snapshot",HERE/"physical-ram-snapshot.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
VIRTUAL=(0x01,0x00F8,2); PHYSICAL=(0x03,0x0400,32)
TARGETS=(("dma0",0x0020,16),("dma1",0x0030,16),("uart01",0x03A0,16),("dma_sel",0x03B0,16))
ROUNDS=12
ORIG=m.frame

def frame(function:int,address:int,length:int)->bytes:
    allowed={(0x01,0x00F8,2),(0x03,0x0400,32)} | {(0x03,a,l) for _,a,l in TARGETS}
    if (function,address,length) in allowed:
        b=bytes((0x41,0x05,0x00,function,address>>8,address&0xff,length))
        return b+bytes((m.checksum(b),))
    return ORIG(function,address,length)
m.frame=frame

def decode_dma(d:bytes):
    return (int.from_bytes(d[0:3],"little"),int.from_bytes(d[4:7],"little"),int.from_bytes(d[8:10],"little"),d[12])

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--execute",action="store_true"); ap.add_argument("--self-test",action="store_true")
    args=ap.parse_args()
    if args.self_test:
        assert frame(*VIRTUAL).hex()=="4105000100f80200"
        assert frame(0x03,0x0020,16)[3:7]==bytes.fromhex("03 00 20 10")
        assert frame(0x03,0x03B0,16)[3:7]==bytes.fromhex("03 03 b0 10")
        print("SELFTEST=PASS"); return 0
    if not args.execute:
        print("plan only; use --execute for fixed read-only SFR V/P probe"); return 0
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
        results=[]
        for name,addr,length in TARGETS:
            vals={"V":[],"P":[]}; delays={"V":[],"P":[]}
            for n in range(ROUNDS):
                for label,stim in (("V",VIRTUAL),("P",PHYSICAL)):
                    r=w.request(*stim)
                    if r["status"]!="SUCCESS": raise m.ProbeError(f"stimulus {label} failed")
                    t0=time.monotonic(); q=w.request(0x03,addr,length); dt=(time.monotonic()-t0)*1000.0
                    if q["status"]!="SUCCESS" or len(q["data"])!=length: raise m.ProbeError(f"SFR read {name} failed")
                    vals[label].append(q["data"]); delays[label].append(dt)
                if (n+1)%4==0: m.guard_current(w)
            disjoint=[]
            for off in range(length):
                sv={x[off] for x in vals["V"]}; sp={x[off] for x in vals["P"]}
                if sv.isdisjoint(sp): disjoint.append(off)
            results.append((name,addr,vals,delays,disjoint))
            log(f"SFR {name} addr=0x{addr:04x} Vuniq={len(set(vals['V']))} Puniq={len(set(vals['P']))} "
                f"disjoint={','.join(str(x) for x in disjoint) or '-'} "
                f"vmed={sorted(delays['V'])[len(delays['V'])//2]:.1f}ms pmed={sorted(delays['P'])[len(delays['P'])//2]:.1f}ms")
            if name in ("dma0","dma1"):
                log("  V_DMA="+str(collections.Counter(decode_dma(x) for x in vals["V"])))
                log("  P_DMA="+str(collections.Counter(decode_dma(x) for x in vals["P"])))
            else:
                log("  V_RAW="+str(collections.Counter(x.hex() for x in vals["V"])))
                log("  P_RAW="+str(collections.Counter(x.hex() for x in vals["P"])))
        total=sum(len(x[4]) for x in results); log("DISJOINT_TOTAL="+str(total))
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