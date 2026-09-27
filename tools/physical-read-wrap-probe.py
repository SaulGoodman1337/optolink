#!/opt/optolink/venv/bin/python
"""Read-only Physical_READ 0xffff boundary discriminator."""
from __future__ import annotations
import argparse,fcntl,importlib.util,os,signal,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("physical_ram_snapshot",HERE/"physical-ram-snapshot.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
CASES=((0xFFF0,32),(0xFFF8,16),(0xFFFF,2),(0x0000,32),(0x0000,16),(0x0000,1))
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
        assert fixed_frame(0x03,0xFFF0,32).hex()=="41050003fff02017"
        assert fixed_frame(0x03,0xFFFF,2).hex()=="41050003ffff0208"
        print("SELFTEST=PASS"); return 0
    if not args.execute: print("plan only"); return 0
    fd=os.open(m.LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600); fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    log=lambda s: print(time.strftime("%H:%M:%S"),s,flush=True)
    states={u:m.active(u) for u in (m.SCHEDULE,m.PARTY,m.SPLITTER)}; changed=[]; w=None
    prev={sig:signal.getsignal(sig) for sig in m.ABORT}
    for sig in m.ABORT: signal.signal(sig,lambda s,f: (_ for _ in ()).throw(m.ProbeError(f"signal {s}")))
    try:
        for u in (m.SCHEDULE,m.PARTY,m.SPLITTER):
            if states[u]: m.svc("stop",u); changed.append(u); log("STOPPED "+u)
        w=m.Wire(m.read_port(),log); w.enter()
        ident=w.request(0x01,*m.IDENT)
        if ident["status"]!="SUCCESS" or ident["data"]!=bytes.fromhex("20 c2"): raise m.ProbeError("identity failed")
        base=m.monitor_snapshot(w)
        if base[0x5738]!=b"\x00" or base[0xA132][28]!=0: raise m.ProbeError("baseline active fault")
        results={}
        for address,length in CASES:
            vals=[]
            for rep in range(3):
                r=w.request(0x03,address,length)
                vals.append((r["status"],r["data"]))
                log(f"A=0x{address:04x} N={length} rep={rep} status={r['status']} data={r['data'].hex()}")
            results[(address,length)]=vals
            m.guard_current(w)
        low32=results[(0x0000,32)][0][1]
        for a,n,cross in ((0xFFF0,32,16),(0xFFF8,16,8),(0xFFFF,2,1)):
            d=results[(a,n)][0][1]
            tail=d[-cross:]
            low=low32[:cross]
            log(f"COMPARE A=0x{a:04x} cross={cross} tail={tail.hex()} low0={low.hex()} wraps={int(tail==low)}")
        after=m.monitor_snapshot(w)
        if after[0x5738]!=b"\x00" or after[0xA132][28]!=0: raise m.ProbeError("final active fault")
        for a in m.HISTORY:
            if after[a]!=base[a]: raise m.ProbeError(f"fault history changed 0x{a:04x}")
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