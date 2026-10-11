#!/usr/bin/env python3
"""Offline verification of WB2A 166a/166b invariant and non-causal RX association.

Checks 79 SHA/manifest-attested full-RAM source images and two exact Oct 11
single-FC03 capture sources. Pure file analysis, no controller action.
A difference of 6 between metadata bytes is an observed INVARIANT, not
proof of a ring buffer, ISR flag, protocol framing or emulator entry point.
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
def helper(filename,name):
    spec=importlib.util.spec_from_file_location(name,ROOT/filename)
    if spec is None or spec.loader is None:raise ValueError("original source helper unavailable")
    m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m
    spec.loader.exec_module(m);return m
crc=helper("wb2a-vitotrol-optolink-rx-audit.py","vt_meta_invariant_crc")
p=helper("wb2a-vitotrol-master31-meta-pair-audit.py","vt_meta_invariant_master")
f=helper("wb2a-vitotrol-fused-rx-audit.py","vt_meta_invariant_fused")
ARCH_SHA=crc.KNOWN_ARCHIVES["fullram"]
EARLY_SHA="d22dfbc58cad99798be16aac9bf8b9c55598eeb35f25316b54690bffc5c3a258"
NEW_SHA="d6cc2f4b69d3171944f22f1b5fb015c0bca4fc51dc28b2bb26137932b632db43"


class UntrustedEvidence(ValueError):pass


def check_sha(blob:bytes,expected:str,max_len:int):
    if type(blob) is not bytes or not 0<len(blob)<=max_len or hashlib.sha256(blob).hexdigest()!=expected:
        raise UntrustedEvidence("not a pinned original capture")


def verify_pair(first:int,second:int) -> dict:
    if type(first) is not int or type(second) is not int or not 0<=first<=255 or not 0<=second<=255:
        raise UntrustedEvidence("single-byte metadata required")
    return {"raw":f"{first:02x}{second:02x}",
            "difference_mod_256":(first-second)&255,
            "first_is_second_plus_6":(first-second)&255==6,
            "firmware_owner_proven":False}


def evaluate(historic:bytes,early:bytes,new:bytes)->dict:
    check_sha(historic,ARCH_SHA,crc.MAX_ARCHIVE_BYTES)
    check_sha(early,EARLY_SHA,150_000)
    check_sha(new,NEW_SHA,180_000)
    earlydata=json.loads(early)
    earlyaudit=f.inspect(earlydata)
    laterdata=json.loads(new)
    lateraudit=p.inspect(laterdata)
    counts=Counter();pairs=[]
    with tarfile.open(fileobj=io.BytesIO(historic),mode="r:gz") as tar:
        manifest=crc._manifest(tar,"p300-fullram")
        for i in range(1,80):
            name=f"snapshots/s{i:05d}"
            info=json.loads(crc._verified(tar,manifest,"p300-fullram",name+".json",max_size=8000))
            image=crc._verified(tar,manifest,"p300-fullram",name+".bin",max_size=20_480)
            if (len(image)!=20_480 or info.get("complete") is not True or
                info.get("device_id")!="20c2" or info.get("software")!="0103"):
                raise UntrustedEvidence("not an original WB2A 20K snapshot")
            first=image[0x166a-0x400];second=image[0x166b-0x400]
            pair=verify_pair(first,second)
            counts[pair["raw"]]+=1
            pairs.append({"source":"fullram","index":i,**pair})
    recent=Counter()
    for item in lateraudit["events"]:
        pair=bytes.fromhex(item["meta_166a_and_166b_single_read"])
        if len(pair)!=2:raise UntrustedEvidence("wrong 0x164c FC03 copy width")
        point=verify_pair(pair[0],pair[1])
        recent[point["raw"]]+=1
        pairs.append({"source":"new_live","index":item["cycle"],**point})
    if counts!={"0600":78,"0a04":1} or recent!={"0600":8}:
        raise UntrustedEvidence("unexpected historic or new metadata pair")
    if not all(x["first_is_second_plus_6"] for x in pairs):
        raise UntrustedEvidence("observed candidate difference invariant broken")
    early_fused=earlyaudit["fused_crc_tail_to_metadata_byte_counts"]
    new_fused=lateraudit["fused_crc_last_to_166a_counts"]
    if early_fused!={"c6|06":15,"53|0a":1} or new_fused!={"c6|06":15,"53|06":1}:
        raise UntrustedEvidence("cross-session CRC/meta sample population altered")
    return {
        "mode":"SHA_ATTESTED_OFFLINE_RX_METADATA_PAIR_NONCAUSAL",
        "original_sha256":{"fullram":ARCH_SHA,"early_fused":EARLY_SHA,"new_class31_fused":NEW_SHA},
        "historical_samples":79,"new_live_paired_samples":8,
        "total_pair_samples":len(pairs),
        "historical_166a166b_counts":dict(sorted(counts.items())),
        "new_same_fc03_166a166b_counts":dict(sorted(recent.items())),
        "all_observed_166a_minus_166b_mod_256_is_6":True,
        "observed_pair_difference":6,
        "previous_crc_end_to_166a_single_copy_counts":early_fused,
        "new_crc_end_to_166a_single_copy_counts":new_fused,
        "crc_last_byte_53_can_coexist_with_166a_06":True,
        "crc_last_byte_53_also_observed_with_166a_0a":True,
        "metadata_a_direct_deterministic_function_of_crc_tail_proven":False,
        "meta_pair_is_ring_buffer_or_ISR_flag_proven":False,
        "possible_two_related_offsets_not_proven":True,
        "controller_writes":0,"new_hardware_io":0,
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fullram",type=Path,required=True)
    parser.add_argument("--fused",type=Path,required=True)
    parser.add_argument("--master31",type=Path,required=True)
    parser.add_argument("--out",type=Path)
    a=parser.parse_args()
    sources=(a.fullram,a.fused,a.master31)
    if any(not p.is_file() or p.is_symlink() for p in sources):
        parser.error("exact original regular source files required")
    result=evaluate(*(p.read_bytes() for p in sources))
    text=json.dumps(result,sort_keys=True,indent=2)+"\n"
    if a.out:a.out.write_text(text)
    print(text)


if __name__=="__main__":main()
