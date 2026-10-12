#!/usr/bin/env python3
"""20C2 P300 read-only A/B/A: is FC0x65=FC05 and FC0x63=FC03?

Extremely narrow native-P300-only FC03/05/63/65 comparison; through the
existing production splitter, never an independent serial owner. 0x63 and 0x65
have high three sequence bits set while their low five bits alias 0x03 / 0x05.
Not allowed to call equality based on host interpretation alone; verify the
real WB2A device and retain diagnostic failures.
No flash/ROM address, no RAM/UART/SFR/EEPROM/physical writes, no mode
programming, no 64-KiB scan, no controller-side DMA/IRQ/reset, no new service.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location(
 "wb2a_fc_sequence_status_parsing",HERE/"wb2a-vitotrol-p300-overread-readonly.py")
if not s or not s.loader:raise RuntimeError("existing validated P300 read parser missing")
base=importlib.util.module_from_spec(s);sys.modules[s.name]=base;s.loader.exec_module(base)
CONFIG=Path("/opt/optolink/settings_ini.py")
ORIG_SHA=base.CONFIG_EXPECTED_VS1_SHA
TIMER="wb2a-vitotrol-p300-fc-alias-restore-20261012.timer"
OUT=Path("/tmp/wb2a-vitotrol-p300-fc-alias-live-20261012.json")
ID="read;0x00f8;8"
CONTROLS=(
  "read;0x27a0;1", "read;0x27b0;1",
  "read;0x7342;1", "read;0x5738;1",
)
# Only in situ stable physical SRAM and documented EEPROM_R/KBUS_GATEWAY_R.
# 0x0000/8 and 0x00f8/8 are original *already successful* fc101 targets,
# 0x0017/2 and fc5/0x0000..FF are previously accepted EEPROM reads.
PAIRS=(
  ("EEPROM_ZERO","request;5;0x0000;8","request;101;0x0000;8"),
  ("EEPROM_F8","request;5;0x00f8;8","request;101;0x00f8;8"),
  ("EEPROM_17","request;5;0x0017;2","request;101;0x0017;2"),
  ("SRAM_DESCRIPTOR","request;3;0x0b6d;4","request;99;0x0b6d;4"),
  ("SRAM_POINTER","request;3;0x0b74;4","request;99;0x0b74;4"),
)
# Reversing pair ordering on second pass minimizes timing/order confounding.
SERIES=(
  (ID,*CONTROLS),
  tuple(z for _label,a,b in PAIRS for z in (a,b)),
  tuple(z for _label,a,b in PAIRS for z in (b,a)),
  (*CONTROLS,ID),
)
REQUESTS=tuple(z for group in SERIES for z in group)
ALLOWED=set(REQUESTS)
assert len(REQUESTS)==2+8+4*len(PAIRS)
assert len(REQUESTS)==30
assert all(cmd.startswith(("request;","read;")) for cmd in REQUESTS)
assert all(cmd.startswith("read;") or int(cmd.split(';')[1]) in (3,5,99,101)
           for cmd in REQUESTS)
assert all(int(cmd.split(';')[-1])<=8 for cmd in REQUESTS)
for label,a,b in PAIRS:
 assert int(a.split(';')[1])&31==int(b.split(';')[1])&31
 assert int(a.split(';')[1])!=int(b.split(';')[1])
 assert a.split(';')[2:]==b.split(';')[2:]

# For validated requests, never treat 03/01 diagnostic as successful memory.
REPLY=re.compile(r"^([^\r\n]+?)\s+<- openv/resp:\s*(\d+);(?:0x)?([0-9a-fA-F]+);([0-9a-fA-F]*)\s*$",re.M)

class Refused(RuntimeError):pass


def parse_response(command:str,console:str)->dict:
 if command not in ALLOWED or type(console) is not str or len(console)>4000:
  raise Refused("unknown command or oversized shared output")
 matches=REPLY.findall(console)
 if len(matches)!=1:raise Refused("not exactly one real response")
 echo,status,hexaddr,payload=matches[0]
 if echo.strip()!=command:raise Refused("answer request echo mismatch")
 wanted=int(command.split(';')[2 if command.startswith('request;') else 1],16)
 got=int(hexaddr,16)
 status=int(status)
 if wanted!=got or status not in (1,3):
  raise Refused("unexpected address/status code")
 size=int(command.rsplit(';',1)[1])
 if status==1 and len(payload)!=2*size:
  raise Refused("success with unexpected payload length")
 if status==3 and len(payload)>32:raise Refused("overlong error diagnostics")
 return {
  "cmd":command,"status":status,"address":f"0x{wanted:04x}",
  "accepted":status==1,"data":payload.lower() if status==1 else None,
  "error_diag":payload.lower() if status==3 else None,
  "fc_raw":int(command.split(';')[1]) if command.startswith('request;') else 1,
  "fc_low5":(int(command.split(';')[1]) if command.startswith('request;') else 1)&31,
  "sequence_hi3":(int(command.split(';')[1]) if command.startswith('request;') else 1)>>5,
 }


def verify_host(config:bytes,owner:bool,timer:bool):
 if not owner or not timer or type(config) is not bytes:
  raise Refused("original serial owner plus independent restore required")
 rebuilt=config.replace(b"vs1protocol = False",b"vs1protocol = True",1)
 if b"vs1protocol = False" not in config or hashlib.sha256(rebuilt).hexdigest()!=ORIG_SHA:
  raise Refused("original pinned production config not exactly restored by one flag")


def capture(send):
 records=[]
 for i,cmd in enumerate(REQUESTS):
  val=parse_response(cmd,send(cmd))
  val["index"]=i
  print(json.dumps(val,sort_keys=True),flush=True)
  records.append(val)
  if i==0 and val["data"]!=base.TARGET:
   raise Refused("device is not original 20C2/0103")
  if 1<=i<=4 and val["data"]!="00":
   raise Refused("preflight A0/B0/status did not match baseline")
  if i>=len(REQUESTS)-5:
   expected=base.TARGET if cmd==ID else "00"
   if val["data"]!=expected:raise Refused("post-check changed; rollback")
 per_pair=[]
 for j,(label,a,b) in enumerate(PAIRS):
  i0=5+2*j;i1=5+2*len(PAIRS)+2*j
  aa=[records[i0],records[i1+1]]
  bb=[records[i0+1],records[i1]]
  if [x["cmd"] for x in aa]!=[a,a] or [x["cmd"] for x in bb]!=[b,b]:
   raise Refused("unexpected pair order/replay alignment")
  def stable(arr):
   return all(q["accepted"] for q in arr) and arr[0]["data"]==arr[1]["data"]
  equal_all=all(x["status"]==y["status"] and
                x["data"]==y["data"] and x["error_diag"]==y["error_diag"]
                for x,y in zip(aa,bb))
  per_pair.append({
   "kind":label,"base_cmd":a,"high_seq_cmd":b,
   "base_2_status":[x["status"] for x in aa],
   "base_2_data":[x["data"] for x in aa],
   "high_seq_2_status":[x["status"] for x in bb],
   "high_seq_2_data":[x["data"] for x in bb],
   "both_devices_successful_and_stable":stable(aa) and stable(bb),
   "two_repeat_AB_BA_exactly_equal":equal_all,
   "same_dispatcher_proven_by_equality":False,
  })
 return {
  "mode":"WB2A_REAL_NATIVE_P300_FC_LOW5_VS_HIGH3_ALIAS_READONLY_AB_BA",
  "target":"20C2/0103",
  "host_fc03_fc99_same_five_low_bits":True,
  "host_fc05_fc101_same_five_low_bits":True,
  "full_vs2_function_byte_is_still_transmitted":True,
  "controller_routing_may_depend_on_high_bits_or_runtime":True,
  "controller_request_count":len(records),
  "controller_writes":0,
  "pairs":per_pair,
  "rows":records,
  "all_five_pairs_repeated_exactly_equal":all(
    row["two_repeat_AB_BA_exactly_equal"] for row in per_pair),
  "real_GWG_or_KM_bus_gateway_service_proven":False,
  "ROM_bank_page_copy_monitor_detected":False,
 }


def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument("--execute",action="store_true")
 ap.add_argument("--output",type=Path)
 args=ap.parse_args()
 if not args.execute:
  print(json.dumps({"mode":"DRY_RUN","commands":REQUESTS,
    "fc":[3,5,99,101],"writes":0,
    "independent_restore_required":True},indent=2));return
 if args.output!=OUT or OUT.exists():
  ap.error("exact new /tmp output required")
 def active(unit):
  return subprocess.run(["systemctl","is-active","--quiet",unit],
                        capture_output=True,timeout=5).returncode==0
 verify_host(CONFIG.read_bytes(),owner=active("optolink-splitter.service"),timer=active(TIMER))
 def send(cmd):
  if cmd not in ALLOWED:raise Refused("not whitelisted")
  q=subprocess.run(["/usr/local/bin/optolink-debug","request",cmd,"--timeout","7"],
                   capture_output=True,text=True,timeout=12)
  if q.returncode:raise Refused("transport read failed: "+cmd+" "+q.stderr[-200:])
  return q.stdout
 data=capture(send)
 OUT.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
 print(json.dumps({"source":"SAVED","controller_reads":data["controller_request_count"],
  "pair_equal":[x["two_repeat_AB_BA_exactly_equal"] for x in data["pairs"]],
  "writes":0},sort_keys=True))


if __name__=="__main__":main()
