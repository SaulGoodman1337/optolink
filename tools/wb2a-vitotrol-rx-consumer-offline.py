#!/usr/bin/env python3
"""A: cross-audit original RX RAM, deep polling, and Vitotrol preseed outcomes.

Read-only OFFLINE forensic work. Full-RAM/deep archives and the two original
preseed session JSONs must match SHA-pinned local evidence. No service
interaction, socket, serial, firmware, DMA, UART, SFR, or controller writes.
"""
from __future__ import annotations
from collections import Counter
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import sys
import tarfile

HERE=Path(__file__).resolve().parent
BASE=0x0400
RAM_SIZE=20_480
PIN_PRESEED={
    "v300_initial_preseed": "ae5ae8bc80839a51800c5457e71b439f639665c911019e5415f15b9c2fcd0d32",
    "v300_earlier_preseed": "5067e57033525811c258ac5c3152ce74b5df88e67f3b3551cfdb7e18fea14797",
}
ORIGINAL_B3="0011b3100101f811f938fa01fb0a1db1"
NATURAL_B1="0001b10a010110fe23d8"
SPECIAL_B1="0001b10a010100004353"
DESC="42160afe"


def load_helper(filename, name):
    spec=importlib.util.spec_from_file_location(name,HERE/filename)
    if spec is None or spec.loader is None:
        raise RuntimeError("original hash-attestation helper missing")
    m=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=m
    spec.loader.exec_module(m)
    return m


audit=load_helper("wb2a-vitotrol-optolink-rx-audit.py","wb2a_vt_rx_consumer_audit")
context=load_helper("wb2a-vitotrol-optolink-rx-context.py","wb2a_vt_rx_consumer_context")


class EvidenceRejected(ValueError):pass


def pinned_file(path:Path, sha:str, limit:int) -> bytes:
    if not path.is_file() or path.is_symlink() or path.stat().st_size>limit:
        raise EvidenceRejected("bounded regular file required")
    data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=sha:
        raise EvidenceRejected("source not the pinned hardware evidence")
    return data


