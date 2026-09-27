#!/usr/bin/env python3
"""Offline classifier for M16C-style 11-byte scheduler records in RAM snapshots.

Input files are raw 0x0400..0x53ff Physical_READ snapshots.
No hardware access is performed.
"""
from __future__ import annotations
import argparse
from pathlib import Path

BASE=0x0400
END=0x53FF
SIZE=END-BASE+1

def records(data:bytes):
    out=[]
    for i in range(0,len(data)-10):
        a=BASE+i
        nxt=int.from_bytes(data[i:i+2],"little")
        cb=int.from_bytes(data[i+2:i+6],"little")
        tick=int.from_bytes(data[i+6:i+8],"little")
        period=int.from_bytes(data[i+8:i+10],"little")
        flag=data[i+10]
        if (nxt==0 or BASE<=nxt<=END) and 0xC0000<=cb<=0xFFFFF and period<=20000 and flag in (0,1):
            out.append((a,nxt,cb,tick,period,flag))
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("snapshot",type=Path)
    ap.add_argument("--compare",type=Path)
    args=ap.parse_args()
    data=args.snapshot.read_bytes()
    if len(data)!=SIZE:
        raise SystemExit(f"expected {SIZE} bytes, got {len(data)}")
    a=records(data)
    b=records(args.compare.read_bytes()) if args.compare else []
    common_addrs={r[0] for r in a} & {r[0] for r in b} if b else set()
    print(f"snapshot_records={len(a)}")
    if b:
        print(f"compare_records={len(b)} common_addresses={len(common_addrs)}")
    for rec in a:
        addr,nxt,cb,tick,period,flag=rec
        common=" common" if addr in common_addrs else ""
        print(f"0x{addr:04X} next=0x{nxt:04X} callback=0x{cb:05X} "
              f"tick=0x{tick:04X} period={period} flag={flag}{common}")
    if b:
        print("\nCOMMON_RECORDS")
        bm={r[0]:r for r in b}
        for r in a:
            if r[0] not in common_addrs: continue
            q=bm[r[0]]
            static=(r[1],r[2],r[4],r[5])==(q[1],q[2],q[4],q[5])
            print(f"0x{r[0]:04X} callback=0x{r[2]:05X} period={r[4]} "
                  f"flag={r[5]} tick1=0x{r[3]:04X} tick2=0x{q[3]:04X} "
                  f"static_fields_equal={static}")

if __name__=="__main__":
    main()