#!/usr/bin/env python3
"""Two-cycle, five-window native P300 FC03 low-RAM probe for WB2A 20C2/0103.

This is a READER ONLY; the external root supervisor must first arm a
verified independent, already-existing VS1 restore timer. No SFR/DMA,
program-ROM high address, reset, maintenance, or controller write command.
Raw response files stay private under /tmp. MQTT uses original splitter.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import statistics
import sys

HERE=Path(__file__).resolve().parent
BASE=Path("/home/chatgpt-admin/optolink-vitotrol-rpm-20261010/tools/wb2a-vitotrol-persistent-mqtt-readonly.py")
spec=importlib.util.spec_from_file_location("wb2a_five_window_broker_base",BASE)
if spec is None or spec.loader is None:raise RuntimeError("pinned original read-only transport absent")
base=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=base
spec.loader.exec_module(base)

WINDOWS={
 "ram_1de0":(0x1DE0,32),
 "ram_1e60":(0x1E60,32),
 "ram_3300":(0x3300,32),
 "ram_0700":(0x0700,32),
 "ram_2180":(0x2180,32),
}
TARGET="20c2000300000103"
MODE="EXACT_POSTRESTART_FC03_P300_FIVE_WINDOWS_READ_ONLY"
PINNED_OUTPUT=Path("/tmp/wb2a-postrestart-five-window-live-20261012.json")
READS={key:f"request;3;0x{addr:04x};{n}" for key,(addr,n) in WINDOWS.items()}
for key,cmd in READS.items():
    if cmd in base.ALLOWED and base.ALLOWED[cmd]!=WINDOWS[key]:
        raise RuntimeError("conflicting physical SRAM read alias")
    base.ALLOWED[cmd]=WINDOWS[key]
    base.P300_ONLY.add(cmd)

class Refused(ValueError):pass

def capture(bus):
    def req(command):
        if command not in base.P300_ONLY:
            raise Refused("not within pinned native P300 whitelist")
        row=bus.request(command,deadline_s=5)
        addr,length=base.ALLOWED[command]
        if (row.get("command")!=command
            or row.get("address")!=f"0x{addr:04x}"
            or row.get("controller_read_only") is not True
            or row.get("valid_read") is not True
            or len(bytes.fromhex(row.get("data","")))!=length):
            raise Refused("malformed or insufficient low RAM read")
        return row
    identity=req(base.IDENTITY)
    if identity["data"]!=TARGET:raise Refused("unexpected device or software")
    pre=[req(cmd) for cmd in base.CHECKS]
    if any(row["data"]!="00" for row in pre):
        raise Refused("preflight state guard not clear")
    cycles=[]
    names=list(READS)
    for index in range(2):
        order=names if index==0 else list(reversed(names))
        row={key:req(READS[key]) for key in order}
        cycles.append({"index":index,"reads":row,
                       "all_low_RAM_reads_sequential_not_atomic":True})
    post=[req(cmd) for cmd in base.CHECKS]
    if any(row["data"]!="00" for row in post):
        raise Refused("postflight state guard no longer clear")
    if len(bus.request_log)!=19:
        raise Refused("expected exactly nineteen no-write requests")
    values={key:[x["reads"][key]["data"] for x in cycles] for key in names}
    return {
        "schema":1,"mode":MODE,"target":"20C2/0103",
        "identity":identity,"preflight":pre,"cycles":cycles,"postflight":post,
        "controller_reads":19,"controller_writes":0,
        "one_serial_owner":True,
        "ordinary_16bit_low_sram_FC03_only":True,
        "physical_RAM_nonatomic":True,
        "original_VS1_restore_required":True,
        "comparisons_within_new_samples":{
            key:{"same_32_bytes":v[0]==v[1],
                 "different_byte_count":sum(a!=b for a,b in zip(bytes.fromhex(v[0]),bytes.fromhex(v[1])))}
            for key,v in values.items()
        },
        "median_request_ms":round(statistics.median(row["duration_ms"] for row in bus.request_log),3),
        "main_program_ROM_bytes_observed":0,
    }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--execute",action="store_true")
    p.add_argument("--output",type=Path)
    a=p.parse_args()
    if not a.execute:
        print(json.dumps({"mode":"DRY_RUN_NO_CONTROLLER_IO",
          "five_fixed_reads":READS,"cycles":2,"identity":base.IDENTITY,
          "guards":base.CHECKS,"writes":0},indent=2))
        return
    if a.output!=PINNED_OUTPUT:
        p.error("only pinned private /tmp result file supported")
    base.assert_protocol(True)
    if "/opt/optolink" not in sys.path:sys.path.insert(0,"/opt/optolink")
    from homeassistant_publish import connect_mqtt
    with base.BrokerReads(lambda:connect_mqtt(retries=1,delay=1)) as broker:
        result=capture(broker)
    a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"mode":MODE,"reads":result["controller_reads"],"writes":0,
      "two_cycle_matches":{k:v["same_32_bytes"] for k,v in result["comparisons_within_new_samples"].items()},
      "private_capture_path":str(a.output)}))

if __name__=="__main__":
    main()
