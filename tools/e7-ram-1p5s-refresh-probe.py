#!/opt/optolink/venv/bin/python
"""Guarded 1.5 s refresh test for E7 RAM override at 0x20A5."""
from __future__ import annotations
import argparse,fcntl,importlib.util,os,signal,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('smoke',HERE/'e7-ram-physical-write-smoke.py'); s=importlib.util.module_from_spec(spec); spec.loader.exec_module(s); m=s.m
INTERVAL=1.5; SAMPLE=0.25; DURATION=12.0; BASE=30; OVERRIDE=100
ORIG=m.frame

def frame(function,address,length):
    if function==0x03 and address==s.BLOCK and length==32:
        b=bytes((0x41,0x05,0x00,0x03,address>>8,address&0xff,length)); return b+bytes((m.checksum(b),))
    if function==0x01 and (address,length) in ((s.E7,1),(s.WW,1),(s.GFA,11),(s.A1,2),(s.A3C,1)):
        b=bytes((0x41,0x05,0x00,0x01,address>>8,address&0xff,length)); return b+bytes((m.checksum(b),))
    return ORIG(function,address,length)
m.frame=frame

def vread(w,a,l):
    r=w.request(0x01,a,l)
    if r['status']!='SUCCESS' or len(r['data'])!=l: raise m.ProbeError(f'vread failed 0x{a:04x}')
    return r['data']

def pread(w):
    r=w.request(0x03,s.BLOCK,32)
    if r['status']!='SUCCESS' or len(r['data'])!=32: raise m.ProbeError('pread failed')
    return r['data'][s.RAM-s.BLOCK]

def pwrite(w,value):
    if value not in (BASE,OVERRIDE): raise m.ProbeError('blocked value')
    b=bytes((0x41,0x06,0x00,0x04,s.RAM>>8,s.RAM&0xff,1,value)); w.send(b+bytes((m.checksum(b),)))
    if w.exact(1)!=b'\x06': raise m.ProbeError('write ack failed')
    h=w.exact(2); msg=h+w.exact(h[1]+1); w.send(b'\x06')
    if m.checksum(msg[:-1])!=msg[-1] or (msg[2]&0x0f)!=1: raise m.ProbeError('write failed')

def state(w):
    g=vread(w,s.GFA,11); a1=vread(w,s.A1,2)
    return {'e7':vread(w,s.E7,1)[0],'ram':pread(w),'ww':vread(w,s.WW,1)[0],'flame':int(bool(g[5]&0x20)),'a1':a1[1],'a3c':vread(w,s.A3C,1)[0]}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--execute',action='store_true'); ap.add_argument('--self-test',action='store_true'); args=ap.parse_args()
    if args.self_test:
        assert INTERVAL==1.5 and DURATION==12.0; print('SELFTEST=PASS'); return 0
    if not args.execute: print('plan only'); return 0
    fd=os.open(m.LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600); fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    log=lambda x: print(time.strftime('%H:%M:%S'),x,flush=True)
    services={u:m.active(u) for u in (m.SCHEDULE,m.PARTY,m.SPLITTER)}; stopped=[]; w=None; dirty=False
    prev={sig:signal.getsignal(sig) for sig in m.ABORT}
    for sig in m.ABORT: signal.signal(sig,lambda sn,fr: (_ for _ in ()).throw(m.ProbeError(f'signal {sn}')))
    samples=[]; writes=0
    try:
        for u in (m.SCHEDULE,m.PARTY,m.SPLITTER):
            if services[u]: m.svc('stop',u); stopped.append(u)
        w=m.Wire(m.read_port(),log); w.enter(); ident=w.request(0x01,*m.IDENT)
        if ident['status']!='SUCCESS' or ident['data']!=bytes.fromhex('20 c2'): raise m.ProbeError('identity failed')
        fault=m.monitor_snapshot(w)
        if fault[0x5738]!=b'\x00' or fault[0xA132][28]!=0: raise m.ProbeError('active fault')
        st0=state(w); log('BASE '+str(st0))
        if st0['e7']!=BASE or st0['ram']!=BASE or st0['ww'] or st0['flame']: raise m.ProbeError('unsafe baseline')
        start=time.monotonic(); next_write=start
        while True:
            now=time.monotonic()
            if now-start>=DURATION: break
            if now>=next_write:
                pwrite(w,OVERRIDE); dirty=True; writes+=1; log(f'WRITE100 t={now-start:.3f}s n={writes}')
                next_write += INTERVAL
            st=state(w); tnow=time.monotonic()-start; samples.append((tnow,st)); log(f'SAMPLE t={tnow:.3f}s {st}')
            if st['ww'] or st['flame']: raise m.ProbeError('operating state changed during test')
            time.sleep(max(0.0,SAMPLE-(time.monotonic()-now)))
        pwrite(w,BASE); dirty=False; time.sleep(.5); end=state(w); log('RESTORE '+str(end))
        if end['e7']!=BASE or end['ram']!=BASE: raise m.ProbeError('restore verify failed')
        lows=[(t,st) for t,st in samples if st['a1']<100 or st['a3c']<100 or st['ram']<100]
        log(f'SUMMARY writes={writes} samples={len(samples)} low_samples={len(lows)}')
        for t,st in lows: log(f'LOW t={t:.3f}s {st}')
        after=m.monitor_snapshot(w)
        if after[0x5738]!=b'\x00' or after[0xA132][28]!=0: raise m.ProbeError('final active fault')
        for a in m.HISTORY:
            if after[a]!=fault[a]: raise m.ProbeError(f'history changed 0x{a:04x}')
        log('FAULT_GUARD=PASS'); w.leave(); w.close(); w=None; return 0
    finally:
        if w:
            try:
                if dirty or pread(w)!=BASE: pwrite(w,BASE); log('EMERGENCY_RESTORE=30')
            except Exception as e: log('RESTORE_ERROR '+str(e))
            try:w.close()
            except:pass
        for u in reversed(stopped):
            try:m.svc('start',u)
            except:pass
        for sig,h in prev.items(): signal.signal(sig,h)
        os.close(fd)
if __name__=='__main__': raise SystemExit(main())
