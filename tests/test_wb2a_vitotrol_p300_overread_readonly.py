"""Exact 2013 P300 FC01 valid-start overread hypothesis, zero serial/mock only."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest

P=Path(__file__).resolve().parents[1]/"tools/wb2a-vitotrol-p300-overread-readonly.py"
s=importlib.util.spec_from_file_location("wb2a_2013_p300_overlap_test",P)
m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m)
PRE=Path("/tmp/wb2a-vitotrol-p300-overread-vs1-before-20261012.log")


class UnitTests(unittest.TestCase):
 def test_all_requests_bounded_FC01_and_guards(self):
  x=m.plan()
  self.assertEqual(len(x["requests"]),21)
  self.assertEqual(x["MCU_writes"],0)
  self.assertTrue(x["only_P300_FC01_Virtual_READ"])
  self.assertEqual(max(v["length"] for v in x["requests"]),16)
  self.assertEqual(m.SERIES[0],m.START_BASELINE)
  self.assertEqual(m.SERIES[-1],m.START_BASELINE)
  self.assertEqual(m.CHALLENGES.count("read;0x0a5c;16"),2)
  self.assertFalse(any("request;" in z for z in m.SERIES))

 def test_pinned_vs1_original_if_present(self):
  try:raw=PRE.read_bytes()
  except (FileNotFoundError,PermissionError):self.skipTest("private original VS1 measurement not here")
  self.assertEqual(m.verify_source(raw),m.VS1_ORIGINAL_SHA)
  with self.assertRaises(m.Refused):m.verify_source(raw+b"x")
  with self.assertRaises(m.Refused):m.verify_source(b"{}")

 def test_host_requires_exact_restore_and_P300_config(self):
  with self.assertRaises(m.Refused):
   m.check_host(config=b"vs1protocol = True",timer_active=True,owner_active=True)
  with self.assertRaises(m.Refused):
   m.check_host(config=b"vs1protocol = False",timer_active=False,owner_active=True)
  with self.assertRaises(m.Refused):
   m.check_host(config=b"vs1protocol = False",timer_active=True,owner_active=False)
  with self.assertRaises(m.Refused):
   m.check_host(config=b"vs1protocol = False",timer_active=True,owner_active=True)

 def test_parser_accept_success_and_error_but_never_fake_payload(self):
  c="read;0x0100;4"
  self.assertEqual(m.parse_response(c,c+"  <- openv/resp: 1;0x100;ffffffff")["data"],"ffffffff")
  bad=m.parse_response(c,c+"  <- openv/resp: 3;0x100;?")
  self.assertEqual((bad["status"],bad["data"]),(3,None))
  errbytes=m.parse_response(c,c+"  <- openv/resp: 3;0x100;ee00")
  self.assertEqual((errbytes["status"],errbytes["data"],errbytes["error_raw_payload"]),(3,None,"ee00"))
  for raw in (c+"  <- openv/resp: 1;0x100;ff",
              c+"  <- openv/resp: 1;0x200;ffffffff",
              c+"  <- openv/resp: 2;0x100;ffffffff",
              "read;0x00f8;4 <- openv/resp: 1;0x100;ffffffff"):
   with self.subTest(raw=raw),self.assertRaises(m.Refused):
    m.parse_response(c,raw)

 def test_original_overread_hypothesis_true_in_mock(self):
  defaults={
   m.START_BASELINE:m.TARGET,
   "read;0x27a0;1":"00","read;0x27b0;1":"00",
   "read;0x7342;1":"00","read;0x5738;1":"00",
   "read;0x00f8;4":"20c20003",
   "read;0x00f8;16":m.VS1_CHECK["read;0x00f8;16"],
   "read;0x00fc;12":"00000103ffffffffffffffff",
   "read;0x0a5c;4":"00000000",
   "read;0x0a5c;16":m.VS1_CHECK["read;0x0a5c;16"],
   "read;0x0a60;4":"00000000",
  }
  def fake(command):
   if command in ("read;0x0100;4","read;0x0a64;4"):
    return command+f"  <- openv/resp: 3;0x{int(command.split(';')[1],16):x};?"
   return command+f"  <- openv/resp: 1;0x{int(command.split(';')[1],16):x};"+defaults[command]
  r=m.capture(fake)
  self.assertEqual(r["controller_reads"],21)
  self.assertTrue(r["direct_neighbor_rejected_but_overshot_by_long_read"])
  self.assertTrue(r["issue_142_2013_effect_is_proven_on_own_20C2"])
  self.assertFalse(r["controller_firmware_dump_obtained"])
  self.assertEqual(r["controller_writes"],0)

 def test_no_false_positive_if_direct_neighbors_success(self):
  defaults={m.START_BASELINE:m.TARGET,**{
   c:"00" for c in m.GUARDS},
   **m.VS1_CHECK,"read;0x00fc;12":"00000103ffffffffffffffff",
   "read;0x0a60;4":"00000000","read;0x00f8;4":"20c20003"}
  def fake(command):
   return command+f" <- openv/resp: 1;0x{int(command.split(';')[1],16):x};"+defaults[command]
  r=m.capture(fake)
  self.assertFalse(r["direct_neighbor_rejected_but_overshot_by_long_read"])
  self.assertFalse(r["issue_142_2013_effect_is_proven_on_own_20C2"])

 def test_failclosed_guard_before_experimental_queries(self):
  seen=[]
  def fake(cmd):
   seen.append(cmd)
   data="20c2000300000103" if len(seen)==1 else "01"
   return cmd+f" <- openv/resp: 1;0x{int(cmd.split(';')[1],16):x};"+data
  with self.assertRaises(m.Refused):
   m.capture(fake)
  self.assertEqual(seen,[m.START_BASELINE,m.GUARDS[0]])


if __name__=="__main__":unittest.main()
