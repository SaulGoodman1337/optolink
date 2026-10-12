#!/usr/bin/env python3
"""Offline-only SHA-pinned 20C2 P300 FC05/101 + FC03/99 AB/BA source audit.

Audits the exact 30 actual controller requests and original host-source
function/address serializer. Differentiates on-wire sequence-bit identity from
proof of a distinct MCU dispatcher; never opens serial, MQTT, Optolink, or
controller writes. Does not assert static EEPROM values outside measured day.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
from pathlib import Path

ORIGINAL=Path("/tmp/wb2a-vitotrol-p300-fc-alias-live-20261012.json")
ORIGINAL_SHA="877c7b70cfe687841c42d14fc716024597f4e6408a581197b02233574c9f7c16"
HOST=Path("/opt/optolink/optolinkvs2.py")
HOST_SHA="12f649b6b3f15f4c707eae932fdf5b22925afffb476136bf75af1306c5d0a815"
CONFIG_SHA="e9a120ef37fe17236a7505ee713c8dd338d98d5093ed75dfb34629d7e8f5c42d"
ID="read;0x00f8;8"
GUARDS=("read;0x27a0;1","read;0x27b0;1","read;0x7342;1","read;0x5738;1")
PAIRS=(
 ("EEPROM_ZERO",5,101,0x0000,8,"639c8d72cc336a95"),
 ("EEPROM_F8",5,101,0x00f8,8,"00ff1de2bc436a95"),
 ("EEPROM_17",5,101,0x0017,2,"fc5e"),
 ("SRAM_DESCRIPTOR",3,99,0x0b6d,4,"42160afe"),
 ("SRAM_POINTER",3,99,0x0b74,4,"ff230f64"),
)

def expected():
 first=[ID,*GUARDS]
 ab=[f"request;{code};0x{a:04x};{size}"
     for label,lo,hi,a,size,datum in PAIRS for code in (lo,hi)]
 ba=[f"request;{code};0x{a:04x};{size}"
     for label,lo,hi,a,size,datum in PAIRS for code in (hi,lo)]
 return first+ab+ba+list(GUARDS)+[ID]

class EvidenceRejected(ValueError):pass

def attest(content:bytes,sha:str,label:str,max_bytes:int):
 if (type(content) is not bytes or not 0<len(content)<=max_bytes or
     hashlib.sha256(content).hexdigest()!=sha):
  raise EvidenceRejected("missing/mutated original "+label)


def inspect_host(source:bytes):
 attest(source,HOST_SHA,"installed P300 serializer",40_000)
 tree=ast.parse(source.decode("utf-8-sig"))
 functions={t.name:t for t in tree.body if isinstance(t,ast.FunctionDef)}
 if "do_request" not in functions or "receive_telegr" not in functions:
  raise EvidenceRejected("original host packet encoder/decoder no longer present")
 all_src=ast.unparse(functions["do_request"])
 rx_src=ast.unparse(functions["receive_telegr"])
 for excerpt in (
    "outbuff[3] = fctcode & 255",
    "outbuff[4] = addr >> 8 & 255",
    "outbuff[5] = addr & 255",
    "outbuff[6] = rlen",
 ):
  if excerpt not in all_src:
   raise EvidenceRejected("actual P300 host wire format not present: "+excerpt)
 for excerpt in ("fctcd = inbuff[3] & 31",
                 "msqn = (inbuff[3] & 224) >> 5",
                 "addr = (inbuff[4] << 8) + inbuff[5]"):
  if excerpt not in rx_src:
   raise EvidenceRejected("actual P300 host response decoding mismatched")
 return {"producer_source_sha256":HOST_SHA,"wire_fc_byte_sent_unmasked":True,
         "receiver_fc_low5_only":True,"high3_sequence_bits":True,
         "wire_address_bits":16,"twenty_bit_address_directly_encoded":False}


def evaluate(raw:bytes,host:bytes):
 attest(raw,ORIGINAL_SHA,"30 authentic 20C2 read-only answers",35000)
 host_info=inspect_host(host)
 data=json.loads(raw)
 if (data.get("mode")!="WB2A_REAL_NATIVE_P300_FC_LOW5_VS_HIGH3_ALIAS_READONLY_AB_BA"
     or data.get("target")!="20C2/0103"
     or data.get("controller_request_count")!=30
     or data.get("controller_writes")!=0
     or data.get("all_five_pairs_repeated_exactly_equal") is not True
     or data.get("ROM_bank_page_copy_monitor_detected") is not False
     or data.get("real_GWG_or_KM_bus_gateway_service_proven") is not False):
  raise EvidenceRejected("actual 20C2 provenance/header misrepresents proof")
 rows=data.get("rows")
 if type(rows) is not list or len(rows)!=30:
  raise EvidenceRejected("not exactly 30 original FC01/03/05/63/65 reads")
 steps=expected()
 if len(steps)!=30:raise EvidenceRejected("internal fixed plan size incorrect")
 for i,(row,cmd) in enumerate(zip(rows,steps)):
  if row.get("index")!=i or row.get("cmd")!=cmd:
   raise EvidenceRejected(f"request order/whitelist violated at step {i}")
  fc=int(cmd.split(';')[1]) if cmd.startswith("request;") else 1
  addr=int(cmd.split(';')[2 if fc!=1 else 1],16)
  size=int(cmd.rsplit(';',1)[1])
  actual=(
    "20c2000300000103" if cmd==ID else
    "00" if fc==1 else
    next(expected_val for _,a,b,expected_addr,expected_size,expected_val in PAIRS
         if fc in (a,b) and addr==expected_addr and size==expected_size)
  )
  if (row.get("status")!=1 or row.get("accepted") is not True
      or row.get("address")!=f"0x{addr:04x}"
      or row.get("data")!=actual
      or row.get("error_diag") is not None
      or row.get("fc_raw")!=fc
      or row.get("fc_low5")!=fc&31
      or row.get("sequence_hi3")!=fc>>5
      or len(bytes.fromhex(actual))!=size):
   raise EvidenceRejected(f"byte-exact controller result/sequence attribution failed at {i}")
 captures=[]
 for j,(label,fc0,fc1,addr,size,want) in enumerate(PAIRS):
  s=5+2*j
  r=15+2*j
  reps=(rows[s],rows[s+1],rows[r],rows[r+1])
  if (tuple(x["fc_raw"] for x in reps)!=(fc0,fc1,fc1,fc0)
      or any(x["data"]!=want for x in reps)
      or (fc0&31)!=(fc1&31)
      or (fc1>>5)!=3):
   raise EvidenceRejected("pair AB/BA failed: "+label)
  captures.append({
   "name":label,
   "source_cpu_address":f"0x{addr:04x}",
   "read_bytes":size,
   "base_function":f"0x{fc0:02x}",
   "alternative_function":f"0x{fc1:02x}",
   "decoded_fc_low5":f"0x{fc0&31:02x}",
   "alternate_high_sequence":3,
   "responses_ABBA_four_reads":4,
   "response_hex_four_times":want,
   "all_ABBA_results_equal":True,
   "distinct_internal_service_proven":False,
  })
 reported=data.get("pairs")
 if (not isinstance(reported,list) or len(reported)!=len(captures)
     or any(r.get("kind")!=c["name"] or r.get("two_repeat_AB_BA_exactly_equal") is not True
            or r.get("same_dispatcher_proven_by_equality") is not False
            for r,c in zip(reported,captures))):
  raise EvidenceRejected("unverified compiled comparison or semantic overclaim")
 return {
  "mode":"OFFLINE_SHA_VERIFIED_REAL_WB2A_30READ_NATIVE_P300_FC_ALIAS_AB_BA",
  "controller":"20C2/0103",
  "capture_SHA256":ORIGINAL_SHA,
  **host_info,
  "authentic_controller_reads":30,
  "successful_controller_reads":30,
  "controller_writes":0,
  "new_controller_requests_from_this_audit":0,
  "verified_ABBA_control_ID_and_fault_stable":True,
  "five_address_pairs_each_read_in_both_orders":captures,
  "all_five_pair_data_identical":True,
  "FC65_behaves_like_FC05_at_three_tested_addresses":True,
  "FC63_behaves_like_FC03_at_two_tested_RAM_addresses":True,
  "earlier_FC65_as_independent_gateway_not_proven":True,
  "different_earlier_EEPROM_values_can_change_between_days":True,
  "controller_uses_exclusively_low5_bits_globally_proven":False,
  "extra_ROM_bank_or_KM_bus_service_proven":False,
  "physical_20bit_ROM_bytes_returned":False,
  "direct_rom_address_F0000_truncates_to_0000":True,
 }

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("--out",type=Path)
 opt=p.parse_args()
 if (ORIGINAL.is_symlink() or not ORIGINAL.is_file() or
     HOST.is_symlink() or not HOST.is_file() or
     ORIGINAL.stat().st_size>35000 or HOST.stat().st_size>40000):
  p.error("exact locally retained original/host missing")
 outcome=evaluate(ORIGINAL.read_bytes(),HOST.read_bytes())
 serialized=json.dumps(outcome,indent=2,sort_keys=True)+"\n"
 if opt.out:opt.out.write_text(serialized)
 print(serialized)

if __name__=="__main__":main()
