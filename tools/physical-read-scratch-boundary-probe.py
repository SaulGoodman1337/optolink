#!/opt/optolink/venv/bin/python
"""Read-only boundary probe for Physical_READ scratch capacity.

Reads fixed source 0x3300 with lengths 33/40/48/56, then samples 0x1960/32.
If scratch at 0x1933 extends beyond 32 bytes, source tail bytes should appear
at 0x1960.. before the fixed RX request workspace begins at 0x196c.
No writes, private opcodes, or arbitrary addresses.
"""
from __future__ import annotations
import argparse, fcntl, importlib.util, os, signal, time
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("physical_ram_snapshot",HERE/"physical-ram-snapshot.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

SOURCE=0x3300
OBS=0x1960
LENS=(48,49,50,51,52,53,54,55,56)
REPS=3
ORIG=m.frame
ALLOWED={(SOURCE,n) for n in LENS}|{(OBS,32)}

def fixed_frame(function,address,length):
    if function==0x03 and (address,length) in ALLOWED:
        b=bytes((0x41,0x05,0x00,0x03,address>>8,address&0xff,length))
        return b+bytes((m.checksum(b),))
    return ORIG(function,address,length)
m.frame=fixed_frame

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--execute",action="store_true")
    ap.add_argument("--self-test",action="store_true")
    args=ap.parse_args()
    if args.self_test:
        for n in LENS:
            assert fixed_frame(0x03,SOURCE,n)[6]==n
        assert fixed_frame(0x03,OBS,32).hex()=="41050003196020a1"
        print("SELFTEST=PASS"); return 0
    if not args.execute:
        print("plan only; use --execute"); return 0
    fd=os.open(m.LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    log=lambda s: print(time.strftime("%H:%M:%S"),s,flush=True)
    states={u:m.active(u) for u in (m.SCHEDULE,m.PARTY,m.SPLITTER)}
    if not states[m.SPLITTER]: raise m.ProbeError("splitter not running")
    changed=[]; w=None
    prev={sig:signal.getsignal(sig) for sig in m.ABORT}
    for sig in m.ABORT:
        signal.signal(sig,lambda s,f: (_ for _ in ()).throw(m.ProbeError(f"signal {s}")))
    try:
        for u in (m.SCHEDULE,m.PARTY,m.SPLITTER):
            if states[u]: m.svc("stop",u); changed.append(u); log("STOPPED "+u)
        w=m.Wire(m.read_port(),log); w.enter()
        ident=w.request(0x01,*m.IDENT)
        if ident["status"]!="SUCCESS" or ident["data"]!=bytes.fromhex("20 c2"):
            raise m.ProbeError("identity failed")
        base=m.monitor_snapshot(w)
        if base[0x5738]!=b"\x00" or base[0xA132][28]!=0:
            raise m.ProbeError("baseline active fault")

        for n in LENS:
            for rep in range(REPS):
                src=w.request(0x03,SOURCE,n)
                expected_len=min(n,55)
                if src["status"]!="SUCCESS" or len(src["data"])!=expected_len:
                    raise m.ProbeError(f"source failed n={n} got={len(src['data'])}")
                obs=w.request(0x03,OBS,32)
                if obs["status"]!="SUCCESS" or len(obs["data"])!=32:
                    raise m.ProbeError("observation failed")
                # Scratch starts 0x1933. OBS starts at scratch offset 0x2d = 45.
                tail_off=OBS-0x1933
                effective=len(src["data"])
                expected=src["data"][tail_off:effective] if effective>tail_off else b""
                got=obs["data"][:len(expected)]
                ok=(got==expected)
                log(f"N={n:02d} rep={rep} source={src['data'].hex()} obs={obs['data'].hex()} tail_off={tail_off} expected={expected.hex()} got={got.hex()} match={int(ok)}")
                if not ok:
                    raise m.ProbeError(f"scratch tail mismatch n={n}")
            m.guard_current(w)
        after=m.monitor_snapshot(w)
        if after[0x5738]!=b"\x00" or after[0xA132][28]!=0:
            raise m.ProbeError("final active fault")
        for a in m.HISTORY:
            if after[a]!=base[a]: raise m.ProbeError(f"fault history changed 0x{a:04x}")
        log("FAULT_GUARD=PASS"); w.leave(); return 0
    finally:
        if w:
            try:w.close()
            except Exception:pass
        for u in reversed(changed):
            try:m.svc("start",u); log("RESTORED "+u)
            except Exception as exc:log("RESTORE_ERROR "+str(exc))
        for sig,h in prev.items(): signal.signal(sig,h)
        os.close(fd)
if __name__=="__main__": raise SystemExit(main())