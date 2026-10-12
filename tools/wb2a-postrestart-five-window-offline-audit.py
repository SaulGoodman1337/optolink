#!/usr/bin/env python3
"""SHA-pinned Oct 12 P300 five-window live read vs 79 verified Oct 9 images.

Strictly OFFLINE original-source audit; fault archives optional in this tool.
Data provenance comes from live host logger, not from independent controller
authentication. Matching SRAM is not proof of ROM, copied data or reset cause.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
SOURCE=HERE/"wb2a-romcopy-nullmodel-original.py"
sp=importlib.util.spec_from_file_location("fivewin_pinned_romcopy_orig",SOURCE)
if sp is None or sp.loader is None:raise RuntimeError("strict original 79-sample validator absent")
m=importlib.util.module_from_spec(sp)
sys.modules[sp.name]=m
sp.loader.exec_module(m)
MODE="EXACT_POSTRESTART_FC03_P300_FIVE_WINDOWS_READ_ONLY"
ID="20c2000300000103"
PINNED_LIVE_SHA="ed290530bdd718dd044bd57b07d94c160fb15728a74f3486872cd12fcaa64549"
WINDOWS={
    "ram_1de0":(0x1DE0,32),
    "ram_1e60":(0x1E60,32),
    "ram_3300":(0x3300,32),
    "ram_0700":(0x0700,32),
    "ram_2180":(0x2180,32),
}
SLICES={
    "A_8byte_descriptor":("ram_1de0",5,8,0x1DE5),
    "B_8byte_descriptor":("ram_1e60",10,8,0x1E6A),
    "A_29byte_target":("ram_3300",1,29,0x3301),
    "B_7byte_target":("ram_0700",5,7,0x0705),
    "control_byte_2184":("ram_2180",4,1,0x2184),
}
CHECKS=(0x27A0,0x27B0,0x7342,0x5738)

class SourceRejected(ValueError):
    pass

def verified_row(row,command,address,n):
    if (not isinstance(row,dict) or row.get("command")!=command or
        row.get("address")!=f"0x{address:04x}" or row.get("valid_read") is not True
        or row.get("controller_read_only") is not True or
        type(row.get("data")) is not str or len(row["data"])!=2*n):
        raise SourceRejected("malformed or non-read-only P300 log record")
    try:value=bytes.fromhex(row["data"])
    except ValueError as e:raise SourceRejected("response hex malformed") from e
    if len(value)!=n:raise SourceRejected("invalid fixed size")
    return value

def decode_capture(raw):
    if type(raw) is not bytes or hashlib.sha256(raw).hexdigest()!=PINNED_LIVE_SHA:
        raise SourceRejected("live file byte-level SHA256 changed")
    cap=json.loads(raw)
    if (cap.get("schema")!=1 or cap.get("mode")!=MODE or cap.get("target")!="20C2/0103"
        or cap.get("controller_reads")!=19 or cap.get("controller_writes")!=0
        or cap.get("one_serial_owner") is not True
        or cap.get("ordinary_16bit_low_sram_FC03_only") is not True):
        raise SourceRejected("wrong capture mode/controller command budget")
    ident=verified_row(cap.get("identity"),"read;0x00f8;8",0x00f8,8)
    if ident.hex()!=ID:raise SourceRejected("identity changed")
    for name in ("preflight","postflight"):
        rows=cap.get(name)
        if not isinstance(rows,list) or len(rows)!=4:raise SourceRejected("missing guard")
        for i,addr in enumerate(CHECKS):
            if verified_row(rows[i],f"read;0x{addr:04x};1",addr,1)!=b"\x00":
                raise SourceRejected("nonzero pre/post controller fault guard")
    cycles=cap.get("cycles")
    if not isinstance(cycles,list) or len(cycles)!=2:raise SourceRejected("wrong number of cycles")
    decoded=[]
    for i,cy in enumerate(cycles):
        if cy.get("index")!=i or set(cy.get("reads",{}))!=set(WINDOWS):
            raise SourceRejected("unexpected or out-of-order physical RAM commands")
        parsed={}
        for name,(addr,n) in WINDOWS.items():
            parsed[name]=verified_row(cy["reads"][name],f"request;3;0x{addr:04x};{n}",addr,n)
        decoded.append(parsed)
    return decoded

def old_at(image,addr,n):
    i=addr-m.BASE
    if i<0 or i+n>len(image):raise SourceRejected("out-of-range historical SRAM")
    return image[i:i+n]

def compare(originals, capture):
    mask=m.stable_mask(originals)
    if m.scan_for_shape(originals[0],mask)!=m.EXACT_EXPECTED:
        raise SourceRejected("old 79-image far-pointer original certificate changed")
    parsed=decode_capture(capture)
    result={}
    for name,(addr,n) in WINDOWS.items():
        values=[r[name] for r in parsed]
        oldvalues=[old_at(image,addr,n) for image in originals]
        between=[i for i in range(n) if values[0][i]!=values[1][i]]
        result[name]={
            "address":f"0x{addr:04x}","bytes":n,
            "new_two_cycle_exact_match":not between,
            "new_two_cycle_changed_addresses":[f"0x{addr+i:04x}" for i in between],
            "vs_oct9_first_image_changed_bytes":[
                sum(x!=y for x,y in zip(v,oldvalues[0])) for v in values],
            "vs_oct9_79_images_exact_match_counts":[sum(v==x for x in oldvalues) for v in values],
            "oct9_stable_positions_within_window":sum(mask[addr-m.BASE:addr-m.BASE+n]),
        }
    fields={}
    for name,(window,offset,n,addr) in SLICES.items():
        old=[old_at(image,addr,n) for image in originals]
        new=[x[window][offset:offset+n] for x in parsed]
        fields[name]={
            "address":f"0x{addr:04x}","bytes":n,
            "new_two_cycle_identical":new[0]==new[1],
            "new_two_cycle_vs_oct9_first_matches":[z==old[0] for z in new],
            "new_two_cycle_oct9_exact_match_counts":[sum(z==b for b in old) for z in new],
            "old_distinct_values_across_79_images":len(set(old)),
            "changed_relative_to_old_first":[sum(a!=b for a,b in zip(z,old[0])) for z in new],
        }
    return {
        "audit":"PASS",
        "old_79_image_sha256":m.ARCHIVE_SHA256,
        "new_original_live_capture_sha256":PINNED_LIVE_SHA,
        "device":"20C2/0103",
        "old_complete_nonatomic_snapshots":len(originals),
        "new_read_only_FC03_requests":10,
        "new_own_log_full_read_count":19,
        "controller_writes":0,
        "windows":result,
        "candidate_fields":fields,
        "program_ROM_bytes_recovered":0,
        "ROM_to_SRAM_transfer_proven":False,
        "timing_of_controller_restart_proven_by_capture":False,
        "original_live_capture_authenticated_by_controller_signature":False,
        "origin":"private independently pinned original Oct9 tar + Oct12 host result",
    }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--oct9",type=Path,required=True)
    p.add_argument("--oct12",type=Path,required=True)
    p.add_argument("--output",type=Path)
    a=p.parse_args()
    if a.oct9.is_symlink() or a.oct12.is_symlink():
        raise SourceRejected("unexpected symlink")
    images=m.attested_images(a.oct9.read_bytes())
    cap=a.oct12.read_bytes()
    result=compare(images,cap)
    result_json=json.dumps(result,sort_keys=True,indent=2)+"\n"
    if a.output:a.output.write_text(result_json,encoding="utf-8")
    print(result_json,end="")

if __name__=="__main__":
    try:main()
    except (SourceRejected,m.InvalidArchiveOrHypothesis,ValueError,KeyError,OSError) as err:
        print("ORIGINAL_P300_COMPARISON_REJECTED:",err,file=sys.stderr)
        sys.exit(2)
