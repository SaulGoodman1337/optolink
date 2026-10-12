#!/usr/bin/env python3
"""Read-only offline verification of Oct 12 WB2A P300 SRAM delta structure.

Attests original Oct 9 79-snapshot tar, three original Oct 11 P300
host captures, actual Oct 12 19-request P300 capture, and four complete
VS1 fault-archive captures. Looks for byte-position/bit-plane clustering
in 0x3301..0x331e and validates against permutation and historical SRAM
difference controls. No Optolink I/O, no controller writes or firmware dump.

WARNING: Because the address range/period were noticed post hoc,
permutation-tail fractions are DESCRIPTIVE only, not formal p-values.
A repeated 3-byte stride does not establish a record schema.
"""
from __future__ import annotations

from collections import Counter
import argparse
import hashlib
import importlib.util
import itertools
import json
import math
from pathlib import Path
import random
import sys

TOOLS=Path(__file__).resolve().parent
REPO_ROOT=TOOLS.parent
OLD=Path("/root/p300-trial-work/research-bundles/p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz")
NEW=Path("/tmp/wb2a-postrestart-five-window-live-20261012.json")
EVENT_DIR=Path("/tmp")
GATE=Path("/home/chatgpt-admin/optolink-vitotrol-rpm-20261010/tools/wb2a-experiment-fault-gate.py")
FAULT_SOURCES={
    "pre":("wb2a-5win-fault-baseline-20261012.json",
           "316caaebf012431b7c7089a897b002d1c3976c276c080b4a748a6e00b04ee2b1"),
    "post_0":("wb2a-5win-fault-post0-snapshot-20261012.json",
           "3ca5fb5e192d57687179bedb7907ca6871ff8a54836a5b88ec5851b3c4d9012f"),
    "post_5":("wb2a-5win-fault-post5-snapshot-20261012.json",
           "6ae0dd86551c5652c15cc1bc429c2d3facd4a2b5f6a2bc0d69b9399bc0602dcf"),
    "post_20":("wb2a-5win-fault-post15-snapshot-20261012.json",
           "c72672e4f1835bb90f011f62a0404fd84849b2039bf053f3cb143f66874234f0"),
}
BASE_ADDR=0x3301
FRAME=30
KNOWN_DIFF_OFFSETS=(4,6,9,12,21,24,27)
KNOWN_MASKS=(0x80,0x10,0x40,0x40,0x80,0x80,0x24)
CONTROL_SEED=20261012
CONTROL_COUNT=100_000
PERIODS=tuple(range(2,9))


class BadSource(ValueError):
    pass


def load_module(module_name:str,path:Path):
    if path.is_symlink() or not path.is_file():
        raise BadSource("source module missing or symlinked")
    sp=importlib.util.spec_from_file_location(module_name,path)
    if sp is None or sp.loader is None:raise BadSource("source module unavailable")
    obj=importlib.util.module_from_spec(sp)
    sys.modules[sp.name]=obj
    sp.loader.exec_module(obj)
    return obj


def source_read(path:Path,wanted_sha:str,min_size=100,max_size=100_000):
    if path.is_symlink() or not path.is_file() or not min_size<=path.stat().st_size<=max_size:
        raise BadSource("unknown private original source length or path")
    content=path.read_bytes()
    if hashlib.sha256(content).hexdigest()!=wanted_sha:
        raise BadSource("original SHA256 changed for "+str(path))
    return content


def exact_hypergeom_tail(n:int,m:int,k:int,hits:int)->float:
    """P(X>=hits) from uniformly choosing k distinct addresses in n bytes."""
    if type(n)!=int or type(m)!=int or type(k)!=int or type(hits)!=int or not (0<=m<=n and 0<=k<=n and 0<=hits<=k):
        raise BadSource("invalid hypergeometric arguments")
    return sum(math.comb(m,j)*math.comb(n-m,k-j) for j in range(hits,min(k,m)+1)
               if k-j<=n-m)/math.comb(n,k)


