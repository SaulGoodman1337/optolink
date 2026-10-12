#!/usr/bin/env python3
"""Audit 8x whole-TX/last-RX-CRC/paired-166a+166b FC03 reads.

A valid TX frame is a byte sequence in RAM, not proof it appeared on the
electrical bus. Consecutive P300 physical reads are NOT temporally atomic.
"""
from __future__ import annotations
from collections import Counter
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
def module(filename,name):
    spec=importlib.util.spec_from_file_location(name,HERE/filename)
    if spec is None or spec.loader is None:raise RuntimeError("source missing")
    r=importlib.util.module_from_spec(spec);sys.modules[spec.name]=r
    spec.loader.exec_module(r);return r
probe=module("wb2a-vitotrol-master31-meta-pair-readonly.py","vt_master31_capture_validator")
crc=module("wb2a-vitotrol-optolink-rx-audit.py","vt_master31_crc")


class InvalidEvidence(ValueError):pass


def validate(row,cmd):
    if not isinstance(row,dict) or row.get("command")!=cmd:
        raise InvalidEvidence("unrecognized request")
    data=row.get("response",{})
    if (not isinstance(data,dict) or data.get("valid_read") is not True or
        data.get("command")!=cmd or data.get("address")!=f"0x{probe.ADDR[cmd]:04x}"):
        raise InvalidEvidence("response not bound to source address/status")
    try:binary=bytes.fromhex(data["data"])
    except (KeyError,TypeError,ValueError) as exc:raise InvalidEvidence("bad binary") from exc
    if len(binary)!=probe.WIDTH[cmd]:raise InvalidEvidence("read was not required byte length")
    a=row.get("start");b=row.get("end")
    if type(a) not in (int,float) or type(b) not in (int,float) or a>=b or b-a>12:
        raise InvalidEvidence("invalid source time")
    return binary,float(a),float(b)


def extract_tx(binary:bytes) -> dict:
    if type(binary) is not bytes or len(binary)!=32:
        raise InvalidEvidence("whole TX must fit 32 bytes")
    n=binary[3]
    if not 8<=n<=22:
        return {"header":binary[:3].hex(),"frame_hex":None,
                "crc_valid":False,"length_valid":False}
    frame=binary[:n]
    return {"header":frame[:3].hex(),"frame_hex":frame.hex(),
            "crc_valid":crc.crc16_kermit(frame)==0,
            "length_valid":frame[3]==n,
            "register_byte":f"0x{frame[6]:02x}" if frame[2]==0x31 and n>=9 else None,
            "one_fc03_ram_copy":True,
            "electrical_bus_transmission_proven":False}


