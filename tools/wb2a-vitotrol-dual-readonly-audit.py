#!/usr/bin/env python3
"""Pure offline audit of bounded Optolink FC03/FC99 and RX-context live JSON."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

HIGH = (0xE000, 0xF000, 0xFFF0)
LOW_COMPARE = ((0x0B51,0x0B40), (0x0B74,0x0B60), (0x0B7E,0x0B60))
CODES = {"READ_ONLY_NATIVE_P300", "HIGH_FC03_FC99_ABA_READ_ONLY"}


class EvidenceRejected(ValueError):
    pass


def expected_rows(rows):
    if not isinstance(rows,list):
        raise EvidenceRejected("non-list controller rows")
    for r in rows:
        if not isinstance(r,dict):
            raise EvidenceRejected("non-object controller response")
        cmd=r.get("command","")
        if not (isinstance(cmd,str) and cmd.startswith(("read;","request;3;","request;99;"))):
            raise EvidenceRejected("write/unknown opcode in claimed read-only report")
        if not r.get("valid_read") or r.get("code") != 1:
            raise EvidenceRejected("failed controller read")
        raw=r.get("data","")
        try:
            b=bytes.fromhex(raw)
        except (TypeError,ValueError) as exc:
            raise EvidenceRejected("invalid byte sequence") from exc
        n=int(cmd.split(";")[-1])
        if len(b)!=n:
            raise EvidenceRejected("controller payload size mismatch")
    return {r["command"]:r["data"] for r in rows}


def validate(doc):
    if not isinstance(doc,dict) or doc.get("target")!="20C2/0103" or doc.get("mode") not in CODES:
        raise EvidenceRejected("wrong target or response model")
    if doc.get("controller_writes")!=0:
        raise EvidenceRejected("not read-only")
    ident=expected_rows([doc["identity"]])
    if ident.get("read;0x00f8;8")!="20c2000300000103":
        raise EvidenceRejected("incorrect real controller signature")
    for name in ("baseline","after"):
        obj=expected_rows(doc[name])
        if len(obj)!=4 or any(obj.get(f"read;0x{addr:04x};1")!="00"
                              for addr in (0x27A0,0x27B0,0x7342,0x5738)):
            raise EvidenceRejected("unverified controller coding/fault")
    if doc["mode"]=="READ_ONLY_NATIVE_P300":
        rows=doc.get("rx_samples",[])
        if not 1<=len(rows)<=3:
            raise EvidenceRejected("missing repeat snapshots")
        for group in rows:
            state=expected_rows(group["rows"])
            for required in ("request;3;0x0b40;32","request;3;0x0b60;32",
                             "request;3;0x161a;32","request;3;0x1640;32",
                             "request;3;0x0054;1","request;3;0x03ac;2",
                             "read;0x0a5c;4","read;0x089c;1"):
                if required not in state:raise EvidenceRejected("missing RX evidence anchor")
        for name in ("rom_service","indirect_service","copy_context"):
            expected_rows(doc[name])
    else:
        windows=doc.get("windows",[])
        if not 2<=len(windows)<=4:
            raise EvidenceRejected("too few high-memory windows")
        for window in windows:
            vals=expected_rows(window["rows"])
            for adr in HIGH:
                for req in (f"request;3;0x{adr:04x};16",f"request;99;0x{adr:04x};2",
                            f"request;99;0x{adr+2:04x};2"):
                    if req not in vals:raise EvidenceRejected("incomplete high A/B/A")
    return doc


def summarize(first, extended, aba):
    for x in (first,extended,aba):validate(x)
    if first["mode"]!="READ_ONLY_NATIVE_P300" or extended["mode"]!="READ_ONLY_NATIVE_P300" or aba["mode"]!="HIGH_FC03_FC99_ABA_READ_ONLY":
        raise EvidenceRejected("incorrect ordered experiment set")
    first_low = expected_rows(first["indirect_service"])
    snapshot = expected_rows(first["rx_samples"][0]["rows"])
    low_matches={}
    for addr,start in LOW_COMPARE:
        cmd=f"request;99;0x{addr:04x};2"
        anchor=f"request;3;0x{start:04x};32"
        b=bytes.fromhex(snapshot[anchor])
        off=addr-start
        low_matches[f"0x{addr:04x}"]={
            "fc99":first_low.get(cmd),
            "fc03_ram_snapshot":b[off:off+2].hex(),
            "same_bytes_at_separate_times":first_low.get(cmd)==b[off:off+2].hex(),
        }
    rom=[]
    for name,source in (("first",first),("extended",extended)):
        a=expected_rows(source["rom_service"])
        ind=expected_rows(source["indirect_service"])
        for addr in HIGH:
            rom.append({
                "run":name,"address":f"0x{addr:04x}",
                "fc03_first_two":a[f"request;3;0x{addr:04x};16"][:4],
                "fc03_full":a[f"request;3;0x{addr:04x};16"],
                "fc99_first_two":ind.get(f"request;99;0x{addr:04x};2"),
            })
    aba_rows=[]
    for w in aba["windows"]:
        row=expected_rows(w["rows"])
        for adr in HIGH:
            full=row[f"request;3;0x{adr:04x};16"]
            indirect=row[f"request;99;0x{adr:04x};2"]
            nextword=row[f"request;99;0x{adr+2:04x};2"]
            aba_rows.append({
                "cycle":w["index"],"address":f"0x{adr:04x}",
                "fc03_first_two":full[:4],
                "fc03_repeated_words":len(set(full[i:i+4] for i in range(0,len(full),4)))==1,
                "fc99_first_two":indirect,"fc99_plus_two":nextword,
                "same_first_two":full[:4]==indirect,
            })
    rx=[]
    for name,doc in (("first",first),("extended",extended)):
        for samp in doc["rx_samples"]:
            obj=expected_rows(samp["rows"])
            ctx=bytes.fromhex(obj["request;3;0x0b60;32"])
            siric=int(obj["request;3;0x0054;1"],16)
            u1c1=bytes.fromhex(obj["request;3;0x03ac;2"])[1]
            tx=bytes.fromhex(obj["request;3;0x161a;32"])
            receive=bytes.fromhex(obj["request;3;0x1640;32"])
            rx.append({
                "run":name,"cycle":samp["index"],
                "scheduler_0b6b":f"{ctx[0x0B6B-0x0B60]:02x}",
                "descriptor_0b6d":ctx[13:17].hex(),
                "master_tx_prefix":tx[:4].hex(),
                "rx_ram_prefix":receive[2:8].hex(),
                "s1ric":f"{siric:02x}",
                "u1c1":f"{u1c1:02x}",
                "physical_irq_pending_seen":bool(siric & 8 or u1c1 & 8),
                "swindex":obj["read;0x0a5c;4"],
                "sensor":obj["read;0x089c;1"],
            })
    return {
        "mode": "CONTROLLER_LIVE_EVIDENCE_OFFLINE_AUDIT",
        "high_address_ab_a":aba_rows,
        "rom_high_controls":rom,
        "low_indirect_vs_ram":low_matches,
        "rx_samples":rx,
        "all_rx_descriptors_stable":all(s["descriptor_0b6d"]=="42160afe" for s in rx),
        "any_physical_rx_irq_seen":any(s["physical_irq_pending_seen"] for s in rx),
        "any_participant_swindex_seen":any(s["swindex"]!="00000000" for s in rx),
        "any_room_sensor_valid_seen":any(s["sensor"]!="03" for s in rx),
        "proven_20bit_rom_ingress":False,
        "proven_firmware_dispatcher_entry":False,
        "proven_vitotrol_registration":False,
        "request_count":sum(1+len(d["baseline"])+len(d["after"])+
            (len(d.get("rom_service",[]))+len(d.get("indirect_service",[]))+
             len(d.get("copy_context",[]))+
             sum(len(g["rows"]) for g in d.get("rx_samples",[]))+
             sum(len(g["rows"]) for g in d.get("windows",[]))) for d in (first,extended,aba)),
        "source_json_only":True,
        "restoration_verified_separately_not_in_source_json":True,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("first","extended","aba"):
        p.add_argument("--"+name,required=True,type=Path)
    a=p.parse_args()
    objs=[]
    for f in (a.first,a.extended,a.aba):
        if f.stat().st_size>200_000: p.error("oversize evidence")
        objs.append(json.loads(f.read_text()))
    print(json.dumps(summarize(*objs),sort_keys=True,indent=2))


if __name__=="__main__":
    main()
