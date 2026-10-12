#!/usr/bin/env python3
"""Bounded P300 FC01 datpoint-length overread: OpenV issue #142 (2013).

P300-mode only, MQTT through ORIGINAL splitter as sole serial owner. All
requests are FC01/Virtual_READ on known real WB2A virtual locations or
direct neighbors. 16-byte maximum; no custom function opcodes/extra payload,
physical/SFR reads, ROM bank selects or MCU/production writes. The separate
root supervisor arms independent VS1 rollback BEFORE changing settings.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

ROOT=Path("/home/chatgpt-admin/optolink-vitotrol-rpm-20261010")
CONFIG=Path("/opt/optolink/settings_ini.py")
CONFIG_EXPECTED_VS1_SHA="e9a120ef37fe17236a7505ee713c8dd338d98d5093ed75dfb34629d7e8f5c42d"
OUTPUT=Path("/tmp/wb2a-vitotrol-p300-overread-live-20261012.json")
TIMER="wb2a-vitotrol-p300-overread-retry-restore-20261012.timer"
TARGET="20c2000300000103"
START_BASELINE="read;0x00f8;8"
GUARDS=("read;0x27a0;1","read;0x27b0;1",
        "read;0x7342;1","read;0x5738;1")
CHALLENGES=(
 "read;0x00f8;4",
 "read;0x00f8;16",
 "read;0x0100;4",
 "read;0x00fc;12",
 "read;0x0a5c;4",
 "read;0x0a5c;16",
 "read;0x0a60;4",
 "read;0x0a64;4",
 "read;0x0a5c;16",
 "read;0x0100;4",
)
FINISH=("read;0x0a5c;4",*GUARDS,START_BASELINE)
SERIES=(START_BASELINE,*GUARDS,*CHALLENGES,*FINISH)
MAX_RESPONSE=3200
RESPONSE=re.compile(r"^([^\r\n]+?)\s+<- openv/resp:\s*(.+)$",re.M)
CONTENT=re.compile(r"^(\d+);(?:0x)?([0-9a-fA-F]+);([0-9a-fA-F]*|\?)$")
ALLOWED=set(SERIES)
VS1_ORIGINAL_SHA="a866236160c737e47df55c2625e684aad1f0c1bf3f3708c60183ad569caf804d"
VS1_CHECK={
 "read;0x00f8;4":"20c20003",
 "read;0x00f8;16":"20c2000300000103ffffffffffffffff",
 "read;0x0100;4":"ffffffff",
 "read;0x0a5c;4":"00000000",
 "read;0x0a5c;16":"0000000000000000ffffffffffffffff",
 "read;0x0a60;4":"00000000",
 "read;0x0a64;4":"ffffffff",
}
assert len(SERIES)==21
assert len(ALLOWED)==len(set(SERIES))
assert all(s.startswith("read;0x") for s in SERIES)
assert all(1 <= int(s.rsplit(";",1)[1]) <= 16 for s in SERIES)

class Refused(RuntimeError):pass


def plan()->dict:
 return {
  "mode":"P300_2013_ISSUE142_VALID_START_OVERREAD_BOUNDARY_GATES",
  "device":"WB2A VDensHO1 20C2/0103",
  "requests":[{"cmd":c,"address":hex(int(c.split(";")[1],16)),
               "length":int(c.rsplit(";",1)[1])} for c in SERIES],
  "program_ROM_access_claimed":False,
  "MCU_writes":0,
  "only_P300_FC01_Virtual_READ":True,
  "max_length":16,
  "independent_original_VS1_restore_required":True,
  "VS1_source_sha256":VS1_ORIGINAL_SHA,
 }


def verify_source(raw:bytes):
 if type(raw) is not bytes or hashlib.sha256(raw).hexdigest()!=VS1_ORIGINAL_SHA:
  raise Refused("unmodified previously measured VS1 9-request source missing")
 s=raw.decode("utf-8")
 for command,payload in VS1_CHECK.items():
  if f"REQUEST={command}\n" not in s or not re.search(re.escape(command)+r"\s+<- openv/resp: 1;",s):
   raise Refused("original VS1 source does not attest requested known baseline")
  # Exact one-line response check, avoid inferring from nearby other commands.
  pat=re.compile(re.escape(command)+r"\s+<- openv/resp: 1;0x[0-9a-f]+;"+
                 re.escape(payload)+r"\s*$",re.M)
  if not pat.search(s):
   raise Refused("known original VS1 payload altered "+command)
 return VS1_ORIGINAL_SHA


def check_host(*,config:bytes,timer_active:bool,owner_active:bool):
 if (type(config) is not bytes or b"vs1protocol = False" not in config
     or not timer_active or not owner_active):
  raise Refused("requires P300 mode with original owner and armed restore")
 # All assigned bytes except one known literal must match the saved, hashed VS1
 # file; no arbitrary unrelated production config edits permitted.
 reconstructed=config.replace(b"vs1protocol = False",b"vs1protocol = True",1)
 if hashlib.sha256(reconstructed).hexdigest()!=CONFIG_EXPECTED_VS1_SHA:
  raise Refused("temporary P300 settings differ from pinned original snapshot")


def parse_response(command:str,text:str)->dict:
 if command not in ALLOWED or type(text) is not str or len(text)>MAX_RESPONSE:
  raise Refused("request/output outside closed read-only series")
 results=RESPONSE.findall(text)
 if len(results)!=1:
  raise Refused("expected exactly one CLI response for "+command)
 echoed,body=results[0]
 if echoed.strip()!=command:
  raise Refused("wrong response request echo")
 match=CONTENT.fullmatch(body.strip())
 if not match:raise Refused("unknown controller error/response format: "+body[:90])
 code=int(match[1]);addr=int(match[2],16)
 wanted_addr=int(command.split(";")[1],16)
 if addr!=wanted_addr or code not in (1,3,21,255):
  raise Refused("unexpected status/address in controller response")
 data=match[3].lower()
 req_len=int(command.rsplit(";",1)[1])
 if code==1:
  if data=="?" or len(data)!=req_len*2:
   raise Refused("successful answer not an exact declared byte count")
 else:
  # A P300 Error/NAK may carry vendor-specific error bytes. Preserve them
  # distinctly from successful read data and never treat them as SRAM.
  if len(data)>32:
   raise Refused("oversized unknown controller error diagnostic")
 return {"cmd":command,"status":code,"address":f"0x{addr:04x}",
         "data":data if code==1 else None,
         "error_raw_payload":None if code==1 else data,
         "accepted":code==1,"error":None if code==1 else code}


def capture(run_cmd):
 rows=[]
 for index,command in enumerate(SERIES):
  raw=run_cmd(command)
  parsed=parse_response(command,raw)
  parsed["index"]=index
  rows.append(parsed)
  print(json.dumps(parsed,sort_keys=True),flush=True)
  if index==0 and parsed["data"]!=TARGET:
   raise Refused("real P300 device ID mismatch; no experimental reads")
  if index in range(1,1+len(GUARDS)) and parsed["data"]!="00":
   raise Refused("control coding/fault preflight failed")
  if index>=len(SERIES)-len(FINISH):
   if command in (*GUARDS,"read;0x0a5c;4") and parsed["data"] not in ("00","00000000"):
    raise Refused("after-read status/participant integrity changed")
   if command==START_BASELINE and parsed["data"]!=TARGET:
    raise Refused("last device ID changed")
 by=lambda x:[r for r in rows if r["cmd"]==x]
 outcomes={}
 for c in dict.fromkeys(CHALLENGES):
  entries=by(c)
  outcomes[c]={"status":[r["status"] for r in entries],
               "data":[r["data"] for r in entries]}
 id_long=by("read;0x00f8;16")
 part_long=by("read;0x0a5c;16")
 id_direct=by("read;0x0100;4")
 part_direct=by("read;0x0a64;4")
 id_known=id_long[0]["data"]==VS1_CHECK["read;0x00f8;16"]
 part_known=all(r["data"]==VS1_CHECK["read;0x0a5c;16"] for r in part_long)
 bypass=bool(id_known and all(not r["accepted"] for r in id_direct)
             or part_known and all(not r["accepted"] for r in part_direct))
 return {
  "mode":"P300_2013_ISSUE142_VIRTUAL_OVERREAD_REAL_WB2A",
  "device":"20C2/0103",
  "controller_reads":len(rows),"controller_writes":0,
  "original_VS1_9_read_source_sha256":VS1_ORIGINAL_SHA,
  "rows":rows,"challenge_outcomes":outcomes,
  "id_16bytes_equal_to_live_VS1":id_known,
  "vitotrol_index_16bytes_equal_to_live_VS1":part_known,
  "direct_neighbor_rejected_but_overshot_by_long_read":bypass,
  "issue_142_2013_effect_is_proven_on_own_20C2":bypass,
  "RW_or_program_rom_service_identified":False,
  "program_ROM_20bit_address_proven":False,
  "controller_firmware_dump_obtained":False,
 }


def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument("--execute",action="store_true")
 ap.add_argument("--output",type=Path)
 args=ap.parse_args()
 if not args.execute:
  print(json.dumps(plan(),indent=2,sort_keys=True));return
 if args.output!=OUTPUT:
  ap.error("exact private source file path required")
 # Original must exist and be bytewise checked before any P300 request.
 verify_source(Path("/tmp/wb2a-vitotrol-p300-overread-vs1-before-20261012.log").read_bytes())
 def active(unit):
  return subprocess.run(["systemctl","is-active","--quiet",unit],
                        capture_output=True,timeout=5).returncode==0
 check_host(config=CONFIG.read_bytes(),timer_active=active(TIMER),
            owner_active=active("optolink-splitter.service"))
 if OUTPUT.exists():raise Refused("will not overwrite original live recording")
 def actual_read(command):
  if command not in ALLOWED:raise Refused("unsupported command")
  p=subprocess.run(["/usr/local/bin/optolink-debug","request",command,"--timeout","7"],
                   capture_output=True,text=True,timeout=12)
  if p.returncode:
   raise Refused("one bounded live read CLI failed "+command+
                 " output="+(p.stdout+p.stderr)[-100:])
  return p.stdout
 report=capture(actual_read)
 OUTPUT.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
 print(json.dumps({"status":"SOURCE_SAVED","reads":report["controller_reads"],
  "writes":0,"bypass":report["direct_neighbor_rejected_but_overshot_by_long_read"],
  "ROM":report["controller_firmware_dump_obtained"]},sort_keys=True))


if __name__=="__main__":main()