def preseed_analysis(doc:dict, label:str) -> dict:
    if label not in PIN_PRESEED or not isinstance(doc,dict):
        raise EvidenceRejected("unrecognized preseed source")
    if (doc.get("remote_accepted_by_regulator") is not False
        or doc.get("controller_rx_isr_or_parser_invocation_proven") is not False
        or doc.get("km_bus_phy_is_not_emulated") is not True
        or doc.get("restore_ok") is not True
        or doc.get("rx_physical_write_readback_exact") is not True):
        raise EvidenceRejected("original preseed readback/recovery state mismatch")
    samples=doc.get("live_snapshots")
    if not isinstance(samples,list) or not 4<=len(samples)<=12:
        raise EvidenceRejected("wrong bounded preseed sample count")
    rows=[]
    for i,s in enumerate(samples):
        rawrx=s.get("rx_candidate",{}).get("raw")
        rawtx=s.get("master_tx",{}).get("raw")
        if not isinstance(rawrx,str) or not isinstance(rawtx,str):
            raise EvidenceRejected("missing receiver/transmitter raw bytes")
        try:
            rx=bytes.fromhex(rawrx)
            tx=bytes.fromhex(rawtx)
            meta=bytes.fromhex(s["rx_metadata"])
            desc=bytes.fromhex(s["rx_descriptor"])
            idx=int(s["rx_descriptor_index"],16)
        except (TypeError,KeyError,ValueError) as exc:
            raise EvidenceRejected("invalid live sample values") from exc
        if len(rx)!=32 or len(tx)!=32 or len(meta)!=3 or len(desc)!=4:
            raise EvidenceRejected("incorrect sample memory width")
        if rx[:2]!=bytes(2) or desc!=bytes.fromhex(DESC) or not 0<=idx<=0xff:
            raise EvidenceRejected("preseed descriptor or receive payload invalid")
        size=rx[5]
        if not 8<=size<=20:
            raise EvidenceRejected("unexpected receiver frame length")
        frame=rx[2:2+size]
        if audit.crc16_kermit(frame)!=0:
            raise EvidenceRejected("not a complete CRC-valid original RX")
        if frame.hex() not in {ORIGINAL_B3,NATURAL_B1,SPECIAL_B1}:
            raise EvidenceRejected("unrecognized RX frame form in source")
        if not isinstance(s.get("sample_s"),(int,float)):
            raise EvidenceRejected("missing sample monotonic time")
        rows.append({
            "index":i,"sample_s":s["sample_s"],
            "rx_frame":frame.hex(),"rx_class":f"0x{frame[1]:02x}",
            "rx_metadata":meta.hex(),"descriptor":desc.hex(),
            "descriptor_preceding_byte":f"0x{idx:02x}",
            "master_tx_prefix":tx[:3].hex(),
            "observer_is_uart_phy":False,
        })
    if any(b["sample_s"]<=a["sample_s"] for a,b in zip(rows,rows[1:])):
        raise EvidenceRejected("non-increasing sample time")
    # This pair is significant: original B3 in RAM was replaced naturally
    # without changing the observed 0x166A..166C metadata triple.
    initial=rows[0];second=rows[1]
    if initial["rx_frame"]!=ORIGINAL_B3 or second["rx_frame"]!=NATURAL_B1:
        raise EvidenceRejected("expected original preseed -> natural B1 sequence not found")
    return {
        "source":label,"samples":len(rows),
        "initial_class11_B3_found_in_ram":True,
        "next_class01_B1_replaced_B3":True,
        "initial_metadata":initial["rx_metadata"],
        "second_metadata":second["rx_metadata"],
        "metadata_unchanged_across_replacement":initial["rx_metadata"]==second["rx_metadata"],
        "all_metadata_equal":len({r["rx_metadata"] for r in rows})==1,
        "descriptor_stable":len({r["descriptor"] for r in rows})==1,
        "preceding_descriptor_byte_values":dict(sorted(Counter(r["descriptor_preceding_byte"] for r in rows).items())),
        "master_header_counts":dict(sorted(Counter(r["master_tx_prefix"] for r in rows).items())),
        "actual_controller_vitotrol_registered":False,
        "controller_state_writes_authorized_by_this_audit":False,
        "sparse_non_atomic_rows":rows,
    }


def fullram_analysis(tar:tarfile.TarFile) -> dict:
    mf=audit._manifest(tar,"p300-fullram")
    pairs=Counter(); frame_counts=Counter(); status_counts=Counter()
    descriptor_counts=Counter(); class11=0
    for i in range(1,80):
        name=f"snapshots/s{i:05d}"
        meta=json.loads(audit._verified(tar,mf,"p300-fullram",name+".json",max_size=8000))
        raw=audit._verified(tar,mf,"p300-fullram",name+".bin",max_size=RAM_SIZE)
        if len(raw)!=RAM_SIZE or meta.get("complete") is not True or meta.get("marker")!="COMPLETE":
            raise EvidenceRejected("missing full immutable original SRAM image")
        def at(addr,n):
            return raw[addr-BASE:addr-BASE+n]
        rx=at(0x1642,20)
        rx_len=rx[3]
        if not 8<=rx_len<=20 or audit.crc16_kermit(rx[:rx_len])!=0:
            raise EvidenceRejected("non-valid natural RX")
        frame=rx[:rx_len].hex()
        prefix=at(0x0B6B,1).hex()
        neighbor=at(0x166A,3).hex()
        descriptor=at(0x0B6D,4).hex()
        frame_counts[frame]+=1
        status_counts[prefix]+=1
        descriptor_counts[descriptor]+=1
        pairs[(frame,prefix,neighbor)]+=1
        class11+=int(rx[1]==0x11)
    return {
        "snapshots":79,"rx_counts":dict(sorted(frame_counts.items())),
        "descriptor_0b6d_counts":dict(sorted(descriptor_counts.items())),
        "preceding_byte_0b6b_counts":dict(sorted(status_counts.items())),
        "rx_by_descriptor_preceding_and_166a":[
            {"rx":a,"preceding":b,"neighbor_166a_166c":c,"count":n}
            for (a,b,c),n in sorted(pairs.items())],
        "class11_rx_buffer_samples":class11,
        "metadata_and_frame_not_read_atomically":True,
        "rx_descriptor_semantics_proven":False,
    }


