#!/opt/optolink/venv/bin/python
"""Determine whether E7 RAM reload is timer-driven or triggered by Virtual_READ."""
from __future__ import annotations
import argparse,fcntl,importlib.util,os,signal,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('smoke',HERE/'e7-ram-physical-write-smoke.py'); s=importlib.util.module_from_spec(spec); spec.loader.exec_module(s); m=s.m
RAM=s.RAM; BLOCK=s.BLOCK; BASE=30; TEST=31; ORIG=m.frame

def frame(function,address,length):
    if function==0x03 and address==BLOCK and length==32:
        b=bytes((0x41,0x05,0x00,0x03,address>>8,address&0xff,length)); return b+bytes((m.checksum(b),))
    if function==0x01 and (address,length) in ((s.E7,1),(0x00F8,2),(s.WW,1),(s.GFA,11),(s.A1,2),(s.A3C,1)):
        b=bytes((0x41,0x05,0x00,0x01,address>>8,address&0xff,length)); return b+bytes((m.checksum(b),))
    return ORIG(function,address,length)
m.frame=frame

def pread(w):
    r=w.request(0x03,BLOCK,32)
    if r['status']!='SUCCESS' or len(r['data'])!=32: raise m.ProbeError('pread failed')
    return r['data'][RAM-BLOCK]

def vread(w,a,l):
    r=w.request(0x01,a,l)
    if r['status']!='SUCCESS': raise m.ProbeError('vread failed')
    return r['data']

def pwrite(w,val):
    if val not in (BASE,TEST): raise m.ProbeError('blocked')
    b=bytes((0x41,0x06,0x00,0x04,RAM>>8,RAM&0xff,1,val)); w.send(b+bytes((m.checksum(b),)))
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
            if states[u]: m.svc('stop',u); stopped.append(u)
        w=m.Wire(m.read_port(),log); w.enter()
        ident=w.request(0x01,*m.IDENT)
        if ident['status']!='SUCCESS' or ident['data']!=bytes.fromhex('20 c2'): raise m.ProbeError('identity failed')
        fault=m.monitor_snapshot(w)
        if fault[0x5738]!=b'\x00' or fault[0xA132][28]!=0: raise m.ProbeError('active fault')
        g=vread(w,s.GFA,11); ww=vread(w,s.WW,1)[0]
        if ww or (g[5]&0x20): raise m.ProbeError('unsafe baseline')
        if pread(w)!=BASE: raise m.ProbeError('RAM baseline not 30')

        pwrite(w,TEST); dirty=True; log('WRITE31_A')
        time.sleep(2.0)
        a=pread(w); log(f'AFTER_IDLE_2S ram={a}')
        pwrite(w,BASE); dirty=False

        pwrite(w,TEST); dirty=True; log('WRITE31_B')
        vread(w,0x00F8,2)
        b=pread(w); log(f'AFTER_IDENT_READ ram={b}')
        pwrite(w,BASE); dirty=False

        pwrite(w,TEST); dirty=True; log('WRITE31_C')
        ev=vread(w,s.E7,1)[0]
        c=pread(w); log(f'AFTER_E7_READ e7={ev} ram={c}')
        pwrite(w,BASE); dirty=False

        pwrite(w,TEST); dirty=True; log('WRITE31_D')
        vread(w,s.GFA,11)
        d=pread(w); log(f'AFTER_GFA_READ ram={d}')
        pwrite(w,BASE); dirty=False

        pwrite(w,TEST); dirty=True; log('WRITE31_E')
        vread(w,s.WW,1)
        e=pread(w); log(f'AFTER_WW_READ ram={e}')
        pwrite(w,BASE); dirty=False

        pwrite(w,TEST); dirty=True; log('WRITE31_F')
        vread(w,s.A1,2)
        f=pread(w); log(f'AFTER_A1_READ ram={f}')
        pwrite(w,BASE); dirty=False

        pwrite(w,TEST); dirty=True; log('WRITE31_G')
        vread(w,s.A3C,1)
        g=pread(w); log(f'AFTER_A3C_READ ram={g}')
        pwrite(w,BASE); dirty=False
        log('DONE'); w.leave(); w.close(); w=None; return 0
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
