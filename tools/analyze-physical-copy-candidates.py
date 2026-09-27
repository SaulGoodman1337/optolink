#!/usr/bin/env python3
"""Offline scanner for ROM-to-RAM-like 3+3+2 tuples in paired RAM snapshots.

Looks for stable 8-byte layouts containing one high 20-bit program-range pointer,
one low-RAM pointer and a small count. No hardware access is performed.
"""
from __future__ import annotations
import argparse
from pathlib import Path

BASE=0x0400
END=0x53FF
SIZE=END-BASE+1

def scan(a:bytes,b:bytes):
    out=[]
    for i in range(0,SIZE-7):
        if a[i:i+8]!=b[i:i+8]:
            continue
        d=a[i:i+8]
        addr=BASE+i
        src=int.from_bytes(d[0:3],"little")
        dst=int.from_bytes(d[3:6],"little")
        cnt=int.from_bytes(d[6:8],"little")
        if 0xC0000<=src<=0xFFFFF and BASE<=dst<=END and 1<=cnt<=256:
            out.append(("src3-dst3-cnt2",addr,src,dst,cnt,d.hex()))
        dst=int.from_bytes(d[0:3],"little")
        src=int.from_bytes(d[3:6],"little")
        cnt=int.from_bytes(d[6:8],"little")
        if BASE<=dst<=END and 0xC0000<=src<=0xFFFFF and 1<=cnt<=256:
            out.append(("dst3-src3-cnt2",addr,src,dst,cnt,d.hex()))
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("pass1",type=Path)
    ap.add_argument("pass2",type=Path)
    args=ap.parse_args()
    a=args.pass1.read_bytes(); b=args.pass2.read_bytes()
    if len(a)!=SIZE or len(b)!=SIZE:
        raise SystemExit(f"expected {SIZE}-byte snapshots")
    rows=scan(a,b)
    print(f"stable_copy_shape_candidates={len(rows)}")
    for typ,addr,src,dst,cnt,raw in rows:
        off=dst-BASE
        payload=a[off:off+cnt]
        payload2=b[off:off+cnt]
        print(f"{typ} ram=0x{addr:04X} src=0x{src:05X} dst=0x{dst:04X} "
              f"count={cnt} dest_stable={payload==payload2} "
              f"dest={payload.hex()} raw={raw}")

if __name__=="__main__":
    main()