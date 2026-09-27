#!/opt/optolink/venv/bin/python
from __future__ import annotations
import argparse,fcntl,importlib.util,os,signal,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("physical_ram_snapshot",HERE/"physical-ram-snapshot.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
CASES=((0xFFFC,8),(0xFFFD,8),(0xFFFE,8),(0xFFFF,8),(0xFFFC,1),(0xFFFD,1),(0xFFFE,1),(0xFFFF,1),(0x0000,16))
ORIG=m.frame
def fixed_frame(function,address,length):
    if function==0x03 and (address,length) in CASES:
        b=bytes((0x41,0x05,0x00,0x03,address>>8,address&0xff,length))
        return b+bytes((m.checksum(b),))
    return ORIG(function,address,length)
m.frame=fixed_frame
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--execute",action="store_true"); ap.add_argument("--self-test",action="store_true"); args=ap.parse_args()
    if args.self_test:
        for a,n in CASES: assert fixed_frame(0x03,a,n)[6]==n
        print("SELFTEST=PASS"); return 0
    if not args.execute: print("plan only"); return 0
    fd=os.open(m.LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600); fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    log=lambda s: print(time.strftime("%H:%M:%S"),s,flush=True)
    states={u:m.active(u) for u in (m.SCHEDULE,m.PARTY,m.SPLITTER)}; changed=[]; w=None
    prev={sig:signal.getsignal(sig) for sig in m.ABORT}
    for sig in m.ABORT: signal.signal(sig,lambda s,f: (_ for _ in ()).throw(m.ProbeError(f"signal {s}")))
    try:
        for u in (m.SCHEDULE,m.PARTY,m.SPLITTER):
            if states[u]:m.svc("stop",u);changed.append(u);log("STOPPED "+u)
        w=m.Wire(m.read_port(),log);w.enter()
        ident=w.request(0x01,*m.IDENT)
        if ident["status"]!="SUCCESS" or ident["data"]!=bytes.fromhex("20 c2"):raise m.ProbeError("identity failed")
        base=m.monitor_snapshot(w)
        if base[0x5738]!=b"\x00" or base[0xA132][28]!=0:raise m.ProbeError("baseline active fault")
        results={}
        for a,n in CASES:
            rr=[]
            for rep in range(3):
                q=w.request(0x03,a,n); rr.append(q["data"])
                log(f"A=0x{a:04x} N={n} rep={rep} status={q['status']} data={q['data'].hex()}")
            results[(a,n)]=rr
        low=results[(0x0000,16)][0]
        log("LOW16="+low.hex())
        for a in (0xFFFC,0xFFFD,0xFFFE,0xFFFF):
            block=results[(a,8)][0]; lead=0x10000-a
            log(f"MAP A=0x{a:04x} pre={block[:lead].hex()} post={block[lead:].hex()} low0={low[:8-lead].hex()} low1={low[1:1+8-lead].hex()}")
        after=m.monitor_snapshot(w)
        if after[0x5738]!=b"\x00" or after[0xA132][28]!=0:raise m.ProbeError("final active fault")
        for a in m.HISTORY:
            if after[a]!=base[a]:raise m.ProbeError(f"fault history changed 0x{a:04x}")
        log("FAULT_GUARD=PASS");w.leave();return 0
    finally:
        if w:
            try:w.close()
            except Exception:pass
        for u in reversed(changed):
            try:m.svc("start",u);log("RESTORED "+u)
            except Exception as exc:log("RESTORE_ERROR "+str(exc))
        for sig,h in prev.items():signal.signal(sig,h)
        os.close(fd)
if __name__=="__main__":raise SystemExit(main())