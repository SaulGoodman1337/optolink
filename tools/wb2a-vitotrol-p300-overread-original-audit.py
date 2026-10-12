#!/usr/bin/env python3
"""Byte-exact, offline SHA256 audit of two real WB2A P300 FC01 overread windows.

Prevents a P300 error frame with the diagnostic byte '01' from being
misidentified as a memory value. Separates proven start filtering and
overlapping response bytes from unproven physical RAM/ROM disclosure.
Never imports or invokes a serial, MQTT, controller, programmer or write API.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

SOURCES={
  "first":(
    "/tmp/wb2a-vitotrol-p300-overread-live-20261012.json",
    "8188cce0fc9f3278cd162a4de8e34c5f2ba4865d90820e53a32dbc5d87102a31"),
  "second":(
    "/tmp/wb2a-vitotrol-p300-nonff-live-20261012.json",
    "d6b7e967d72d84d7e1f0e657329a77910ebafae0d1a7a9c47dd23dd40a557c80"),
}
VS1_SOURCES={
  "first":("a866236160c737e47df55c2625e684aad1f0c1bf3f3708c60183ad569caf804d",
           "/tmp/wb2a-vitotrol-p300-overread-vs1-before-20261012.log"),
  "second":("d16967b41cf6717abb597cdea3e95b53f77d554b115262acc93e53f31799bd36",
            "/tmp/wb2a-vitotrol-p300-nonff-vs1-before-20261012.log"),
}
E01=("03/01",None)
ID="20c2000300000103"
P1_ROWS=[
 ("00f8",8,ID),("27a0",1,"00"),("27b0",1,"00"),
 ("7342",1,"00"),("5738",1,"00"),
 ("00f8",4,"20c20003"),
 ("00f8",16,"20c2000300000103ffffffffffffffff"),
 ("0100",4,E01),("00fc",12,"00000103ffffffffffffffff"),
 ("0a5c",4,"00000000"),
 ("0a5c",16,"0000000000000000ffffffffffffffff"),
 ("0a60",4,"00000000"),("0a64",4,E01),
 ("0a5c",16,"0000000000000000ffffffffffffffff"),
 ("0100",4,E01),("0a5c",4,"00000000"),
 ("27a0",1,"00"),("27b0",1,"00"),("7342",1,"00"),
 ("5738",1,"00"),("00f8",8,ID),
]
P2_ROWS=[
 ("00f8",8,ID),("27a0",1,"00"),("27b0",1,"00"),("7342",1,"00"),
 ("5738",1,"00"),
 ("27a0",16,"00ff02f7000524000105ffffffffffff"),
 ("27a8",1,"01"),("27a8",1,"01"),("27a2",1,"02"),
 ("27a1",1,E01),
 ("27a0",16,"00ff02f7000524000105ffffffffffff"),
 ("0896",2,"c800"),
 ("0896",16,"c800c800ffff0303ffffffffffffffff"),
 ("089c",1,"03"),("089d",1,"03"),("089b",1,E01),
 ("0896",16,"c800c800ffff0303ffffffffffffffff"),
 ("0a5c",4,"00000000"),
 ("27a0",1,"00"),("27b0",1,"00"),("7342",1,"00"),
 ("5738",1,"00"),("00f8",8,ID),
]

class EvidenceRejected(ValueError): pass

def attest(data:bytes,label:str,sha:str):
 if (type(data) is not bytes or len(data)>35000 or
     hashlib.sha256(data).hexdigest()!=sha):
  raise EvidenceRejected(f"original {label} missing or content changed")

def verify_rows(report:dict,expected:list,label:str):
 rows=report.get("rows")
 if type(rows) is not list or len(rows)!=len(expected):
  raise EvidenceRejected(f"invalid number of {label} reads")
 for i,(actual,(addr,size,data)) in enumerate(zip(rows,expected)):
  if (actual.get("index")!=i
      or actual.get("cmd")!=f"read;0x{addr};{size}"
      or actual.get("address")!=f"0x{addr}"
      or actual.get("accepted") is not (data!=E01)):
   raise EvidenceRejected(f"{label} request order/address/flag changed at {i}")
  if data==E01:
   if (actual.get("status")!=3 or actual.get("error")!=3
       or actual.get("error_raw_payload")!="01" or actual.get("data") is not None):
    raise EvidenceRejected(f"{label} diagnostic must NOT be interpreted as read bytes")
  else:
   if (actual.get("status")!=1 or actual.get("data")!=data
       or actual.get("error") is not None or actual.get("error_raw_payload") is not None
       or len(bytes.fromhex(data))!=size):
    raise EvidenceRejected(f"{label} controller success bytes differed")
 return {"total":len(rows),"successful":sum(x[2]!=E01 for x in expected),
         "rejected_status03_diagnostic01":sum(x[2]==E01 for x in expected)}

def audit(original_first:bytes,original_second:bytes,vs1_first:bytes,vs1_second:bytes):
 for tag,data in (("first",original_first),("second",original_second)):
  attest(data,tag+" P300",SOURCES[tag][1])
 for tag,data in (("first",vs1_first),("second",vs1_second)):
  attest(data,tag+" VS1",VS1_SOURCES[tag][0])
 first=json.loads(original_first);second=json.loads(original_second)
 if (first.get("mode")!="P300_2013_ISSUE142_VIRTUAL_OVERREAD_REAL_WB2A"
     or first.get("device")!="20C2/0103" or first.get("controller_reads")!=21
     or first.get("controller_writes")!=0
     or first.get("original_VS1_9_read_source_sha256")!=VS1_SOURCES["first"][0]
     or first.get("direct_neighbor_rejected_but_overshot_by_long_read") is not True
     or first.get("issue_142_2013_effect_is_proven_on_own_20C2") is not True
     or first.get("program_ROM_20bit_address_proven") is not False
     or first.get("controller_firmware_dump_obtained") is not False):
  raise EvidenceRejected("first phase header, read/write gates or semantics differ")
 if (second.get("mode")!="REAL_WB2A_2013_START_GATED_NONFF_BYTE_OVERREAD"
     or second.get("controller_read_requests")!=23
     or second.get("controller_writes")!=0
     or second.get("original_first_live_SHA")!=SOURCES["first"][1]
     or second.get("original_vs1_source_SHA")!=VS1_SOURCES["second"][0]
     or second.get("P300_direct_reject_but_P300_neighbor_long_exposes_nonff") is not False
     or second.get("candidate_overread_27a8_value")!="01"
     or second.get("candidate_direct_27a8_statuses")!=[1,1]
     or second.get("ROM_bank_or_20bit_code_bytes_proven") is not False):
  raise EvidenceRejected("second phase falsification or provenance differs")
 c1=verify_rows(first,P1_ROWS,"first")
 c2=verify_rows(second,P2_ROWS,"second")
 def p1_data(addr,size):
  for a,l,v in P1_ROWS:
   if a==addr and l==size and v!=E01:return bytes.fromhex(v)
  raise EvidenceRejected("missing verified positive address")
 def p2_data(addr,size):
  for a,l,v in P2_ROWS:
   if a==addr and l==size and v!=E01:return bytes.fromhex(v)
  raise EvidenceRejected("missing verified positive address")
 ff_diagnostic=[
  {"direct":"0x0100","error":"03/01","overlap_from":"0x00f8/16",
   "overlap_data":p1_data("00f8",16)[8:12].hex()},
  {"direct":"0x0a64","error":"03/01","overlap_from":"0x0a5c/16",
   "overlap_data":p1_data("0a5c",16)[8:12].hex()},
  {"direct":"0x27a1","error":"03/01","overlap_from":"0x27a0/16",
   "overlap_data":p2_data("27a0",16)[1:2].hex()},
  {"direct":"0x089b","error":"03/01","overlap_from":"0x0896/16",
   "overlap_data":p2_data("0896",16)[5:6].hex()},
 ]
 if any(x["overlap_data"] not in ("ff","ffffffff") for x in ff_diagnostic):
  raise EvidenceRejected("unsupported non-FF forbidden-start claim")
 if (p2_data("27a0",16)[8:9].hex()!="01"
     or p2_data("27a8",1)!=bytes.fromhex("01")
     or p2_data("0896",16)[6:8]!=p2_data("089c",1)+p2_data("089d",1)):
  raise EvidenceRejected("positive non-FF/03 windows incorrect")
 return {
  "mode":"OFFLINE_SHA_ATTESTED_2013_P300_START_FILTER_OVERREAD_GATES",
  "verified_actual_20C2":"20C2/0103",
  "sha256_original_data":{
    "P300_start_filter":SOURCES["first"][1],
    "P300_nonff":SOURCES["second"][1],
    "VS1_start_filter":VS1_SOURCES["first"][0],
    "VS1_nonff":VS1_SOURCES["second"][0],
  },
  "authentic_controller_readonly_calls":c1["total"]+c2["total"],
  "valid_read_responses":c1["successful"]+c2["successful"],
  "status03_diagnostic01_responses":c1["rejected_status03_diagnostic01"]+c2["rejected_status03_diagnostic01"],
  "source_original_phase_stats":{"P300_overread":c1,"P300_nonff":c2},
  "start_filter_rejects_but_extended_data_returned":True,
  "exact_rejected_start_overlap_values":ff_diagnostic,
  "all_directly_rejected_start_overlaps_are_FF":True,
  "nonFF_0x27a8_data_directly_accessible":True,
  "nonFF_0x27a8_value":"01",
  "nonFF_0x27a8_inaccessible_when_direct":False,
  "two_byte_0x089c_0x089d_values_equal_overlap":True,
  "invalid_direct_reply_01_is_diagnostic_never_memory_byte":True,
  "genuine_unmapped_nonFF_RAM_or_ROM_leak_established":False,
  "OEM_catalog_per_address_complete_proven":False,
  "real_m16c_20bit_program_ROM_reader_identified":False,
  "firmware_dump_or_vitotrol_class11_enrollment":False,
  "new_controller_writes":0,
  "offline_audit_controller_io":0,
 }

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument("--out",type=Path)
 opt=ap.parse_args()
 def load(path):
  f=Path(path)
  if f.is_symlink() or not f.is_file() or f.stat().st_size>35000:
   ap.error(f"original missing / not regular / oversized: {path}")
  return f.read_bytes()
 result=audit(
  load(SOURCES["first"][0]),load(SOURCES["second"][0]),
  load(VS1_SOURCES["first"][1]),load(VS1_SOURCES["second"][1]))
 output=json.dumps(result,indent=2,sort_keys=True)+"\n"
 if opt.out:opt.out.write_text(output)
 print(output)

if __name__=="__main__":main()
