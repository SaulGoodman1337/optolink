#!/usr/bin/env python3
"""Pin original native-P300 contrast & Oct-09 FullRAM to prove virtual/physical split.

Offline only: 13 read-only VS1 commands and 20 P300 read-only FC03/guards
were performed in separate already completed runs. The VS1 observations are
literal copied lab transcriptions, not a separate retained raw JSON trace.
No physical 20-bit ROM, program code, bank selector or RX dispatcher inferred.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile

HERE=Path(__file__).resolve().parent
def module(filename,label):
    spec=importlib.util.spec_from_file_location(label,HERE/filename)
    if spec is None or spec.loader is None:raise ValueError("original helper missing")
    m=importlib.util.module_from_spec(spec)
    sys.modules[label]=m
    spec.loader.exec_module(m)
    return m
base=module("wb2a-vitotrol-rom-bridge-contrast-readonly.py","vt_contrast_checker")
source=module("wb2a-vitotrol-optolink-rx-audit.py","vt_contrast_archiver")
P300_SHA="f5a31879fedf8c0af780f020c29e50c47cb7727c15e6305c955e6ae8f05935d1"
ARCHIVE_SHA=source.KNOWN_ARCHIVES["fullram"]
EXPECTED={
"physical_3300":"38361eccb44ddf8ef8efabb787fffe798728084823321183b9a6d4110e3e57cf",
"physical_2182":"16e5cb6a16e516e50016e500bfb94451",
"physical_1de5":"aba20e0133001d0000d0c0a1c00f0002",
"physical_f000":"5497549754975497",
"physical_fff0":"5498549854985498",
}
KNOWN_VS1=base.KNOWN_VS1


class Refused(ValueError):pass


def audit_physical(payload:bytes)->dict:
    if type(payload) is not bytes or hashlib.sha256(payload).hexdigest()!=P300_SHA:
        raise Refused("unexpected native P300 original checksum")
    x=json.loads(payload)
    if (x.get("mode")!="EXACT_FC03_P300_VS1_CONTRAST_READONLY"
        or x.get("controller_reads")!=20 or x.get("controller_writes")!=0
        or x.get("target")!="20C2/0103" or
        x.get("identity",{}).get("data")!=base.TARGET or
        x.get("vitotrol_index",{}).get("data")!="00000000"):
        raise Refused("wrong run scope/identity/write state")
    if len(x.get("cycles",[]))!=2:
        raise Refused("two sequential FC03 cycles required")
    for tag in ("preflight","postflight"):
        guards=x.get(tag)
        if len(guards)!=4 or any(
            z.get("controller_read_only") is not True or z.get("data")!="00"
            for z in guards):
            raise Refused("missing verified guard")
    comps=x.get("comparisons",{})
    if set(comps)!=set(EXPECTED):
        raise Refused("wrong physical address/copy scope")
    rows={}
    for key,expected in EXPECTED.items():
        entries=[c["reads"][key] for c in x["cycles"]]
        addr,n=base.EXPECTED[key]
        for row in entries:
            if (row.get("address")!=f"0x{addr:04x}" or
                row.get("command")!=base.READS[key] or
                row.get("valid_read") is not True or
                row.get("controller_read_only") is not True or
                row.get("data")!=expected or
                len(bytes.fromhex(row["data"]))!=n):
                raise Refused("different physical source bytes/protocol")
        compared=comps[key]
        if (compared.get("physical_copies_equal") is not True or
            compared.get("physical_vs_virtual_equal_on_overlapping_bytes") is not False):
            raise Refused("unexpected virtual/physical classification")
        if (compared.get("vs1_virtual_read_observation_from_same_live_day")!=KNOWN_VS1[key]):
            raise Refused("unexpected VS1 transcription")
        rows[key]={"controller_ram_address":f"0x{addr:04x}",
                  "read_length":n,"native_p300":expected,
                  "vs1_virtual_live_same_day":KNOWN_VS1[key],
                  "native_fc03_repeated_twice_equal":True,
                  "virtual_vs_physical_first_bytes_equal":False}
    return {
       "original_live_sha256":P300_SHA,
       "native_controller_reads":20,
       "native_controller_writes":0,
       "comparison_rows":rows,
       "all_5_address_numeric_equivalence_hypotheses_refuted":True,
       "no_evidence_20bit_program_rom_access":True,
       "VS1_lab_notes_not_independent_sha_attested_binary":True,
    }


def audit_against_archive(p300:bytes,bundle:bytes)->dict:
    r=audit_physical(p300)
    if type(bundle) is not bytes or hashlib.sha256(bundle).hexdigest()!=ARCHIVE_SHA:
        raise Refused("unexpected historical complete FullRAM original")
    with tarfile.open(fileobj=io.BytesIO(bundle),mode="r:gz") as t:
        mf=source._manifest(t,"p300-fullram")
        historical=[]
        for i in range(1,80):
            basename=f"snapshots/s{i:05d}"
            meta=json.loads(source._verified(t,mf,"p300-fullram",
                               basename+".json",max_size=8000))
            if meta.get("complete") is not True or meta.get("marker")!="COMPLETE":
                raise Refused("historical acquisition incomplete")
            old=source._verified(t,mf,"p300-fullram",basename+".bin",max_size=20480)
            if len(old)!=20480:raise Refused("historical RAM size invalid")
            historical.append(old)
    old2182={m[0x2182-0x400:0x2192-0x400].hex() for m in historical}
    if old2182!={"16e5c86a16e516e50016e500bfb94451"}:
        raise Refused("unrecognized 79-image 2182 baseline")
    old3300={m[0x3300-0x400:0x3320-0x400].hex() for m in historical}
    if old3300!={EXPECTED["physical_3300"]}:
        raise Refused("unrecognized 79-image 3300 baseline")
    old1de5={m[0x1de5-0x400:0x1df5-0x400].hex() for m in historical}
    if old1de5!={EXPECTED["physical_1de5"]}:
        raise Refused("unrecognized archive far-source head")
    old2182_bytes=bytes.fromhex(next(iter(old2182)))
    new2182_bytes=bytes.fromhex(EXPECTED["physical_2182"])
    changed=[f"0x{0x2182+i:04x}" for i,(a,b) in enumerate(
       zip(old2182_bytes,new2182_bytes)) if a!=b]
    if changed!=["0x2184"] or old2182_bytes[2]!=0xc8 or new2182_bytes[2]!=0xcb:
        raise Refused("new changed SRAM byte not source-verified")
    r.update({
       "archive_sha256":ARCHIVE_SHA,
       "fullram_original_images_verified":79,
       "historical_0x2182_16_bytes":next(iter(old2182)),
       "live_0x2182_16_bytes":EXPECTED["physical_2182"],
       "stable_0x2182_16bytes_across_79_earlier_fullram":True,
       "long_term_static_tail_invariant_disproven":True,
       "historical_to_live_0x2182_changed_addresses":changed,
       "historical_to_live_0x2184_change":"c8->cb",
       "0x3300_32byte_stable_across_all_79_and_new_live":True,
       "0x1de5_16byte_stable_across_all_79_and_new_live":True,
       "high_FC03_repeating_word_reads":{
         "0xf000":EXPECTED["physical_f000"],
         "0xfff0":EXPECTED["physical_fff0"],
       },
       "high_FC03_words_20bit_rom_proven":False,
       "physical_ISA_memory_bank_mapping_proven":False,
       "firmware_dump_obtained":False,
       "UART1_RX_parser_identified":False,
       "Vitotrol_class11_participant_enrolled":False,
       "controller_io_new_during_audit":0,
       "controller_writes_new_during_audit":0,
    })
    return r


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("p300_source",type=Path)
    p.add_argument("historical_bundle",type=Path)
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    if (any(k.is_symlink() or not k.is_file() for k in
        (a.p300_source,a.historical_bundle))
        or a.p300_source.stat().st_size>60_000
        or a.historical_bundle.stat().st_size>source.MAX_ARCHIVE_BYTES):
        p.error("original bounded private evidence required")
    result=audit_against_archive(a.p300_source.read_bytes(),
                                 a.historical_bundle.read_bytes())
    text=json.dumps(result,sort_keys=True,indent=2)+"\n"
    if a.out:a.out.write_text(text)
    print(text)


if __name__=="__main__":main()
