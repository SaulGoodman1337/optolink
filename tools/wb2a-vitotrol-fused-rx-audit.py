#!/usr/bin/env python3
"""Audit same-FC03-copy RX CRC-tail / 0x166a metadata evidence, offline only.

For FC03 start 0x164b size 32, byte 0 is the end of the natural 10B
reply at 0x1642 and byte 31 is 0x166a. These values share a memory copy.
No broader assertion of simultaneous MCU/ISR state is made.
"""
from __future__ import annotations
from collections import Counter
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent
def load(name,filename):
    spec=importlib.util.spec_from_file_location(name,ROOT/filename)
    if spec is None or spec.loader is None:raise RuntimeError("audit helper missing")
    mod=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=mod
    spec.loader.exec_module(mod)
    return mod
protocol=load("wb2a_fused_rx_probe","wb2a-vitotrol-fused-rx-window.py")
crc=load("wb2a_fused_rx_crc","wb2a-vitotrol-optolink-rx-audit.py")


class EvidenceRejected(ValueError):pass


def extract(record,cmd):
    if not isinstance(record,dict) or record.get("command")!=cmd:
        raise EvidenceRejected("unverified sample command")
    row=record.get("response",{})
    addr,size=(protocol.ADDR,protocol.COUNT) if cmd==protocol.OVERLAP else protocol.base.ALLOWED[cmd]
    if (row.get("command")!=cmd or row.get("valid_read") is not True or
        row.get("address")!=f"0x{addr:04x}"):
        raise EvidenceRejected("wrong returned address/status")
    try:data=bytes.fromhex(row["data"])
    except (TypeError,ValueError,KeyError) as exc:raise EvidenceRejected("wrong encoded payload") from exc
    if len(data)!=size:raise EvidenceRejected("short or long response")
    st=record.get("begin");en=record.get("end")
    if (not isinstance(st,(int,float)) or not isinstance(en,(int,float))
        or st>=en or en-st>12):
        raise EvidenceRejected("unreliable time window")
    return data,float(st),float(en)


