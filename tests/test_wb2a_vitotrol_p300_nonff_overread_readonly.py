"""Strict unit replay of non-FF source-backed 2013 P300 overlap experiment."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/"tools/wb2a-vitotrol-p300-nonff-overread-readonly.py"
s=importlib.util.spec_from_file_location("wb2a_nonff_overread_isolated_test",P)
m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m)


class Tests(unittest.TestCase):
 def test_finite_readonly_and_original_identity(self):
  self.assertEqual(len(m.SERIES),23)
  self.assertEqual(m.SERIES[0],m.ID)
  self.assertEqual(m.SERIES[-1],m.ID)
  self.assertEqual(m.CHALLENGES.count("read;0x27a8;1"),2)
  self.assertEqual(m.CHALLENGES.count("read;0x27a0;16"),2)
  self.assertEqual(set(m.SERIES),m.ALLOWED)
  self.assertTrue(all(c.startswith("read;0x") and 1<=int(c.rsplit(";",1)[1])<=16 for c in m.SERIES))
  self.assertEqual(bytes.fromhex(m.EXPECTED_VS1["read;0x27a0;16"])[8],1)

 def test_original_sources_if_present(self):
  try:a=m.FIRST_PATH.read_bytes();b=m.VS1_PATH.read_bytes()
  except (FileNotFoundError,PermissionError):self.skipTest("private originals not mounted")
  self.assertTrue(m.sources_attested(a,b))
  with self.assertRaises(m.Refused):m.sources_attested(a,b+b"x")
  with self.assertRaises(m.Refused):m.sources_attested(a+b"x",b)

 def test_config_lock_fails_bad_inputs(self):
  with self.assertRaises(m.Refused):
   m.check_host(config=b"vs1protocol = True",restore_active=True,owner_active=True)
  with self.assertRaises(m.Refused):
   m.check_host(config=b"vs1protocol = False",restore_active=False,owner_active=True)
  with self.assertRaises(m.Refused):
   m.check_host(config=b"vs1protocol = False",restore_active=True,owner_active=False)

 def test_nonff_positive_bypass_simulated_never_rom(self):
  controls={m.ID:m.base.TARGET,**{s:"00" for s in m.GUARDS},
            "read;0x0a5c;4":"00000000",
            **m.EXPECTED_VS1}
  def mock(c):
   code=3 if c in ("read;0x27a8;1","read;0x27a1;1","read;0x089b;1") else 1
   data="01" if code==3 else controls[c]
   return c+f" <- openv/resp: {code};0x{int(c.split(';')[1],16):x};{data}"
  r=m.capture(mock)
  self.assertEqual(r["controller_read_requests"],23)
  self.assertEqual(r["candidate_overread_27a8_value"],"01")
  self.assertEqual(r["candidate_direct_27a8_statuses"],[3,3])
  self.assertTrue(r["P300_direct_reject_but_P300_neighbor_long_exposes_nonff"])
  self.assertFalse(r["ROM_bank_or_20bit_code_bytes_proven"])
  self.assertEqual(r["controller_writes"],0)

 def test_false_positive_if_direct_byte_access_succeeds(self):
  controls={m.ID:m.base.TARGET,**{s:"00" for s in m.GUARDS},
            "read;0x0a5c;4":"00000000",
            **m.EXPECTED_VS1,"read;0x27a1;1":"ff"}
  def mock(c):
   code=3 if c=="read;0x089b;1" else 1
   data="01" if code==3 else controls[c]
   return c+f" <- openv/resp: {code};0x{int(c.split(';')[1],16):x};{data}"
  r=m.capture(mock)
  self.assertEqual(r["candidate_direct_27a8_statuses"],[1,1])
  self.assertFalse(r["P300_direct_reject_but_P300_neighbor_long_exposes_nonff"])

 def test_first_guard_stops_later_reads(self):
  seen=[]
  def mock(c):
   seen.append(c)
   return c+f" <- openv/resp: 1;0x{int(c.split(';')[1],16):x};"+(
       m.base.TARGET if len(seen)==1 else "01")
  with self.assertRaises(m.Refused):
   m.capture(mock)
  self.assertEqual(seen,[m.ID,m.GUARDS[0]])


if __name__=="__main__":unittest.main()
