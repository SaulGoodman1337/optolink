#!/opt/optolink/venv/bin/python
"""Guarded reactive E7 RAM override test: repair only on observed firmware reload."""
from __future__ import annotations
import argparse,fcntl,importlib.util,os,signal,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('trig',HERE/'e7-ram-reload-trigger-probe.py'); t=importlib.util.module_from_spec(spec); spec.loader.exec_module(t); m=t.m
DURATION=12.0; BASE=30; OVERRIDE=100; POLL_SLEEP=0.02; SAMPLE_EVERY=0.60

def pwrite100(w):
    b=bytes((0x41,0x06,0x00,0x04,t.RAM>>8,t.RAM&0xff,1,OVERRIDE)); w.send(b+bytes((m.checksum(b),)))
    if w.exact(1)!=b'\x06': raise m.ProbeError('write ack failed')
    h=w.exact(2); msg=h+w.exact(h[1]+1); w.send(b'\x06')
    if m.checksum(msg[:-1])!=msg[-1] or (msg[2]&0x0f)!=1: raise m.ProbeError('write failed')

def pwrite30(w):
    t.pwrite(w,30)

def sample_runtime(w):
    a1=t.vread(w,t.s.A1,2)[1]; a3c=t.vread(w,t.s.A3C,1)[0]
    return a1,a3c

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--execute',action='store_true'); ap.add_argument('--self-test',action='store_true'); args=ap.parse_args()
    if args.self_test: print('SELFTEST=PASS'); return 0
    if not args.execute: print('plan only'); return 0
    fd=os.open(m.LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600); fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    log=lambda x: print(time.strftime('%H:%M:%S'),x,flush=True)
    services={u:m.active(u) for u in (m.SCHEDULE,m.PARTY,m.SPLITTER)}; stopped=[]; w=None; dirty=False
    prev={sig:signal.getsignal(sig) for sig in m.ABORT}
    for sig in m.ABORT: signal.signal(sig,lambda sn,fr: (_ for _ in ()).throw(m.ProbeError(f'signal {sn}')))
    repairs=[]; runtime=[]
    try:
        for u in (m.SCHEDULE,m.PARTY,m.SPLITTER):
            if services[u]: m.svc('stop',u); stopped.append(u)
        w=m.Wire(m.read_port(),log); w.enter(); ident=w.request(0x01,*m.IDENT)
        if ident['status']!='SUCCESS' or ident['data']!=bytes.fromhex('20 c2'): raise m.ProbeError('identity failed')
        fault=m.monitor_snapshot(w)
        if fault[0x5738]!=b'\x00' or fault[0xA132][28]!=0: raise m.ProbeError('active fault')
        g=t.vread(w,t.s.GFA,11); ww=t.vread(w,t.s.WW,1)[0]
        if ww or (g[5]&0x20) or t.pread(w)!=BASE: raise m.ProbeError('unsafe baseline')
        pwrite100(w); dirty=True; start=time.monotonic(); next_sample=start+SAMPLE_EVERY; polls=0
        log('START override=100')
        while True:
            now=time.monotonic()
            if now-start>=DURATION: break
            v=t.pread(w); polls+=1
            if v==BASE:
                det=time.monotonic(); pwrite100(w); done=time.monotonic(); repairs.append((det-start,done-det)); log(f'REPAIR t={det-start:.3f}s write_s={done-det:.3f}')
            if time.monotonic()>=next_sample:
                a1,a3c=sample_runtime(w); ts=time.monotonic()-start; runtime.append((ts,a1,a3c)); log(f'RUNTIME t={ts:.3f}s a1={a1} a3c={a3c}')
                next_sample += SAMPLE_EVERY
            time.sleep(POLL_SLEEP)
        pwrite30(w); dirty=False; time.sleep(.5); a1,a3c=sample_runtime(w); log(f'RESTORE a1={a1} a3c={a3c} ram={t.pread(w)}')
        lows=[x for x in runtime if x[1]<100 or x[2]<100]
        log(f'SUMMARY polls={polls} repairs={len(repairs)} runtime_samples={len(runtime)} low_runtime={len(lows)}')
        for x in lows: log(f'LOW_RUNTIME t={x[0]:.3f}s a1={x[1]} a3c={x[2]}')
        for x in repairs: log(f'REPAIR_STAT t={x[0]:.3f}s write_s={x[1]:.3f}')
        after=m.monitor_snapshot(w)
        if after[0x5738]!=b'\x00' or after[0xA132][28]!=0: raise m.ProbeError('final active fault')
        for a in m.HISTORY:
            if after[a]!=fault[a]: raise m.ProbeError(f'history changed 0x{a:04x}')
        log('FAULT_GUARD=PASS'); w.leave(); w.close(); w=None; return 0
    finally:
        if w:
            try:
                if dirty or t.pread(w)!=BASE: pwrite30(w); log('EMERGENCY_RESTORE=30')
            except Exception as e: log('RESTORE_ERROR '+str(e))
            try:w.close()
            except:pass
        for u in reversed(stopped):
            try:m.svc('start',u)
            except:pass
        for sig,h in prev.items(): signal.signal(sig,h)
        os.close(fd)
if __name__=='__main__': raise SystemExit(main())
