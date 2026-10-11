"""Bytewise original fullRAM vs same-day VS1/P300 contrast; no controller calls."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"tools/wb2a-vitotrol-optolink-rom-contrast-audit.py"
spec=importlib.util.spec_from_file_location("vt_rom_contrast_original_audit_test",SOURCE)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
P300=Path("/tmp/wb2a-vitotrol-rom-contrast-p300-20261011.json")
FULL=Path("/root/p300-trial-work/research-bundles/p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz")


class Tests(unittest.TestCase):
 def test_hashes_and_unique_expected_targets(self):
  self.assertEqual(len(m.P300_SHA),64)
  self.assertNotEqual(m.P300_SHA,m.ARCHIVE_SHA)
  self.assertEqual(set(m.EXPECTED),set(m.base.READS))
  self.assertEqual(len(m.EXPECTED),5)
  self.assertEqual(m.EXPECTED["physical_f000"],"5497549754975497")
  self.assertEqual(m.EXPECTED["physical_fff0"],"5498549854985498")

 def test_bad_origin_provenance_refused(self):
  with self.assertRaises(m.Refused):m.audit_physical(b"")
  with self.assertRaises(m.Refused):m.audit_physical(b"{}")
  with self.assertRaises(m.Refused):m.audit_against_archive(b"{}",b"bad")

 def test_vs1_and_physical_traces_differ_on_all_addresses(self):
  for key,physical in m.EXPECTED.items():
   old=m.KNOWN_VS1[key]
   self.assertNotEqual(physical[:len(old)],old)
   self.assertTrue(len(old)<=len(physical))
  self.assertEqual(m.KNOWN_VS1["physical_3300"],
                   "ff040000ffff14031419700101040000")

 def test_stable_old_vs_new_byte(self):
  self.assertEqual(m.EXPECTED["physical_2182"][:8],"16e5cb6a")
  self.assertEqual(m.EXPECTED["physical_3300"][:8],"38361ecc")

 def test_original_private_inputs_if_accessible(self):
  try:current=P300.read_bytes();full=FULL.read_bytes()
  except (FileNotFoundError,PermissionError):
   self.skipTest("original root-only sources not available")
  result=m.audit_against_archive(current,full)
  self.assertEqual(result["historical_to_live_0x2182_changed_addresses"],["0x2184"])
  self.assertEqual(result["historical_to_live_0x2184_change"],"c8->cb")
  self.assertEqual(result["fullram_original_images_verified"],79)
  self.assertTrue(result["all_5_address_numeric_equivalence_hypotheses_refuted"])
  self.assertTrue(result["long_term_static_tail_invariant_disproven"])
  self.assertTrue(result["0x3300_32byte_stable_across_all_79_and_new_live"])
  self.assertFalse(result["firmware_dump_obtained"])
  self.assertFalse(result["physical_ISA_memory_bank_mapping_proven"])
  self.assertEqual(result["native_controller_writes"],0)
  self.assertEqual(result["controller_writes_new_during_audit"],0)


if __name__=="__main__":unittest.main()
