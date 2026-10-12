"""P300 known multibyte interior test: non-FF inaccessible byte, never RAM/ROM."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest

P=Path(__file__).resolve().parents[1]/"tools/wb2a-vitotrol-p300-interior-byte-readonly.py"
spec=importlib.util.spec_from_file_location("wb2a_interior_byte_2013_test",P)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m
spec.loader.exec_module(m)


class Tests(unittest.TestCase):
 def test_readonly_plan_fixed_21_and_no_commands(self):
  self.assertEqual(len(m.SERIES),21)
  self.assertEqual(len(m.CHALLENGES),11)
  self.assertEqual(m.SERIES[0],m.ID)
  self.assertEqual(m.SERIES[-1],m.ID)
  self.assertEqual(set(m.SERIES),m.ALLOWED)
  for x in m.SERIES:
   self.assertTrue(x.startswith("read;0x"))
   self.assertLessEqual(int(x.rsplit(";",1)[1]),16)
  self.assertNotIn("request;4;",' '.join(m.SERIES))
  self.assertEqual(m.ORIGINAL_VS1_SHA[:8],"31fb39a6")

 def test_source_attestation_if_real_captures_exist(self):
  try:vs1=m.ORIGINAL_VS1_PATH.read_bytes();p300=m.FIRST_ORIGINAL.read_bytes()
  except (FileNotFoundError,PermissionError):self.skipTest("private data not mounted")
  self.assertTrue(m.verify_sources(vs1,p300))
  with self.assertRaises(m.Refused):m.verify_sources(vs1+b"x",p300)
  with self.assertRaises(m.Refused):m.verify_sources(vs1,p300+b"x")

 def test_host_guard_fails_without_original_config(self):
  for args in ((b"vs1protocol = True",True,True),
               (b"vs1protocol = False",False,True),
               (b"vs1protocol = False",True,False),
               (b"vs1protocol = False",True,True)):
   with self.subTest(args=args),self.assertRaises(m.Refused):
    m.check_host(*args)

 def test_interior_validated_nonff_only_not_ROM(self):
  fixed={m.ID:m.base.TARGET,**{g:"00" for g in m.GUARDS},
         "read;0x088e;8":"2026101201081813",
         "read;0x088e;16":"2026101201081813c800c800ffff0303",
         "read;0x0896;2":"c800",
         "read;0x0898;2":"c800",
         "read;0x0a5c;4":"00000000",
         "read;0x00fa;1":"00"}
  denied={"read;0x088f;1","read;0x0897;1",
          "read;0x0899;1","read;0x0a5d;1"}
  def mock(c):
   stat=3 if c in denied else 1
   data="01" if stat==3 else fixed[c]
   return c+f" <- openv/resp: {stat};0x{int(c.split(';')[1],16):x};{data}"
  result=m.capture(mock)
  self.assertTrue(result["P300_interior_year_0x26_block_visible_but_directly_rejected"])
  self.assertTrue(result["P300_interior_temp_0x00_block_visible_but_directly_rejected"])
  self.assertTrue(result["inside_data_point_inaccessible_nonFF_block_bytes_proven"])
  self.assertFalse(result["nonFF_bytes_from_unmapped_physical_CPU_RAM_proven"])
  self.assertFalse(result["20bit_M16C_program_ROM_dump"])
  self.assertEqual(result["controller_read_requests"],21)
  self.assertEqual(result["controller_writes"],0)

 def test_rejection_not_claimed_if_direct_succeeds(self):
  fixed={m.ID:m.base.TARGET,**{g:"00" for g in m.GUARDS},
         "read;0x088e;8":"2026101201081813",
         "read;0x088e;16":"2026101201081813c800c800ffff0303",
         "read;0x0896;2":"c800",
         "read;0x0898;2":"c800",
         "read;0x0a5c;4":"00000000",
         "read;0x00fa;1":"00",
         "read;0x088f;1":"26",
         "read;0x0897;1":"00",
         "read;0x0899;1":"00",
         "read;0x0a5d;1":"00"}
  def mock(c):
   return c+f" <- openv/resp: 1;0x{int(c.split(';')[1],16):x};"+fixed[c]
  res=m.capture(mock)
  self.assertFalse(res["P300_interior_year_0x26_block_visible_but_directly_rejected"])
  self.assertFalse(res["P300_interior_temp_0x00_block_visible_but_directly_rejected"])

 def test_mismatched_status_fails_before_test(self):
  observed=[]
  def mock(c):
   observed.append(c)
   val=m.base.TARGET if len(observed)==1 else "03"
   return c+f" <- openv/resp: 1;0x{int(c.split(';')[1],16):x};"+val
  with self.assertRaises(m.Refused):m.capture(mock)
  self.assertEqual(observed,[m.ID,m.GUARDS[0]])


if __name__=="__main__":unittest.main()
