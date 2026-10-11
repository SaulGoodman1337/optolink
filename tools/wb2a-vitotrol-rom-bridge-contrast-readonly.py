#!/usr/bin/env python3
"""Bounded physical/virtual ROM-bridge contrast on WB2A 20C2/0103.

P300 phase ONLY, existing splitter sole serial owner via MQTT; no new UART,
no writes, no interrupt/DMA manipulations, no unusual/unspecified FCs.
The supervisor *must* schedule verified independent original-VS1 rollback
before starting this tool. An optolink physical read of a 16-bit address
does not expose M16C 20-bit program ROM.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import statistics
import sys

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location(
 "wb2a_vt_rom_bridge_contrast_base",HERE/"wb2a-vitotrol-persistent-mqtt-readonly.py")
if not spec or not spec.loader:raise RuntimeError("original guarded P300 client missing")
base=importlib.util.module_from_spec(spec);sys.modules[spec.name]=base
spec.loader.exec_module(base)
# Strict finite set of *physical* low-16-bit FC03 memory reads, not a
# generalized "read any address" API and no undocumented protocol opcodes.
READS={
 "physical_3300":"request;3;0x3300;32",
 "physical_2182":"request;3;0x2182;16",
 "physical_1de5":"request;3;0x1de5;16",
 "physical_f000":"request;3;0xf000;8",
 "physical_fff0":"request;3;0xfff0;8",
}
EXPECTED={
 "physical_3300":(0x3300,32),
 "physical_2182":(0x2182,16),
 "physical_1de5":(0x1de5,16),
 "physical_f000":(0xf000,8),
 "physical_fff0":(0xfff0,8),
}
if set(READS)!=set(EXPECTED):raise RuntimeError("broken explicit whitelist")
for k,cmd in READS.items():
 address,count=EXPECTED[k]
 if cmd!=f"request;3;0x{address:04x};{count}":
  raise RuntimeError("physical ROM contrast must use FC03 fixed size")
 if cmd in base.ALLOWED and base.ALLOWED[cmd]!=(address,count):
  raise RuntimeError("conflicting existing read descriptor")
 base.ALLOWED[cmd]=(address,count)
 base.P300_ONLY.add(cmd)

TARGET="20c2000300000103"
KNOWN_VS1={
 "physical_3300":"ff040000ffff14031419700101040000",
 "physical_2182":"ff"*16,
 "physical_1de5":"ff"*16,
 "physical_f000":"ff"*8,
 "physical_fff0":"ff"*8,
}


class Refused(ValueError):pass


def capture(bus,*,cycles=2):
 if type(cycles) is not int or cycles!=2:
  raise Refused("exactly two bounded physical-copy contrast cycles")
 def read(cmd):
  if cmd not in base.P300_ONLY:
   raise Refused("not fixed read-only P300 command")
  row=bus.request(cmd)
  if (row.get("controller_read_only") is not True or
      row.get("valid_read") is not True or
      row.get("address")!=f"0x{base.ALLOWED[cmd][0]:04x}" or
      len(bytes.fromhex(row["data"]))!=base.ALLOWED[cmd][1]):
   raise Refused("invalid controller read")
  return row
 id_=read(base.IDENTITY)
 if id_["data"]!=TARGET:raise Refused("wrong controller identity")
 before=[read(c) for c in base.CHECKS]
 if any(x["data"]!="00" for x in before):raise Refused("nonoriginal coding/status, fail-closed")
 cycles_out=[]
 for i in range(cycles):
  order=tuple(READS) if i%2==0 else tuple(reversed(tuple(READS)))
  rows={k:read(READS[k]) for k in order}
  cycles_out.append({"index":i,"reads":rows})
 after=[read(c) for c in base.CHECKS]
 if any(x["data"]!="00" for x in after):raise Refused("controller status changed")
 sw=read("read;0x0a5c;4")
 if sw["data"]!="00000000":raise Refused("unexpected participant index")
 comparisons={}
 for k,(addr,count) in EXPECTED.items():
  values=[row["reads"][k]["data"] for row in cycles_out]
  old=KNOWN_VS1[k]
  comparisons[k]={
   "address":f"0x{addr:04x}","physical_bytes":count,
   "physical_first_copy":values[0],
   "physical_second_copy":values[1],
   "physical_copies_equal":values[0]==values[1],
   "vs1_virtual_read_observation_from_same_live_day":old,
   "first_physical_prefix_equals_vs1":values[0].startswith(old),
   "physical_vs_virtual_equal_on_overlapping_bytes":
        values[0][:len(old)//2*2]==old[:len(values[0])],
   "virtual_and_physical_proven_same_address_domain":False,
   "physical_20bit_program_rom_access_proven":False,
  }
 return {
  "mode":"EXACT_FC03_P300_VS1_CONTRAST_READONLY",
  "identity":id_,"target":"20C2/0103",
  "preflight":before,"postflight":after,"vitotrol_index":sw,
  "cycles":cycles_out,"comparisons":comparisons,
  "controller_reads":len(bus.request_log),
  "median_request_ms":round(statistics.median(
      x["duration_ms"] for x in bus.request_log),3),
  "controller_writes":0,
  "physical_high_rom_banks_addressable":False,
  "original_v300_class11_registered":False,
  "independent_original_vs1_restore_required":True,
  "new_serial_owner":False,
  "ordinary_16bit_low_address_fc03_only":True,
  "onwire_MCU_20bit_flash_bank_selection_proven":False,
 }


def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("--execute",action="store_true")
 p.add_argument("--output",type=Path)
 a=p.parse_args()
 if not a.execute:
  print(json.dumps({"mode":"DRY_RUN","fixed_reads":READS,
      "repeats":2,"new_controller_writes":0},indent=2))
  return
 if not a.output or str(a.output)!="/tmp/wb2a-vitotrol-rom-contrast-p300-20261011.json":
  p.error("only pinned private /tmp ROM contrast source")
 base.assert_protocol(True)
 if "/opt/optolink" not in sys.path:sys.path.insert(0,"/opt/optolink")
 from homeassistant_publish import connect_mqtt
 with base.BrokerReads(lambda:connect_mqtt(retries=1,delay=1)) as bus:
  result=capture(bus)
 a.output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
 print(json.dumps({"reads":result["controller_reads"],"writes":0,
    "matches":{k:v["physical_vs_virtual_equal_on_overlapping_bytes"]
               for k,v in result["comparisons"].items()}}))


if __name__=="__main__":main()
