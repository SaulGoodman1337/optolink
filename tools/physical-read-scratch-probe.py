#!/opt/optolink/venv/bin/python
"""Bounded read-only probe for the 20C2 Physical_READ copy scratch path.

Proves the fixed low-RAM staging geometry using only allowlisted Physical_READs:
  source 0x3300 with lengths 1,2,7,16,29,32
  prime  0x0700/32
  scratch self-read 0x1933/32
  TX workspace read 0x19A0/32

No write function, no arbitrary address input, no private opcode.
"""
from __future__ import annotations

import argparse
import fcntl
import importlib.util
import os
import signal
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("physical_ram_snapshot",HERE/"physical-ram-snapshot.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

SOURCE=0x3300
PRIME=0x0700
SCRATCH=0x1933
TX_SAMPLE=0x19A0
LENS=(1,2,7,16,29,32)
REPS=3
ORIGINAL_FRAME=m.frame
ALLOWED={(SOURCE,n) for n in LENS} | {(PRIME,32),(SCRATCH,32),(TX_SAMPLE,32)}

def fixed_frame(function:int,address:int,length:int)->bytes:
    if function==0x03 and (address,length) in ALLOWED:
        b=bytes((0x41,0x05,0x00,0x03,address>>8,address&0xff,length))
        return b+bytes((m.checksum(b),))
    return ORIGINAL_FRAME(function,address,length)

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--execute",action="store_true")
    ap.add_argument("--self-test",action="store_true")
    args=ap.parse_args()

    if args.self_test:
        for n in LENS:
            f=fixed_frame(0x03,SOURCE,n)
            assert f[:6]==bytes((0x41,0x05,0x00,0x03,0x33,0x00))
            assert f[6]==n
        f=fixed_frame(0x03,SCRATCH,32)
        assert f.hex()=="4105000319332074"
        print("SELFTEST=PASS")
        return 0

    if not args.execute:
        print("plan only; use --execute for the fixed read-only scratch probe")
        return 0

    m.frame=fixed_frame
    fd=os.open(m.LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    states={u:m.active(u) for u in (m.SCHEDULE,m.PARTY,m.SPLITTER)}
    if not states[m.SPLITTER]:
        raise m.ProbeError("splitter not running before probe")
    changed=[]
    w=None
    previous={sig:signal.getsignal(sig) for sig in m.ABORT}
    for sig in m.ABORT:
        signal.signal(sig,lambda s,f: (_ for _ in ()).throw(m.ProbeError(f"signal {s}")))
    log=lambda s: print(time.strftime("%H:%M:%S"),s,flush=True)

    try:
        for u in (m.SCHEDULE,m.PARTY,m.SPLITTER):
            if states[u]:
                m.svc("stop",u)
                changed.append(u)
                log("STOPPED "+u)

        w=m.Wire(m.read_port(),log)
        w.enter()
        ident=w.request(0x01,*m.IDENT)
        if ident["status"]!="SUCCESS" or ident["data"]!=bytes.fromhex("20 c2"):
            raise m.ProbeError("20C2 identity failed")
        base=m.monitor_snapshot(w)
        if base[0x5738]!=b"\x00" or base[0xA132][28]!=0:
            raise m.ProbeError("baseline active fault")

        for n in LENS:
            for rep in range(REPS):
                prime=w.request(0x03,PRIME,32)
                if prime["status"]!="SUCCESS" or prime["data"]!=b"\x64"*32:
                    raise m.ProbeError("0x0700 prime payload changed")

                src=w.request(0x03,SOURCE,n)
                if src["status"]!="SUCCESS" or src["address"]!=SOURCE or len(src["data"])!=n:
                    raise m.ProbeError(f"source read failed len={n}")

                scratch=w.request(0x03,SCRATCH,32)
                if scratch["status"]!="SUCCESS" or len(scratch["data"])!=32:
                    raise m.ProbeError("scratch read failed")

                # Self-reading the scratch overwrites byte 0 with the checksum of
                # the current 0x1933/32 request (0x74). Bytes 1..N-1 must retain
                # the just-read source payload; bytes N..31 retain the 0x64 prime.
                expected_tail=src["data"][1:]+b"\x64"*(32-n)
                if scratch["data"][0]!=0x74 or scratch["data"][1:]!=expected_tail:
                    raise m.ProbeError(f"scratch geometry mismatch len={n}")

                # Repeat the source read so the immediately following 0x19A0
                # sample sees that source response in the fixed TX workspace.
                src2=w.request(0x03,SOURCE,n)
                tx=w.request(0x03,TX_SAMPLE,32)
                if tx["status"]!="SUCCESS" or len(tx["data"])!=32:
                    raise m.ProbeError("TX workspace read failed")
                payload_off=0x19B5-TX_SAMPLE
                visible=max(0,min(n,32-payload_off))
                got=tx["data"][payload_off:payload_off+visible]
                if got!=src2["data"][:visible]:
                    raise m.ProbeError(f"TX payload mismatch len={n}")

                log(
                    f"PASS len={n:02d} rep={rep} "
                    f"source={src['data'].hex()} scratch={scratch['data'].hex()} "
                    f"tx_visible={got.hex()}"
                )

            m.guard_current(w)

        after=m.monitor_snapshot(w)
        if after[0x5738]!=b"\x00" or after[0xA132][28]!=0:
            raise m.ProbeError("final active fault")
        for a in m.HISTORY:
            if after[a]!=base[a]:
                raise m.ProbeError(f"fault history changed at 0x{a:04x}")
        log("FAULT_GUARD=PASS")
        w.leave()
        return 0
    finally:
        if w:
            try:
                w.close()
            except Exception:
                pass
        for u in reversed(changed):
            try:
                m.svc("start",u)
                log("RESTORED "+u)
            except Exception as exc:
                log("RESTORE_ERROR "+str(exc))
        for sig,h in previous.items():
            signal.signal(sig,h)
        os.close(fd)

if __name__=="__main__":
    raise SystemExit(main())