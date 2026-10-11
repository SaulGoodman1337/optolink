#!/usr/bin/env python3
"""Read-only forensic validator of captured M16C DMA SFR snapshots.

No controller connection, no DMA trigger/write or serial-owner change.
The 20-bit SARi and DARi registers are interpreted per the M16C/62P manual.
"""
from __future__ import annotations
from collections import Counter
import argparse
import json
from pathlib import Path

IDENTITY = "20c2000300000103"
DMA_REG = "request;3;0x0020;32"
DMA_TRIG = "request;3;0x03b8;4"
SENSOR = "read;0x089c;1"
SWINDEX = "read;0x0a5c;4"
BASELINE = ("read;0x27a0;1", "read;0x27b0;1",
            "read;0x7342;1", "read;0x5738;1")


class InvalidCapture(ValueError):
    pass


def check_baseline(rows):
    if len(rows) != len(BASELINE):
        raise InvalidCapture("missing baseline")
    for item, command in zip(rows, BASELINE):
        if checked_simple(item,command,1) != bytes(1):
            raise InvalidCapture("controller codings or current fault changed")


def checked_simple(row: dict, command: str, size: int) -> bytes:
    if not isinstance(row, dict) or row.get("command")!=command or row.get("code")!=1 or row.get("valid_read") is not True:
        raise InvalidCapture("wrong controller read")
    try:
        data=bytes.fromhex(row["data"])
    except (ValueError,KeyError,TypeError) as exc:
        raise InvalidCapture("invalid bytes") from exc
    if len(data)!=size:
        raise InvalidCapture("unexpected length")
    parts=command.split(";")
    requested=int(parts[2 if parts[0]=="request" else 1],16)
    if row.get("address")!=f"0x{requested:04x}":
        raise InvalidCapture("wrong response address")
    return data


def interpret_dma(raw: bytes, selectors: bytes):
    if len(raw)!=32 or len(selectors)!=4:
        raise InvalidCapture("incorrect DMA register lengths")
    channels=[]
    for i in (0,1):
        offset=i*16
        source=int.from_bytes(raw[offset:offset+3],"little")
        dest=int.from_bytes(raw[offset+4:offset+7],"little")
        if source > 0xFFFFF or dest > 0xFFFFF:
            raise InvalidCapture("reserved high pointer bits not zero")
        control=raw[offset+12]
        if control&0xC0:
            raise InvalidCapture("reserved DMCON bits nonzero")
        channels.append({
            "channel":i, "sar":f"0x{source:05x}", "dar":f"0x{dest:05x}",
            "tcr":int.from_bytes(raw[offset+8:offset+10],"little"),
            "con":f"0x{control:02x}",
            "dma_enabled":bool(control&0x08),
            "dma_request":bool(control&0x04),
            "src_forward":bool(control&0x10),
            "dst_forward":bool(control&0x20),
            "selector":f"0x{selectors[2*i]:02x}",
            "program_rom_source":0xC0000<=source<=0xFFFFF
        })
    return channels


def audit(doc: dict) -> dict:
    if not isinstance(doc,dict) or doc.get("target")!="20C2/0103" or doc.get("mode")!="M16C_DMA_ROM_BRIDGE_OCCUPANCY_READ_ONLY":
        raise InvalidCapture("wrong controller or mode")
    if doc.get("controller_writes")!=0 or doc.get("dma_triggered") is not False:
        raise InvalidCapture("not a read-only hardware capture")
    ident=checked_simple(doc.get("identity"),"read;0x00f8;8",8)
    if ident.hex()!=IDENTITY:
        raise InvalidCapture("wrong device signature")
    check_baseline(doc.get("baseline",[]))
    check_baseline(doc.get("after",[]))
    samples=doc.get("dma_snapshots",[])
    if not isinstance(samples,list) or not 2<=len(samples)<=6:
        raise InvalidCapture("invalid snapshot count")
    entries=[]
    for idx, snap in enumerate(samples):
        if not isinstance(snap,dict) or snap.get("index")!=idx:
            raise InvalidCapture("invalid sample index")
        arr=snap.get("reads")
        if not isinstance(arr,list) or len(arr)!=4:
            raise InvalidCapture("missing DMA read")
        data={row["command"]:row for row in arr}
        if len(data)!=4 or set(data)!={DMA_REG,DMA_TRIG,SENSOR,SWINDEX}:
            raise InvalidCapture("extra/missing controller operation")
        r=checked_simple(data[DMA_REG],DMA_REG,32)
        t=checked_simple(data[DMA_TRIG],DMA_TRIG,4)
        v=checked_simple(data[SENSOR],SENSOR,1).hex()
        idx_value=checked_simple(data[SWINDEX],SWINDEX,4).hex()
        entries.append({"index":idx,"channels":interpret_dma(r,t),
                        "sensor_status":v,"remote_index":idx_value})
    out=[]
    for ch in (0,1):
        rows=[s["channels"][ch] for s in entries]
        counters={r["tcr"] for r in rows}
        sources={r["sar"] for r in rows}
        enabled=sum(r["dma_enabled"] for r in rows)
        selectors={r["selector"] for r in rows}
        destinations={r["dar"] for r in rows}
        out.append({
            "channel":ch,"selectors":sorted(selectors),
            "source_set":sorted(sources),
            "dest_set":sorted(destinations),
            "transfer_counts":sorted(counters),
            "dma_enabled_samples":enabled,
            "nonconstant_transfer_count":len(counters)>1,
            "source_position_changed":len(sources)>1,
            "rom_source_samples":sum(x["program_rom_source"] for x in rows),
            "cannot_assume_unused":(len(counters)>1 or len(sources)>1 or enabled>0 or len(selectors)>0),
        })
    return {"target":"20C2/0103","mode":"OFFLINE_DMA_ROM_BRIDGE_FEASIBILITY",
            "samples":entries,"channels":out,
            "observed_uart_dma_ownership":[out[0]["selectors"],out[1]["selectors"]],
            "all_channels_must_be_treated_as_owned":all(x["cannot_assume_unused"] for x in out),
            "viable_safe_live_dma_write_plan":False,
            "dma_has_20bit_source_address_architecture":True,
            "rom_data_obtained":False,"controller_writes":0,
            "uncertain_silicon_variant":True}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("source",type=Path)
    p.add_argument("--out",type=Path)
    args=p.parse_args()
    if args.source.stat().st_size>80_000:
        p.error("oversized source file")
    result=audit(json.loads(args.source.read_text()))
    data=json.dumps(result,indent=2,sort_keys=True)+chr(10)
    if args.out:
        args.out.write_text(data)
    print(data)


if __name__=="__main__":
    main()
