#!/usr/bin/env python3
"""Forensic audit of bounded single-owner persistent MQTT/P300 read-only capture.

Per-read controller copy is coherent only for the returned byte range, NOT
an electrically measured UART1 ISR, ACK or master-to-slave request/reply.
The shared MQTT response channel has no request UUID: exact attribution
against concurrent same-address callers remains unproven.
"""
from __future__ import annotations
from collections import Counter
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import sys

HERE=Path(__file__).resolve().parent
def helper(filename,name):
    spec=importlib.util.spec_from_file_location(name,HERE/filename)
    if spec is None or spec.loader is None:raise ValueError("missing original audit source")
    m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m
    spec.loader.exec_module(m);return m
reader=helper("wb2a-vitotrol-persistent-mqtt-readonly.py","vt_persistent_rx_source")
crc=helper("wb2a-vitotrol-optolink-rx-audit.py","vt_persistent_rx_crc")


class InvalidEvidence(ValueError):pass


def check_read(row,cmd):
    if not isinstance(row,dict) or row.get("command")!=cmd or row.get("valid_read") is not True:
        raise InvalidEvidence("read not positively attested")
    addr,size=reader.ALLOWED[cmd]
    if row.get("address")!=f"0x{addr:04x}" or row.get("controller_read_only") is not True:
        raise InvalidEvidence("incorrect returned address")
    try:data=bytes.fromhex(row["data"])
    except (ValueError,TypeError,KeyError) as exc:raise InvalidEvidence("invalid P300 bytes") from exc
    if len(data)!=size:raise InvalidEvidence("response shortened/oversized")
    start=row.get("mono_start");end=row.get("mono_response")
    if (type(start) not in (float,int) or type(end) not in (float,int)
        or start>=end or end-start>5.5):
        raise InvalidEvidence("stale or nonmonotonic MQTT reply")
    return data,float(start),float(end)


def decode_tx(raw:bytes) -> dict:
    if len(raw)!=32:raise InvalidEvidence("whole master frame not in one 32B copy")
    n=raw[3]
    if not 8<=n<=22:
        return {"header":raw[:3].hex(),"frame":None,"crc_valid":False,
                "declared_length_in_range":False,
                "physical_km_bus_traffic_proven":False}
    frame=raw[:n]
    return {"header":frame[:3].hex(),"frame":frame.hex(),
            "crc_valid":crc.crc16_kermit(frame)==0,
            "declared_length_in_range":True,
            "physical_km_bus_traffic_proven":False}


