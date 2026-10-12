#!/usr/bin/env python3
"""Native P300 read-only windows for CRC-valid whole TX, RX tail and meta pair.

Five strictly whitelisted 32-byte controller Physical_READ per cycle:
 TX 0x161a/32 (whole <=22B master frame), fused 0x164b/32 (RX CRC end
 + metadata 166a), paired-meta 0x164c/32 (166a+166b), fused again, TX again.
 All reads sequential/non-atomic, no MCU RX ISR or on-wire attribution.
 Before native-P300 configuration a SEPARATE watchdog must be running.
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
spec=importlib.util.spec_from_file_location("vt_master31_parent",
    HERE/"wb2a-vitotrol-fused-rx-window.py")
if spec is None or spec.loader is None:raise RuntimeError("source missing")
fused=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=fused
spec.loader.exec_module(fused)

TX="request;3;0x161a;32"
FUSED=fused.OVERLAP
METAPAIR="request;3;0x164c;32"
STATUS=fused.base.BASELINE
IDENTITY=fused.base.IDENTITY[0]
EXTRA=(fused.FINAL[0],fused.FINAL[1])
ALLOWED=frozenset((TX,FUSED,METAPAIR,IDENTITY,
                   *(a[0] for a in STATUS),*EXTRA))
assert ALLOWED == set((TX,FUSED,METAPAIR,IDENTITY,*(a[0] for a in STATUS),*EXTRA))
assert all(s.startswith(("read;","request;3;")) for s in ALLOWED)
WIDTH={c:(32 if c in (TX,FUSED,METAPAIR) else fused.base.ALLOWED[c][1])
       for c in ALLOWED}
ADDR={**{k:fused.base.ALLOWED[k][0] for k in ALLOWED
          if k in fused.base.ALLOWED},
      FUSED:0x164b,METAPAIR:0x164c}


class Refused(ValueError):pass


def reader(command,*,runner=subprocess.run, old=fused.base.invoke):
    if command not in ALLOWED:raise Refused("unknown or write P300 command")
    if command in fused.base.ALLOWED:
        row=old(command)
    else:
        pkt=runner(["/usr/local/bin/optolink-debug","request",
                    command,"--timeout","6"],
                   capture_output=True,text=True,timeout=11,check=False)
        entries=list(fused.base.RESPONSE.finditer(pkt.stdout))
        if pkt.returncode!=0 or len(entries)!=1:
            raise Refused("unexpected native P300 response")
        entry=entries[0]
        if int(entry[1])!=1 or int(entry[2],16)!=ADDR[command]:
            raise Refused("controller rejected or wrong physical address")
        try:payload=bytes.fromhex(entry[3])
        except ValueError as exc:raise Refused("nonhex hardware response") from exc
        if len(payload)!=WIDTH[command]:raise Refused("wrong physical read size")
        row={"command":command,"address":f"0x{ADDR[command]:04x}",
             "code":1,"data":payload.hex(),"valid_read":True}
    if (not isinstance(row,dict) or row.get("command")!=command
        or row.get("address")!=f"0x{ADDR[command]:04x}"
        or row.get("valid_read") is not True):
        raise Refused("unverified request/response match")
    try:data=bytes.fromhex(row["data"])
    except (TypeError,ValueError,KeyError) as exc:raise Refused("missing data") from exc
    if len(data)!=WIDTH[command]:raise Refused("missing response bytes")
    return row


def timed(command,*,read_fn=reader,clock=time.monotonic):
    start=clock();r=read_fn(command);end=clock()
    if start>end or end-start>12:raise Refused("request timeout/nonmonotonic")
    return {"command":command,"response":r,"start":round(start,6),
            "end":round(end,6),"elapsed_ms":round((end-start)*1000,3)}


def state_gate(records):
    if len(records)!=4:raise Refused("missing baseline")
    for record,expected in zip(records,STATUS):
        if (record["command"]!=expected[0]
            or record["response"]["data"]!="00"):
            raise Refused("nonzero coding/fault before or after")


def run(*,cycles=8,read_fn=reader,clock=time.monotonic):
    if type(cycles) is not int or not 4<=cycles<=8:
        raise Refused("only 4..8 bounded sampling cycles")
    identity=timed(IDENTITY,read_fn=read_fn,clock=clock)
    if identity["response"]["data"]!=fused.base.EXPECTED_ID:
        raise Refused("wrong target firmware")
    before=[timed(x[0],read_fn=read_fn,clock=clock) for x in STATUS]
    state_gate(before)
    rounds=[]
    seq=(TX,FUSED,METAPAIR,FUSED,TX)
    for i in range(cycles):
        rows=[timed(cmd,read_fn=read_fn,clock=clock) for cmd in seq]
        rounds.append({"index":i,"rows":rows,"read_order":list(seq),
                       "rx_master_phy_timing_proven":False,
                       "reads_are_sequential":True})
    after=[timed(x[0],read_fn=read_fn,clock=clock) for x in STATUS]
    state_gate(after)
    end=[timed(c,read_fn=read_fn,clock=clock) for c in EXTRA]
    return {
        "mode":"READONLY_FUSED_META_PAIR_WHOLE_TX_20C2",
        "identity":identity,"device":"20C2/0103",
        "baseline":before,"rounds":rounds,"after":after,
        "vitotrol_state":end,
        "samples":cycles,"total_commands":11+len(seq)*cycles,
        "controller_writes":0,"controller_dma_uart_irq_writes":0,
        "same_copy_pair_166a_166b":True,
        "master_0x31_crc_in_one_controller_copy":True,
        "master_and_rx_separate_nonatomic_reads":True,
        "uart1_ISR_or_KM_PHY_sampled":False,
        "no_second_serial_owner":True,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--execute",action="store_true")
    p.add_argument("--cycles",type=int,default=8)
    p.add_argument("--output",type=Path)
    args=p.parse_args()
    if not args.execute:
        print(json.dumps({"mode":"DRY_RUN","reads":sorted(ALLOWED),
                          "controller_writes":0,"restore_required":True},indent=2))
        return
    if not args.output or not str(args.output).startswith("/tmp/wb2a-vitotrol-master31-pair-"):
        p.error("output must be private /tmp/wb2a-vitotrol-master31-pair-*")
    fused.base.require_native()
    result=run(cycles=args.cycles)
    args.output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"cycle_count":args.cycles,"reads":result["total_commands"],
                      "writes":0,"output":str(args.output)},sort_keys=True))


if __name__=="__main__":main()
