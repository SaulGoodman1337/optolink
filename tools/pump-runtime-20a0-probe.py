#!/opt/optolink/venv/bin/python
from __future__ import annotations
import argparse, fcntl, importlib.util, os, signal, time
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('smoke',HERE/'e7-ram-physical-write-smoke.py')
s=importlib.util.module_from_spec(spec); spec.loader.exec_module(s); m=s.m
BLOCK=0x20A0
ORIG=m.frame

def frame(function,address,length):
    if function==0x03 and address==BLOCK and length==32:
        b=bytes((0x41,0x05,0x00,0x03,address>>8,address&0xff,length)); return b+bytes((m.checksum(b),))
    if function==0x01 and (address,length) in ((s.E7,1),(s.WW,1),(s.GFA,11),(s.A1,2),(s.A3C,1)):
        b=bytes((0x41,0x05,0x00,0x01,address>>8,address&0xff,length)); return b+bytes((m.checksum(b),))
    return ORIG(function,address,length)
m.frame=frame

def readv(w,a,l):
    r=w.request(0x01,a,l)
    if r['status']!='SUCCESS' or len(r['data'])!=l: raise m.ProbeError('read failed')
    return r['data']

def block(w):
    r=w.request(0x03,BLOCK,32)
    if r['status']!='SUCCESS' or len(r['data'])!=32: raise m.ProbeError('block read failed')
    return r['data']

def st(w):
    g=readv(w,s.GFA,11); a1=readv(w,s.A1,2)
    return {'e7':readv(w,s.E7,1)[0],'ww':readv(w,s.WW,1)[0],'flame':int(bool(g[5]&0x20)),'a1':a1[1],'a3c':readv(w,s.A3C,1)[0]}

def pwrite(w,value):
    if value not in (30,100): raise m.ProbeError('blocked')
    b=bytes((0x41,0x06,0x00,0x04,s.RAM>>8,s.RAM&0xff,1,value)); w.send(b+bytes((m.checksum(b),)))
    if w.exact(1)!=b'\x06': raise m.ProbeError('ack failed')
    h=w.exact(2); msg=h+w.exact(h[1]+1); w.send(b'\x06')
    if m.checksum(msg[:-1])!=msg[-1] or (msg[2]&0x0f)!=1: raise m.ProbeError('write failed')

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--execute',action='store_true'); ap.add_argument('--self-test',action='store_true'); args=ap.parse_args()
    if args.self_test:
        assert frame(0x03,BLOCK,32)[3:7]==bytes.fromhex('03 20 a0 20'); print('SELFTEST=PASS'); return 0
    if not args.execute: print('plan only'); return 0
    fd=os.open(m.LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600); fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    log=lambda x: print(time.strftime('%H:%M:%S'),x,flush=True)
    states={u:m.active(u) for u in (m.SCHEDULE,m.PARTY,m.SPLITTER)}; stopped=[]; w=None; dirty=False
    prev={sig:signal.getsignal(sig) for sig in m.ABORT}
    for sig in m.ABORT: signal.signal(sig,lambda sn,fr: (_ for _ in ()).throw(m.ProbeError(f'signal {sn}')))
    try:
        for u in (m.SCHEDULE,m.PARTY,m.SPLITTER):
            if states[u]: m.svc('stop',u); stopped.append(u); log('STOPPED '+u)
        w=m.Wire(m.read_port(),log); w.enter()
        ident=w.request(0x01,*m.IDENT)
        if ident['status']!='SUCCESS' or ident['data']!=bytes.fromhex('20 c2'): raise m.ProbeError('identity failed')
        base_fault=m.monitor_snapshot(w)
        s0=st(w); b0=block(w); log('STATE0 '+str(s0)); log('B0 '+b0.hex())
        if s0['e7']!=30 or s0['ww'] or s0['flame']: raise m.ProbeError('unsafe baseline')
        pwrite(w,100); dirty=True; time.sleep(.2)
        s1=st(w); b1=block(w); log('STATE1 '+str(s1)); log('B1 '+b1.hex())
        time.sleep(.35)
        s2=st(w); b2=block(w); log('STATE2 '+str(s2)); log('B2 '+b2.hex())
        pwrite(w,30); dirty=False; time.sleep(.8)
        s3=st(w); b3=block(w); log('STATE3 '+str(s3)); log('B3 '+b3.hex())
        for i,(a,b,c,d) in enumerate(zip(b0,b1,b2,b3)):
            if len({a,b,c,d})>1: log(f'CHG 0x{BLOCK+i:04X} {a}->{b}->{c}->{d}')
        after=m.monitor_snapshot(w)
        if after[0x5738]!=b'\x00' or after[0xA132][28]!=0: raise m.ProbeError('final active fault')
        for a in m.HISTORY:
            if after[a]!=base_fault[a]: raise m.ProbeError(f'history changed 0x{a:04x}')
        log('FAULT_GUARD=PASS'); w.leave(); w.close(); w=None; return 0
    finally:
        if w:
            try:
                if dirty: pwrite(w,30); log('RESTORE=30')
            except Exception as e: log('RESTORE_ERROR '+str(e))
            try:w.close()
            except Exception:pass
        for u in reversed(stopped):
            try:m.svc('start',u); log('RESTORED '+u)
            except Exception as e: log('SERVICE_RESTORE_ERROR '+str(e))
        for sig,h in prev.items(): signal.signal(sig,h)
        os.close(fd)

if __name__=='__main__': raise SystemExit(main())
