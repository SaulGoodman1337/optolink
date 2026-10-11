#!/usr/bin/env python3
"""SHA-attested offline correlation of rare B1 RX/meta with master 0x31.

Sources: real Oct 9 Deep + 79 fullRAM, and Oct 11 fused FC03 read capture.
No serial, sockets, subprocess, service changes, writes, ROM, or fake
UART ISR causality. A master TX split across FC03 reads is NOT one frame.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile

HERE=Path(__file__).resolve().parent
def source(filename,name):
    spec=importlib.util.spec_from_file_location(name,HERE/filename)
    if spec is None or spec.loader is None:raise RuntimeError("missing original evidence parser")
    m=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=m
    spec.loader.exec_module(m)
    return m

ctx=source("wb2a-vitotrol-optolink-rx-context.py","vt_class31_ctx")
crc=ctx.audit
fused=source("wb2a-vitotrol-fused-rx-audit.py","vt_class31_fused")
DEEP_SHA=crc.KNOWN_ARCHIVES["deep"]
FULL_SHA=crc.KNOWN_ARCHIVES["fullram"]
FUSED_SHA="d22dfbc58cad99798be16aac9bf8b9c55598eeb35f25316b54690bffc5c3a258"
BURST_SHA="7d539f98f5861554bf325c981bae33d13263997f96bc7233d42f694b0f5de65f"
NORMAL_B1_A="0001b10a010110fe23d8"
NORMAL_B1_B="0001b10a01011000d2c6"
RARE_B1="0001b10a010100004353"


class InvalidEvidence(ValueError):pass


def pinned(blob:bytes, sha:str, bound:int) -> None:
    if type(blob) is not bytes or not 0<len(blob)<=bound or hashlib.sha256(blob).hexdigest()!=sha:
        raise InvalidEvidence("source hash/size mismatch")


def deep_scan(tar:tarfile.TarFile)->dict:
    manifest=crc._manifest(tar,"p300-deep")
    payload=crc._verified(tar,manifest,"p300-deep","p300.jsonl",max_size=5_000_000)
    records=[];tx_header_counts=Counter();tx_crc=Counter()
    rx_counts=Counter();rare_events=[]
    all_rx=0
    for line in payload.splitlines():
        row=json.loads(line)
        reads=row.get("reads",{})
        if "ram_1640" not in reads:continue
        all_rx+=1
        low=ctx._block(row,"ram_1600","0x1600")
        mid=ctx._block(row,"ram_1620","0x1620")
        rx=ctx._block(row,"ram_1640","0x1640")
        raw_tx=low[0x161a-0x1600:]+mid
        head=raw_tx[:3].hex()
        n=raw_tx[3]
        frame=raw_tx[:n] if 8<=n<=22 else b""
        tx_valid=bool(frame and len(frame)==n and crc.crc16_kermit(frame)==0)
        tx_header_counts[head]+=1;tx_crc["VALID" if tx_valid else "MIXED_OR_BAD"]+=1
        rxframe=crc.parse_1640_block(rx)["frame_hex"]
        rx_counts[rxframe]+=1
        tx0=reads["ram_1600"]["t_monotonic"]
        tx1=reads["ram_1620"]["t_monotonic"]
        tr=reads["ram_1640"]["t_monotonic"]
        if not (tx0<tx1<tr):
            raise InvalidEvidence("invalid timestamps or nonsequential reads")
        if head=="010031" or rxframe==RARE_B1:
            records.append({
                "index":row["index"],
                "master_header":head,
                "composite_master_frame":frame.hex(),
                "master_crc_valid":tx_valid,
                "master_crc_residual":f"0x{crc.crc16_kermit(frame):04x}" if frame else None,
                "receiver_frame":rxframe,
                "receiver_crc_valid":crc.crc16_kermit(bytes.fromhex(rxframe))==0,
                "tx_half_read_gap_ms":round((tx1-tx0)*1000,3),
                "rx_after_first_tx_ms":round((tr-tx0)*1000,3),
                "both_master_halves_were_one_physical_frame_proven":False,
                "master_command_caused_rx_proven":False,
            })
        if rxframe==RARE_B1:
            rare_events.append(row["index"])
    if all_rx!=295 or rare_events!=[145]:
        raise InvalidEvidence("not the known original 295-sample rare trace")
    if tx_header_counts["010031"]!=2:
        raise InvalidEvidence("0x31 headers are not the known two samples")
    if len(records)!=2 or {x["index"] for x in records}!={145,1417}:
        raise InvalidEvidence("unexpected original class31 sample set")
    valid_with_rare=sum(x["receiver_frame"]==RARE_B1 and x["master_crc_valid"] for x in records)
    if valid_with_rare!=0:
        raise InvalidEvidence("unexpected actual verified 0x31/rare pairing")
    return {
        "total_nonatomic_rx_samples":all_rx,
        "rx_frames":dict(sorted(rx_counts.items())),
        "master_tx_first_3_bytes":dict(sorted(tx_header_counts.items())),
        "master_composite_crc_validity":dict(sorted(tx_crc.items())),
        "class31_header_instances":len(records),
        "class31_valid_complete_master_frames_with_rare_rx":valid_with_rare,
        "rare_rx_indices":rare_events,
        "class31_rows":records,
        "class31_request_causes_rare_receiver_proven":False,
        "crc_invalid_composite_proves_bad_wire_packet":False,
    }


def fullram_special(tar:tarfile.TarFile)->dict:
    manifest=crc._manifest(tar,"p300-fullram")
    framemeta=Counter(); rare=[]
    for i in range(1,80):
        name=f"snapshots/s{i:05d}"
        meta=json.loads(crc._verified(tar,manifest,"p300-fullram",name+".json",max_size=8000))
        img=crc._verified(tar,manifest,"p300-fullram",name+".bin",max_size=20_480)
        if len(img)!=20_480 or meta.get("complete") is not True or meta.get("device_id")!="20c2" or meta.get("software")!="0103":
            raise InvalidEvidence("unmatched 20C2 full RAM image")
        a=lambda x,n:img[x-0x400:x-0x400+n]
        rx=a(0x1642,10).hex()
        rxmeta=a(0x166a,3).hex()
        framemeta[(rx,rxmeta)]+=1
        if rx==RARE_B1:
            rare.append({"index":i,"rx_frame":rx,"metadata":rxmeta,
                         "tx_161a_nonatomic_snapshot_prefix":a(0x161a,16).hex(),
                         "0b6b":a(0x0b6b,1).hex(),
                         "absolute_scan_atomic":False})
    if len(rare)!=1 or rare[0]["index"]!=64 or rare[0]["metadata"]!="0a0401":
        raise InvalidEvidence("not the original one rare fullram sample")
    return {
        "complete_images":79,"rare_images":rare,
        "frame_to_166a_166c_pairs":[{"frame":a,"metadata":b,"n":v}
                                     for (a,b),v in sorted(framemeta.items())],
        "rare_166b_is_04":rare[0]["metadata"][2:4]=="04",
        "rare_166c_is_01":rare[0]["metadata"][4:6]=="01",
        "scan_image_not_atomic":True,
    }


def crc31_counterfactuals(row:dict) -> dict:
    if row["master_header"]!="010031" or row["index"]!=145:
        raise InvalidEvidence("only the observed non-CRC-valid 145 request")
    raw=bytes.fromhex(row["composite_master_frame"])
    if len(raw)!=9 or raw[:6]!=bytes.fromhex("010031090101"):
        raise InvalidEvidence("wrong master composite")
    possibilities={}
    for register in (0x00,0x01,0x10,0x11):
        pre=raw[:6]+bytes([register])
        checksum=crc.crc16_kermit(pre).to_bytes(2,"little")
        possibilities[f"0x{register:02x}"]={
            "crc_valid_synthetic_request":(pre+checksum).hex(),
            "recorded_crc_tail_matches":checksum==raw[7:9],
            "checksum_tail":checksum.hex(),
            "observed_on_wire":False,
        }
    return {
        "observed_unverified_composite":raw.hex(),
        "recorded_last_three_bytes":raw[-3:].hex(),
        "counterfactuals":possibilities,
        "no_counterfactual_transmitted":True,
    }


def run(deep:bytes,full:bytes,fused_blob:bytes,burst:bytes)->dict:
    for val,sha,bound in ((deep,DEEP_SHA,crc.MAX_ARCHIVE_BYTES),
                          (full,FULL_SHA,crc.MAX_ARCHIVE_BYTES),
                          (fused_blob,FUSED_SHA,150_000),
                          (burst,BURST_SHA,150_000)):
        pinned(val,sha,bound)
    with tarfile.open(fileobj=io.BytesIO(deep),mode="r:gz") as dt:
        d=deep_scan(dt)
    with tarfile.open(fileobj=io.BytesIO(full),mode="r:gz") as ft:
        f=fullram_special(ft)
        m=crc._manifest(ft,"p300-fullram")
        timed=ctx.fullram_snapshot_timeline(ft,m,64)
    live=fused.inspect(json.loads(fused_blob))
    raw_burst=json.loads(burst)
    if raw_burst.get("mode")!="P300_KNOWN_READONLY_FAST_RX" or raw_burst.get("controller_writes")!=0:
        raise InvalidEvidence("wrong new burst capture")
    if live["fused_crc_tail_to_metadata_byte_counts"]!={"53|0a":1,"c6|06":15}:
        raise InvalidEvidence("live rare pair changed")
    event145=next(x for x in d["class31_rows"] if x["index"]==145)
    event1417=next(x for x in d["class31_rows"] if x["index"]==1417)
    if event145["master_crc_valid"] or not event1417["master_crc_valid"]:
        raise InvalidEvidence("historic CRC discrimination lost")
    return {
        "mode":"SHA_ATTESTED_VITOTROL_B1_MASTER31_RX_META_CORRELATION",
        "source_hashes":{"deep":DEEP_SHA,"fullram":FULL_SHA,
                         "fused":FUSED_SHA,"rx_burst":BURST_SHA},
        "deep":d,"historic_fullram":f,
        "special_snapshot_64_read_timeline":timed,
        "synthetic_crc31_register_examples":crc31_counterfactuals(event145),
        "fused_live_32byte_crc_tail_and_meta":live["fused_crc_tail_to_metadata_byte_counts"],
        "fused_live_rare_166b_read_proven":False,
        "fullram_historic_rare_166a_and_166b":"0a04",
        "rare_frame_independently_seen_in_deep_and_fullram":True,
        "CRC_valid_class31_causes_rare_B1":False,
        "potential_class31_involvement_excluded":False,
        "unknown_rx_parser_or_ISR_verified":False,
        "controller_reads":0,"controller_writes":0,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--deep",type=Path,required=True)
    p.add_argument("--fullram",type=Path,required=True)
    p.add_argument("--fused",type=Path,required=True)
    p.add_argument("--burst",type=Path,required=True)
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    inputs=(a.deep,a.fullram,a.fused,a.burst)
    if any(q.is_symlink() or not q.is_file() for q in inputs):
        p.error("four regular original evidence files required")
    if a.out and not str(a.out).startswith("/tmp/wb2a-vitotrol-"):
        p.error("only /tmp/private research output")
    result=run(*(q.read_bytes() for q in inputs))
    obj=json.dumps(result,indent=2,sort_keys=True)+"\n"
    if a.out:a.out.write_text(obj)
    print(obj)


if __name__=="__main__":main()