def residue_statistics(changed:tuple[int,...],length=FRAME):
    if (not isinstance(changed,tuple) or type(length)!=int or length!=FRAME or
        any(type(i)!=int or not 0<=i<length for i in changed)
        or len(changed)!=len(set(changed)) or len(changed)==0):
        raise BadSource("unexpected 30-byte changed-offset input")
    result={}
    candidate=[]
    for period in PERIODS:
        slots=[]
        for phase in range(period):
            eligible=sum(i%period==phase for i in range(length))
            hits=sum(i%period==phase for i in changed)
            tail=exact_hypergeom_tail(length,eligible,len(changed),hits)
            slots.append({"phase":phase,"slots":eligible,"hits":hits,
                          "fixed_single_phase_tail_fraction":round(tail,9)})
            candidate.append((tail,period,phase))
        result[str(period)]=slots
    best=min(candidate)
    # An independent exact phase-ANY combinatorial tail for k=7 at period3,
    # where no two phases can simultaneously contain >=6 of seven positions.
    if len(changed)!=7:raise BadSource("the exact seven-difference control no longer applies")
    slots=[sum(i%3==phase for i in range(length)) for phase in range(3)]
    ways=sum(sum(math.comb(n,j)*math.comb(length-n,7-j)
                 for j in range(6,8) if j<=n and 7-j<=length-n) for n in slots)
    exact=ways/math.comb(length,7)
    return {
        "period_2_through_8_phase_counts":result,
        "best_posthoc_unadjusted_single_phase":{"period":best[1],"phase":best[2],
          "tail_fraction":round(best[0],9)},
        "fixed_period3_6of7_any_phase_exact_tail_fraction":round(exact,9),
        "fixed_period3_6of7_any_phase_fraction_is_posthoc_descriptive":True,
    }


def period_scan_min_tail(changed:tuple[int,...],n=FRAME):
    k=len(changed)
    best=1.0
    for p in PERIODS:
        counts=Counter(i%p for i in changed)
        for phase in range(p):
            slots=(n-1-phase)//p+1 if phase<n else 0
            best=min(best,exact_hypergeom_tail(n,slots,k,counts[phase]))
    return best


def multiscan_permutation(changed:tuple[int,...],iterations=CONTROL_COUNT):
    if type(iterations)!=int or not 500<=iterations<=CONTROL_COUNT:
        raise BadSource("unbounded or too-small control")
    minimum=period_scan_min_tail(changed)
    rnd=random.Random(CONTROL_SEED)
    hits=0
    for _ in range(iterations):
        other=tuple(sorted(rnd.sample(range(FRAME),len(changed))))
        if period_scan_min_tail(other)<=minimum+1e-14:hits+=1
    return {
        "seed":CONTROL_SEED,"permutations":iterations,
        "statistic":"min single-phase hypergeometric tail over all stride periods 2..8 and phases",
        "permutations_at_least_as_extreme":hits,
        "scan_adjusted_descriptive_tail_fraction":round((hits+1)/(iterations+1),7),
        "source_selected_after_observing_candidate":True,
        "formal_independent_p_value":False,
    }


def historic_spatial_control(images:list[bytes],length=FRAME):
    """Exact consecutive-history RAM differences, rolling all length30 windows.

    Overlapping SRAM windows are highly dependent; this is a raw background
    prevalence figure, NOT a binomial null or independent sample test.
    """
    if len(images)!=79 or any(type(x)!=bytes or len(x)!=20_480 for x in images):
        raise BadSource("full authentic 79-image historical cohort required")
    total_seven=0; clustered=0
    comparisons=0
    sample_addresses=[]
    for before,after in zip(images,images[1:]):
        differences=bytes(a!=b for a,b in zip(before,after))
        mod=[0,0,0]
        for index in range(length):
            if differences[index]:mod[index%3]+=1
        for i in range(len(differences)-length+1):
            if i:
                before_i=i-1;add_i=i+length-1
                if differences[before_i]:mod[before_i%3]-=1
                if differences[add_i]:mod[add_i%3]+=1
            comparisons+=1
            if sum(mod)==7:
                total_seven+=1
                if max(mod)>=6:
                    clustered+=1
                    if len(sample_addresses)<12:sample_addresses.append(f"0x{0x400+i:04x}")
    return {
        "historical_nonatomic_image_pairs":len(images)-1,
        "30byte_overlapping_window_pair_comparisons":comparisons,
        "historical_windows_with_exactly_seven_changed_bytes":total_seven,
        "historical_windows_with_seven_changes_and_six_at_stride3":clustered,
        "historical_fraction_given_seven":round(clustered/total_seven,6) if total_seven else None,
        "samples_if_any":sample_addresses,
        "overlapping_windows_are_not_independent":True,
    }


