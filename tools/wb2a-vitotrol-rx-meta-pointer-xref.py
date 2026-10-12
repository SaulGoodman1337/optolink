#!/usr/bin/env python3
"""Offline literal LE16 address scans across attested historical WB2A RAM.

Searching RAM for literal 16-bit addresses can reveal candidate descriptor
bytes, not ownership, a firmware callback, executable code or safe writes.
"""
from __future__ import annotations
from collections import Counter
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("vt_rx_meta_xref_crc",
    ROOT/"wb2a-vitotrol-optolink-rx-audit.py")
if spec is None or spec.loader is None:raise ValueError("archive helper unavailable")
source=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=source
spec.loader.exec_module(source)
TARGETS=(0x161a,0x1642,0x166a,0x166b,0x166c)


class InvalidArchive(ValueError):pass


def literal_hits(image:bytes, targets:tuple[int,...]=TARGETS)->dict:
    if type(image) is not bytes or len(image)!=20480:
        raise InvalidArchive("20K original memory image only")
    out={}
    for t in targets:
        if not 0x400<=t<=0x53ff:raise InvalidArchive("not an ordinary SRAM byte target")
        search=t.to_bytes(2,"little")
        found=[];position=0
        while True:
            pos=image.find(search,position)
            if pos<0:break
            found.append(pos+0x400)
            position=pos+1
        out[f"0x{t:04x}"]=found
    return out


def scan(blob:bytes)->dict:
    if type(blob) is not bytes or hashlib.sha256(blob).hexdigest()!=source.KNOWN_ARCHIVES["fullram"]:
        raise InvalidArchive("unrecognized full RAM archive source")
    allhits={f"0x{x:04x}":Counter() for x in TARGETS}
    with tarfile.open(fileobj=io.BytesIO(blob),mode="r:gz") as tar:
        mf=source._manifest(tar,"p300-fullram")
        for i in range(1,80):
            base=f"snapshots/s{i:05d}"
            meta=json.loads(source._verified(tar,mf,"p300-fullram",base+".json",max_size=8000))
            data=source._verified(tar,mf,"p300-fullram",base+".bin",max_size=20480)
            if len(data)!=20480 or meta.get("complete") is not True:
                raise InvalidArchive("invalid snapshot size/status")
            for label,items in literal_hits(data).items():
                for addr in items:allhits[label][f"0x{addr:04x}"]+=1
    return {
        "mode":"OFFLINE_LE16_LITERAL_RX_CONTEXT_CANDIDATE_SCAN",
        "archive_sha256":source.KNOWN_ARCHIVES["fullram"],
        "samples":79,"targets":{label:{
            "distinct_hit_addresses":len(addresses),
            "positions_observed_79_of_79":sorted(k for k,v in addresses.items() if v==79),
            "all_hit_positions_and_counts":dict(sorted(addresses.items())),
        } for label,addresses in sorted(allhits.items())},
        "literal_hit_proves_pointer":False,
        "ROM_code_xref_analyzed":False,
        "controller_io":0,"controller_writes":0,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("archive",type=Path)
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    if a.archive.is_symlink() or not a.archive.is_file():
        p.error("original regular archive mandatory")
    blob=a.archive.read_bytes()
    if len(blob)>source.MAX_ARCHIVE_BYTES:
        p.error("oversized archive")
    data=scan(blob)
    out=json.dumps(data,sort_keys=True,indent=2)+"\n"
    if a.out:a.out.write_text(out)
    print(out)


if __name__=="__main__":main()
