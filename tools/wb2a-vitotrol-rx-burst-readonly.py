#!/usr/bin/env python3
"""Optolink P300 fast RX-read-only probe with fixed, known-live FC03 locations.

Requires prior independent systemd restoration and singleton original serial
owner (handled by a SEPARATE session supervisor). Rejects any non-P300 owner,
unexpected identity/coding/fault, wrong response, or request outside whitelist.
Never emits controller writes, DMA triggers, UART reconfiguration or KM frames.
The individual P300 reads are sequential, NOT atomic.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parent
MODULE=ROOT/"wb2a-vitotrol-dual-readonly-probe.py"
spec=importlib.util.spec_from_file_location("wb2a_rx_burst_parent",MODULE)
if spec is None or spec.loader is None:raise RuntimeError("missing pre-validated safe P300 transport")
base=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=base
spec.loader.exec_module(base)

# Every request has already been hardware-tested. No high-ROM, FC99,
# EEPROM, out-of-list, physical write or speculative ROM bank command.
RX=("request;3;0x1640;32","request;3;0x1660;32")
NEIGHBOR=("request;3;0x0b60;32","request;3;0x161a;32")
STATUS=("read;0x0a5c;4","read;0x089c;1")
ACCEPT=frozenset((base.IDENTITY[0],*(x[0] for x in base.BASELINE),
                  *RX,*NEIGHBOR,*STATUS))
assert ACCEPT.issubset(base.ALLOWED)
assert all((c.startswith("request;3;") or c.startswith("read;")) for c in ACCEPT)
EXPECTED_SIZES={x:base.ALLOWED[x][1] for x in ACCEPT}


class Refused(RuntimeError):pass


def invoke_timed(cmd:str, *, execute=base.invoke, clock=time.monotonic, now=None)->dict:
    if cmd not in ACCEPT:
        raise Refused("request not on exact known-safe read whitelist")
    start=clock()
    reply=execute(cmd)
    end=clock()
    if not isinstance(reply,dict) or not reply.get("valid_read"):
        raise Refused("hardware read not confirmed")
    if reply.get("command")!=cmd or reply.get("address")!=f"0x{base.ALLOWED[cmd][0]:04x}":
        raise Refused("mismatched response")
    try:payload=bytes.fromhex(reply["data"])
    except (ValueError,KeyError,TypeError) as exc:raise Refused("malformed reply") from exc
    if len(payload)!=EXPECTED_SIZES[cmd]:
        raise Refused("unexpected response payload size")
    if end<start or end-start>12.0:
        raise Refused("sample timeout or nonmonotonic clock")
    if now is None:
        now=lambda:datetime.now(timezone.utc).isoformat()
    return {"command":cmd,"result":reply,"mono_start":round(start,6),
            "mono_end":round(end,6),"duration_ms":round(1000*(end-start),3),
            "utc_completed":now()}


def check_baseline(reads,*,label:str):
    if len(reads)!=len(base.BASELINE):
        raise Refused("missing "+label+" baseline")
    if any(r["command"]!=a[0] or r["result"]["data"]!="00"
           for r,a in zip(reads,base.BASELINE)):
        raise Refused("configuration or device fault mismatch at "+label)


def run(*, cycles:int=8,execute=base.invoke,clock=time.monotonic)->dict:
    if type(cycles) is not int or not 4<=cycles<=8:
        raise Refused("only 4..8 tightly bounded cycles")
    started=clock()
    identity=invoke_timed(base.IDENTITY[0],execute=execute,clock=clock)
    if identity["result"]["data"]!=base.EXPECTED_ID:
        raise Refused("device identity is not original 20C2/0103")
    before=[invoke_timed(cmd,execute=execute,clock=clock) for cmd,_,_ in base.BASELINE]
    check_baseline(before,label="before")
    rounds=[]
    for cycle in range(cycles):
        # Swap ordering of candidate RX and metadata per cycle; never infer
        # simultaneous state nor IRQ causality from the resulting records.
        lead=RX if cycle%2==0 else tuple(reversed(RX))
        seq=(*lead,*NEIGHBOR,*STATUS)
        rows=[invoke_timed(c,execute=execute,clock=clock) for c in seq]
        rounds.append({"index":cycle,"order":list(seq),"reads":rows,
                       "atomic":False,"controller_rx_ownership_proven":False})
    after=[invoke_timed(cmd,execute=execute,clock=clock) for cmd,_,_ in base.BASELINE]
    check_baseline(after,label="after")
    return {
        "mode":"P300_KNOWN_READONLY_FAST_RX",
        "device":"20C2/0103",
        "identity":identity,"baseline":before,
        "rounds":rounds,"after":after,
        "samples":cycles,"total_reads":1+8+6*cycles,
        "duration_seconds":round(clock()-started,3),
        "all_reads_nonatomic":True,
        "no_code_injection":True,
        "controller_writes":0,
        "new_serial_owner":False,
        "controller_rom_read_verified":False,
        "km_bus_rx_isr_verified":False,
        "vitotrol_parser_commit_verified":False,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--execute",action="store_true")
    p.add_argument("--cycles",type=int,default=8)
    p.add_argument("--output",type=Path)
    opts=p.parse_args()
    if not opts.execute:
        print(json.dumps({"status":"DRY_RUN_ONLY","whitelist":sorted(ACCEPT),
                          "controller_writes":0,"independent_restore_required":True},indent=2))
        return
    if not opts.output or not str(opts.output).startswith("/tmp/wb2a-vitotrol-rx-burst-"):
        p.error("output must be under /tmp/wb2a-vitotrol-rx-burst-")
    base.require_native()
    result=run(cycles=opts.cycles)
    opts.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"output":str(opts.output),"reads":result["total_reads"],
                      "cycles":result["samples"],
                      "elapsed_s":result["duration_seconds"],"writes":0},sort_keys=True))


if __name__=="__main__":main()
