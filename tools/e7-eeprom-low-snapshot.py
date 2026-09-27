#!/opt/optolink/venv/bin/python
"""Read-only 256-byte EEPROM_READ snapshot for E7 source correlation."""
from __future__ import annotations
import argparse, fcntl, importlib.util, json, os, signal, time
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('base',HERE/'physical-ram-snapshot.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
BLOCKS=tuple(range(0,0x100,0x10)); ORIG=m.frame

def frame(function,address,length):
    if function==0x05 and address in BLOCKS and length==16:
        b=bytes((0x41,0x05,0x00,0x05,address>>8,address&0xff,16)); return b+bytes((m.checksum(b),))
    return ORIG(function,address,length)
m.frame=frame

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--execute',action='store_true'); ap.add_argument('--output'); ap.add_argument('--self-test',action='store_true'); args=ap.parse_args()
    if args.self_test:
        assert len(BLOCKS)==16; print('SELFTEST=PASS'); return 0
    if not args.execute: print('plan only'); return 0
    out=Path(args.output or f'/tmp/e7-eeprom-low-{time.strftime("%Y%m%d-%H%M%S")}.json')
    fd=os.open(m.LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600); fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    log=lambda x: print(time.strftime('%H:%M:%S'),x,flush=True)
    states={u:m.active(u) for u in (m.SCHEDULE,m.PARTY,m.SPLITTER)}; stopped=[]; w=None
    prev={sig:signal.getsignal(sig) for sig in m.ABORT}
    for sig in m.ABORT: signal.signal(sig,lambda sn,fr: (_ for _ in ()).throw(m.ProbeError(f'signal {sn}')))
    try:
        for u in (m.SCHEDULE,m.PARTY,m.SPLITTER):
            if states[u]: m.svc('stop',u); stopped.append(u); log('STOPPED '+u)
        w=m.Wire(m.read_port(),log); w.enter()
        ident=w.request(0x01,*m.IDENT)
        if ident['status']!='SUCCESS' or ident['data']!=bytes.fromhex('20 c2'): raise m.ProbeError('identity failed')
        fault=m.monitor_snapshot(w)
        if fault[0x5738]!=b'\x00' or fault[0xA132][28]!=0: raise m.ProbeError('active fault')
        image=bytearray()
        for a in BLOCKS:
            r=w.request(0x05,a,16)
            if r['status']!='SUCCESS' or len(r['data'])!=16: raise m.ProbeError(f'EEPROM read failed 0x{a:04x}')
            image.extend(r['data'])
        out.write_text(json.dumps({f'0x{i:02X}':v for i,v in enumerate(image)},indent=2)+'\n'); log('OUTPUT='+str(out)); log('FAULT_GUARD=PASS'); w.leave(); w.close(); w=None; return 0
    finally:
        if w:
            try:w.close()
            except Exception:pass
        for u in reversed(stopped):
            try:m.svc('start',u); log('RESTORED '+u)
            except Exception as e: log('RESTORE_ERROR '+str(e))
        for sig,h in prev.items(): signal.signal(sig,h)
        os.close(fd)

if __name__=='__main__': raise SystemExit(main())
