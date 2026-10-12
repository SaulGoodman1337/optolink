#!/usr/bin/env python3
"""Cross-validate rare RX 32B FC03 copy against pinned historic 79 RAM images.

This never contacts the controller. It confirms that a full 32-byte source
window 0x164b..0x166a observed in an Oct 11 single P300 READ precisely
matches snapshot 64 of Oct 9, and checks the old frame and CRC.
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

HERE=Path(__file__).resolve().parent
ORIGINAL_SHA="d22dfbc58cad99798be16aac9bf8b9c55598eeb35f25316b54690bffc5c3a258"
HISTORIC_SHA="94d5842b6dc5759ecb446a4c617b60b72873b639885d116032f783abdef8431c"
START=0x164B
SIZE=32


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,HERE/path)
    if spec is None or spec.loader is None:raise RuntimeError("original helper missing")
    m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m
    spec.loader.exec_module(m)
    return m


fused=module("wb2a_cross_fused","wb2a-vitotrol-fused-rx-audit.py")
ram=module("wb2a_cross_ram","wb2a-vitotrol-optolink-rx-audit.py")


class InvalidEvidence(ValueError):pass


def compare_windows(archived:dict[str,list[int]], live:list[bytes]) -> dict:
    if not isinstance(archived,dict) or len(archived)<1 or not isinstance(live,list) or not live:
        raise InvalidEvidence("both populations required")
    if any(not isinstance(b,bytes) or len(b)!=SIZE for b in live):
        raise InvalidEvidence("exact 32B live source windows required")
    if any(len(k)!=SIZE*2 for k in archived):
        raise InvalidEvidence("32B archive windows only")
    common=Counter(w.hex() for w in live)
    match=sorted(set(common)&set(archived))
    mismatched=sorted(set(common)-set(archived))
    differences=[]
    most=common.most_common(1)[0][0]
    for other,n in common.items():
        if other==most:continue
        changed=[f"0x{START+i:04x}" for i,(a,b) in enumerate(zip(
            bytes.fromhex(most),bytes.fromhex(other))) if a!=b]
        differences.append({"window_hex":other,"occurrences":n,
                            "different_addresses_from_modal_live":changed})
    return {
        "archive_unique_32byte_patterns":len(archived),
        "live_total_32byte_samples":len(live),
        "live_unique_patterns":len(common),
        "identical_32byte_archive_and_live_patterns":[
            {"hex":x,"live_count":common[x],
             "archive_snapshot_ids":archived[x],
             "matches_all_32_bytes":True} for x in match
        ],
        "live_only_pattern_counts":{h:common[h] for h in mismatched},
        "live_pattern_differences":differences,
        "two_bytes_in_one_copy_not_full_uart_ISR_atomicity":True,
    }


def run(capture:bytes,historic:bytes) -> dict:
    if not isinstance(capture,bytes) or hashlib.sha256(capture).hexdigest()!=ORIGINAL_SHA:
        raise InvalidEvidence("not the authentic fused live source")
    if not isinstance(historic,bytes) or hashlib.sha256(historic).hexdigest()!=HISTORIC_SHA:
        raise InvalidEvidence("not the authentic historical fullRAM source")
    report=fused.inspect(json.loads(capture))
    archived={}
    legacy={}
    with tarfile.open(fileobj=io.BytesIO(historic),mode="r:gz") as tar:
        manifest=ram._manifest(tar,"p300-fullram")
        for i in range(1,80):
            prefix=f"snapshots/s{i:05d}"
            metadata=json.loads(ram._verified(tar,manifest,"p300-fullram",prefix+".json",max_size=8000))
            if (metadata.get("complete") is not True or metadata.get("marker")!="COMPLETE"
                or metadata.get("device_id")!="20c2" or metadata.get("software")!="0103"):
                raise InvalidEvidence("wrong original capture image metadata")
            image=ram._verified(tar,manifest,"p300-fullram",prefix+".bin",max_size=20_480)
            if len(image)!=20_480:raise InvalidEvidence("partial RAM image")
            window=image[START-0x400:START-0x400+SIZE]
            archived.setdefault(window.hex(),[]).append(i)
            frame=image[0x1642-0x400:0x1642-0x400+10]
            if ram.crc16_kermit(frame)!=0:raise InvalidEvidence("bad historical RX CRC")
            legacy[i]={"rx_frame":frame.hex(),
                       "metadata_166a_166c":image[0x166A-0x400:0x166D-0x400].hex()}
    windows=[
        bytes.fromhex(x["response"]["data"])
        for cycle in json.loads(capture)["cycles"]
        for x in (cycle["reads"][0],cycle["reads"][3])
    ]
    cross=compare_windows(archived,windows)
    historical_special=[i for i,v in legacy.items() if v["rx_frame"]=="0001b10a010100004353"]
    if historical_special!=[64]:
        raise InvalidEvidence("historic rare RX 64 not independently supported")
    exact_matches=cross["identical_32byte_archive_and_live_patterns"]
    rare=[r for r in exact_matches if r["archive_snapshot_ids"]==[64]]
    if not rare or rare[0]["live_count"]<1:
        raise InvalidEvidence("cross-era rare 32-byte match absent")
    if legacy[64]["metadata_166a_166c"]!="0a0401":
        raise InvalidEvidence("old rare triple did not match")
    return {
        "mode":"SHA_ATTESTED_FUSED_VS_HISTORICAL_32BYTE_WINDOW",
        "sha_capture":ORIGINAL_SHA,"sha_fullram":HISTORIC_SHA,
        "new_fused_summary":{k:report[k] for k in ("full_cycles",
              "individual_overlapped_fc03_reads","fused_crc_tail_to_metadata_byte_counts",
              "vitotrol_swindex_0a5c")},
        "old_complete_images":79,
        "historical_rare_image":64,
        "historic_rare_crc_valid_frame":legacy[64]["rx_frame"],
        "historic_rare_meta_triple":legacy[64]["metadata_166a_166c"],
        "crosscheck":cross,
        "historic_is_nonatomic_32byte_blocks":True,
        "new_match_is_single_fc03_32byte_copy":True,
        "sample_causality_or_interrupt_state_proven":False,
        "rom_bytes_read":False,"controller_writes":0,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("fused_original",type=Path)
    p.add_argument("historic_archive",type=Path)
    p.add_argument("--out",type=Path)
    args=p.parse_args()
    if args.fused_original.is_symlink() or args.historic_archive.is_symlink():
        raise InvalidEvidence("do not follow data symlinks")
    if args.fused_original.stat().st_size>150_000 or args.historic_archive.stat().st_size>ram.MAX_ARCHIVE_BYTES:
        raise InvalidEvidence("size cap")
    result=run(args.fused_original.read_bytes(),args.historic_archive.read_bytes())
    output=json.dumps(result,indent=2,sort_keys=True)+"\n"
    if args.out:args.out.write_text(output)
    print(output)


if __name__=="__main__":main()
