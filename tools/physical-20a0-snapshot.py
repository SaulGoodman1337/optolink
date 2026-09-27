#!/opt/optolink/venv/bin/python
from __future__ import annotations
import fcntl,importlib.util,os,signal,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('base',HERE/'physical-ram-snapshot.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
BLOCK=0x20A0; ORIG=m.frame

def frame(function,address,length):
    if function==0x03 and address==BLOCK and length==32:
        b=bytes((0x41,0x05,0x00,0x03,address>>8,address&0xff,32)); return b+bytes((m.checksum(b),))
    return ORIG(function,address,length)
m.frame=frame

def main():
    fd=os.open(m.LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600); fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    log=lambda x: print(time.strftime('%H:%M:%S'),x,flush=True); states={u:m.active(u) for u in (m.SCHEDULE,m.PARTY,m.SPLITTER)}; stopped=[]; w=None
    try:
        for u in (m.SCHEDULE,m.PARTY,m.SPLITTER):
            if states[u]: m.svc('stop',u); stopped.append(u)
        w=m.Wire(m.read_port(),log); w.enter(); ident=w.request(0x01,*m.IDENT)
        if ident['status']!='SUCCESS' or ident['data']!=bytes.fromhex('20 c2'): raise m.ProbeError('identity failed')
        fault=m.monitor_snapshot(w)
        if fault[0x5738]!=b'\x00' or fault[0xA132][28]!=0: raise m.ProbeError('active fault')
        r=w.request(0x03,BLOCK,32)
        if r['status']!='SUCCESS' or len(r['data'])!=32: raise m.ProbeError('read failed')
        print('BLOCK20A0='+r['data'].hex()); w.leave(); w.close(); w=None; return 0
    finally:
        if w:
            try:w.close()
            except:pass
        for u in reversed(stopped):
            try:m.svc('start',u)
            except:pass
        os.close(fd)
if __name__=='__main__': raise SystemExit(main())
