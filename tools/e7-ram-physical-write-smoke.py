#!/opt/optolink/venv/bin/python
"""One-byte guarded Physical_WRITE smoke test for confirmed E7 RAM copy 0x20A5.

Fixed experiment only: with WW=0/flame=0 and virtual E7=30, write RAM 30->31,
observe, then restore 30. No arbitrary address/value interface.
"""
from __future__ import annotations
import argparse, fcntl, importlib.util, os, signal, time
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('physical_ram_snapshot',HERE/'physical-ram-snapshot.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
RAM=0x20A5; BLOCK=0x20A0; E7=0x27E7; WW=0x650A; GFA=0x55D3; A1=0x7663; A3C=0x0A3C
BASE=30; TEST=31; ORIG=m.frame

def frame(function:int,address:int,length:int)->bytes:
    if function==0x03 and address==BLOCK and length==32:
        b=bytes((0x41,0x05,0x00,0x03,address>>8,address&0xff,length)); return b+bytes((m.checksum(b),))
    if function==0x01 and (address,length) in ((E7,1),(WW,1),(GFA,11),(A1,2),(A3C,1)):
        b=bytes((0x41,0x05,0x00,0x01,address>>8,address&0xff,length)); return b+bytes((m.checksum(b),))
    return ORIG(function,address,length)
m.frame=frame

def readv(w,a,l):
    r=w.request(0x01,a,l)
    if r['status']!='SUCCESS' or len(r['data'])!=l: raise m.ProbeError(f'Virtual_READ failed 0x{a:04x}')
    return r['data']

def read_ram(w):
    r=w.request(0x03,BLOCK,32)
    if r['status']!='SUCCESS' or len(r['data'])!=32: raise m.ProbeError('Physical_READ failed')
    return r['data'][RAM-BLOCK]

def state(w):
    g=readv(w,GFA,11); a1=readv(w,A1,2)
    return {'e7':readv(w,E7,1)[0],'ram':read_ram(w),'ww':readv(w,WW,1)[0],'flame':int(bool(g[5]&0x20)),'a1_out':a1[0],'a1_speed':a1[1],'a3c':readv(w,A3C,1)[0]}

def pwrite(w,value:int):
    if value not in (BASE,TEST): raise m.ProbeError('blocked RAM value')
    b=bytes((0x41,0x06,0x00,0x04,RAM>>8,RAM&0xff,1,value)); req=b+bytes((m.checksum(b),))
    w.send(req); first=w.exact(1)
    if first!=b'\x06': raise m.ProbeError('Physical_WRITE ACK failed: '+first.hex())
    h=w.exact(2); msg=h+w.exact(h[1]+1)
    if m.checksum(msg[:-1])!=msg[-1]: raise m.ProbeError('Physical_WRITE checksum failed')
    w.send(b'\x06')
    if (msg[2]&0x0f)!=1: raise m.ProbeError('Physical_WRITE controller error: '+msg.hex())

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--execute',action='store_true'); ap.add_argument('--self-test',action='store_true'); args=ap.parse_args()
    if args.self_test:
        assert frame(0x03,BLOCK,32)[3:7]==bytes.fromhex('03 20 a0 20')
        print('SELFTEST=PASS'); return 0
    if not args.execute: print('plan only; use --execute'); return 0
    fd=os.open(m.LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600); fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    log=lambda s: print(time.strftime('%H:%M:%S'),s,flush=True)
    states={u:m.active(u) for u in (m.SCHEDULE,m.PARTY,m.SPLITTER)}; stopped=[]; w=None; wrote=False
    if not states[m.SPLITTER]: raise m.ProbeError('splitter not running')
    prev={sig:signal.getsignal(sig) for sig in m.ABORT}
    for sig in m.ABORT: signal.signal(sig,lambda s,f: (_ for _ in ()).throw(m.ProbeError(f'signal {s}')))
    try:
        for u in (m.SCHEDULE,m.PARTY,m.SPLITTER):
            if states[u]: m.svc('stop',u); stopped.append(u); log('STOPPED '+u)
        w=m.Wire(m.read_port(),log); w.enter()
        ident=w.request(0x01,*m.IDENT)
        if ident['status']!='SUCCESS' or ident['data']!=bytes.fromhex('20 c2'): raise m.ProbeError('20C2 identity failed')
        base_fault=m.monitor_snapshot(w)
        if base_fault[0x5738]!=b'\x00' or base_fault[0xA132][28]!=0: raise m.ProbeError('baseline active fault')
        s0=state(w); log('STATE0 '+str(s0))
        if s0['e7']!=BASE or s0['ram']!=BASE or s0['ww'] or s0['flame']: raise m.ProbeError('safe baseline not present')
        pwrite(w,TEST); wrote=True; time.sleep(.15)
        s1=state(w); log('STATE1 '+str(s1))
        pwrite(w,BASE); wrote=False; time.sleep(.15)
        s2=state(w); log('STATE2 '+str(s2))
        if s2['ram']!=BASE or s2['e7']!=BASE: raise m.ProbeError('restore verify failed')
        after=m.monitor_snapshot(w)
        if after[0x5738]!=b'\x00' or after[0xA132][28]!=0: raise m.ProbeError('final active fault')
        for a in m.HISTORY:
            if after[a]!=base_fault[a]: raise m.ProbeError(f'fault history changed at 0x{a:04x}')
        log('FAULT_GUARD=PASS'); w.leave(); w.close(); w=None; return 0
    finally:
        if w:
            try:
                if wrote or read_ram(w)!=BASE: pwrite(w,BASE); log('RAM_EMERGENCY_RESTORE=30')
            except Exception as e: log('RAM_EMERGENCY_RESTORE_ERROR '+str(e))
            try:w.close()
            except Exception:pass
        for u in reversed(stopped):
            try:m.svc('start',u); log('RESTORED '+u)
            except Exception as e: log('RESTORE_ERROR '+str(e))
        for sig,h in prev.items(): signal.signal(sig,h)
        os.close(fd)

if __name__=='__main__': raise SystemExit(main())
