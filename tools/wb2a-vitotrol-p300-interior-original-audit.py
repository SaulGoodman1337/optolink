#!/usr/bin/env python3
"""Offline SHA-locked verification of 65 actual WB2A P300 read-only requests.

The third 2013 OpenV overread case is strictly an interior byte of a valid
virtual data point, not proof of program ROM or unrestricted physical memory.
The two prior sources are independently rechecked with the SHA-pinned
wb2a-vitotrol-p300-overread-original-audit.py. No serial/MQTT/MCU imports.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location(
 "wb2a_p300_two_windows_authentic",HERE/"wb2a-vitotrol-p300-overread-original-audit.py")
if not spec or not spec.loader: raise RuntimeError("original two-window auditor missing")
old=importlib.util.module_from_spec(spec);sys.modules[spec.name]=old
spec.loader.exec_module(old)
ORIG_THIRD=Path("/tmp/wb2a-vitotrol-p300-interior-byte-live-20261012.json")
ORIG_VS1=Path("/tmp/wb2a-vitotrol-p300-internalbyte-vs1-before-20261012.log")
THIRD_SHA="fb3e27e8596a498440fe32f9bd73a5d5157956390bf8319c7c8bc4cb2083f772"
VS1_SHA="31fb39a6d5ddb6338af76a72d84dbe3a90902a36940cb3ba8304a5077e8a8b04"
ID="20c2000300000103"
ERR=("03/01",None)
THIRD_ROWS=[
 ("00f8",8,ID),
 ("27a0",1,"00"),("27b0",1,"00"),("7342",1,"00"),("5738",1,"00"),
 ("088e",8,"2026101201082040"),
 ("088f",1,ERR),
 ("088e",8,"2026101201082043"),
 ("0896",2,"c800"),
 ("0897",1,ERR),
 ("0898",2,"c800"),
 ("0899",1,ERR),
 ("0a5c",4,"00000000"),
 ("0a5d",1,ERR),
 ("00fa",1,"00"),
 ("088e",16,"2026101201082056c800c800ffff0303"),
 ("27a0",1,"00"),("27b0",1,"00"),("7342",1,"00"),("5738",1,"00"),
 ("00f8",8,ID),
]

class Refused(ValueError):pass

def authenticate(data:bytes,sha:str,label:str):
 if type(data) is not bytes or len(data)>40000 or hashlib.sha256(data).hexdigest()!=sha:
  raise Refused("unverified private "+label)

def verify(real_first:bytes,real_second:bytes,vs1_first:bytes,vs1_second:bytes,
           real_third:bytes,vs1_third:bytes):
 before=old.audit(real_first,real_second,vs1_first,vs1_second)
 authenticate(real_third,THIRD_SHA,"P300 third capture")
 authenticate(vs1_third,VS1_SHA,"VS1 third baseline")
 third=json.loads(real_third)
 if (third.get("mode")!="REAL_WB2A_P300_INTERIOR_BYTE_NONFF_START_REJECTION"
     or third.get("original_VS1_sha256")!=VS1_SHA
     or third.get("original_previous_P300_sha256")!=old.SOURCES["first"][1]
     or third.get("controller_read_requests")!=21
     or third.get("controller_writes")!=0
     or third.get("P300_interior_year_0x26_block_visible_but_directly_rejected") is not True
     or third.get("P300_interior_temp_0x00_block_visible_but_directly_rejected") is not True
     or third.get("inside_data_point_inaccessible_nonFF_block_bytes_proven") is not True
     or third.get("nonFF_bytes_from_unmapped_physical_CPU_RAM_proven") is not False
     or third.get("20bit_M16C_program_ROM_dump") is not False):
  raise Refused("third header/outcome is not original")
 rows=third.get("rows")
 if type(rows) is not list or len(rows)!=len(THIRD_ROWS):
  raise Refused("not exactly third 21 controller reads")
 for i,(read,(a,l,value)) in enumerate(zip(rows,THIRD_ROWS)):
  if (read.get("index")!=i or
      read.get("cmd")!=f"read;0x{a};{l}" or
      read.get("address")!=f"0x{a}" or
      read.get("accepted") is not (value!=ERR)):
   raise Refused("third original byte-order/scope mismatch")
  if value==ERR:
   if (read.get("status")!=3 or read.get("data") is not None
       or read.get("error")!=3 or read.get("error_raw_payload")!="01"):
    raise Refused("third 03/01 diagnostic incorrectly interpreted as memory")
  elif (read.get("status")!=1 or read.get("data")!=value
        or read.get("error") is not None or read.get("error_raw_payload") is not None
        or len(bytes.fromhex(value))!=l):
   raise Refused("third original valid FC01 reply no longer byte-exact")
 # Only known MULTIBYTE VIRTUAL datum interiors: forbidden start + nonFF.
 if (bytes.fromhex(rows[5]["data"])[1]!=0x26 or
     bytes.fromhex(rows[7]["data"])[1]!=0x26 or
     bytes.fromhex(rows[15]["data"])[1]!=0x26 or
     bytes.fromhex(rows[8]["data"])[1]!=0x00 or
     bytes.fromhex(rows[10]["data"])[1]!=0x00):
  raise Refused("nonFF and zero interiors not source-attested")
 vs=vs1_third.decode("utf-8")
 for needle in (
     "read;0x088e;8  <- openv/resp: 1;0x88e;2026101201081813",
     "read;0x088f;1  <- openv/resp: 1;0x88f;ff",
     "read;0x0896;2  <- openv/resp: 1;0x896;c800",
     "read;0x0897;1  <- openv/resp: 1;0x897;ff",
     "read;0x0898;2  <- openv/resp: 1;0x898;c800",
     "read;0x0899;1  <- openv/resp: 1;0x899;ff",
     "read;0x0a5c;4  <- openv/resp: 1;0xa5c;00000000",
     "read;0x0a5d;1  <- openv/resp: 1;0xa5d;ff",
 ):
  if needle not in vs:
   raise Refused("VS1 predecessor did not attest interior/direct mismatch")
 c3={"total":len(rows),"success":sum(x[2]!=ERR for x in THIRD_ROWS),
     "error03_diagnostic01":sum(x[2]==ERR for x in THIRD_ROWS)}
 if before["authentic_controller_readonly_calls"]+c3["total"]!=65:
  raise Refused("three independent P300 sessions missing")
 return {
  "mode":"OFFLINE_BYTE_VERIFIED_OPENV_2013_P300_VALID_START_INTERIOR_BYTES",
  "device":"WB2A VDensHO1 20C2/0103",
  "three_original_P300_sha256":[old.SOURCES["first"][1],old.SOURCES["second"][1],THIRD_SHA],
  "three_original_VS1_sha256":[old.VS1_SOURCES["first"][0],old.VS1_SOURCES["second"][0],VS1_SHA],
  "actual_P300_read_request_count":65,
  "actual_P300_successful_response_count":before["valid_read_responses"]+c3["success"],
  "actual_P300_error03_01_count":before["status03_diagnostic01_responses"]+c3["error03_diagnostic01"],
  "third_original_21_controller_read_requests":c3,
  "read_block_088e_8_returns_real_2026_year_byte_26":True,
  "direct_088f_1_is_error03_diagnostic01":True,
  "P300_valid_start_exposes_nonFF_byte_at_interior_088f":True,
  "direct_0897_and_0899_rejected_but_two_byte_temp_reads_expose_00":True,
  "direct_0a5d_rejected_but_0a5c_4_exposes_00":True,
  "P300_rejected_start_is_not_equivalent_unaddressable_virtual_interior":True,
  "all_prior_non_datapoint_overlaps_from_starts_returned_FF":True,
  "2026_KW2_C7_old_frontend_program_ROM_access_unproven":True,
  "no_general_unmapped_physical_ROM_or_RAM_disclosure_proven":True,
  "manufacturer_20bit_ROM_service_found":False,
  "firmware_dump_obtained":False,
  "new_controller_read_requests_for_offline_audit":0,
  "new_controller_writes":0,
 }

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("--out",type=Path)
 opt=p.parse_args()
 def load(fn):
  f=Path(fn)
  if f.is_symlink() or not f.is_file() or f.stat().st_size>40000:
   p.error("source missing/not regular/unexpected size: "+str(fn))
  return f.read_bytes()
 result=verify(
  load(old.SOURCES["first"][0]),load(old.SOURCES["second"][0]),
  load(old.VS1_SOURCES["first"][1]),load(old.VS1_SOURCES["second"][1]),
  load(ORIG_THIRD),load(ORIG_VS1))
 content=json.dumps(result,sort_keys=True,indent=2)+"\n"
 if opt.out:opt.out.write_text(content)
 print(content)

if __name__=="__main__":main()