def decoded_targets(images,rows):
    import sys
    if len(images)!=79 or len(rows)!=2:raise BadSource("expected old/new source counts")
    p=BASE_ADDR-0x0400
    old=[img[p:p+FRAME] for img in images]
    new=[x["ram_3300"][1:31] for x in rows]
    if not all(len(x)==FRAME for x in old+new):
        raise BadSource("incomplete 30-byte original")
    if len(set(old))!=1:raise BadSource("original Oct9 30-byte source not static")
    if new[0]!=new[1]:raise BadSource("Oct12 low-RAM window not repeatable")
    return old[0],new[0]


def bitplane_report(old:bytes,new:bytes):
    if not (type(old)==type(new)==bytes and len(old)==len(new)==FRAME):
        raise BadSource("expected two full 30-byte original samples")
    changed=tuple(i for i,(a,b) in enumerate(zip(old,new)) if a!=b)
    masks=tuple(old[i]^new[i] for i in changed)
    if changed!=KNOWN_DIFF_OFFSETS or masks!=KNOWN_MASKS:
        raise BadSource("historical live A-target byte difference pattern drifted")
    flips=Counter(bit for mask in masks for bit in range(8) if mask&(1<<bit))
    words=[]
    for i in range(0,FRAME,3):
        before=old[i:i+3]
        after=new[i:i+3]
        words.append({
            "record":i//3,
            "changed_byte_positions":[j for j in range(3) if before[j]!=after[j]],
            "least_significant_word_delta":int.from_bytes(after,"little")-int.from_bytes(before,"little"),
            "third_byte_unchanged":before[2]==after[2],
            "old_value_is_valid_plain_20bit_address":int.from_bytes(before,"little")<=0xFFFFF,
            "new_value_is_valid_plain_20bit_address":int.from_bytes(after,"little")<=0xFFFFF,
            "old_value_is_direct_high_rom_address":0xC0000<=int.from_bytes(before,"little")<=0xFFFFF,
            "new_value_is_direct_high_rom_address":0xC0000<=int.from_bytes(after,"little")<=0xFFFFF,
        })
    if len(words)!=10 or not all(w["third_byte_unchanged"] for w in words):
        raise BadSource("unexpected old/new triplet morphology")
    return {
        "range":"0x3301..0x331e",
        "byte_count":FRAME,
        "changed_byte_count":len(changed),
        "unchanged_byte_count":FRAME-len(changed),
        "changed_absolute_addresses":[f"0x{BASE_ADDR+i:04x}" for i in changed],
        "changed_offsets":changed,
        "xor_masks":[f"0x{x:02x}" for x in masks],
        "total_flipped_bits":sum(mask.bit_count() for mask in masks),
        "bit_plane_counts":{str(i):flips.get(i,0) for i in range(8)},
        "changed_byte_positions_mod3":dict(sorted(Counter(i%3 for i in changed).items())),
        "complete_24bit_triplets_from_0x3301":len(words),
        "hypothetical_copy_descriptor_count_bytes":29,
        "30byte_triplet_frame_exceeds_hypothetical_29byte_copy_by_one_byte":True,
        "all_third_bytes_unchanged":True,
        "changed_triplets":sum(bool(x["changed_byte_positions"]) for x in words),
        "changed_triplets_with_multiple_byte_changes":sum(len(x["changed_byte_positions"])>1 for x in words),
        "possible_plain_20bit_LITTLE_ENDIAN_values":sum(x["old_value_is_valid_plain_20bit_address"] for x in words),
        "possible_direct_high_ROM_LITTLE_ENDIAN_values":sum(x["old_value_is_direct_high_rom_address"] for x in words),
        "triplets":words,
        "copy_hypothesis_source_pointer_remains_unverified":True,
        "three_byte_record_schema_proven":False,
        "p300_observed_program_ROM_bytes":0,
    }


