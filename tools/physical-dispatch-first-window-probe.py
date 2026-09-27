#!/opt/optolink/venv/bin/python
"""Read-only earliest-observable dispatch differential probe.

For each fixed RAM window, alternates Virtual_READ and Physical_READ stimuli,
then reads that window first (~one P300 transaction later). No writes.
"""
from __future__ import annotations
import argparse, collections, fcntl, importlib.util, json, os, signal, time
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("physical_ram_snapshot",HERE/"physical-ram-snapshot.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

VIRTUAL=(0x01,0x00F8,2)
PHYSICAL=(0x03,0x0400,32)
WINDOWS=(0x1A60,0x1D80,0x1DA0,0x1DC0,0x1DE0,0x1E00,0x1E60)
REPS=10
ORIG=m.frame
def fixed_frame(function,address,length):
    if (function,address,length)==VIRTUAL:
        b=bytes((0x41,0x05,0x00,0x01,address>>8,address&0xff,length))
        return b+bytes((m.checksum(b),))
    return ORIG(function,address,length)
m.frame=fixed_frame

def far_hits(a,d):
    out=[]
    for i in range(len(d)-3):
        v=int.from_bytes(d[i:i+4],"little")
        if 0xE0000<=v<=0xFFFFF: out.append((a+i,v))
    return out
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--execute",action="store_true")
    ap.add_argument("--self-test",action="store_true")
    args=ap.parse_args()
    if args.self_test:
        assert fixed_frame(*VIRTUAL).hex()=="4105000100f80200"
        for a in WINDOWS: assert ORIG(0x03,a,m.CHUNK)[3]==3
        print("SELFTEST=PASS"); return 0
    if not args.execute:
        print("plan only; use --execute"); return 0
    fd=os.open(m.LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    log=lambda s: print(time.strftime("%H:%M:%S"),s,flush=True)
    states={u:m.active(u) for u in (m.SCHEDULE,m.PARTY,m.SPLITTER)}
    changed=[]; w=None; rows=[]
    prev={sig:signal.getsignal(sig) for sig in m.ABORT}
    for sig in m.ABORT:
        signal.signal(sig,lambda s,f: (_ for _ in ()).throw(m.ProbeError(f"signal {s}")))
    try:
        for u in (m.SCHEDULE,m.PARTY,m.SPLITTER):
            if states[u]: m.svc("stop",u); changed.append(u); log("STOPPED "+u)
        w=m.Wire(m.read_port(),log); w.enter()
        ident=w.request(0x01,*m.IDENT)
        if ident["status"]!="SUCCESS" or ident["data"]!=bytes.fromhex("20 c2"):
            raise m.ProbeError("identity failed")
        base=m.monitor_snapshot(w)
        if base[0x5738]!=b"\x00" or base[0xA132][28]!=0:
            raise m.ProbeError("baseline active fault")
        for a in WINDOWS:
            for n in range(REPS):
                order=(("V",VIRTUAL),("P",PHYSICAL)) if n%2==0 else (("P",PHYSICAL),("V",VIRTUAL))
                for label,stim in order:
                    s=w.request(*stim)
                    if s["status"]!="SUCCESS": raise m.ProbeError("stimulus failed")
                    t0=time.monotonic()
                    q=w.request(0x03,a,m.CHUNK)
                    if q["status"]!="SUCCESS" or len(q["data"])!=m.CHUNK:
                        raise m.ProbeError(f"window failed 0x{a:04x}")
                    rows.append({"address":a,"rep":n,"label":label,
                                 "delay_ms":(time.monotonic()-t0)*1000,
                                 "data":q["data"]})
                if (n+1)%5==0: m.guard_current(w)
            log(f"WINDOW_DONE=0x{a:04x}")

        summary=[]
        for a in WINDOWS:
            rr=[r for r in rows if r["address"]==a]
            vv=[r["data"] for r in rr if r["label"]=="V"]
            pp=[r["data"] for r in rr if r["label"]=="P"]
            strict=[]
            for off in range(m.CHUNK):
                sv={d[off] for d in vv}; sp={d[off] for d in pp}
                if sv.isdisjoint(sp): strict.append(off)
            vf=collections.Counter(x for d in vv for x in far_hits(a,d))
            pf=collections.Counter(x for d in pp for x in far_hits(a,d))
            summary.append({
              "address":a,"v_unique":len(set(vv)),"p_unique":len(set(pp)),
              "strict_disjoint_offsets":strict,
              "v_delay_ms":round(sum(r["delay_ms"] for r in rr if r["label"]=="V")/REPS,3),
              "p_delay_ms":round(sum(r["delay_ms"] for r in rr if r["label"]=="P")/REPS,3),
              "far_only_v":[f"0x{x[0]:04x}=0x{x[1]:05x}:{vf[x]}" for x in vf.keys()-pf.keys()],
              "far_only_p":[f"0x{x[0]:04x}=0x{x[1]:05x}:{pf[x]}" for x in pf.keys()-vf.keys()]
            })
        stamp=time.strftime("%Y%m%d-%H%M%S")
        out=Path("/tmp")/f"physical-dispatch-first-window-{stamp}.json"
        out.write_text(json.dumps({"summary":summary,"rows":[
          {"address":r["address"],"rep":r["rep"],"label":r["label"],
           "delay_ms":round(r["delay_ms"],3),"data":r["data"].hex()} for r in rows
        ]},indent=2)+"\n")
        for s in summary:
            log("WIN 0x%04x Vuniq=%d Puniq=%d strict=%s Vdelay=%.1f Pdelay=%.1f farV=%s farP=%s" %
                (s["address"],s["v_unique"],s["p_unique"],
                 ",".join(map(str,s["strict_disjoint_offsets"])) or "-",
                 s["v_delay_ms"],s["p_delay_ms"],
                 ",".join(s["far_only_v"]) or "-",
                 ",".join(s["far_only_p"]) or "-"))
        log("OUT="+str(out))
        after=m.monitor_snapshot(w)
        if after[0x5738]!=b"\x00" or after[0xA132][28]!=0:
            raise m.ProbeError("final active fault")
        for a in m.HISTORY:
            if after[a]!=base[a]: raise m.ProbeError(f"fault history changed at 0x{a:04x}")
        log("FAULT_GUARD=PASS"); w.leave(); return 0
    finally:
        if w:
            try:w.close()
            except Exception:pass
        for u in reversed(changed):
            try:m.svc("start",u); log("RESTORED "+u)
            except Exception as exc:log("RESTORE_ERROR "+str(exc))
        for sig,h in prev.items():signal.signal(sig,h)
        os.close(fd)
if __name__=="__main__": raise SystemExit(main())