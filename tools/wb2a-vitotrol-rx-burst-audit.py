#!/usr/bin/env python3
"""Forensic interpretation of a bounded non-atomic WB2A read-only P300 RX burst.

Strictly offline, no serial transport. Every sampled read is timestamped;
status/IRQ metadata and frames must NOT be treated as atomic.
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
def helper(name,path):
    spec=importlib.util.spec_from_file_location(name,HERE/path)
    if spec is None or spec.loader is None:raise RuntimeError("required helper absent")
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module
    spec.loader.exec_module(module)
    return module
crc=helper("rx_burst_crc","wb2a-vitotrol-optolink-rx-audit.py")
recorder=helper("rx_burst_verify","wb2a-vitotrol-rx-burst-readonly.py")
ID=bytes.fromhex("20c2000300000103")


class InvalidEvidence(ValueError):pass


def validate_read(row,cmd:str)->tuple[bytes,float,float]:
    if not isinstance(row,dict) or row.get("command")!=cmd:
        raise InvalidEvidence("wrong/nonexistent request in burst")
    result=row.get("result")
    if not isinstance(result,dict) or (result.get("command")!=cmd or
        result.get("valid_read") is not True or
        result.get("address")!=f"0x{recorder.base.ALLOWED[cmd][0]:04x}"):
        raise InvalidEvidence("unverified response")
    try:data=bytes.fromhex(result["data"])
    except (ValueError,TypeError,KeyError) as exc:raise InvalidEvidence("invalid hex") from exc
    if len(data)!=recorder.EXPECTED_SIZES[cmd]:
        raise InvalidEvidence("truncated payload")
    st=row.get("mono_start");et=row.get("mono_end")
    if not isinstance(st,(int,float)) or not isinstance(et,(int,float)) or st>=et or et-st>12:
        raise InvalidEvidence("bad timestamps")
    return data,float(st),float(et)


def parse(frame:bytes)->dict:
    if len(frame)<4:
        return {"valid_crc":False,"reason":"too short"}
    n=frame[3]
    if not 8<=n<=len(frame):
        return {"valid_crc":False,"reason":"invalid frame length"}
    val=frame[:n]
    return {
        "frame_hex":val.hex(),
        "frame_header":val[:3].hex(),
        "declared_frame_length":n,
        "crc_ok":crc.crc16_kermit(val)==0,
        "class11_vitotrol_rx":len(val)>1 and val[1]==0x11,
    }


def evaluate(document:dict,*,source_sha:str|None=None)->dict:
    if not isinstance(document,dict) or document.get("mode")!="P300_KNOWN_READONLY_FAST_RX":
        raise InvalidEvidence("unrecognized recording")
    if document.get("device")!="20C2/0103" or document.get("controller_writes")!=0 or (
        document.get("all_reads_nonatomic") is not True):
        raise InvalidEvidence("not an attested read-only WB2A run")
    data,_,_=validate_read(document["identity"],recorder.base.IDENTITY[0])
    if data!=ID:raise InvalidEvidence("not exact 20C2/0103 device")
    for stage in ("baseline","after"):
        rows=document.get(stage)
        if not isinstance(rows,list) or len(rows)!=4:raise InvalidEvidence("missing status guards")
        for rec,default in zip(rows,recorder.base.BASELINE):
            b,_,_=validate_read(rec,default[0])
            if b!=bytes(1):raise InvalidEvidence("nonzero fault/coding")

    windows=document.get("rounds")
    if not isinstance(windows,list) or not 4<=len(windows)<=8 or (
        document.get("samples")!=len(windows) or
        document.get("total_reads")!=9+len(windows)*6):
        raise InvalidEvidence("unexpected sampling scope")
    rx_counter=Counter();metadata=Counter();descriptor=Counter()
    preceding=Counter();pair=Counter();masters=Counter();transitions=[]
    sensor=Counter();swindex=Counter();events=[]
    last_end=document["baseline"][-1]["mono_end"]
    for i,entry in enumerate(windows):
        seq=(*(recorder.RX if i%2==0 else tuple(reversed(recorder.RX))),
             *recorder.NEIGHBOR,*recorder.STATUS)
        rows=entry.get("reads")
        if entry.get("index")!=i or entry.get("atomic") is not False or (
            entry.get("order")!=list(seq)) or not isinstance(rows,list) or len(rows)!=6:
            raise InvalidEvidence("wrong sample ordering/atomicity")
        captured={}
        for cmd,row in zip(seq,rows):
            data,start,end=validate_read(row,cmd)
            if start<last_end:
                raise InvalidEvidence("out-of-order or overlapping reads")
            last_end=end
            captured[cmd]=(data,start,end)
        rx=recorder.RX[0];nb=recorder.RX[1];q=recorder.NEIGHBOR[0]
        x=parse(captured[rx][0][2:])
        t=parse(captured[recorder.NEIGHBOR[1]][0])
        meta=captured[nb][0][0x0a:0x0d].hex()
        desc=captured[q][0][0x0d:0x11].hex()
        pred=captured[q][0][0x0b]
        # Data are recorded sequentially, so only observational association.
        delta_ms=(captured[nb][1]-captured[rx][2])*1000 if i%2==0 else (
            captured[rx][1]-captured[nb][2])*1000
        if delta_ms<0:raise InvalidEvidence("timestamp order reversed")
        rx_mid=(captured[rx][1]+captured[rx][2])/2
        meta_mid=(captured[nb][1]+captured[nb][2])/2
        midpoint_separation_ms=abs(rx_mid-meta_mid)*1000
        rx_counter[(x.get("frame_hex"),x.get("crc_ok"))]+=1
        masters[(t.get("frame_header"),t.get("crc_ok"))]+=1
        metadata[meta]+=1;descriptor[desc]+=1;preceding[f"{pred:02x}"]+=1
        pair[(x.get("frame_hex"),meta,f"{pred:02x}")]+=1
        sensor[captured[recorder.STATUS[1]][0].hex()]+=1
        swindex[captured[recorder.STATUS[0]][0].hex()]+=1
        events.append({
            "cycle":i,"rx":x,"master_tx":t,
            "meta_166a_166c":meta,"descriptor_0b6d_0b70":desc,
            "preceding_0b6b":f"{pred:02x}","sensor_089c":captured[recorder.STATUS[1]][0].hex(),
            "swindex_0a5c":captured[recorder.STATUS[0]][0].hex(),
            "rx_meta_read_order":"RX_FIRST" if i%2==0 else "METADATA_FIRST",
            "host_gap_between_sequential_calls_ms":round(delta_ms,3),
            "rx_meta_midpoint_separation_ms":round(midpoint_separation_ms,3),
            "rx_command_elapsed_ms":round((captured[rx][2]-captured[rx][1])*1000,3),
            "meta_command_elapsed_ms":round((captured[nb][2]-captured[nb][1])*1000,3),
            "six_read_window_s":round(captured[seq[-1]][2]-captured[seq[0]][1],3),
            "observations_atomic":False,
            "physical_rx_isr_proven":False,
        })
    for a,b in zip(events,events[1:]):
        if a["rx"]["frame_hex"]!=b["rx"]["frame_hex"]:
            transitions.append({"from_cycle":a["cycle"],"to_cycle":b["cycle"],
                                "from":a["rx"]["frame_hex"],"to":b["rx"]["frame_hex"],
                                "metadata_pair":[a["meta_166a_166c"],b["meta_166a_166c"]],
                                "consumer_trigger_proven":False})
    return {
        "mode":"FORENSIC_P300_RX_BURST_NONATOMIC",
        "source_sha256":source_sha,
        "samples":len(events),"complete_verified_requests":document["total_reads"],
        "rx_frame_and_crc_counts":[{"frame":k[0],"crc_valid":k[1],"n":n}
                                   for k,n in sorted(rx_counter.items())],
        "master_frame_counts":[{"header":k[0],"crc_valid":k[1],"n":n}
                               for k,n in sorted(masters.items())],
        "metadata_counts":dict(sorted(metadata.items())),
        "descriptor_counts":dict(sorted(descriptor.items())),
        "preceding_0b6b_counts":dict(sorted(preceding.items())),
        "paired_rx_meta_preceding":[{"rx":a,"meta":b,"byte_0b6b":c,"n":n}
                                   for (a,b,c),n in sorted(pair.items())],
        "sensor_089c":dict(sorted(sensor.items())),
        "swindex_0a5c":dict(sorted(swindex.items())),
        "rx_frame_transitions":transitions,
        "cycle_events":events,
        "interrupt_register_not_sampled":True,
        "tx_rx_samples_sequential_non_atomic":True,
        "controller_uart_rx_consumer_proven":False,
        "vitotrol_enrollment_proven":False,
        "controller_writes":0,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("capture_json",type=Path)
    p.add_argument("--out",type=Path)
    args=p.parse_args()
    data=args.capture_json.read_bytes()
    if len(data)>150_000:raise InvalidEvidence("unexpectedly large capture")
    report=evaluate(json.loads(data),source_sha=hashlib.sha256(data).hexdigest())
    output=json.dumps(report,indent=2,sort_keys=True)+"\n"
    if args.out:args.out.write_text(output)
    print(output)


if __name__=="__main__":main()