def read_fault_sources(directory:Path):
    gate=load_module("postrestart_romcopy_original_fault_gate_readonly",GATE)
    captures={}
    for key,(name,sha) in FAULT_SOURCES.items():
        record=json.loads(source_read(directory/name,sha,300,60_000))
        gate.validate(record)
        captures[key]=record
    base=captures["pre"]
    reports={}
    for key in ("post_0","post_5","post_20"):
        verdict=gate.compare(base,captures[key])
        if verdict["verdict"]!="NO_CHANGE_OBSERVED" or verdict["new_or_active_faults"]:
            raise BadSource("fault history changed after read-only experiment: "+key)
        reports[key]={
            "complete_system_archive_checked":verdict["complete_system_archive_checked"],
            "complete_gfa_archive_checked":verdict["complete_gfa_archive_checked"],
            "elapsed_since_baseline_s":verdict["sample_age_seconds"],
            "no_new_or_active_faults_at_check":True,
        }
    return {"all_original_fault_archives_sha256_passed":True,
            "new_controller_write_commands":0,
            "fault_verdicts":reports,
            "all_75minute_late_watch_completed":False}


HOST_ALIAS_EXPECTED={
    ("BedienSparbetriebM2~0x3302","0x3302",1),
    ("BedienPartybetriebM2~0x3303","0x3303",1),
    ("BedienRTSolltemperaturM2~0x3306","0x3306",1),
    ("BedienRTSolltemperaturReduziertM2~0x3307","0x3307",1),
    ("BedienRTSoll_PartyM2~0x3308","0x3308",1),
    ("FerienBeginnM2~0x3309","0x3309",8),
    ("FerienEndeM2~0x3311","0x3311",8),
}


def parse_host_virtual_alias_rows(rows:list[dict])->dict:
    selected=[]
    for r in rows:
        raw=r.get("Address")
        if not isinstance(raw,str) or not raw.startswith("0x"):
            continue
        try:addr=int(raw,16)
        except ValueError:raise BadSource("invalid OEM alias address")
        if not 0x3301<=addr<=0x331e:continue
        if r.get("FCRead")!="Virtual_READ":
            raise BadSource("new OEM request mapping at physical-like numeric address")
        length=r.get("BlockLength")
        if not isinstance(length,str) or not length.isdecimal():
            raise BadSource("invalid OEM host block length")
        selected.append((r["ID"],raw,int(length)))
    if set(selected)!=HOST_ALIAS_EXPECTED or len(selected)!=7:
        raise BadSource("the seven genuine VDensHO1 virtual datapoints have changed")
    return {
        "WB2A_host_Virtual_READ_event_count_in_numeric_range":len(selected),
        "host_Virtual_READ_events":[
          {"ID":name,"virtual_address":address,"length":n}
          for name,address,n in sorted(selected,key=lambda x:(x[1],x[0]))
        ],
        "host_virtual_0x330x_addresses_equal_P300_FC03_physical_RAM_proven":False,
        "named_holiday_and_M2_setpoint_objects_are_NOT_controller_ROM_proven":True,
        "main_ROM_origin_discovered":False,
    }


def host_catalog_alias_audit()->dict:
    c=load_module("wb2a_romcopy_host_alias_independent_original",
                  TOOLS/"wb2a-gwg-vs1-p300-generation-oracle-audit.py")
    for label in ("dp","events"):
        path,sha,size=c.SOURCES[label]
        c.sha_original(path,sha,size)
    types,ids,links,defs,meta=c.load_catalog(c.DP,c.EVENT)
    profile=[p for p,name in types.items() if name=="VDensHO1"]
    if profile!=["60"] or meta["all_link_count"]!=104339:
        raise BadSource("not genuine current WB2A host profile")
    rows=[defs[ids[event_id]] for event_id in links["60"]]
    return parse_host_virtual_alias_rows(rows)