def inspect(data:dict,source_hash:str|None=None) -> dict:
    if (not isinstance(data,dict) or data.get("mode")!="READONLY_FUSED_META_PAIR_WHOLE_TX_20C2"
        or data.get("device")!="20C2/0103"
        or data.get("controller_writes")!=0 or data.get("controller_dma_uart_irq_writes")!=0
        or data.get("master_and_rx_separate_nonatomic_reads") is not True):
        raise InvalidEvidence("not original bounded read-only capture")
    if validate(data["identity"],probe.IDENTITY)[0].hex()!=probe.fused.base.EXPECTED_ID:
        raise InvalidEvidence("wrong boiler device")
    for group in ("baseline","after"):
        rows=data.get(group)
        if not isinstance(rows,list) or len(rows)!=4:
            raise InvalidEvidence("pre/post status missing")
        for row,ref in zip(rows,probe.STATUS):
            binary,_,_=validate(row,ref[0])
            if binary!=bytes(1):raise InvalidEvidence("unexpected controller fault/coding")
    cycles=data.get("rounds")
    if not isinstance(cycles,list) or not 4<=len(cycles)<=8 or (
        data.get("samples")!=len(cycles) or
        data.get("total_commands")!=11+len(cycles)*5):
        raise InvalidEvidence("unexpected request count")
    tx_counter=Counter(); tx_frames=Counter(); tx_valid=Counter()
    fused_pairs=Counter();meta_pairs=Counter();transitions=[]
    events=[];last=data["baseline"][-1]["end"]
    req=(probe.TX,probe.FUSED,probe.METAPAIR,probe.FUSED,probe.TX)
    for i,s in enumerate(cycles):
        rows=s.get("rows")
        if (s.get("index")!=i or s.get("read_order")!=list(req)
            or s.get("reads_are_sequential") is not True
            or not isinstance(rows,list) or len(rows)!=5):
            raise InvalidEvidence("wrong request bracket ordering")
        decoded=[]
        for row,cmd in zip(rows,req):
            item=validate(row,cmd)
            if item[1]<last:raise InvalidEvidence("overlapping non-atomic reads")
            last=item[2];decoded.append(item)
        left,early,pair,late,right=decoded
        before=extract_tx(left[0]);after=extract_tx(right[0])
        for k,part in (("before",before),("after",after)):
            tx_counter[part["header"]]+=1
            tx_valid["VALID" if part["crc_valid"] else "UNVERIFIED"]+=1
            if part["frame_hex"]:tx_frames[part["frame_hex"]]+=1
        a,b=pair[0][-2],pair[0][-1]
        key=f"{a:02x}{b:02x}"
        meta_pairs[key]+=1
        early_pair=f"{early[0][0]:02x}|{early[0][-1]:02x}"
        late_pair=f"{late[0][0]:02x}|{late[0][-1]:02x}"
        fused_pairs[early_pair]+=1;fused_pairs[late_pair]+=1
        if early_pair!=late_pair:
            transitions.append({"cycle":i,"before":early_pair,"after":late_pair,
                                "same_cycle_not_causality":True})
        events.append({
            "cycle":i,"master_before":before,"master_after":after,
            "fused_crc_and_166a_before":early_pair,
            "fused_crc_and_166a_after":late_pair,
            "meta_166a_and_166b_single_read":key,
            "meta_166a_matches_both_fused_reads":(a==early[0][-1]==late[0][-1]),
            "master_read_bracketing_nonatomic":True,
            "elapsed_five_read_seconds":round(right[2]-left[1],3),
            "physical_Master31_to_RX_trigger_proven":False,
        })
    end=data.get("vitotrol_state")
    if not isinstance(end,list) or len(end)!=2:raise InvalidEvidence("missing final Vitotrol state")
    sw=validate(end[0],probe.EXTRA[0])[0]
    sensor=validate(end[1],probe.EXTRA[1])[0]
    return {
        "mode":"FORENSIC_WHOLE_TX_FUSED_RX_META_PAIR_NONATOMIC",
        "original_source_sha256":source_hash,
        "cycles":len(cycles),"validated_read_requests":data["total_commands"],
        "master_0x31_reads_whole_ram_copy":sum(
            x["header"]=="010031" for e in events
            for x in (e["master_before"],e["master_after"])),
        "master_tx_header_counts":dict(sorted(tx_counter.items())),
        "master_tx_full_frame_counts":dict(sorted(tx_frames.items())),
        "master_tx_single_read_crc_validity":dict(sorted(tx_valid.items())),
        "fused_crc_last_to_166a_counts":dict(sorted(fused_pairs.items())),
        "same_fc03_copy_166a166b_counts":dict(sorted(meta_pairs.items())),
        "within_cycle_fused_pair_transitions":transitions,
        "events":events,
        "swindex_0a5c":sw.hex(),"sensor_089c":sensor.hex(),
        "both_meta_bytes_same_32B_copy":True,
        "RX_and_master_one_copy":False,
        "physical_KM_bus_master_0x31_causes_rare_rx_proven":False,
        "ROM_Read":False,"controller_writes":0,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("original_json",type=Path)
    p.add_argument("--out",type=Path)
    args=p.parse_args()
    data=args.original_json.read_bytes()
    if len(data)>180_000:raise InvalidEvidence("captured data too large")
    obj=inspect(json.loads(data),source_hash=hashlib.sha256(data).hexdigest())
    out=json.dumps(obj,sort_keys=True,indent=2)+"\n"
    if args.out:args.out.write_text(out)
    print(out)


if __name__=="__main__":main()