def inspect(capture:dict,*,sha256=None)->dict:
    if (not isinstance(capture,dict) or capture.get("mode")!="PERSISTENT_MQTT_READONLY_P300"
        or capture.get("target")!="20C2/0103"
        or capture.get("controller_writes")!=0
        or capture.get("mqtt_response_request_id_available") is not False
        or capture.get("one_serial_owner") is not True
        or capture.get("controller_state_atomic") is not False):
        raise InvalidEvidence("not source-attested bounded original P300 run")
    idraw,idstart,idend=check_read(capture["identity"],reader.IDENTITY)
    if idraw.hex()!=reader.VALID_ID:raise InvalidEvidence("not WB2A 20C2/0103")
    cycles=capture.get("cycles")
    if not isinstance(cycles,list) or not 4<=len(cycles)<=32 or capture.get("cycle_count")!=len(cycles):
        raise InvalidEvidence("wrong measurement limit")
    for key in ("baseline","after"):
        checks=capture.get(key)
        if not isinstance(checks,list) or len(checks)!=4:
            raise InvalidEvidence("missing before/after guards")
        for item,cmd in zip(checks,reader.CHECKS):
            if check_read(item,cmd)[0]!=bytes(1):
                raise InvalidEvidence("controller coding/fault not original")
    final=capture.get("final")
    if not isinstance(final,list) or len(final)!=2:
        raise InvalidEvidence("missing Vitotrol state samples")
    endstate=[check_read(row,cmd)[0].hex() for row,cmd in zip(
        final,("read;0x0a5c;4","read;0x089c;1"))]
    expected_total=11+len(cycles)*3
    if capture.get("read_count")!=expected_total:
        raise InvalidEvidence("unexpected number of P300 reads")
    rx_counts=Counter();meta_counts=Counter();tx_counts=Counter();crc_count=Counter()
    joint=Counter();rows_out=[];sample_order=[]
    last=capture["baseline"][-1]["mono_response"]
    duration_ms=[];temporal_cross_mismatches=0
    for i,cycle in enumerate(cycles):
        expect=(reader.RX,reader.META,reader.MASTER) if i%2==0 else (
                reader.MASTER,reader.META,reader.RX)
        records=cycle.get("rows")
        if cycle.get("index")!=i or not isinstance(records,list) or len(records)!=3:
            raise InvalidEvidence("missing or reordered sample")
        payload={}
        for row,cmd in zip(records,expect):
            raw,start,finish=check_read(row,cmd)
            if start<last:raise InvalidEvidence("overlapping/stale individual copies")
            last=finish
            duration_ms.append(row["duration_ms"])
            payload[cmd]=(raw,start,finish)
        fused=payload[reader.RX][0]
        meta=payload[reader.META][0]
        tx=decode_tx(payload[reader.MASTER][0])
        # [0] is crc end at 164b; [31] is 166a in a single copy.
        # Meta copy starts 164c and its bytes 30/31 are 166a/166b.
        pair=f"{fused[0]:02x}|{fused[-1]:02x}"
        cur=f"{meta[-2]:02x}{meta[-1]:02x}"
        rx_counts[pair]+=1;meta_counts[cur]+=1
        tx_counts[tx["header"]]+=1
        crc_count["VALID" if tx["crc_valid"] else "UNVERIFIED"]+=1
        joint[f"{pair}|{cur}|{tx['header']}"]+=1
        differ=(fused[-1]!=meta[-2])
        temporal_cross_mismatches+=int(differ)
        rows_out.append({
            "cycle":i,"fused_rx_last_crc_and_166a":pair,
            "metadata_pair_166a_166b_from_one_copy":cur,
            "meta_difference_166a_minus_166b_mod256":(meta[-2]-meta[-1])&255,
            "metadata_166a_same_across_two_sequential_reads":not differ,
            "master":tx,"request_order":list(expect),
            "data_copies_not_atomic_with_each_other":True,
            "elapsed_three_reads_ms":round((max(z[2] for z in payload.values())-
                                              min(z[1] for z in payload.values()))*1000,3),
        })
        sample_order.append(list(expect))
    all_durations=capture.get("durations_ms")
    if not isinstance(all_durations,list) or len(all_durations)!=expected_total:
        raise InvalidEvidence("missing full duration inventory")
    return {
        "mode":"OFFLINE_VALIDATED_32_CYCLE_P300_FAST_RX_META_MASTER",
        "source_sha256":sha256,
        "cycle_count":len(cycles),"validated_reads":expected_total,
        "rx_crc_last_and_166a_single_copy_counts":dict(sorted(rx_counts.items())),
        "metadata_166a166b_single_copy_counts":dict(sorted(meta_counts.items())),
        "master_header_counts":dict(sorted(tx_counts.items())),
        "master_frame_crc_counts":dict(sorted(crc_count.items())),
        "crosscopy_rx_meta_master_counts":dict(sorted(joint.items())),
        "crosscopy_166a_disagreements":temporal_cross_mismatches,
        "three_read_rounds":rows_out,
        "median_single_request_ms":round(statistics.median(all_durations),3),
        "p95_single_request_ms":round(sorted(all_durations)[int(.95*(len(all_durations)-1))],3),
        "zero_controller_writes":True,
        "vitotrol_swindex":endstate[0],"sensor_089c":endstate[1],
        "mqtt_same_address_request_attribution_proven":False,
        "physical_km_bus_event_or_uart_irq_proven":False,
        "next_safe_step":"record two distinct metadata states closer in time; no RAM writes",
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("original",type=Path)
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    blob=a.original.read_bytes()
    if len(blob)>350_000:raise InvalidEvidence("unexpectedly large recording")
    out=json.dumps(inspect(json.loads(blob),sha256=hashlib.sha256(blob).hexdigest()),
                   sort_keys=True,indent=2)+"\n"
    if a.out:a.out.write_text(out)
    print(out)


if __name__=="__main__":main()
