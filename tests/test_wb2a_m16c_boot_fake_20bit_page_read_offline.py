"""Actual binary's 20-bit page read protocol checked with FAKE PTY only."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest

P=Path(__file__).resolve().parents[1]/"tools/wb2a-m16c-boot-fake-20bit-page-read-offline.py"
s=importlib.util.spec_from_file_location("wb2a_m16c_20bit_fake_test",P)
m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m)


class TestFake20bit(unittest.TestCase):
 def test_page_addressing_math_not_truncated_at_16bit(self):
  self.assertEqual(m.START,0xF0000)
  self.assertEqual(m.END,0xF01FF)
  self.assertEqual(m.END-m.START+1,512)
  self.assertEqual(m.TX,bytes.fromhex("b07070ff000fff010f"))
  self.assertEqual(len(m.SYNTHETIC_PAGES),2)
  self.assertTrue(all(len(x)==256 for x in m.SYNTHETIC_PAGES))

 def test_full_real_executable_20bit_serial_fake_if_available(self):
  try:m.gate.safe_hash(m.gate.FLASHER,750000)
  except (FileNotFoundError,PermissionError):
   self.skipTest("private built executable unavailable")
  r=m.test_virtual_20bit_reader()
  self.assertEqual(r["transmitted_bootloader_bytes"],m.TX.hex())
  self.assertEqual(r["actual_pages_256bytes"],2)
  self.assertEqual(r["synthetic_flash_bytes_returned"],512)
  self.assertTrue(r["full_20bit_address_passed_untruncated_in_BOOT_PROTOCOL"])
  self.assertFalse(r["full_20bit_address_passed_untruncated_in_OPTOLINK_P300"])
  self.assertFalse(r["actual_WB2A_flash_bytes_recovered"])
  self.assertEqual(r["physical_controller_IO"],0)
  self.assertEqual(r["controller_writes"],0)

 def test_simulation_is_always_isolated_from_real_heating_uart(self):
  text=P.read_text()
  self.assertIn('pty.openpty()',text)
  self.assertIn('dev.startswith("/dev/pts/")',text)
  self.assertIn('tempfile.TemporaryDirectory',text)
  self.assertNotIn('/dev/ttyUSB0',text)
  self.assertNotIn('/dev/serial/by-id',text)
  self.assertEqual(m.SYNTHETIC_PAGES[0][:3],bytes([0,1,2]))
  self.assertEqual(m.SYNTHETIC_PAGES[1][:3],bytes([255,254,253]))

 def test_flasher_original_hash_is_pinned(self):
  self.assertEqual(m.gate.EXPECTED_FLASHER_SHA,
                   "8b097885014d1ee082b6c66a58bfd51ce93b3e58abc64c349eddc6335d5784ce")
  self.assertEqual(m.gate.EXPECTED_FLASHER_COMMIT,
                   "cc8f1c387a5bb86ff25600eacb59a576b5312163")


if __name__=="__main__":unittest.main()
