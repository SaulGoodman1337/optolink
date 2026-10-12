"""Fail-closed ROM contrast: exact 16-bit FC03 requests and archival comparison."""
import importlib.util
from pathlib import Path
import sys
import unittest

SPEC=importlib.util.spec_from_file_location(
 "wb2a_vt_rom_contrast_test",Path(__file__).resolve().parents[1]
 /"tools/wb2a-vitotrol-rom-bridge-contrast-readonly.py")
m=importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name]=m
SPEC.loader.exec_module(m)


class Fake:
 def __init__(self,bad_cmd=None,bad_identity=False):
  self.request_log=[];self.t=1000.
  self.bad_cmd=bad_cmd;self.bad_identity=bad_identity
 def request(self,cmd):
  addr,n=m.base.ALLOWED[cmd]; data=bytearray(n)
  if cmd==m.base.IDENTITY:
   data[:]=bytes.fromhex(m.TARGET if not self.bad_identity else "00"*8)
  if cmd=="read;0x089c;1":data[:]=bytes.fromhex("03")
  if cmd=="read;0x0a5c;4":data[:]=bytes.fromhex("00000000")
  if cmd==m.READS["physical_3300"]:
   data[:16]=bytes.fromhex("38361eccb44ddf8ef8efabb787fffe79")
  if cmd==m.READS["physical_2182"]:
   data[:]=bytes.fromhex("16e5c86a16e516e50016e500bfb94451")
  self.t+=.19
  row={"command":cmd,"address":f"0x{addr:04x}","data":data.hex(),
       "valid_read":True,"controller_read_only":True,
       "mono_start":self.t,"mono_response":self.t+.17,"duration_ms":170.0}
  if cmd==self.bad_cmd:row["controller_read_only"]=False
  self.request_log.append(row)
  return row


class Tests(unittest.TestCase):
 def test_explicit_fixed_safe_fcs(self):
  self.assertEqual(len(m.READS),5)
  self.assertEqual(len(set(m.READS.values())),5)
  for key,cmd in m.READS.items():
   addr,n=m.EXPECTED[key]
   self.assertEqual(cmd,f"request;3;0x{addr:04x};{n}")
   self.assertEqual(m.base.ALLOWED[cmd],(addr,n))
   self.assertIn(cmd,m.base.P300_ONLY)
   self.assertLessEqual(addr,0xffff)
  self.assertTrue(all("write" not in x.lower() and ";4;" not in x
                      for x in m.READS.values()))
 def test_two_cycle_report_and_guards(self):
  f=Fake();r=m.capture(f)
  self.assertEqual(r["controller_reads"],20)
  self.assertEqual(r["controller_writes"],0)
  self.assertTrue(r["ordinary_16bit_low_address_fc03_only"])
  self.assertTrue(all(x["physical_copies_equal"] for x in r["comparisons"].values()))
  self.assertFalse(r["comparisons"]["physical_3300"]["physical_vs_virtual_equal_on_overlapping_bytes"])
  self.assertFalse(r["comparisons"]["physical_2182"]["physical_vs_virtual_equal_on_overlapping_bytes"])
  self.assertFalse(r["onwire_MCU_20bit_flash_bank_selection_proven"])
  self.assertFalse(r["original_v300_class11_registered"])
 def test_malformed_cycle_target_and_bad_read_refused(self):
  for cycles in (0,1,3,False,2.0):
   with self.subTest(cycles=cycles),self.assertRaises(m.Refused):
    m.capture(Fake(),cycles=cycles)
  with self.assertRaises(m.Refused):m.capture(Fake(bad_identity=True))
  with self.assertRaises(m.Refused):m.capture(Fake(bad_cmd=m.READS["physical_3300"]))
 def test_unknown_command_not_in_base(self):
  self.assertNotIn("request;4;0x3300;32",m.base.ALLOWED)
  self.assertNotIn("request;3;0x0000;64",m.base.ALLOWED)
  self.assertNotIn("request;99;0xf000;16",m.base.ALLOWED)


if __name__=="__main__":unittest.main()
