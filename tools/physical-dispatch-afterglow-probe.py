#!/opt/optolink/venv/bin/python
"""Read-only differential capture of short-lived P300 dispatch afterglow.

Alternates a fixed Virtual_READ stimulus and a fixed Physical_READ stimulus,
then samples the same fixed RAM windows immediately afterwards. No writes,
no arbitrary addresses, and normal identity/fault-history guards remain active.
"""
from __future__ import annotations
import argparse, collections, fcntl, importlib.util, json, os, signal, time
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("physical_ram_snapshot",HERE/"physical-ram-snapshot.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

VIRTUAL=(0x01,0x00F8,2)
PHYSICAL=(0x03,0x0400,32)
WINDOWS=(0x1960,0x1A60,0x1D80,0x1DA0,0x1DC0,0x1DE0,0x1E00,0x1E60)
ROUNDS=24
ORIG_FRAME=m.frame

def fixed_frame(function:int,address:int,length:int)->bytes:
    if function==0x01 and (function,address,length)==VIRTUAL:
        b=bytes((0x41,0x05,0x00,0x01,address>>8,address&0xff,length))
        return b+bytes((m.checksum(b),))
    return ORIG_FRAME(function,address,length)
m.frame=fixed_frame

def far_hits(block_addr:int,data:bytes):
    out=[]
    for i in range(0,len(data)-3):
        v=int.from_bytes(data[i:i+4],"little")
        if 0xE0000 <= v <= 0xFFFFF:
            out.append((block_addr+i,v))
    return out
def capture_after(w, stimulus, label, n):
    fn,addr,length=stimulus
    r=w.request(fn,addr,length)
    if r["status"]!="SUCCESS":
        raise m.ProbeError(f"{label} stimulus failed: {r['status']}")
    t0=time.monotonic()
    blocks=[]
    for a in WINDOWS:
        q=w.request(0x03,a,m.CHUNK)
        if q["status"]!="SUCCESS" or len(q["data"])!=m.CHUNK:
            raise m.ProbeError(f"sample failed at 0x{a:04x}")
        blocks.append((a,q["data"],time.monotonic()-t0))
    return {"round":n,"label":label,"blocks":blocks}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--execute",action="store_true")
    ap.add_argument("--self-test",action="store_true")
    args=ap.parse_args()
    if args.self_test:
        assert fixed_frame(*VIRTUAL).hex()=="4105000100f80200"
        for a in WINDOWS:
            assert ORIG_FRAME(0x03,a,m.CHUNK)[3]==0x03
        d=bytes.fromhex("00 00 00 00 34 12 0f 00")+bytes(24)
        assert far_hits(0x1000,d)==[(0x1004,0xF1234)]
        print("SELFTEST=PASS"); return 0
    if not args.execute:
        print("plan only; use --execute for fixed read-only dispatch capture"); return 0

    fd=os.open(m.LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    log=lambda s: print(time.strftime("%H:%M:%S"),s,flush=True)
    states={u:m.active(u) for u in (m.SCHEDULE,m.PARTY,m.SPLITTER)}
    if not states[m.SPLITTER]: raise m.ProbeError("splitter not running before probe")
    changed=[]; w=None
    prev={sig:signal.getsignal(sig) for sig in m.ABORT}
    for sig in m.ABORT:
        signal.signal(sig,lambda s,f: (_ for _ in ()).throw(m.ProbeError(f"signal {s}")))
    rows=[]
    try:
        for u in (m.SCHEDULE,m.PARTY,m.SPLITTER):
            if states[u]:
                m.svc("stop",u); changed.append(u); log("STOPPED "+u)
        w=m.Wire(m.read_port(),log); w.enter()
        ident=w.request(0x01,*m.IDENT)
        if ident["status"]!="SUCCESS" or ident["data"]!=bytes.fromhex("20 c2"):
            raise m.ProbeError("20C2 identity failed")
        base=m.monitor_snapshot(w)
        if base[0x5738]!=b"\x00" or base[0xA132][28]!=0:
            raise m.ProbeError("baseline active fault")

        for n in range(ROUNDS):
            order=(("V",VIRTUAL),("P",PHYSICAL)) if n%2==0 else (("P",PHYSICAL),("V",VIRTUAL))
            for label,stim in order:
                row=capture_after(w,stim,label,n)
                rows.append(row)
                if (len(rows)%8)==0: m.guard_current(w)
            if (n+1)%4==0: log(f"ROUND={n+1}/{ROUNDS}")

        bylabel={"V":[],"P":[]}
        for row in rows: bylabel[row["label"]].append(row)
        summary={"windows":[],"far_pointer_hits":{"V":{},"P":{}}}
        for wi,a in enumerate(WINDOWS):
            vv=[r["blocks"][wi][1] for r in bylabel["V"]]
            pp=[r["blocks"][wi][1] for r in bylabel["P"]]
            diff_offsets=[]
            for off in range(m.CHUNK):
                sv={x[off] for x in vv}; sp={x[off] for x in pp}
                if sv.isdisjoint(sp): diff_offsets.append(off)
            summary["windows"].append({
                "address":a,
                "v_unique":len(set(vv)),
                "p_unique":len(set(pp)),
                "strict_disjoint_offsets":diff_offsets,
                "first_v_delay_ms":round(bylabel["V"][0]["blocks"][wi][2]*1000,3),
                "first_p_delay_ms":round(bylabel["P"][0]["blocks"][wi][2]*1000,3),
            })
        for label in ("V","P"):
            c=collections.Counter()
            for row in bylabel[label]:
                for a,d,_ in row["blocks"]:
                    for pos,val in far_hits(a,d):
                        c[(pos,val)]+=1
            summary["far_pointer_hits"][label]={
                f"0x{pos:04x}=0x{val:05x}":cnt for (pos,val),cnt in c.most_common()
            }
        only_v=[]; only_p=[]
        vc=set(summary["far_pointer_hits"]["V"]); pc=set(summary["far_pointer_hits"]["P"])
        only_v=sorted(vc-pc); only_p=sorted(pc-vc)
        summary["far_only_v"]=only_v
        summary["far_only_p"]=only_p
        stamp=time.strftime("%Y%m%d-%H%M%S")
        out=Path("/tmp")/f"physical-dispatch-afterglow-{stamp}.json"
        serial=[]
        for row in rows:
            serial.append({
                "round":row["round"],"label":row["label"],
                "blocks":[{"address":a,"data":d.hex(),"delay_ms":round(dt*1000,3)}
                          for a,d,dt in row["blocks"]]
            })
        out.write_text(json.dumps({"summary":summary,"rows":serial},indent=2)+"\n")
        for x in summary["windows"]:
            log("WIN 0x%04x Vuniq=%d Puniq=%d strict=%s Vdelay=%.1fms Pdelay=%.1fms" %
                (x["address"],x["v_unique"],x["p_unique"],
                 ",".join(str(o) for o in x["strict_disjoint_offsets"]) or "-",
                 x["first_v_delay_ms"],x["first_p_delay_ms"]))
        log("FAR_ONLY_V="+(",".join(only_v) if only_v else "none"))
        log("FAR_ONLY_P="+(",".join(only_p) if only_p else "none"))
        log("OUT="+str(out))

        after=m.monitor_snapshot(w)
        if after[0x5738]!=b"\x00" or after[0xA132][28]!=0:
            raise m.ProbeError("final active fault")
        for a in m.HISTORY:
            if after[a]!=base[a]:
                raise m.ProbeError(f"fault history changed at 0x{a:04x}")
        log("FAULT_GUARD=PASS")
        w.leave(); return 0
    finally:
        if w:
            try: w.close()
            except Exception: pass
        for u in reversed(changed):
            try: m.svc("start",u); log("RESTORED "+u)
            except Exception as exc: log("RESTORE_ERROR "+str(exc))
        for sig,h in prev.items(): signal.signal(sig,h)
        os.close(fd)

if __name__=="__main__":
    raise SystemExit(main())