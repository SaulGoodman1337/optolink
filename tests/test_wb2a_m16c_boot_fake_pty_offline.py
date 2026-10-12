"""Real m16cflasher binary tested via private unconnected PTY, never Optolink."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest

P=Path(__file__).resolve().parents[1]/"tools/wb2a-m16c-boot-fake-pty-check-offline.py"
s=importlib.util.spec_from_file_location("wb2a_pty_fake_bootloader_unit",P)
m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m)


class FakeBoot(unittest.TestCase):
 def test_explicit_only_version_and_status(self):
  self.assertEqual(set(m.ALLOWED),{"ver","status"})
  self.assertEqual(m.ALLOWED["ver"][0],bytes.fromhex("b0fb"))
  self.assertEqual(m.ALLOWED["status"][0],bytes.fromhex("b070"))
  self.assertTrue(m.TIMEOUT<15)
  with self.assertRaises(m.Refused):m.virtual_test("read")
  with self.assertRaises(m.Refused):m.virtual_test("erase")
  with self.assertRaises(m.Refused):m.virtual_test("download")
  with self.assertRaises(m.Refused):m.virtual_test("status=/dev/ttyUSB0")

 def test_real_binary_with_simulated_bootloader_version(self):
  try:m.gates.safe_hash(m.gates.FLASHER,750000)
  except (FileNotFoundError,PermissionError):self.skipTest("real pinned flasher absent")
  a=m.virtual_test("ver")
  self.assertEqual(a["actual_flasher_command_bytes"],"b0fb")
  self.assertIn("VER4.04",a["actual_stdout_prefix"])
  self.assertEqual(a["process_returncode"],0)
  self.assertTrue(a["no_real_hardware_serial_IO"])
  self.assertFalse(a["physical_controller_connected"])
  self.assertFalse(a["real_bootloader_state_verified"])

 def test_real_binary_with_simulated_bootloader_status(self):
  try:m.gates.safe_hash(m.gates.FLASHER,750000)
  except (FileNotFoundError,PermissionError):self.skipTest("real pinned flasher absent")
  a=m.virtual_test("status")
  self.assertEqual(a["actual_flasher_command_bytes"],"b070")
  self.assertIn("0x0c00",a["actual_stdout_prefix"])
  self.assertEqual(a["process_returncode"],0)
  self.assertFalse(a["physical_controller_connected"])

 def test_source_is_pinned_and_cannot_accept_real_USB_path(self):
  source=P.read_text()
  self.assertIn('path.startswith("/dev/serial")',source)
  self.assertIn('path.startswith("/dev/pts/")',source)
  self.assertIn("pty.openpty()",source)
  self.assertNotIn("/dev/ttyUSB",source)
  self.assertEqual(len(m.gates.EXPECTED_FLASHER_SHA),64)


if __name__=="__main__":unittest.main()