def deep_analysis(tar:tarfile.TarFile) -> dict:
    # Already validates FC03 block addresses, widths, monotonic read ordering
    # for the rare events; no assertion that samples represent wire frames.
    older=context.deep_context(tar)
    if older.get("paired_1640_contexts")!=295:
        raise EvidenceRejected("expected 295 genuine archived deep read pairs")
    return {
        "paired_contexts":older["paired_1640_contexts"],
        "tx_crc_validity":older["tx_crc_validity"],
        "master_header_counts":older["paired_tx_header_counts"],
        "rare_events":older["special_events"],
        "physical_uart1_irq_verified":False,
        "non_atomic_master_to_rx_observation":True,
    }


def run(full:bytes,deep:bytes,preseeds:dict[str,bytes]) -> dict:
    if set(preseeds)!=set(PIN_PRESEED):
        raise EvidenceRejected("both original preseed experiments required")
    if hashlib.sha256(full).hexdigest()!=audit.KNOWN_ARCHIVES["fullram"] or (
        hashlib.sha256(deep).hexdigest()!=audit.KNOWN_ARCHIVES["deep"]):
        raise EvidenceRejected("unknown original RAM/deep input SHA")
    # Full original bundle audit independently validates CRC/manifest.
    full_info=audit.audit_bundle("fullram",full)
    deep_info=audit.audit_bundle("deep",deep)
    pre={}
    for label,content in preseeds.items():
        if hashlib.sha256(content).hexdigest()!=PIN_PRESEED[label]:
            raise EvidenceRejected("preseed JSON SHA mismatch")
        pre[label]=preseed_analysis(json.loads(content),label)
    with tarfile.open(fileobj=io.BytesIO(full),mode="r:gz") as t:
        ram=fullram_analysis(t)
    with tarfile.open(fileobj=io.BytesIO(deep),mode="r:gz") as t:
        deep_result=deep_analysis(t)
    if full_info.get("frames_sampled")!=79 or deep_info.get("frames_sampled")!=295:
        raise EvidenceRejected("archive number/sample checksum check failed")
    return {
        "mode":"SHA_ATTESTED_RX_CONSUMER_OFFLINE",
        "source_sha256":{"fullram":audit.KNOWN_ARCHIVES["fullram"],
                         "deep":audit.KNOWN_ARCHIVES["deep"],
                         **preseeds_sha()},
        "fullram":ram,"deep":deep_result,"preseed":pre,
        "total_preseed_snapshots":sum(x["samples"] for x in pre.values()),
        "preseed_b3_then_b1_without_166a_state_change":all(
            x["metadata_unchanged_across_replacement"] for x in pre.values()),
        "class11_ram_injection_proves_uart_rx":False,
        "rx_ready_flag_identified":False,
        "consumer_dispatcher_or_vitotrol_commit_proven":False,
        "observer_samples_non_atomic":True,
        "controller_io":0,"controller_writes":0,
    }


def preseeds_sha():
    return {"preseed_"+k:v for k,v in PIN_PRESEED.items()}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fullram",type=Path,required=True)
    p.add_argument("--deep",type=Path,required=True)
    p.add_argument("--preseed",type=Path,required=True)
    p.add_argument("--preseed-earlier",type=Path,required=True)
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    for path in (a.fullram,a.deep):
        if path.is_symlink() or not path.is_file() or path.stat().st_size>audit.MAX_ARCHIVE_BYTES:
            p.error("unbounded/missing original source")
    pre={
        "v300_initial_preseed":pinned_file(a.preseed,PIN_PRESEED["v300_initial_preseed"],25_000),
        "v300_earlier_preseed":pinned_file(a.preseed_earlier,PIN_PRESEED["v300_earlier_preseed"],25_000),
    }
    result=run(a.fullram.read_bytes(),a.deep.read_bytes(),pre)
    output=json.dumps(result,indent=2,sort_keys=True)+"\n"
    if a.out:
        a.out.write_text(output)
    print(output)


if __name__=="__main__":main()
