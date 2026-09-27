#!/opt/optolink/venv/bin/python
"""Read-only verification of EEPROM_READ segment 0x1000 against active coding-plug dump."""
from __future__ import annotations
import argparse, fcntl, importlib.util, os, signal, time
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('physical_ram_snapshot',HERE/'physical-ram-snapshot.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
TARGETS=tuple((0x1000+o,min(55,512-o)) for o in range(0,512,55)); ORIG=m.frame
REF=HERE.parent/'config/optolink-splitter/research/coding-plug/2026-09-25-active-7833971/7173085-3_CHL-G_3F1_94V-0_f01.bin'

def frame(function,address,length):
    if function==0x05 and (address,length) in TARGETS:
        b=bytes((0x41,0x05,0x00,0x05,address>>8,address&0xff,length)); return b+bytes((m.checksum(b),))
    return ORIG(function,address,length)
m.frame=frame

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--execute',action='store_true'); ap.add_argument('--self-test',action='store_true'); args=ap.parse_args()
    if args.self_test:
        assert REF.exists() and len(REF.read_bytes())==512; print('SELFTEST=PASS'); return 0
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
        ref=REF.read_bytes()
        for addr,length in TARGETS:
            r=w.request(0x05,addr,length); off=addr-0x1000; exp=ref[off:off+length]
            log(f'CP addr=0x{addr:04x} status={r["status"]} len={len(r["data"])} match={int(r["status"]=="SUCCESS" and r["data"]==exp)} data={r["data"].hex()}')
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