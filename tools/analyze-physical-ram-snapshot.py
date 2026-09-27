#!/usr/bin/env python3
"""Offline analyzer for paired 20C2 Physical_READ RAM snapshots.

The expected image is the fixed 0x0400..0x53ff region captured by
physical-ram-snapshot.py. This tool performs no device I/O.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

BASE=0x0400
END=0x53FF
SIZE=END-BASE+1
PROGRAM_MIN=0xC0000
PROGRAM_MAX=0xFFFFF
SFR16={"U0TB":0x03A2,"U1TB":0x03AA,"DM0SL":0x03B8,"DM1SL":0x03BA}

def p300_frames(buf:bytes):
    out=[]
    for i in range(len(buf)-7):
        if buf[i] != 0x41: continue
        n=buf[i+1]
        total=n+3
        if not 1 <= n <= 64 or i+total > len(buf): continue
        msg=buf[i:i+total]
        if (sum(msg[1:-1]) & 0xff) != msg[-1]: continue
        out.append({"address":BASE+i,"type":msg[2]&0x0f,"function":msg[3],"frame":msg.hex()})
    return out

def occurrences(buf:bytes,pat:bytes):
    out=[]; s=0
    while True:
        i=buf.find(pat,s)
        if i<0: return out
        out.append(BASE+i); s=i+1

def far_pointers(a:bytes,b:bytes,alignment:int=4):
    out=[]
    for i in range(0,SIZE-3,alignment):
        if a[i:i+4] != b[i:i+4]: continue
        v=int.from_bytes(b[i:i+4],"little")
        if PROGRAM_MIN <= v <= PROGRAM_MAX:
            out.append({"ram_address":BASE+i,"target":v,"bytes":b[i:i+8].hex()})
    return out

def page_diff(a:bytes,b:bytes):
    return [{"address":BASE+off,"changed":sum(x!=y for x,y in zip(a[off:off+0x100],b[off:off+0x100]))}
            for off in range(0,SIZE,0x100)]

def fill_runs(buf:bytes,value:int=0x55,min_len:int=8):
    out=[]; i=0
    while i<len(buf):
        if buf[i] != value:
            i+=1; continue
        j=i+1
        while j<len(buf) and buf[j]==value: j+=1
        if j-i>=min_len: out.append({"start":BASE+i,"end":BASE+j-1,"length":j-i})
        i=j
    return out

def far_pointer_density(a:bytes,b:bytes,window:int=0x40):
    rows=[]
    for off in range(0,SIZE,window):
        hits=[]
        for i in range(off,min(off+window,SIZE-3)):
            if a[i:i+4] != b[i:i+4]: continue
            v=int.from_bytes(b[i:i+4],"little")
            if PROGRAM_MIN <= v <= PROGRAM_MAX:
                hits.append({"ram_address":BASE+i,"target":v})
        if hits: rows.append({"start":BASE+off,"end":BASE+off+window-1,"hits":hits})
    rows.sort(key=lambda x:len(x["hits"]),reverse=True)
    return rows

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("pass1",type=Path); ap.add_argument("pass2",type=Path)
    ap.add_argument("--json",type=Path)
    args=ap.parse_args()
    a=args.pass1.read_bytes(); b=args.pass2.read_bytes()
    if len(a)!=SIZE or len(b)!=SIZE: raise SystemExit(f"expected {SIZE} bytes per image")
    changed=[BASE+i for i,(x,y) in enumerate(zip(a,b)) if x!=y]
    frames1=p300_frames(a); frames2=p300_frames(b)
    ptr4=far_pointers(a,b,4)
    report={
      "range":{"start":BASE,"end":END,"size":SIZE},
      "sha256_pass1":hashlib.sha256(a).hexdigest(),
      "sha256_pass2":hashlib.sha256(b).hexdigest(),
      "changed_bytes":len(changed),"stable_bytes":SIZE-len(changed),
      "page_diff":page_diff(a,b),
      "p300_frames_pass1":frames1,"p300_frames_pass2":frames2,
      "stable_far_pointers_aligned4":ptr4,
      "stable_far_pointer_density_64":far_pointer_density(a,b),
      "fill_55_runs_pass2":fill_runs(b),
      "sfr_literal_occurrences":{k:[f"0x{x:04x}" for x in occurrences(b,v.to_bytes(2,"little"))] for k,v in SFR16.items()},
      "ring":{
        "base_literal_occurrences":[f"0x{x:04x}" for x in occurrences(b,(0x19EE).to_bytes(2,"little"))],
        "region_sha256_pass1":hashlib.sha256(a[0x19EE-BASE:0x1A6E-BASE]).hexdigest(),
        "region_sha256_pass2":hashlib.sha256(b[0x19EE-BASE:0x1A6E-BASE]).hexdigest(),
        "descriptor_1a6e_1a8f_pass1":a[0x1A6E-BASE:0x1A90-BASE].hex(),
        "descriptor_1a6e_1a8f_pass2":b[0x1A6E-BASE:0x1A90-BASE].hex(),
      }
    }
    print(f"RAM 0x{BASE:04X}..0x{END:04X}: {SIZE} bytes")
    print(f"changed={len(changed)} stable={SIZE-len(changed)}")
    print(f"valid P300-like frames: pass1={len(frames1)} pass2={len(frames2)}")
    for f in frames2: print(f"  RAM 0x{f['address']:04X}: type={f['type']} fc=0x{f['function']:02X} {f['frame']}")
    print(f"stable 4-byte-aligned far/program pointers={len(ptr4)}")
    for p in ptr4: print(f"  RAM 0x{p['ram_address']:04X} -> 0x{p['target']:05X}")
    for rr in report["fill_55_runs_pass2"]: print(f"0x55 run: 0x{rr['start']:04X}..0x{rr['end']:04X} len={rr['length']}")
    for rr in report["stable_far_pointer_density_64"][:5]: print(f"pointer-dense: 0x{rr['start']:04X}..0x{rr['end']:04X} hits={len(rr['hits'])}")
    for k,v in report['sfr_literal_occurrences'].items(): print(f"{k} literal: {','.join(v) if v else '-'}")
    print("ring base 0x19EE literal: "+(','.join(report['ring']['base_literal_occurrences']) or '-'))
    if args.json:
        args.json.write_text(json.dumps(report,indent=2)+"\n")
        print("JSON="+str(args.json))

if __name__=="__main__": main()