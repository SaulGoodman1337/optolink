#!/usr/bin/env python3
"""2013 OpenV P300 start-filter bypass validation on a NON-FF WB2A byte.

Select source-backed Vitotrol coding 0x27A0/16 (byte +8 = 01) versus
direct 0x27A8/1; side checks 0x0896 sensor packet. FC01 Virtual_READ ONLY.
Never a write, free-form code, 20-bit ROM attempt, reset, or second serial
owner. Requires two immutable prior 20C2/VS1 originals, independent timer.
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
 "wb2a_p300_original_2013_overread_base",HERE/"wb2a-vitotrol-p300-overread-readonly.py")
if not spec or not spec.loader:raise RuntimeError("base parsed immutable source unavailable")
base=importlib.util.module_from_spec(spec);sys.modules[spec.name]=base
spec.loader.exec_module(base)

PINNED_FIRST_SHA="8188cce0fc9f3278cd162a4de8e34c5f2ba4865d90820e53a32dbc5d87102a31"
PINNED_VS1_SHA="d16967b41cf6717abb597cdea3e95b53f77d554b115262acc93e53f31799bd36"
FIRST_PATH=Path("/tmp/wb2a-vitotrol-p300-overread-live-20261012.json")
VS1_PATH=Path("/tmp/wb2a-vitotrol-p300-nonff-vs1-before-20261012.log")
OUTPUT=Path("/tmp/wb2a-vitotrol-p300-nonff-live-20261012.json")
TIMER="wb2a-vitotrol-p300-nonff-restore-20261012.timer"
ID="read;0x00f8;8"
GUARDS=base.GUARDS
CHALLENGES=(
 "read;0x27a0;16",
 "read;0x27a8;1",
 "read;0x27a8;1",
 "read;0x27a2;1",
 "read;0x27a1;1",
 "read;0x27a0;16",
 "read;0x0896;2",
 "read;0x0896;16",
 "read;0x089c;1",
 "read;0x089d;1",
 "read;0x089b;1",
 "read;0x0896;16",
)
FINISH=("read;0x0a5c;4",*GUARDS,ID)
SERIES=(ID,*GUARDS,*CHALLENGES,*FINISH)
ALLOWED=set(SERIES)
base.ALLOWED.update(ALLOWED)
assert len(SERIES)==23
assert all(x.startswith("read;0x") and int(x.rsplit(";",1)[1])<=16 for x in SERIES)
EXPECTED_VS1={
 "read;0x00f8;8":"20c2000300000103",
 "read;0x27a0;1":"00",
 "read;0x27a0;16":"00ff02f7000524000105ffffffffffff",
 "read;0x27a8;1":"01",
 "read;0x27a2;1":"02",
 "read;0x0896;2":"c800",
 "read;0x0896;16":"c800c800ffff0303ffffffffffffffff",
 "read;0x089c;1":"03",
 "read;0x089d;1":"03",
 "read;0x089b;1":"ff",
 "read;0x5738;1":"00",
}

class Refused(ValueError):pass


def sources_attested(first:bytes,vs1:bytes):
 if (type(first) is not bytes or hashlib.sha256(first).hexdigest()!=PINNED_FIRST_SHA
     or type(vs1) is not bytes or hashlib.sha256(vs1).hexdigest()!=PINNED_VS1_SHA):
  raise Refused("previous original source/VS1 contrast no longer byte-exact")
 old=json.loads(first)
 if (old.get("device")!="20C2/0103"
     or old.get("controller_writes")!=0
     or old.get("controller_reads")!=21
     or old.get("direct_neighbor_rejected_but_overshot_by_long_read") is not True):
  raise Refused("original direct-rejection observation not independently attested")
 text=vs1.decode("utf-8")
 for cmd,payload in EXPECTED_VS1.items():
  if (f"REQUEST={cmd}\n" not in text or
      not re.search(re.escape(cmd)+r"\s+<- openv/resp:\s*1;0x[0-9a-f]+;"+
                    re.escape(payload)+r"\s*$",text,re.M)):
   raise Refused("VS1 manufacturer-source-backed value does not match original: "+cmd)
 if bytes.fromhex(EXPECTED_VS1["read;0x27a0;16"])[8]!=1:
  raise Refused("non-FF target offset incorrect")
 return True


def check_host(*,config:bytes,restore_active:bool,owner_active:bool):
 if not restore_active or not owner_active or type(config) is not bytes:
  raise Refused("only active original-owner P300 with independent restoration")
 reverted=config.replace(b"vs1protocol = False",b"vs1protocol = True",1)
 if (b"vs1protocol = False" not in config or
     hashlib.sha256(reverted).hexdigest()!=base.CONFIG_EXPECTED_VS1_SHA):
  raise Refused("native P300 is not the original verified config")


def capture(run_cmd):
 rows=[]
 for idx,c in enumerate(SERIES):
  raw=run_cmd(c)
  row=base.parse_response(c,raw)
  row["index"]=idx
  rows.append(row)
  print(json.dumps(row,sort_keys=True),flush=True)
  if idx==0 and row["data"]!=base.TARGET:
   raise Refused("wrong actual controller, stop")
  if idx in range(1,5) and row["data"]!="00":
   raise Refused("initial guards wrong, stop")
  if idx>=len(SERIES)-len(FINISH):
   expected=base.TARGET if c==ID else ("00000000" if c=="read;0x0a5c;4" else "00")
   if row["data"]!=expected:
    raise Refused("controller status changed during test")
 def values(k):
  return [x for x in rows if x["cmd"]==k]
 long=values("read;0x27a0;16")
 direct=values("read;0x27a8;1")
 a2=values("read;0x27a2;1")
 viable=(len(long)==2 and all(v["accepted"] and
            v["data"]==EXPECTED_VS1["read;0x27a0;16"] for v in long)
         and len(direct)==2 and all(not x["accepted"] and
                                   x["status"]==3 for x in direct)
         and len(a2)==1 and a2[0]["data"]=="02")
 leaked_hex=bytes.fromhex(long[0]["data"])[8:9].hex() if long[0]["accepted"] else None
 return {
  "mode":"REAL_WB2A_2013_START_GATED_NONFF_BYTE_OVERREAD",
  "controller_read_requests":len(rows),"controller_writes":0,
  "original_first_live_SHA":PINNED_FIRST_SHA,
  "original_vs1_source_SHA":PINNED_VS1_SHA,
  "rows":rows,
  "candidate_direct_27a8_statuses":[x["status"] for x in direct],
  "candidate_27a8_VS1_value":"01",
  "candidate_overread_27a8_value":leaked_hex,
  "P300_direct_reject_but_P300_neighbor_long_exposes_nonff":
       bool(viable and leaked_hex=="01"),
  "neigh_0896_long":";".join(v["data"] or "ERR" for v in values("read;0x0896;16")),
  "neigh_089b_direct_statuses":[x["status"] for x in values("read;0x089b;1")],
  "ROM_bank_or_20bit_code_bytes_proven":False,
  "valid_nonff_cross_datapoint_bytes_prove_actual_CPU_physical_ROM":False,
 }


def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("--execute",action="store_true")
 p.add_argument("--output",type=Path)
 args=p.parse_args()
 if not args.execute:
  print(json.dumps({"mode":"DRY_RUN","read_requests":SERIES,
    "max_bytes":16,"controller_writes":0,"needs_original_sha":True},indent=2))
  return
 if args.output!=OUTPUT or OUTPUT.exists():
  p.error("requires fresh exact private /tmp original file")
 sources_attested(FIRST_PATH.read_bytes(),VS1_PATH.read_bytes())
 def active(name):
  return subprocess.run(["systemctl","is-active","--quiet",name],
                        timeout=5,capture_output=True).returncode==0
 check_host(config=base.CONFIG.read_bytes(),restore_active=active(TIMER),
             owner_active=active("optolink-splitter.service"))
 def request(cmd):
  if cmd not in ALLOWED:raise Refused("not fixed read-only whitelist")
  task=subprocess.run(["/usr/local/bin/optolink-debug","request",cmd,"--timeout","7"],
                       capture_output=True,text=True,timeout=12)
  if task.returncode:raise Refused("read command failed: "+cmd)
  return task.stdout
 result=capture(request)
 OUTPUT.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
 print(json.dumps({"status":"ORIGINAL_CAPTURE_SAVED",
  "nonff_effect":result["P300_direct_reject_but_P300_neighbor_long_exposes_nonff"],
  "raw":result["candidate_overread_27a8_value"],
  "writes":0},sort_keys=True))


if __name__=="__main__":main()