def audit(oct9:Path,oct12:Path,oct11_folder:Path,fault_folder:Path,
          *,permutations=CONTROL_COUNT,history=True):
    new_m=load_module("postrestart_romcopy_new_fivewin_attestor",TOOLS/"wb2a-postrestart-five-window-offline-audit.py")
    cross_m=load_module("postrestart_romcopy_original_oct11_attestor",TOOLS/"wb2a-romcopy-crosssession-offline.py")
    o=new_m.m
    if oct9.is_symlink() or not oct9.is_file() or oct9.stat().st_size!=o.ARCHIVE_SIZE:
        raise BadSource("wrong Oct9 original archive path/size")
    image_bytes=oct9.read_bytes()
    images=o.attested_images(image_bytes)
    live=source_read(oct12,new_m.PINNED_LIVE_SHA,2000,35_000)
    parsed=new_m.decode_capture(live)
    old,new=decoded_targets(images,parsed)
    cross=cross_m.audit(oct9,oct11_folder)
    if cross["A_29byte_target_oct11_compared_observations"]!=4:
        raise BadSource("Oct11 independent A-target contrast incomplete")
    if cross["A_8byte_tuple_oct11_compared_observations"]!=4:
        raise BadSource("Oct11 independent A pointer contrast incomplete")
    same=new_m.compare(images,live)
    if same["candidate_fields"]["A_29byte_target"]["changed_relative_to_old_first"]!=[7,7]:
        raise BadSource("Oct12 A target did not match pinned seven-byte changes")
    if same["candidate_fields"]["A_8byte_descriptor"]["changed_relative_to_old_first"]!=[0,0]:
        raise BadSource("Oct12 A source pointer changed")
    morphology=bitplane_report(old,new)
    diffs=tuple(morphology["changed_offsets"])
    result={
        "audit":"PASS",
        "proof_scope":"ORIGINAL_HOST_P300_LOW_SRAM_DATA_ONLY",
        "date":"2026-10-12",
        "sources":{
            "oct9_79_complete_images_sha256":o.ARCHIVE_SHA256,
            "oct11_three_original_capture_sha256":cross["sources_sha256"],
            "oct12_new_19read_original_sha256":new_m.PINNED_LIVE_SHA,
            "fault_4_original_capture_sha256":{key:sha for key,(_,sha) in FAULT_SOURCES.items()},
        },
        "oct9_complete_original_images":79,
        "oct11_independent_A_target_reads":4,
        "oct12_new_A_target_reads":2,
        "A_source_pointer_unchanged_from_Oct9_to_Oct12":True,
        "A_target_new_value_not_equal_original_Oct9_or_Oct11":True,
        "bitplane":morphology,
        "stride3_exploratory":residue_statistics(diffs),
        "period2_through_8_multiple_scan_control":multiscan_permutation(diffs,permutations),
        "historical_ram_change_controls":historic_spatial_control(images) if history else None,
        "OEM_VDensHO1_numeric_Virtual_READ_alias_crosscheck":host_catalog_alias_audit(),
        "safety_original_complete_archives":read_fault_sources(fault_folder),
        "statistical_tests_are_posthoc_descriptive_not_formal_p_values":True,
        "static_ROM_copy_inferred_from_sparse_changed_SRAM_bytes":False,
        "valid_20bit_ROM_pointer_table_inferred_from_triplets":False,
        "verified_program_ROM_bytes":0,
        "hardware_requests_by_this_audit":0,
        "controller_writes_by_this_audit":0,
    }
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--oct9",type=Path,default=OLD)
    p.add_argument("--oct12",type=Path,default=NEW)
    p.add_argument("--oct11-dir",type=Path,default=EVENT_DIR)
    p.add_argument("--fault-dir",type=Path,default=EVENT_DIR)
    p.add_argument("--permutations",type=int,default=CONTROL_COUNT)
    p.add_argument("--no-historical-control",action="store_true",
                   help="For tests; full audit always includes this control")
    p.add_argument("--out",type=Path)
    opts=p.parse_args()
    result=audit(opts.oct9,opts.oct12,opts.oct11_dir,opts.fault_dir,
                 permutations=opts.permutations,history=not opts.no_historical_control)
    data=json.dumps(result,sort_keys=True,indent=2)+"\n"
    if opts.out:opts.out.write_text(data,encoding="utf-8")
    print(data,end="")


if __name__=="__main__":
    try:main()
    except (OSError,BadSource,ValueError,KeyError,json.JSONDecodeError) as e:
        print("POSTRESTART_ROMCOPY_STRIDE_AUDIT_REJECTED: "+str(e),file=sys.stderr)
        sys.exit(2)
