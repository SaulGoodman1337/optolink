"""No live boiler boot attempts: SHA-pinned M16C/62P bench-only gate."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/"tools/wb2a-m16c-boot-hardware-preflight-offline.py"
spec=importlib.util.spec_from_file_location("wb2a_safe_boot_offline_unit",P)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
ORIGINAL={
  str(m.FLASHER):m.EXPECTED_FLASHER_SHA,
  str(m.DMA):m.EXPECTED_DMA_SOURCE_SHA,
  str(m.CONFIG):m.EXPECTED_CONFIG_SHA,
}


class OfflineBenchGates(unittest.TestCase):
 def test_unidentified_real_chip_not_flash_assumed(self):
  r=m.analyze(source_hashes=ORIGINAL)
  self.assertEqual(r["status"],"NO_LIVE_BOOT_TRIGGER_PERMITTED")
  self.assertEqual(r["family_interpretation"],"UNIDENTIFIED")
  self.assertFalse(r["preflight_evidence_gates"]["exact_board_mcu_marking_provided"])
  self.assertFalse(r["bootloader_connected"])
  self.assertEqual(r["serial_ports_opened"],0)
  self.assertEqual(r["controller_commands_sent"],0)
  self.assertEqual(r["controller_writes"],0)

 def test_known_2010_KW2_mask_ROM_not_renesas_flash_boot(self):
  for name in ("M30612MCA","M30612MCA-XXXFP","m30612mca-xxxgp"):
   with self.subTest(name=name):
    a=m.analyze(part_no=name,source_hashes=ORIGINAL)
    self.assertEqual(a["family_interpretation"],"MASK_ROM_NO_FLASH_BOOT")
    self.assertFalse(a["preflight_evidence_gates"]["flash_variant_plausible"])
    self.assertTrue(a["source_not_applicable_to_mask_ROM_M30612MCA"])

 def test_candidate_other_controller_not_proof_local_WB2A(self):
  r=m.analyze(part_no="M30624FGPFP-U3C",source_hashes=ORIGINAL)
  self.assertEqual(r["family_interpretation"],
                   "POTENTIAL_FLASH_M16C62P_CONFIRM_PACKAGE_AND_REVISION")
  self.assertFalse(r["all_documented_evidence_gates_supplied"])
  self.assertFalse(r["actual_device_identification_by_laser_marking_proven_by_software"])
  self.assertFalse(r["mcu_flash_type_verified_on_real_WB2A"])
  self.assertFalse(r["bootloader_connected"])
  self.assertFalse(r["full_flash_dump_now_possible"])

 def test_even_all_documentary_conditions_cannot_trigger_live_mode(self):
  r=m.analyze(part_no="M30624FGPFP",spare_board=True,
              lab_supply_verified=True,validated_pinout=True,
              uart1_isolated=True,id_code_available=True,source_hashes=ORIGINAL)
  self.assertTrue(r["all_documented_evidence_gates_supplied"])
  self.assertFalse(r["actual_GG1_pinout_electrically_verified_by_software"])
  self.assertEqual(r["status"],"NO_LIVE_BOOT_TRIGGER_PERMITTED")
  self.assertFalse(r["program_ROM_20bit_bytes_recovered"])
  self.assertEqual(r["controller_writes"],0)

 def test_original_source_mismatches_fail_closed(self):
  for key in ORIGINAL:
   data=ORIGINAL.copy();data[key]="0"*64
   with self.subTest(key=key),self.assertRaises(m.NotAttested):
    m.analyze(source_hashes=data)

 def test_safe_serial_and_boot_pin_separation(self):
  r=m.analyze(source_hashes=ORIGINAL)
  self.assertIn("UART0",r["current_optolink_program_UART"])
  self.assertEqual(r["standard_M16C62P_flash_boot_UART"],"UART1 RXD1/TXD1")
  self.assertEqual(r["production_optolink_serial_settings"],"4800-8E2")
  self.assertEqual(r["bench_flashboot_UART_settings"],"9600-8N1 (m16cflasher default)")
  self.assertFalse(r["actual_optolink_optical_receiver_wired_to_boot_RXD1_proven"])
  self.assertTrue(r["raw_optolink_cannot_directly_activate_the_M16C62P_boot_ROM"])
  self.assertEqual(r["safe_future_connectivity_checks_on_isolated_spare_only"],
                   ["ver","status"])
  for operation in ("erase","program","download","lock_off"):
   self.assertIn(operation,r["disallowed_operations_even_for_preflight"])

 def test_real_host_source_attestations_if_mounted(self):
  try:
   for f in m.PATHS:
    if not f.is_file():
     self.skipTest("private original executable or DMA source not mounted")
  except PermissionError:self.skipTest("private remote files inaccessible")
  d=m.analyze()
  self.assertTrue(all(x["sha256_valid"] for x in d["source_attestations"]))
  self.assertEqual(m.provenance()["flasher_source_commit"],
                   "cc8f1c387a5bb86ff25600eacb59a576b5312163")


if __name__=="__main__":unittest.main()
