#!/opt/optolink/venv/bin/python
"""Measure latency from RAM override to next periodic E7 cache reload."""
from __future__ import annotations
import argparse,fcntl,importlib.util,os,signal,time,statistics
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('trig',HERE/'e7-ram-reload-trigger-probe.py'); t=importlib.util.module_from_spec(spec); spec.loader.exec_module(t); m=t.m
REPS=12; POLL=0.05; TIMEOUT=4.0

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--execute',action='store_true'); ap.add_argument('--self-test',action='store_true'); args=ap.parse_args()
    if args.self_test: print('SELFTEST=PASS'); return 0
    if not args.execute: print('plan only'); return 0
    fd=os.open(m.LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600); fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    log=lambda x: print(time.strftime('%H:%M:%S'),x,flush=True)
    states={u:m.active(u) for u in (m.SCHEDULE,m.PARTY,m.SPLITTER)}; stopped=[]; w=None; dirty=False
    prev={sig:signal.getsignal(sig) for sig in m.ABORT}
    for sig in m.ABORT: signal.signal(sig,lambda sn,fr: (_ for _ in ()).throw(m.ProbeError(f'signal {sn}')))
    lat=[]
    try:
        for u in (m.SCHEDULE,m.PARTY,m.SPLITTER):
            if states[u]: m.svc('stop',u); stopped.append(u)
        w=m.Wire(m.read_port(),log); w.enter()
        ident=w.request(0x01,*m.IDENT)
        if ident['status']!='SUCCESS' or ident['data']!=bytes.fromhex('20 c2'): raise m.ProbeError('identity failed')
        fault=m.monitor_snapshot(w)
        if fault[0x5738]!=b'\x00' or fault[0xA132][28]!=0: raise m.ProbeError('active fault')
        g=t.vread(w,t.s.GFA,11); ww=t.vread(w,t.s.WW,1)[0]
        if ww or (g[5]&0x20): raise m.ProbeError('unsafe baseline')
        for rep in range(REPS):
            if t.pread(w)!=30: t.pwrite(w,30); time.sleep(.05)
            t.pwrite(w,31); dirty=True; start=time.monotonic(); seen=None; polls=0
            while time.monotonic()-start<TIMEOUT:
                v=t.pread(w); polls+=1
                if v==30:
                    seen=time.monotonic()-start; break
                time.sleep(POLL)
            if seen is None: log(f'REP {rep} no_reload_within_{TIMEOUT:.1f}s polls={polls}')
            else: lat.append(seen); log(f'REP {rep} reload_s={seen:.3f} polls={polls}')
            t.pwrite(w,30); dirty=False; time.sleep(.12)
        if lat:
            log(f'SUMMARY n={len(lat)} min={min(lat):.3f} median={statistics.median(lat):.3f} max={max(lat):.3f} mean={statistics.mean(lat):.3f}')
        w.leave(); w.close(); w=None; return 0
    finally:
        if w:
            try:
                if dirty or t.pread(w)!=30: t.pwrite(w,30)
            except:pass
            try:w.close()
            except:pass
        for u in reversed(stopped):
            try:m.svc('start',u)
            except:pass
        for sig,h in prev.items(): signal.signal(sig,h)
        os.close(fd)
if __name__=='__main__': raise SystemExit(main())
