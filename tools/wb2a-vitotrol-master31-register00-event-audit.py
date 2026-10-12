#!/usr/bin/env python3
"""Strict offline proof chain: natural CRC-valid 31/00 -> rare CRC-valid B1/00.

This audits RAM copies read sequentially through one existing Optolink owner,
not electrical KM-Bus transmission or an MCU RX ISR. Original sources pinned
to Oct 9 fullRAM archive and Oct 11 event capture. Never contacts controller.
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
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,HERE/path)
    if spec is None or spec.loader is None:raise RuntimeError("missing source")
    m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m
    spec.loader.exec_module(m);return m
crc=load("wb2a-vitotrol-optolink-rx-audit.py","vt_reg00_audit_crc")
ev=load("wb2a-vitotrol-persistent-event-watch.py","vt_reg00_audit_event")

EVENT_SHA="26669707fbd572f25a384b865740c730ec9f4b7e1035cde33cbb142ae99d2e27"
FULL_SHA=crc.KNOWN_ARCHIVES["fullram"]
KNOWN_MASTER="0100310901010027fa"
KNOWN_REPLY="0001b10a010100004353"


class InvalidEvidence(ValueError):pass


def validate_event(event:dict)->dict:
    if not isinstance(event,dict):raise InvalidEvidence("missing event")
    before=event.get("master_before",{})
    after=event.get("master_after",{})
    rx=event.get("rx_immediate",{})
    pair=event.get("metadata_raw_read",{})
    if event.get("index")!=85:
        raise InvalidEvidence("not the known natural TX register00 event")
    for r,addr in ((before,0x161a),(after,0x161a),(rx,0x1640),(pair,0x164c)):
        if (not isinstance(r,dict) or not r.get("valid_read")
            or r.get("controller_read_only") is not True
            or r.get("address")!=f"0x{addr:04x}"):
            raise InvalidEvidence("unverified read identity/address")
        if len(bytes.fromhex(r["data"]))!=32:
            raise InvalidEvidence("not a single exact controller 32B copy")
        if not r["mono_start"]<r["mono_response"]:
            raise InvalidEvidence("bad sample timestamp")
    prev=[before,rx,pair,after]
    if any(a["mono_response"]>b["mono_start"] for a,b in zip(prev,prev[1:])):
        raise InvalidEvidence("source reads overlap/inverted")
    tx=bytes.fromhex(before["data"])
    txframe=tx[:tx[3]]
    if txframe.hex()!=KNOWN_MASTER or crc.crc16_kermit(txframe)!=0:
        raise InvalidEvidence("not genuine one-copy register 00 CRC-valid 0x31")
    rxbuf=bytes.fromhex(rx["data"])
    if rxbuf[:2]!=b"\x00\x00":
        raise InvalidEvidence("noncanonical RX frame start")
    frame=rxbuf[2:2+rxbuf[5]]
    if frame.hex()!=KNOWN_REPLY or crc.crc16_kermit(frame)!=0:
        raise InvalidEvidence("not rare CRC-valid B1/00 response")
    if txframe[6]!=0 or frame[6]!=0:
        raise InvalidEvidence("0x31 master register != B1 response register")
    followtx=bytes.fromhex(after["data"])
    nextframe=followtx[:followtx[3]]
    if (followtx[:3]!=bytes.fromhex("0100b1") or
        crc.crc16_kermit(nextframe)!=0):
        raise InvalidEvidence("master did not naturally transition to next B1")
    meta=bytes.fromhex(pair["data"])
    if meta[-2:]!=bytes.fromhex("0a07"):
        raise InvalidEvidence("not authenticated 0A07 metadata pair")
    report={
        "natural_event_index":85,
        "master_class31_register00":txframe.hex(),
        "master_crc_valid":True,
        "slave_class01_b1_register00":frame.hex(),
        "slave_crc_valid":True,
        "matching_register_byte":0,
        "metadata_166a166b_from_single_copy":meta[-2:].hex(),
        "next_master_crc_valid_b1":nextframe.hex(),
        "t_master_request_start":before["mono_start"],
        "master_read_duration_ms":before["duration_ms"],
        "rx_read_duration_ms":rx["duration_ms"],
        "meta_read_duration_ms":pair["duration_ms"],
        "next_tx_read_duration_ms":after["duration_ms"],
        "host_gap_after_master_ms":round(
            (rx["mono_start"]-before["mono_response"])*1000,3),
        "time_between_master_copy_start_and_rx_copy_end_ms":round(
            (rx["mono_response"]-before["mono_start"])*1000,3),
        "time_between_master_copy_start_and_metapair_end_ms":round(
            (pair["mono_response"]-before["mono_start"])*1000,3),
        "four_controller_reads_are_sequential":True,
        "controller_uart1_ISR_or_class11_vitotrol_proven":False,
        "onwire_km_master_slave_causality_proven":False,
    }
    return report


def inspect(event_source:bytes,archive_source:bytes)->dict:
    if type(event_source) is not bytes or hashlib.sha256(event_source).hexdigest()!=EVENT_SHA:
        raise InvalidEvidence("not pinned natural event original")
    if type(archive_source) is not bytes or hashlib.sha256(archive_source).hexdigest()!=FULL_SHA:
        raise InvalidEvidence("not pinned original full RAM archive")
    x=json.loads(event_source)
    if (x.get("mode")!="NATURAL_MASTER_EVENT_GATED_OPTOLINK_P300_READONLY" or
        x.get("device")!="20C2/0103" or x.get("controller_writes")!=0 or
        x.get("master_read_count")!=96 or x.get("read_count")!=134 or
        x.get("triggered_header_counts")!={"010031":1} or
        x.get("vitotrol_swindex",{}).get("data")!="00000000"):
        raise InvalidEvidence("unverified live sampling scope")
    if len(x.get("followups",[]))!=1 or len(x.get("background_samples",[]))!=12:
        raise InvalidEvidence("unexpected event/block scope")
    event=validate_event(x["followups"][0])
    with tarfile.open(fileobj=io.BytesIO(archive_source),mode="r:gz") as tar:
        mf=crc._manifest(tar,"p300-fullram")
        meta=json.loads(crc._verified(tar,mf,"p300-fullram",
                       "snapshots/s00064.json",max_size=8000))
        image=crc._verified(tar,mf,"p300-fullram",
                       "snapshots/s00064.bin",max_size=20480)
        if len(image)!=20480 or meta.get("complete") is not True or meta.get("snapshot_id")!=64:
            raise InvalidEvidence("historical snapshot not complete")
    old=image[0x164c-0x400:0x166c-0x400]
    new=bytes.fromhex(x["followups"][0]["metadata_raw_read"]["data"])
    change=[f"0x{0x164c+i:04x}" for i,(a,b) in enumerate(zip(old,new)) if a!=b]
    if change!=["0x166b"] or old[-2:]!=b"\x0a\x04" or new[-2:]!=b"\x0a\x07":
        raise InvalidEvidence("missing historical-to-live one-byte change")
    if image[0x1642-0x400:0x164c-0x400].hex()!=KNOWN_REPLY:
        raise InvalidEvidence("historical rare B1 frame not same")
    return {
        "mode":"OFFLINE_SHA_ATTESTED_CLASS31_00_B1_00_EVENT",
        "event_original_sha256":EVENT_SHA,
        "archive_original_sha256":FULL_SHA,
        "sampling_scope":{"master_tx_samples":96,"real_P300_read_requests":134,
                          "natural_31_followups":1,
                          "normal_B1_background_reads":12},
        "event":event,
        "historic_special_snapshot":64,
        "old_metadata_0x164c_32":old.hex(),
        "new_metadata_0x164c_32":new.hex(),
        "historic_live_identical_bytes_out_of_32":31,
        "historical_to_live_changed_ram_byte_addresses":change,
        "old_meta_166a166b":"0a04",
        "new_meta_166a166b":"0a07",
        "prior_six_byte_difference_invariant_disproven":True,
        "vitotrol_enrolled":False,
        "controller_rom_dump_obtained":False,
        "controller_writes":0,"new_hardware_io":0,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("event_source",type=Path)
    p.add_argument("fullram_source",type=Path)
    p.add_argument("--out",type=Path)
    args=p.parse_args()
    for source in (args.event_source,args.fullram_source):
        if source.is_symlink() or not source.is_file():
            p.error("regular private original evidence required")
    if args.event_source.stat().st_size>300_000 or args.fullram_source.stat().st_size>crc.MAX_ARCHIVE_BYTES:
        p.error("source exceeds size limit")
    result=inspect(args.event_source.read_bytes(),args.fullram_source.read_bytes())
    text=json.dumps(result,indent=2,sort_keys=True)+"\n"
    if args.out:args.out.write_text(text)
    print(text)


if __name__=="__main__":main()
