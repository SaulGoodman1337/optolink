#!/usr/bin/env python3
"""Offline: compare Oct 9 authentic P300 SRAM with independent Oct 11 reads.

Two separate, known live P300 sessions on Oct 11 and one bounded ABA
contrast run are reused strictly as PREEXISTING JSON sources. No hardware,
serial owner, transport mode change, network request, or unpublished ROM
byte is involved. Device identity, READ-ONLY provenance, four pre/post guards
and exact replies are validated before any SRAM comparison.

Source snapshots from Oct 9 are independently attested by SHA/manifest
via wb2a-romcopy-nullmodel-original.py. Pinned raw Oct11 JSON sources
remain private; only aggregate match flags and source SHA are emitted.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location(
    "romcopy_crosssession_original",
    HERE/"wb2a-romcopy-nullmodel-original.py")
if sp is None or sp.loader is None:raise RuntimeError("source verifier unavailable")
original=importlib.util.module_from_spec(sp)
sys.modules[sp.name]=original
sp.loader.exec_module(original)

FILES={
    "contrast":("wb2a-vitotrol-rom-contrast-p300-20261011.json",
        "f5a31879fedf8c0af780f020c29e50c47cb7727c15e6305c955e6ae8f05935d1"),
    "dual":("wb2a-vitotrol-dual-readonly-live-20261011.json",
        "e12a10b500cedbc41cc76e8b54ccba78eecc708c9c71f2e14075a25098bf393e"),
    "dual_high":("wb2a-vitotrol-dual-readonly-high-live-20261011.json",
        "c2896229323eba347620b225ac36263a04ac9b59f9e56d94589e68a6a72d7116"),
}
IDENTITY="20c2000300000103"
CONTRAST_MODE="EXACT_FC03_P300_VS1_CONTRAST_READONLY"
DUAL_MODE="READ_ONLY_NATIVE_P300"
GUARD_ADDRESSES=(0x27A0,0x27B0,0x7342,0x5738)


class SourceMismatch(ValueError):
    pass


def original_json(path:Path,expected_name:str,expected_sha:str)->dict:
    if (not isinstance(path,Path) or path.name!=expected_name or
        path.is_symlink() or not path.is_file() or
        not 500<=path.stat().st_size<=100000):
        raise SourceMismatch("not pinned private historical JSON filename/length")
    data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=expected_sha:
        raise SourceMismatch("original October 11 live JSON SHA is altered")
    root=json.loads(data)
    if not isinstance(root,dict):
        raise SourceMismatch("not a historical observation record")
    return root


def _row(row:dict,addr:int,n:int)->bytes:
    if not isinstance(row,dict):raise SourceMismatch("missing historical P300 read")
    token=f"0x{addr:04x}"
    command=f"request;3;{token};{n}"
    if (row.get("address")!=token or row.get("command")!=command or
        row.get("controller_read_only") is not True or
        row.get("valid_read") is not True or
        type(row.get("data")) is not str or len(row["data"])!=2*n):
        raise SourceMismatch("incorrect or not clearly read-only historical request")
    try:data=bytes.fromhex(row["data"])
    except ValueError as exc:raise SourceMismatch("invalid original P300 response bytes") from exc
    if len(data)!=n:raise SourceMismatch("response byte count inconsistent")
    return data


def _identity_and_safety(info:dict,mode:str,pre:str,post:str)->None:
    if (info.get("mode")!=mode or info.get("target")!="20C2/0103"
        or type(info.get("controller_writes")) is not int or
        info.get("controller_writes")!=0):
        raise SourceMismatch("not an exact validated target/mode/zero-write capture")
    identity=info.get("identity")
    if not isinstance(identity,dict) or identity.get("data")!=IDENTITY:
        raise SourceMismatch("not exact verified 20C2/0103 software")
    if (identity.get("controller_read_only") is not True or
        identity.get("valid_read") is not True or
        identity.get("address") != "0x00f8" or
        identity.get("command") != "read;0x00f8;8"):
        raise SourceMismatch("target identity read was not exact verified read-only")
    first,last=info.get(pre),info.get(post)
    if (type(first) is not list or type(last) is not list
        or len(first)!=4 or len(last)!=4):
        raise SourceMismatch("missing four pre/post device-state guards")
    for batch in (first,last):
        for i,(guard,address) in enumerate(zip(batch,GUARD_ADDRESSES)):
            token=f"0x{address:04x}"
            if (not isinstance(guard,dict) or guard.get("data")!="00"
                or guard.get("address")!=token
                or guard.get("command")!=f"read;{token};1"
                or guard.get("valid_read") is not True
                or guard.get("controller_read_only") is not True):
                raise SourceMismatch("historical fault/participant state guard did not pass")


def compare(original_images:list[bytes], live_sources:dict[str,dict])->dict:
    mask=original.stable_mask(original_images)
    if original.scan_for_shape(original_images[0],mask)!=original.EXACT_EXPECTED:
        raise SourceMismatch("archive had no authentic two copy-looking candidates")
    assert original.BASE==0x0400
    orig=original_images[0]
    original_A=orig[0x1DE5-0x400:0x1DE5-0x400+8]
    original_B=orig[0x1E6A-0x400:0x1E6A-0x400+8]
    original_A_target=orig[0x3301-0x400:0x3301-0x400+29]
    original_tail16=orig[0x2182-0x400:0x2182-0x400+16]
    if set(live_sources)!={"contrast","dual","dual_high"}:
        raise SourceMismatch("exact three historical original sessions required")
    a_seen=b_seen=target_seen=0
    change_indexes=[]
    contrast=live_sources["contrast"]
    _identity_and_safety(contrast,CONTRAST_MODE,"preflight","postflight")
    if (contrast.get("physical_high_rom_banks_addressable") is not False or
        type(contrast.get("cycles")) is not list or len(contrast["cycles"])!=2):
        raise SourceMismatch("not exact historical low SRAM ABA experiment")
    for i,cycle in enumerate(contrast["cycles"]):
        if not isinstance(cycle,dict) or cycle.get("index")!=i:
            raise SourceMismatch("wrong sequence of independent contrast reads")
        reads=cycle.get("reads")
        if not isinstance(reads,dict):
            raise SourceMismatch("missing contrast RAM objects")
        if _row(reads.get("physical_1de5"),0x1DE5,16)[:8]!=original_A:
            raise SourceMismatch("far-shaped A tuple drifted in Oct11 contrast")
        a_seen+=1
        if _row(reads.get("physical_3300"),0x3300,32)[1:30]!=original_A_target:
            raise SourceMismatch("A 29-byte SRAM target drifted in Oct11 contrast")
        target_seen+=1
        newer=_row(reads.get("physical_2182"),0x2182,16)
        different=[j for j,(a,b) in enumerate(zip(newer,original_tail16)) if a!=b]
        change_indexes.append(different)

    for name in ("dual","dual_high"):
        info=live_sources[name]
        _identity_and_safety(info,DUAL_MODE,"baseline","after")
        if info.get("code_execution_or_rom_mapping_proven") is not False:
            raise SourceMismatch("previous session asserts unsupported ROM map")
        rows=info.get("copy_context")
        if not isinstance(rows,list) or len(rows)!=3:
            raise SourceMismatch("missing pinned low-RAM copy context")
        sections={x.get("address"):x for x in rows if isinstance(x,dict)}
        if set(sections)!={"0x1de0","0x1e60","0x3300"}:
            raise SourceMismatch("wrong complete copy-context addresses")
        if _row(sections["0x1de0"],0x1DE0,32)[5:13]!=original_A:
            raise SourceMismatch("A tuple drifted in dual session")
        a_seen+=1
        if _row(sections["0x1e60"],0x1E60,32)[10:18]!=original_B:
            raise SourceMismatch("B tuple drifted in dual session")
        b_seen+=1
        if _row(sections["0x3300"],0x3300,32)[1:30]!=original_A_target:
            raise SourceMismatch("A target drifted in dual session")
        target_seen+=1
    # The 0x2182 change is a useful independent-sample control: some SRAM
    # changed by Oct11, even while the two tuples and target A did not.
    return {
        "audit":"PASS",
        "target":"20C2/0103",
        "oct9_complete_FC03_ram_images":len(original_images),
        "oct11_verified_independent_original_JSON_sources":len(FILES),
        "oct11_2cycle_contrast_starts":2,
        "A_8byte_tuple_oct11_compared_observations":a_seen,
        "A_29byte_target_oct11_compared_observations":target_seen,
        "B_8byte_tuple_oct11_compared_observations":b_seen,
        "A_tuple_equal_oct9":True,
        "A_target_equal_oct9":True,
        "B_tuple_equal_oct9":True,
        "oct11_tail_2182_16byte_differences_offset_lists":change_indexes,
        "Oct11_tail_0x2184_is_different_from_Oct9":all(2 in x for x in change_indexes),
        "A_target_ROM_provenance_verified":False,
        "B_target_oct11_independently_read":False,
        "ROM_to_RAM_copy_causality_proven":False,
        "real_ROM_bytes":0,
        "live_controller_reads":0,
        "live_controller_writes":0,
        "historical_P300_reads_not_atomic":True,
        "oct12_post_C5F9_controller_reboot_ram_snapshot_included":False,
        "sources_sha256": {k:v[1] for k,v in FILES.items()},
        "oct9_RAM_archive_sha256":original.ARCHIVE_SHA256,
    }


def audit(archive:Path,json_directory:Path)->dict:
    if (archive.is_symlink() or not archive.is_file() or
        archive.stat().st_size!=original.ARCHIVE_SIZE):
        raise SourceMismatch("unrecognized historical Oct9 archive")
    images=original.attested_images(archive.read_bytes())
    data={key:original_json(json_directory/filename,filename,sha)
          for key,(filename,sha) in FILES.items()}
    return compare(images,data)


def main()->None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--original-archive",type=Path,required=True)
    p.add_argument("--json-directory",type=Path,required=True)
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    output=json.dumps(audit(a.original_archive,a.json_directory),
                      indent=2,sort_keys=True)+"\n"
    if a.out:a.out.write_text(output,encoding="utf-8")
    print(output,end="")


if __name__=="__main__":
    try:main()
    except (OSError,SourceMismatch,original.InvalidArchiveOrHypothesis,
            ValueError,KeyError,json.JSONDecodeError) as err:
        print("CROSSSESSION_PROVENANCE_REJECTED: "+str(err),file=sys.stderr)
        raise SystemExit(2)