def inspect(document:dict,*,sha256:str|None=None)->dict:
    if (not isinstance(document,dict) or
        document.get("mode")!="P300_FUSED_RX_CRC_METADATA_READ_ONLY" or
        document.get("target")!="20C2/0103" or
        document.get("controller_writes")!=0 or
        document.get("uart_dma_irq_writes")!=0 or
        document.get("single_p300_copy_is_not_isr_atomic") is not True):
        raise EvidenceRejected("not the expected original read-only record")
    if extract(document["identity"],protocol.base.IDENTITY[0])[0].hex()!=protocol.base.EXPECTED_ID:
        raise EvidenceRejected("wrong boiler")
    for key in ("baseline","after"):
        rows=document.get(key)
        if not isinstance(rows,list) or len(rows)!=4:
            raise EvidenceRejected("missing before/after state guard")
        if any(extract(row,expected[0])[0]!=bytes(1)
               for row,expected in zip(rows,protocol.base.BASELINE)):
            raise EvidenceRejected("coding or controller error nonzero")
    snapshots=document.get("cycles")
    if (not isinstance(snapshots,list) or not 4<=len(snapshots)<=8 or
        document.get("sample_count")!=len(snapshots) or
        document.get("requests")!=11+4*len(snapshots)):
        raise EvidenceRejected("cycle count or request count mismatch")
    summary=Counter(); crc_count=Counter();metadata=Counter();full=Counter()
    inconsistent=0; paired=[];prev_end=document["baseline"][-1]["end"]
    observations=[]
    for i,entry in enumerate(snapshots):
        rows=entry.get("reads")
        if (entry.get("index")!=i or len(rows)!=4 or
            entry.get("frame_metadata_atomic") is not False or
            entry.get("two_bytes_within_same_fc03_copy") is not True):
            raise EvidenceRejected("missing bracket")
        cmds=(protocol.OVERLAP,protocol.RX,protocol.META,protocol.OVERLAP)
        verified=[]
        for row,cmd in zip(rows,cmds):
            payload,start,end=extract(row,cmd)
            if start<prev_end:raise EvidenceRejected("non-monotonic original reads")
            prev_end=end
            verified.append((payload,start,end))
        before,full_rx,meta_after,after=verified
        frame_size=full_rx[0][5]
        if not 8<=frame_size<=30:raise EvidenceRejected("unusual natural reply length")
        frame=full_rx[0][2:2+frame_size]
        if crc.crc16_kermit(frame)!=0:
            raise EvidenceRejected("not a CRC-valid natural RX frame")
        # Single-window byte pair, not cross-read correlation.
        for label,z in (("early",before),("late",after)):
            key=f"{z[0][0]:02x}|{z[0][-1]:02x}"
            summary[key]+=1
            crc_count[f"{z[0][0]:02x}"]+=1
            metadata[f"{z[0][-1]:02x}"]+=1
        last_crc_byte=full_rx[0][11]
        actual_166a=meta_after[0][10]
        full[(frame.hex(),f"{actual_166a:02x}")]+=1
        paired.append({
            "cycle":i,
            "frame_hex":frame.hex(),
            "frame_crc16_kermit_valid":True,
            "full_rx_last_crc":f"{last_crc_byte:02x}",
            "separate_metadata_166a":f"{actual_166a:02x}",
            "early_overlap_tail_meta":[f"{before[0][0]:02x}",f"{before[0][-1]:02x}"],
            "late_overlap_tail_meta":[f"{after[0][0]:02x}",f"{after[0][-1]:02x}"],
            "full_rx_tail_agrees_with_both_overlap_reads": (
                last_crc_byte==before[0][0]==after[0][0]),
            "metadata_agrees_with_both_overlap_reads": (
                actual_166a==before[0][-1]==after[0][-1]),
            "copy_atomically_matches_known_received_reply":False,
            "frame_and_metadata_from_independent_reads_nonatomic":True,
            "all_four_requests_elapsed_seconds":round(after[2]-before[1],3),
        })
        if not paired[-1]["full_rx_tail_agrees_with_both_overlap_reads"]:
            inconsistent+=1
    tail=[extract(r,c)[0] for r,c in zip(document["vitotrol_status"],protocol.FINAL)]
    if len(tail)!=2:raise EvidenceRejected("missing participant status")
    return {
        "mode":"OFFLINE_FC03_SINGLE_COPY_CRC_TAIL_AND_METADATA",
        "source_sha256":sha256,
        "full_cycles":len(snapshots),
        "total_validated_reads":document["requests"],
        "individual_overlapped_fc03_reads":2*len(snapshots),
        "fused_crc_tail_to_metadata_byte_counts":dict(sorted(summary.items())),
        "crc_last_byte_counts":dict(sorted(crc_count.items())),
        "metadata_166a_counts":dict(sorted(metadata.items())),
        "full_frame_and_separate_meta_counts":[
            {"frame":a,"metadata":b,"n":n} for (a,b),n in sorted(full.items())],
        "cycles_with_full_rx_crc_tail_mismatch_vs_bracketing_overlaps":inconsistent,
        "cycle_details":paired,
        "vitotrol_swindex_0a5c":tail[0].hex(),
        "sensor_089c":tail[1].hex(),
        "copy_atomic_on_sfr_or_isr_level_proven":False,
        "runnable_receiver_queue_flag_identified":False,
        "participant_index_nonzero_observed":tail[0]!=bytes(4),
        "vitotrol_enrollment_accepted_proven":False,
        "controller_writes":0,
        "no_new_device_io":True,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("capture",type=Path)
    p.add_argument("--out",type=Path)
    args=p.parse_args()
    data=args.capture.read_bytes()
    if len(data)>140_000:raise EvidenceRejected("oversized original capture")
    result=inspect(json.loads(data),sha256=hashlib.sha256(data).hexdigest())
    text=json.dumps(result,indent=2,sort_keys=True)+"\n"
    if args.out:args.out.write_text(text)
    print(text)


if __name__=="__main__":main()
