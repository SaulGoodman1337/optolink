#!/usr/bin/env python3
"""Source-attested P300 FC01 interior-of-multibyte datapoint test on 20C2.

Historical OpenV 2013 issue #142: not all direct start addresses accepted;
longer reads from valid start may return bytes inaccessible individually.
Use original WB2A signed VS1 baseline with year 0x2026, temp C800, FB1=0.
21 immutable read-only MQTT-through-original-splitter commands, NO writes.
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
spec=importlib.util.spec_from_file_location(
 "wb2a_p300_interior_byte_base",HERE/"wb2a-vitotrol-p300-overread-readonly.py")
if not spec or not spec.loader:raise RuntimeError("source-pinned common FC01 parser missing")
base=importlib.util.module_from_spec(spec);sys.modules[spec.name]=base
spec.loader.exec_module(base)
ORIGINAL_VS1_PATH=Path("/tmp/wb2a-vitotrol-p300-internalbyte-vs1-before-20261012.log")
ORIGINAL_VS1_SHA="31fb39a6d5ddb6338af76a72d84dbe3a90902a36940cb3ba8304a5077e8a8b04"
FIRST_ORIGINAL=Path("/tmp/wb2a-vitotrol-p300-overread-live-20261012.json")
FIRST_SHA="8188cce0fc9f3278cd162a4de8e34c5f2ba4865d90820e53a32dbc5d87102a31"
OUTPUT=Path("/tmp/wb2a-vitotrol-p300-interior-byte-live-20261012.json")
TIMER="wb2a-vitotrol-p300-interior-restore-20261012.timer"
ID="read;0x00f8;8"
GUARDS=base.GUARDS
CHALLENGES=(
 "read;0x088e;8",
 "read;0x088f;1",
 "read;0x088e;8",
 "read;0x0896;2",
 "read;0x0897;1",
 "read;0x0898;2",
 "read;0x0899;1",
 "read;0x0a5c;4",
 "read;0x0a5d;1",
 "read;0x00fa;1",
 "read;0x088e;16",
)
FINISH=(*GUARDS,ID)
SERIES=(ID,*GUARDS,*CHALLENGES,*FINISH)
ALLOWED=set(SERIES)
base.ALLOWED.update(ALLOWED)
assert len(SERIES)==21
assert all(c.startswith("read;0x") and int(c.rsplit(";",1)[1])<=16 for c in SERIES)

class Refused(RuntimeError):pass


def verify_sources(vs1:bytes,former:bytes):
 if (type(vs1) is not bytes or
     hashlib.sha256(vs1).hexdigest()!=ORIGINAL_VS1_SHA or
     type(former) is not bytes or hashlib.sha256(former).hexdigest()!=FIRST_SHA):
  raise Refused("original 20C2/VS1/P300 provenance changed")
 first=json.loads(former)
 if (first.get("device")!="20C2/0103" or
     first.get("controller_reads")!=21 or
     first.get("controller_writes")!=0 or
     first.get("issue_142_2013_effect_is_proven_on_own_20C2") is not True):
  raise Refused("no previous actual P300 start-filter attestation")
 text=vs1.decode("utf-8")
 expected={
  "read;0x00f8;8":"20c2000300000103",
  "read;0x088e;8":"2026101201081813",
  "read;0x088f;1":"ff",
  "read;0x0896;2":"c800",
  "read;0x0897;1":"ff",
  "read;0x0898;2":"c800",
  "read;0x0899;1":"ff",
  "read;0x0a5c;4":"00000000",
  "read;0x0a5d;1":"ff",
  "read;0x00fa;1":"00",
 }
 for c,v in expected.items():
  if (f"REQUEST={c}\n" not in text or
      not re.search(re.escape(c)+r"\s+<- openv/resp: 1;0x[0-9a-f]+;"+
                    re.escape(v)+r"\s*$",text,re.M)):
   raise Refused("VS1 original does not contain exact expected prior "+c)
 return True


def check_host(config:bytes,timer_on:bool,owner_on:bool):
 if not timer_on or not owner_on or type(config) is not bytes:
  raise Refused("original serial owner and independent restore timer required")
 restored=config.replace(b"vs1protocol = False",b"vs1protocol = True",1)
 if (b"vs1protocol = False" not in config or
     hashlib.sha256(restored).hexdigest()!=base.CONFIG_EXPECTED_VS1_SHA):
  raise Refused("original production configuration not preserved exactly")


def capture(read):
 rows=[]
 for i,c in enumerate(SERIES):
  parsed=base.parse_response(c,read(c))
  parsed["index"]=i
  rows.append(parsed)
  print(json.dumps(parsed,sort_keys=True),flush=True)
  if i==0 and parsed["data"]!=base.TARGET:raise Refused("different controller")
  if 1<=i<=len(GUARDS) and parsed["data"]!="00":
   raise Refused("invalid initial coding or fault status")
  if i>=len(SERIES)-len(FINISH):
   wanted=base.TARGET if c==ID else "00"
   if parsed["data"]!=wanted:raise Refused("status changed during probe")
 by=lambda q:[x for x in rows if x["cmd"]==q]
 first=by("read;0x088e;8")
 long=by("read;0x088e;16")
 temp=by("read;0x0896;2")
 mid=by("read;0x088f;1")
 midtemp=by("read;0x0897;1")
 middletwo=by("read;0x0899;1")
 fb=by("read;0x0a5d;1")
 # year 20 26 is two arbitrary bytes in original; 0x26 is not FF padding.
 year_data=[bytes.fromhex(x["data"])[1:2].hex() if x["accepted"] else None
            for x in first+long]
 access=status={
  "year_second_byte_from_block":year_data,
  "year_second_byte_direct_status":[x["status"] for x in mid],
  "temperature_low_byte_from_block":[bytes.fromhex(x["data"])[1:2].hex()
                                      if x["accepted"] else None for x in temp],
  "temperature_second_byte_direct_status":[x["status"] for x in midtemp],
  "2nd_temperature_second_byte_direct_status":[x["status"] for x in middletwo],
  "fb1_interior_2nd_byte_direct_status":[x["status"] for x in fb],
 }
 direct_block_true=(all(x=="26" for x in year_data)
                     and len(mid)==1 and mid[0]["status"]==3
                     and mid[0]["error_raw_payload"]=="01"
                     and all(r["status"]==1 for r in first+long))
 low_true=(access["temperature_low_byte_from_block"]==["00"]
           and len(midtemp)==1 and midtemp[0]["status"]==3)
 return {
  "mode":"REAL_WB2A_P300_INTERIOR_BYTE_NONFF_START_REJECTION",
  "original_VS1_sha256":ORIGINAL_VS1_SHA,
  "original_previous_P300_sha256":FIRST_SHA,
  "controller_read_requests":len(rows),
  "controller_writes":0,
  "rows":rows,
  "interior_access":access,
  "P300_interior_year_0x26_block_visible_but_directly_rejected":bool(direct_block_true),
  "P300_interior_temp_0x00_block_visible_but_directly_rejected":bool(low_true),
  "plain_GWG_C7_year_byte_directly_readable_proven":False,
  "inside_data_point_inaccessible_nonFF_block_bytes_proven":bool(direct_block_true),
  "nonFF_bytes_from_unmapped_physical_CPU_RAM_proven":False,
  "20bit_M16C_program_ROM_dump":False,
 }


def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("--execute",action="store_true")
 p.add_argument("--output",type=Path)
 opt=p.parse_args()
 if not opt.execute:
  print(json.dumps({"mode":"DRY_RUN","read_requests":SERIES,
    "controller_writes":0,"requires_actual_VS1_P300_origins":True},indent=2))
  return
 if opt.output!=OUTPUT or OUTPUT.exists():
  p.error("new exact private output only")
 verify_sources(ORIGINAL_VS1_PATH.read_bytes(),FIRST_ORIGINAL.read_bytes())
 def active(x):
  return subprocess.run(["systemctl","is-active","--quiet",x],
                        timeout=5,capture_output=True).returncode==0
 check_host(base.CONFIG.read_bytes(),active(TIMER),active("optolink-splitter.service"))
 def read(c):
  if c not in ALLOWED:raise Refused("read outside fixed bounded whitelist")
  proc=subprocess.run(["/usr/local/bin/optolink-debug","request",c,"--timeout","7"],
                      capture_output=True,text=True,timeout=12)
  if proc.returncode:raise Refused("unsafe/unanswered CLI request "+c)
  return proc.stdout
 result=capture(read)
 OUTPUT.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
 print(json.dumps({"source_saved":str(OUTPUT),"total":result["controller_read_requests"],
    "year_nonff_bypass":result["P300_interior_year_0x26_block_visible_but_directly_rejected"],
    "writes":0},sort_keys=True))

if __name__=="__main__":main()
