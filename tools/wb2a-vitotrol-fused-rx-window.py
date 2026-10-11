#!/usr/bin/env python3
"""Read-only optolink P300 capture of co-located RX CRC tail and metadata byte.

A single 32-byte Physical_READ 0x164b..0x166a includes byte 0x164b (last
byte of 10B B1 RX frame) and 0x166a (first RX-neighbor metadata byte).
The two positions are in ONE controller source-copy, in contrast to the
previous two slow P300 requests. Do not imply CPU/ISR atomicity.

Only a preexisting original serial owner may be used; an independent
systemd rollback must be armed before the P300 protocol switch.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("wb2a_vt_fused_parent",
    HERE/"wb2a-vitotrol-dual-readonly-probe.py")
if spec is None or spec.loader is None:raise RuntimeError("missing tested P300 helper")
base=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=base
spec.loader.exec_module(base)

OVERLAP="request;3;0x164b;32"
ADDR=0x164B
COUNT=32
assert ADDR+COUNT-1==0x166A
RX="request;3;0x1640;32"
META="request;3;0x1660;32"
FINAL=("read;0x0a5c;4","read;0x089c;1")
PREVIOUS=frozenset((base.IDENTITY[0],*(x[0] for x in base.BASELINE),RX,META,*FINAL))
assert PREVIOUS.issubset(base.ALLOWED)
ALLOWED=PREVIOUS|{OVERLAP}


class Refused(ValueError):pass


def read(cmd:str,*,runner=subprocess.run,other=base.invoke)->dict:
    if cmd not in ALLOWED:raise Refused("read not in bounded whitelist")
    if cmd!=OVERLAP:
        out=other(cmd)
    else:
        p=runner(["/usr/local/bin/optolink-debug","request",OVERLAP,"--timeout","6"],
                 capture_output=True,text=True,timeout=11,check=False)
        matches=list(base.RESPONSE.finditer(p.stdout))
        if p.returncode!=0 or len(matches)!=1:
            raise Refused("overlap P300 response failed")
        item=matches[0]
        status=int(item[1]);addr=int(item[2],16);payload=item[3]
        if status!=1 or addr!=ADDR:
            raise Refused("unexpected controller status/address")
        try:raw=bytes.fromhex(payload)
        except ValueError as exc:raise Refused("invalid window data") from exc
        if len(raw)!=COUNT:raise Refused("read response not 32 bytes")
        out={"command":OVERLAP,"code":1,"address":f"0x{ADDR:04x}",
             "data":raw.hex(),"valid_read":True,"controller_read_only":True}
    addr,size=(ADDR,COUNT) if cmd==OVERLAP else base.ALLOWED[cmd]
    if (not isinstance(out,dict) or out.get("command")!=cmd or
        out.get("address")!=f"0x{addr:04x}" or out.get("valid_read") is not True):
        raise Refused("source response not attested")
    try:data=bytes.fromhex(out["data"])
    except (ValueError,KeyError,TypeError) as exc:raise Refused("malformed hex response") from exc
    if len(data)!=size:raise Refused("short/long reply")
    return out


def timed(cmd,*,reader=read,clock=time.monotonic):
    a=clock()
    row=reader(cmd)
    b=clock()
    if b<a or b-a>12:raise Refused("timestamp/timeout guard")
    return {"command":cmd,"response":row,"begin":round(a,6),
            "end":round(b,6),"elapsed_ms":round((b-a)*1000,3)}


def baseline(items):
    if len(items)!=4:raise Refused("missing before/after")
    for i,(cmd,_,_) in enumerate(base.BASELINE):
        if items[i]["command"]!=cmd or items[i]["response"]["data"]!="00":
            raise Refused("controller coding/fault state not neutral")


def run(*,cycles:int=8,reader=read,clock=time.monotonic):
    if type(cycles) is not int or not 4<=cycles<=8:raise Refused("4..8 cycles only")
    idrow=timed(base.IDENTITY[0],reader=reader,clock=clock)
    if idrow["response"]["data"]!=base.EXPECTED_ID:
        raise Refused("not 20C2/0103 WB2A")
    before=[timed(x[0],reader=reader,clock=clock) for x in base.BASELINE]
    baseline(before)
    results=[]
    for i in range(cycles):
        # Bracket previously validated full B1 and metadata reads by two
        # independent same-window overlap captures.
        seq=(OVERLAP,RX,META,OVERLAP)
        rows=[timed(cmd,reader=reader,clock=clock) for cmd in seq]
        results.append({"index":i,"reads":rows,"frame_metadata_atomic":False,
                        "two_bytes_within_same_fc03_copy":True})
    after=[timed(x[0],reader=reader,clock=clock) for x in base.BASELINE]
    baseline(after)
    last=[timed(x,reader=reader,clock=clock) for x in FINAL]
    return {
        "mode":"P300_FUSED_RX_CRC_METADATA_READ_ONLY",
        "target":"20C2/0103","identity":idrow,"baseline":before,
        "cycles":results,"after":after,"vitotrol_status":last,
        "full_frames_and_fused_samples_not_simultaneous":True,
        "single_p300_copy_is_not_isr_atomic":True,
        "controller_writes":0,
        "uart_dma_irq_writes":0,
        "requests":1+8+2+4*cycles,
        "sample_count":cycles,
        "new_serial_owner":False,
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute",action="store_true")
    parser.add_argument("--cycles",type=int,default=8)
    parser.add_argument("--output",type=Path)
    options=parser.parse_args()
    if not options.execute:
        print(json.dumps({"mode":"DRY_RUN","allowed":sorted(ALLOWED),
                          "writes":0,"independent_restore_required":True},indent=2))
        return
    if not options.output or not str(options.output).startswith("/tmp/wb2a-vitotrol-fused-rx-"):
        parser.error("strict /tmp/wb2a-vitotrol-fused-rx- output required")
    base.require_native()
    report=run(cycles=options.cycles)
    options.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"cycles":options.cycles,"requests":report["requests"],"writes":0,
                      "output":str(options.output)},sort_keys=True))


if __name__=="__main__":main()
