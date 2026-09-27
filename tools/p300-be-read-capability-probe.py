#!/opt/optolink/venv/bin/python
"""Bounded read-only P300 BE_READ capability probe using source-backed Vitosoft shapes."""
from __future__ import annotations
import argparse, fcntl, importlib.util, os, signal, time
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('physical_ram_snapshot',HERE/'physical-ram-snapshot.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
TARGETS=(0x0008,0x0057,0x00F5); ORIG=m.frame

def frame(function,address,length):
    if function==0x35 and address in TARGETS and length==1:
        b=bytes((0x41,0x05,0x00,0x35,address>>8,address&0xff,1)); return b+bytes((m.checksum(b),))
    return ORIG(function,address,length)
m.frame=frame

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--execute',action='store_true'); ap.add_argument('--self-test',action='store_true'); args=ap.parse_args()
    if args.self_test:
        assert frame(0x35,0x00F5,1)[3:7]==bytes.fromhex('35 00 f5 01'); print('SELFTEST=PASS'); return 0
    if not args.execute: print('plan only; use --execute'); return 0
    fd=os.open(m.LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600); fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    log=lambda s: print(time.strftime('%H:%M:%S'),s,flush=True)
    states={u:m.active(u) for u in (m.SCHEDULE,m.PARTY,m.SPLITTER)}; changed=[]; w=None
    if not states[m.SPLITTER]: raise m.ProbeError('splitter not running')
    prev={sig:signal.getsignal(sig) for sig in m.ABORT}
    for sig in m.ABORT: signal.signal(sig,lambda s,f: (_ for _ in ()).throw(m.ProbeError(f'signal {s}')))
    try:
        for u in (m.SCHEDULE,m.PARTY,m.SPLITTER):
            if states[u]: m.svc('stop',u); changed.append(u); log('STOPPED '+u)
        w=m.Wire(m.read_port(),log); w.enter()
        ident=w.request(0x01,*m.IDENT)
        if ident['status']!='SUCCESS' or ident['data']!=bytes.fromhex('20 c2'): raise m.ProbeError('20C2 identity failed')
        base=m.monitor_snapshot(w)
        if base[0x5738]!=b'\x00' or base[0xA132][28]!=0: raise m.ProbeError('baseline active fault')
        for addr in TARGETS:
            vals=[]
            for n in range(3):
                r=w.request(0x35,addr,1); vals.append((r['status'],r['data'].hex()))
            log(f'BE addr=0x{addr:04x} vals={vals}')
            m.guard_current(w)
        after=m.monitor_snapshot(w)
        if after[0x5738]!=b'\x00' or after[0xA132][28]!=0: raise m.ProbeError('final active fault')
        for a in m.HISTORY:
            if after[a]!=base[a]: raise m.ProbeError(f'fault history changed at 0x{a:04x}')
        log('FAULT_GUARD=PASS'); w.leave(); return 0
    finally:
        if w:
            try:w.close()
            except Exception:pass
        for u in reversed(changed):
            try:m.svc('start',u); log('RESTORED '+u)
            except Exception as e: log('RESTORE_ERROR '+str(e))
        for sig,h in prev.items(): signal.signal(sig,h)
        os.close(fd)

if __name__=='__main__': raise SystemExit(main())