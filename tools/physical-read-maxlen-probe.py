#!/opt/optolink/venv/bin/python
from __future__ import annotations
import argparse,fcntl,importlib.util,os,signal,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("physical_ram_snapshot",HERE/"physical-ram-snapshot.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
SOURCE=0x3300
LENS=tuple(range(49,57))
ORIG=m.frame
def fixed_frame(function,address,length):
    if function==0x03 and address==SOURCE and length in LENS:
        b=bytes((0x41,0x05,0x00,0x03,address>>8,address&0xff,length))
        return b+bytes((m.checksum(b),))
    return ORIG(function,address,length)
m.frame=fixed_frame
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--execute",action="store_true"); ap.add_argument("--self-test",action="store_true"); args=ap.parse_args()
    if args.self_test:
        for n in LENS: assert fixed_frame(0x03,SOURCE,n)[6]==n
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
        for n in LENS:
            r=w.request(0x03,SOURCE,n)
            log(f"N={n} status={r['status']} command={r.get('command')} addr={r.get('address')} data_len={len(r.get('data',b''))} response={r.get('response',b'').hex()}")
            m.guard_current(w)
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