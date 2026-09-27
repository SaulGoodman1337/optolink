[Reading 112 lines from start (total: 112 lines, 0 remaining)]

#!/opt/optolink/venv/bin/python
"""Fast guarded E7 RAM-copy discriminator for local WB2A/20C2.

Candidates are fixed from the stable 2026-09-26 Physical-RAM passes: bytes that
were 0x1e in both passes. Experiment is fixed to E7 30 -> 31 -> 30 and only
runs with WW=0 and flame=0. No arbitrary address/value interface.
"""
from __future__ import annotations
import argparse, fcntl, importlib.util, json, os, signal, time
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('physical_ram_snapshot',HERE/'physical-ram-snapshot.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
BASE=30; TEST=31; E7=0x27E7; WW=0x650A; GFA=0x55D3
CANDIDATES=(0x04ef,0x0c8d,0x0cae,0x0cbb,0x0ec5,0x0eda,0x0fc3,0x1440,0x15b7,0x15bb,0x15d7,0x18b0,0x190e,0x1de4,0x1df9,0x1dff,0x20a5,0x20b9,0x2204,0x22af,0x24bc,0x24d6,0x24e9,0x25f8,0x264c,0x2686,0x2714,0x2764,0x2916,0x2948,0x298e,0x2ac2,0x2ba3,0x2cbf,0x2cea,0x2d18,0x2e01,0x2e4f,0x2ed8,0x306f,0x3302,0x33f4,0x342a,0x35d6,0x35e6,0x38b1,0x3903,0x3956,0x3c3d,0x3e94,0x3f7f,0x401a,0x4102,0x4229,0x4531,0x4532,0x4644,0x4650,0x47f5,0x4874,0x4881,0x488c,0x4a20,0x4ace,0x4d12,0x4ebb,0x4f19,0x5147,0x51b2,0x5271,0x53a2,0x53ac)
BLOCKS=tuple(sorted({a & ~0x1f for a in CANDIDATES}))
ORIG=m.frame

def frame(function:int,address:int,length:int)->bytes:
    if function==0x01 and (address,length) in ((E7,1),(WW,1),(GFA,11)):
        b=bytes((0x41,0x05,0x00,0x01,address>>8,address&0xff,length)); return b+bytes((m.checksum(b),))
    if function==0x03 and address in BLOCKS and length==m.CHUNK:
        b=bytes((0x41,0x05,0x00,0x03,address>>8,address&0xff,length)); return b+bytes((m.checksum(b),))
    return ORIG(function,address,length)
m.frame=frame

def readv(w,a,l):
    r=w.request(0x01,a,l)
    if r['status']!='SUCCESS' or len(r['data'])!=l: raise m.ProbeError(f'read failed 0x{a:04x}')
    return r['data']

def state(w):
    g=readv(w,GFA,11)
    return {'e7':readv(w,E7,1)[0],'ww':readv(w,WW,1)[0],'flame':int(bool(g[5]&0x20)),'gfa':g.hex()}

def write_e7(w,value:int):
    if value not in (BASE,TEST): raise m.ProbeError('blocked E7 value')
    b=bytes((0x41,0x06,0x00,0x02,E7>>8,E7&0xff,1,value)); req=b+bytes((m.checksum(b),))
    w.send(req); first=w.exact(1)
    if first!=b'\x06': raise m.ProbeError('E7 write ACK failed: '+first.hex())
    h=w.exact(2); msg=h+w.exact(h[1]+1)
    if m.checksum(msg[:-1])!=msg[-1]: raise m.ProbeError('E7 write checksum failed')
    w.send(b'\x06')
    if (msg[2]&0x0f)!=1: raise m.ProbeError('E7 controller error: '+msg.hex())
    if readv(w,E7,1)[0]!=value: raise m.ProbeError('E7 readback mismatch')

def capture(w):
    blocks={}
    for a in BLOCKS:
        r=w.request(0x03,a,m.CHUNK)
        if r['status']!='SUCCESS' or len(r['data'])!=m.CHUNK: raise m.ProbeError(f'Physical_READ failed 0x{a:04x}')
        blocks[a]=r['data']
    return {a:blocks[a & ~0x1f][a-(a & ~0x1f)] for a in CANDIDATES}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--execute',action='store_true'); ap.add_argument('--self-test',action='store_true'); args=ap.parse_args()
    if args.self_test:
        assert len(CANDIDATES)==72 and len(BLOCKS)==62
        assert frame(0x03,BLOCKS[0],32)[3:7]==bytes((0x03,BLOCKS[0]>>8,BLOCKS[0]&0xff,32))
        print('SELFTEST=PASS'); return 0
    if not args.execute: print('plan only; use --execute'); return 0
    fd=os.open(m.LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600); fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    log=lambda s: print(time.strftime('%H:%M:%S'),s,flush=True)
    states={u:m.active(u) for u in (m.SCHEDULE,m.PARTY,m.SPLITTER)}; stopped=[]; w=None
    if not states[m.SPLITTER]: raise m.ProbeError('splitter not running')
    prev={sig:signal.getsignal(sig) for sig in m.ABORT}
    for sig in m.ABORT: signal.signal(sig,lambda s,f: (_ for _ in ()).throw(m.ProbeError(f'signal {s}')))
    stamp=time.strftime('%Y%m%d-%H%M%S')
    wrote_test=False
    try:
        for u in (m.SCHEDULE,m.PARTY,m.SPLITTER):
            if states[u]: m.svc('stop',u); stopped.append(u); log('STOPPED '+u)
        w=m.Wire(m.read_port(),log); w.enter()
        ident=w.request(0x01,*m.IDENT)
        if ident['status']!='SUCCESS' or ident['data']!=bytes.fromhex('20 c2'): raise m.ProbeError('20C2 identity failed')
        base_fault=m.monitor_snapshot(w)
        if base_fault[0x5738]!=b'\x00' or base_fault[0xA132][28]!=0: raise m.ProbeError('baseline active fault')
        s=state(w); log('STATE0 '+json.dumps(s,separators=(',',':')))
        if s['e7']!=BASE or s['ww'] or s['flame']: raise m.ProbeError('safe E7-write window not present')
        r0=capture(w); log(f'BASE_CAPTURE blocks={len(BLOCKS)} candidates={len(CANDIDATES)}')
        s=state(w); log('STATE1 '+json.dumps(s,separators=(',',':')))
        if s['e7']!=BASE or s['ww'] or s['flame']: raise m.ProbeError('state changed before E7 test write')
        write_e7(w,TEST); wrote_test=True; log('E7_WRITE=31')
        time.sleep(.35)
        r1=capture(w); log('TEST_CAPTURE=done')
        write_e7(w,BASE); wrote_test=False; log('E7_RESTORE=30')
        time.sleep(.35)
        r2=capture(w); log('RESTORE_CAPTURE=done')
        exact=[a for a in CANDIDATES if (r0[a],r1[a],r2[a])==(BASE,TEST,BASE)]
        changed_candidates=[a for a in CANDIDATES if (r0[a],r1[a],r2[a])!=(r0[a],r0[a],r0[a])]
        report={'exact_hits':[f'0x{x:04X}' for x in exact],'changed_candidates':{f'0x{x:04X}':[r0[x],r1[x],r2[x]] for x in changed_candidates}}
        out=Path('/tmp')/f'e7-physical-ram-targeted-{stamp}.json'; out.write_text(json.dumps(report,indent=2)+'\n')
        log('EXACT_HITS='+(','.join(report['exact_hits']) if exact else 'none')); log('REPORT='+str(out))
        after=m.monitor_snapshot(w)
        if after[0x5738]!=b'\x00' or after[0xA132][28]!=0: raise m.ProbeError('final active fault')
        for a in m.HISTORY:
            if after[a]!=base_fault[a]: raise m.ProbeError(f'fault history changed at 0x{a:04x}')
        log('FAULT_GUARD=PASS'); w.leave(); w.close(); w=None; return 0
    finally:
        if w:
            try:
                if wrote_test or readv(w,E7,1)[0]!=BASE: write_e7(w,BASE); log('E7_EMERGENCY_RESTORE=30')
            except Exception as e: log('E7_EMERGENCY_RESTORE_ERROR '+str(e))
            try:w.close()
            except Exception:pass
        for u in reversed(stopped):
            try:m.svc('start',u); log('RESTORED '+u)
            except Exception as e: log('RESTORE_ERROR '+str(e))
        for sig,h in prev.items(): signal.signal(sig,h)
        os.close(fd)

if __name__=='__main__': raise SystemExit(main())

[executed on device: optolink-splitter (adb0c2e1-4670-4fc7-a00a-6548706280dd)]