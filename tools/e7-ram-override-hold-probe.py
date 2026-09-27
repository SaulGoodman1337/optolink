#!/opt/optolink/venv/bin/python
"""Guarded volatile E7 RAM override characterization at confirmed RAM 0x20A5.

Fixed sequence only, with WW=0/flame=0 throughout:
30 -> 31 for 10 s -> 30, then 30 -> 100 for 2 s -> 30.
No normal E7 Virtual_WRITE is used.
"""
from __future__ import annotations
import argparse, fcntl, importlib.util, os, signal, time
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('smoke',HERE/'e7-ram-physical-write-smoke.py')
s=importlib.util.module_from_spec(spec); spec.loader.exec_module(s)
m=s.m

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--execute',action='store_true'); ap.add_argument('--self-test',action='store_true'); args=ap.parse_args()
    if args.self_test:
        assert s.RAM==0x20A5 and s.BASE==30
        print('SELFTEST=PASS'); return 0
    if not args.execute: print('plan only; use --execute'); return 0
    fd=os.open(m.LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600); fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    log=lambda x: print(time.strftime('%H:%M:%S'),x,flush=True)
    states={u:m.active(u) for u in (m.SCHEDULE,m.PARTY,m.SPLITTER)}; stopped=[]; w=None; dirty=False
    prev={sig:signal.getsignal(sig) for sig in m.ABORT}
    for sig in m.ABORT: signal.signal(sig,lambda sn,fr: (_ for _ in ()).throw(m.ProbeError(f'signal {sn}')))
    def ensure_safe(tag):
        st=s.state(w); log(tag+' '+str(st))
        if st['ww'] or st['flame'] or st['e7']!=s.BASE or st['ram']!=s.BASE: raise m.ProbeError('safe baseline lost')
        return st
    def ram_write(value):
        nonlocal dirty
        if value not in (30,31,100): raise m.ProbeError('blocked value')
        b=bytes((0x41,0x06,0x00,0x04,s.RAM>>8,s.RAM&0xff,1,value)); req=b+bytes((m.checksum(b),))
        w.send(req); first=w.exact(1)
        if first!=b'\x06': raise m.ProbeError('write ACK failed')
        h=w.exact(2); msg=h+w.exact(h[1]+1)
        if m.checksum(msg[:-1])!=msg[-1]: raise m.ProbeError('write checksum failed')
        w.send(b'\x06')
        if (msg[2]&0x0f)!=1: raise m.ProbeError('write controller error '+msg.hex())
        dirty=(value!=30)
    try:
        for u in (m.SCHEDULE,m.PARTY,m.SPLITTER):
            if states[u]: m.svc('stop',u); stopped.append(u); log('STOPPED '+u)
        w=m.Wire(m.read_port(),log); w.enter()
        ident=w.request(0x01,*m.IDENT)
        if ident['status']!='SUCCESS' or ident['data']!=bytes.fromhex('20 c2'): raise m.ProbeError('20C2 identity failed')
        base_fault=m.monitor_snapshot(w)
        if base_fault[0x5738]!=b'\x00' or base_fault[0xA132][28]!=0: raise m.ProbeError('baseline active fault')
        ensure_safe('BASE')
        ram_write(31); log('RAM=31')
        for i in range(11):
            st=s.state(w); log(f'HOLD31 t={i}s '+str(st))
            if st['ww'] or st['flame']: raise m.ProbeError('operating state changed during hold31')
            if i<10: time.sleep(1)
        ram_write(30); dirty=False; time.sleep(.2); ensure_safe('RESTORE31')
        ram_write(100); log('RAM=100')
        for i in range(5):
            st=s.state(w); log(f'HOLD100 t={i*0.5:.1f}s '+str(st))
            if st['ww'] or st['flame']: raise m.ProbeError('operating state changed during hold100')
            if i<4: time.sleep(.5)
        ram_write(30); dirty=False; time.sleep(.2); ensure_safe('RESTORE100')
        after=m.monitor_snapshot(w)
        if after[0x5738]!=b'\x00' or after[0xA132][28]!=0: raise m.ProbeError('final active fault')
        for a in m.HISTORY:
            if after[a]!=base_fault[a]: raise m.ProbeError(f'fault history changed at 0x{a:04x}')
        log('FAULT_GUARD=PASS'); w.leave(); w.close(); w=None; return 0
    finally:
        if w:
            try:
                if dirty or s.read_ram(w)!=30: ram_write(30); log('RAM_EMERGENCY_RESTORE=30')
            except Exception as e: log('RAM_EMERGENCY_RESTORE_ERROR '+str(e))
            try:w.close()
            except Exception:pass
        for u in reversed(stopped):
            try:m.svc('start',u); log('RESTORED '+u)
            except Exception as e: log('RESTORE_ERROR '+str(e))
        for sig,h in prev.items(): signal.signal(sig,h)
        os.close(fd)

if __name__=='__main__': raise SystemExit(main())
