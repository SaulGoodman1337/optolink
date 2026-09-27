#!/opt/optolink/venv/bin/python
"""Guarded E7 -> Physical-RAM differential mapper for the local WB2A/20C2.

One fixed experiment only: E7 30 -> 31 -> 30 while WW and flame are both off.
Captures the complete readable Physical_READ RAM after each state and reports
bytes following exactly 30 -> 31 -> 30. No arbitrary write/address interface.
"""
from __future__ import annotations
import argparse, fcntl, importlib.util, json, os, signal, time
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('physical_ram_snapshot',HERE/'physical-ram-snapshot.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
ORIG=m.frame
E7=0x27E7; WW=0x650A; GFA=0x55D3; BASE=30; TEST=31

def frame(function:int,address:int,length:int)->bytes:
    if function==0x01 and (address,length) in ((E7,1),(WW,1),(GFA,11)):
        b=bytes((0x41,0x05,0x00,0x01,address>>8,address&0xff,length)); return b+bytes((m.checksum(b),))
    if function==0x02 and address==E7 and length==1:
        raise m.ProbeError('use write_e7 fixed-value builder')
    return ORIG(function,address,length)
m.frame=frame

def readv(w,a,l):
    r=w.request(0x01,a,l)
    if r['status']!='SUCCESS' or r['address']!=a or len(r['data'])!=l: raise m.ProbeError(f'read failed 0x{a:04x}')
    return r['data']

def safe_state(w):
    ww=readv(w,WW,1)[0]; g=readv(w,GFA,11); flame=int(bool(g[5]&0x20)); e7=readv(w,E7,1)[0]
    return {'ww':ww,'flame':flame,'e7':e7,'gfa':g.hex()}

def write_e7(w,value:int):
    if value not in (BASE,TEST): raise m.ProbeError('blocked E7 value')
    b=bytes((0x41,0x06,0x00,0x02,E7>>8,E7&0xff,1,value)); req=b+bytes((m.checksum(b),))
    w.send(req); first=w.exact(1)
    if first!=b'\x06': raise m.ProbeError('E7 write ACK failed: '+first.hex())
    h=w.exact(2); msg=h+w.exact(h[1]+1)
    if m.checksum(msg[:-1])!=msg[-1]: raise m.ProbeError('E7 write checksum failed')
    w.send(b'\x06')
    typ=msg[2]&0x0f
    if typ!=1: raise m.ProbeError('E7 write controller error: '+msg.hex())
    rb=readv(w,E7,1)[0]
    if rb!=value: raise m.ProbeError(f'E7 verify {rb} != {value}')

def ram_pass(w,log,label):
    image=bytearray(); blocks=(m.RAM_END-m.RAM_START+1)//m.CHUNK
    for i,a in enumerate(range(m.RAM_START,m.RAM_END+1,m.CHUNK)):
        r=w.request(0x03,a,m.CHUNK)
        if r['status']!='SUCCESS' or r['address']!=a or len(r['data'])!=m.CHUNK: raise m.ProbeError(f'RAM read failed 0x{a:04x}')
        image.extend(r['data'])
        if (i+1)%128==0: log(f'{label} progress={i+1}/{blocks}')
    return bytes(image)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--execute',action='store_true'); ap.add_argument('--self-test',action='store_true'); ap.add_argument('--wait-seconds',type=int,default=0); args=ap.parse_args()
    if args.self_test:
        assert BASE==30 and TEST==31
        assert frame(0x01,E7,1)[3:7]==bytes.fromhex('01 27 e7 01')
        print('SELFTEST=PASS'); return 0
    if not args.execute: print('plan only; use --execute'); return 0
    fd=os.open(m.LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600); fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    log=lambda s: print(time.strftime('%H:%M:%S'),s,flush=True)
    states={u:m.active(u) for u in (m.SCHEDULE,m.PARTY,m.SPLITTER)}; changed=[]; w=None
    if not states[m.SPLITTER]: raise m.ProbeError('splitter not running')
    prev={sig:signal.getsignal(sig) for sig in m.ABORT}
    for sig in m.ABORT: signal.signal(sig,lambda s,f: (_ for _ in ()).throw(m.ProbeError(f'signal {s}')))
    stamp=time.strftime('%Y%m%d-%H%M%S')
    try:
        for u in (m.SCHEDULE,m.PARTY,m.SPLITTER):
            if states[u]: m.svc('stop',u); changed.append(u); log('STOPPED '+u)
        w=m.Wire(m.read_port(),log); w.enter()
        ident=w.request(0x01,*m.IDENT)
        if ident['status']!='SUCCESS' or ident['data']!=bytes.fromhex('20 c2'): raise m.ProbeError('20C2 identity failed')
        base_fault=m.monitor_snapshot(w)
        if base_fault[0x5738]!=b'\x00' or base_fault[0xA132][28]!=0: raise m.ProbeError('baseline active fault')
        deadline=time.monotonic()+max(0,args.wait_seconds)
        while True:
            s=safe_state(w); log('STATE '+json.dumps(s,separators=(',',':')))
            if s['ww']==0 and s['flame']==0: break
            if time.monotonic()>=deadline: raise m.ProbeError('safe E7-write window not present')
            time.sleep(2)
        if s['e7']!=BASE: raise m.ProbeError(f'require E7={BASE}, got {s["e7"]}')
        r0=ram_pass(w,log,'BASE30'); m.guard_current(w)
        s=safe_state(w)
        if s['ww'] or s['flame'] or s['e7']!=BASE: raise m.ProbeError('state changed before E7 test write')
        write_e7(w,TEST); log('E7_WRITE=31')
        time.sleep(.5); r1=ram_pass(w,log,'TEST31'); m.guard_current(w)
        write_e7(w,BASE); log('E7_RESTORE=30')
        time.sleep(.5); r2=ram_pass(w,log,'RESTORE30'); m.guard_current(w)
        hits=[]
        for i,(a,b,c) in enumerate(zip(r0,r1,r2)):
            if (a,b,c)==(BASE,TEST,BASE): hits.append(m.RAM_START+i)
        report={'baseline':BASE,'test':TEST,'hits':[f'0x{x:04X}' for x in hits],'hit_count':len(hits)}
        out=Path('/tmp')/f'e7-physical-ram-diff-{stamp}.json'; out.write_text(json.dumps(report,indent=2)+'\n')
        log('E7_RAM_HITS='+(','.join(report['hits']) if hits else 'none')); log('REPORT='+str(out))
        after=m.monitor_snapshot(w)
        if after[0x5738]!=b'\x00' or after[0xA132][28]!=0: raise m.ProbeError('final active fault')
        for a in m.HISTORY:
            if after[a]!=base_fault[a]: raise m.ProbeError(f'fault history changed at 0x{a:04x}')
        log('FAULT_GUARD=PASS'); w.leave(); return 0
    finally:
        if w:
            try:
                try:
                    if readv(w,E7,1)[0]!=BASE: write_e7(w,BASE)
                except Exception as e: log('E7_EMERGENCY_RESTORE_ERROR '+str(e))
                w.close()
            except Exception: pass
        for u in reversed(changed):
            try:m.svc('start',u); log('RESTORED '+u)
            except Exception as e: log('RESTORE_ERROR '+str(e))
        for sig,h in prev.items(): signal.signal(sig,h)
        os.close(fd)

if __name__=='__main__': raise SystemExit(main())