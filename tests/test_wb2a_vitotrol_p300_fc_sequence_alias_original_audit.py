"""SHA256-locked real FC 03/63 vs 05/65 P300 AB/BA original source audit."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import sys
import unittest

P=Path(__file__).resolve().parents[1]/"tools/wb2a-vitotrol-p300-fc-sequence-alias-original-audit.py"
spec=importlib.util.spec_from_file_location("fc_sequence_original_capture_auditor_test",P)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)


class Tests(unittest.TestCase):
 def test_exact_30_request_source_plan_and_no_flash_or_writes(self):
  cmds=m.expected()
  self.assertEqual(len(cmds),30)
  self.assertEqual(cmds[:5],[m.ID,*m.GUARDS])
  self.assertEqual(cmds[-5:],[*m.GUARDS,m.ID])
  self.assertEqual(len(m.PAIRS),5)
  self.assertEqual(len(set(cmds)),15)
  self.assertTrue(all(x.startswith("read;") or int(x.split(";")[1]) in (3,5,99,101)
      for x in cmds))
  self.assertTrue(all(1<=int(x.split(';')[-1])<=8 for x in cmds))

 def test_missing_or_fake_original_sources_never_accepted(self):
  with self.assertRaises(m.EvidenceRejected):
   m.evaluate(b"{}",b"other")
  with self.assertRaises(m.EvidenceRejected):
   m.inspect_host(b"print('not the original serializer')")

 def test_real_source_evidence_if_private_host_and_capture_available(self):
  try:a=m.ORIGINAL.read_bytes();b=m.HOST.read_bytes()
  except (FileNotFoundError,PermissionError):
   self.skipTest("private WB2A controller and host originals only on LXC")
  report=m.evaluate(a,b)
  self.assertEqual(report["authentic_controller_reads"],30)
  self.assertEqual(report["successful_controller_reads"],30)
  self.assertTrue(report["all_five_pair_data_identical"])
  self.assertTrue(report["FC65_behaves_like_FC05_at_three_tested_addresses"])
  self.assertTrue(report["FC63_behaves_like_FC03_at_two_tested_RAM_addresses"])
  self.assertFalse(report["controller_uses_exclusively_low5_bits_globally_proven"])
  self.assertFalse(report["physical_20bit_ROM_bytes_returned"])
  self.assertEqual(report["controller_writes"],0)
  self.assertEqual(report["new_controller_requests_from_this_audit"],0)
  self.assertEqual(len(report["five_address_pairs_each_read_in_both_orders"]),5)
  self.assertEqual({x["responses_ABBA_four_reads"] for x in report["five_address_pairs_each_read_in_both_orders"]},{4})
  self.assertTrue(all(x["all_ABBA_results_equal"] for x in report["five_address_pairs_each_read_in_both_orders"]))

 def test_mutated_original_capture_or_serializer_rejected(self):
  try:a=m.ORIGINAL.read_bytes();b=m.HOST.read_bytes()
  except (FileNotFoundError,PermissionError):self.skipTest("private source not mounted")
  for payload,host in ((a+b" ",b),(a,b+b"X"),(a[:-1],b)):
   with self.subTest(lenpayload=len(payload)),self.assertRaises(m.EvidenceRejected):
    m.evaluate(payload,host)

 def test_actual_fc_byte_sequence_and_error_distinction(self):
  try:a=m.ORIGINAL.read_bytes();b=m.HOST.read_bytes()
  except (FileNotFoundError,PermissionError):self.skipTest("private source not mounted")
  body=json.loads(a)
  self.assertEqual({x["status"] for x in body["rows"]},{1})
  p=[x for x in body["rows"] if x["cmd"].startswith("request;")]
  self.assertEqual(len(p),20)
  self.assertEqual({x["fc_raw"] for x in p},{3,5,99,101})
  self.assertEqual({x["sequence_hi3"] for x in p},{0,3})
  self.assertEqual(set(x["data"] for x in p if x["address"]=="0x0b6d"),{"42160afe"})
  self.assertEqual(set(x["data"] for x in p if x["address"]=="0x0b74"),{"ff230f64"})
  self.assertEqual(m.inspect_host(b)["wire_address_bits"],16)


if __name__=="__main__":unittest.main()
