"""Read-only SHA-attested 65 P300 FC01 original transactions on WB2A 20C2."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest

P=Path(__file__).resolve().parents[1]/"tools/wb2a-vitotrol-p300-interior-original-audit.py"
s=importlib.util.spec_from_file_location("vt_p300_three_original_sessions_test",P)
m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m)

def originals():
 keys=[
  m.old.SOURCES["first"][0],m.old.SOURCES["second"][0],
  m.old.VS1_SOURCES["first"][1],m.old.VS1_SOURCES["second"][1],
  m.ORIG_THIRD,m.ORIG_VS1]
 return [Path(x).read_bytes() for x in keys]


class Tests(unittest.TestCase):
 def test_exact_source_hash_list_and_read_scope(self):
  self.assertEqual(len(m.THIRD_SHA),64)
  self.assertEqual(len(m.VS1_SHA),64)
  self.assertEqual(len(m.THIRD_ROWS),21)
  self.assertEqual(sum(n==m.ERR for _,_,n in m.THIRD_ROWS),4)
  self.assertEqual(sum(n!=m.ERR for _,_,n in m.THIRD_ROWS),17)
  self.assertEqual({x[0] for x in m.THIRD_ROWS if x[2]==m.ERR},
                   {"088f","0897","0899","0a5d"})

 def test_unpinned_sources_rejected(self):
  with self.assertRaises(m.Refused):
   m.authenticate(b"{}",m.THIRD_SHA,"test")
  with self.assertRaises(m.Refused):
   m.authenticate(b"",m.VS1_SHA,"test")
  with self.assertRaises(m.old.EvidenceRejected):
   m.verify(b"{}",b"{}",b"{}",b"{}",b"{}",b"{}")

 def test_both_original_2013_gates_and_third_real_if_available(self):
  try:raw=originals()
  except (FileNotFoundError,PermissionError):self.skipTest("original live data on LXC only")
  result=m.verify(*raw)
  self.assertEqual(result["actual_P300_read_request_count"],65)
  self.assertEqual(result["actual_P300_successful_response_count"],56)
  self.assertEqual(result["actual_P300_error03_01_count"],9)
  self.assertTrue(result["P300_valid_start_exposes_nonFF_byte_at_interior_088f"])
  self.assertTrue(result["direct_0897_and_0899_rejected_but_two_byte_temp_reads_expose_00"])
  self.assertTrue(result["direct_0a5d_rejected_but_0a5c_4_exposes_00"])
  self.assertTrue(result["no_general_unmapped_physical_ROM_or_RAM_disclosure_proven"])
  self.assertFalse(result["firmware_dump_obtained"])
  self.assertEqual(result["new_controller_writes"],0)
  self.assertEqual(result["new_controller_read_requests_for_offline_audit"],0)

 def test_third_original_sha_mutations_refused(self):
  try:raw=originals()
  except (FileNotFoundError,PermissionError):self.skipTest("original live data absent")
  p=raw.copy();p[-2]=p[-2]+b"0"
  with self.assertRaises(m.Refused):m.verify(*p)
  p=raw.copy();p[-1]=p[-1]+b" "
  with self.assertRaises(m.Refused):m.verify(*p)
  p=raw.copy();p[0]=p[0]+b" "
  with self.assertRaises(m.old.EvidenceRejected):m.verify(*p)

 def test_2013_error_bytes_not_disclosed_as_memory(self):
  try:raw=originals()
  except (FileNotFoundError,PermissionError):self.skipTest("original data absent")
  import json
  third=json.loads(raw[-2])
  rows=third["rows"]
  by={x["cmd"]:x for x in rows}
  self.assertEqual(bytes.fromhex(by["read;0x088e;8"]["data"])[1],0x26)
  self.assertIsNone(by["read;0x088f;1"]["data"])
  self.assertEqual(by["read;0x088f;1"]["error_raw_payload"],"01")
  self.assertEqual(by["read;0x0897;1"]["error_raw_payload"],"01")
  self.assertEqual(by["read;0x0a5d;1"]["error_raw_payload"],"01")
  self.assertEqual(bytes.fromhex(by["read;0x0896;2"]["data"])[1],0x00)


if __name__=="__main__":unittest.main()
