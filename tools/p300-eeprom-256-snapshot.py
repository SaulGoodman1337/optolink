#!/opt/optolink/venv/bin/python
"""Read-only two-pass snapshot of legacy 8-bit EEPROM_READ space 0x00..0xff."""
from __future__ import annotations
import argparse, fcntl, importlib.util, os, signal, time
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("physical_ram_snapshot",HERE/"physical-ram-snapshot.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
BLOCKS=tuple(range(0x0000,0x0100,0x10)); LEN=16; ORIG=m.frame

def frame(function:int,address:int,length:int)->bytes:
    if function==0x05 and address in BLOCKS and length==LEN:
        b=bytes((0x41,0x05,0x00,0x05,address>>8,address&0xff,length)); return b+bytes((m.checksum(b),))
    return ORIG(function,address,length)
m.frame=frame

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--execute",action="store_true"); ap.add_argument("--self-test",action="store_true"); args=ap.parse_args()
    if args.self_test:
        assert len(BLOCKS)==16 and frame(0x05,0x00F0,16)[3:7]==bytes.fromhex("05 00 f0 10"); print("SELFTEST=PASS"); return 0
    if not args.execute: print("plan only; use --execute"); return 0
    fd=os.open(m.LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600); fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    log=lambda s: print(time.strftime("%H:%M:%S"),s,flush=True)
    states={u:m.active(u) for u in (m.SCHEDULE,m.PARTY,m.SPLITTER)}
    if not states[m.SPLITTER]: raise m.ProbeError("splitter not running")
    changed=[]; w=None; prev={sig:signal.getsignal(sig) for sig in m.ABORT}
    for sig in m.ABORT: signal.signal(sig,lambda s,f: (_ for _ in ()).throw(m.ProbeError(f"signal {s}")))
    try:
        for u in (m.SCHEDULE,m.PARTY,m.SPLITTER):
            if states[u]: m.svc("stop",u); changed.append(u); log("STOPPED "+u)
        w=m.Wire(m.read_port(),log); w.enter()
        ident=w.request(0x01,*m.IDENT)
        if ident["status"]!="SUCCESS" or ident["data"]!=bytes.fromhex("20 c2"): raise m.ProbeError("20C2 identity failed")
        base=m.monitor_snapshot(w)
        if base[0x5738]!=b"\x00" or base[0xA132][28]!=0: raise m.ProbeError("baseline active fault")
        passes=[]
        for pn in (1,2):
            image=bytearray(); errors=[]
            for i,addr in enumerate(BLOCKS):
                r=w.request(0x05,addr,LEN)
                if r["status"]=="SUCCESS" and len(r["data"])==LEN: image.extend(r["data"])
                else: errors.append((addr,r["status"],r["data"].hex())); image.extend(b"\xff"*LEN)
                if (i+1)%4==0: m.guard_current(w)
            passes.append(bytes(image)); log(f"PASS={pn} errors={errors}")
        changed_bytes=sum(a!=b for a,b in zip(*passes)); log(f"DIFF changed={changed_bytes}/256")
        for off in range(0,256,16): log(f"EEPROM {off:02x}: {passes[1][off:off+16].hex()}")
        after=m.monitor_snapshot(w)
        if after[0x5738]!=b"\x00" or after[0xA132][28]!=0: raise m.ProbeError("final active fault")
        for a in m.HISTORY:
            if after[a]!=base[a]: raise m.ProbeError(f"fault history changed at 0x{a:04x}")
        log("FAULT_GUARD=PASS"); w.leave(); return 0
    finally:
        if w:
            try:w.close()
            except Exception:pass
        for u in reversed(changed):
            try:m.svc("start",u); log("RESTORED "+u)
            except Exception as e: log("RESTORE_ERROR "+str(e))
        for sig,h in prev.items(): signal.signal(sig,h)
        os.close(fd)

if __name__=="__main__": raise SystemExit(main())