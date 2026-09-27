#!/opt/optolink/venv/bin/python
"""Estimate periodic reload cadence of confirmed E7 RAM cache 0x20A5."""
from __future__ import annotations
import argparse,fcntl,importlib.util,os,signal,time,collections
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('trig',HERE/'e7-ram-reload-trigger-probe.py'); t=importlib.util.module_from_spec(spec); spec.loader.exec_module(t); m=t.m
DELAYS=(0.10,0.25,0.50,0.75,1.00,1.25,1.50,2.00); REPS=8

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--execute',action='store_true'); ap.add_argument('--self-test',action='store_true'); args=ap.parse_args()
    if args.self_test:
        assert t.RAM==0x20A5 and t.BASE==30 and t.TEST==31; print('SELFTEST=PASS'); return 0
    if not args.execute: print('plan only'); return 0
    fd=os.open(m.LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600); fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    log=lambda x: print(time.strftime('%H:%M:%S'),x,flush=True)
    states={u:m.active(u) for u in (m.SCHEDULE,m.PARTY,m.SPLITTER)}; stopped=[]; w=None; dirty=False
    prev={sig:signal.getsignal(sig) for sig in m.ABORT}
    for sig in m.ABORT: signal.signal(sig,lambda sn,fr: (_ for _ in ()).throw(m.ProbeError(f'signal {sn}')))
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
        results={d:[] for d in DELAYS}
        for d in DELAYS:
            for rep in range(REPS):
                if t.pread(w)!=30: t.pwrite(w,30); time.sleep(.05)
                t.pwrite(w,31); dirty=True
                time.sleep(d)
                v=t.pread(w); results[d].append(v); log(f'delay={d:.2f}s rep={rep} ram={v}')
                t.pwrite(w,30); dirty=False; time.sleep(.05)
        for d in DELAYS:
            c=collections.Counter(results[d]); survive=sum(v==31 for v in results[d]); log(f'SUMMARY delay={d:.2f}s survive={survive}/{REPS} values={dict(c)}')
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
