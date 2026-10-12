"""FC03/99 and FC05/101 actual dispatcher AB/BA experiment: offline gates."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest

PATH=Path(__file__).resolve().parents[1]/"tools/wb2a-vitotrol-p300-fc-sequence-alias-readonly.py"
spec=importlib.util.spec_from_file_location("fc_seq_alias_test",PATH)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)


def fixture(*,alias=True, errors=(),bad_guard=False):
 def inner(cmd):
  fc=int(cmd.split(";")[1]) if cmd.startswith("request;") else 1
  addr=int(cmd.split(";")[2 if cmd.startswith("request;") else 1],16)
  n=int(cmd.split(";")[-1])
  if fc==1:
   v="20c2000300000103" if cmd==m.ID else ("01" if bad_guard else "00")
  elif fc in (5,101):
   if addr==0x0017:v="fc3a"
   elif addr==0x00f8:v="0011223344556677"
   else:v="8013109105100040"
  elif fc in (3,99):
   if addr==0x0b6d:v="42160afe"
   else:v="ff230f64"
  else:raise AssertionError("writer/outside whitelist attempted")
  if not alias and fc in (99,101):v="aa"*n
  iserr=(cmd in errors)
  rc=3 if iserr else 1
  return f"{cmd} <- openv/resp: {rc};0x{addr:x};{'01' if iserr else v}"
 return inner


class Tests(unittest.TestCase):
 def test_all_requests_fixed_read_only_and_controlled_pair_alternation(self):
  self.assertEqual(len(m.REQUESTS),30)
  self.assertEqual(len(m.PAIRS),5)
  self.assertEqual(len(m.ALLOWED),15)
  self.assertTrue(all(int(x.split(";")[-1])<=8 for x in m.REQUESTS))
  self.assertEqual(m.SERIES[0],(m.ID,*m.CONTROLS))
  self.assertEqual(m.SERIES[-1],(*m.CONTROLS,m.ID))
  self.assertEqual([x[1] for x in m.PAIRS[:3]],[
   "request;5;0x0000;8","request;5;0x00f8;8","request;5;0x0017;2"])
  self.assertEqual([x[2] for x in m.PAIRS[3:]],[
   "request;99;0x0b6d;4","request;99;0x0b74;4"])
  self.assertTrue(all(x.startswith("read;") or
      int(x.split(";")[1]) in (3,5,99,101) for x in m.REQUESTS))

 def test_host_config_needs_exact_restore(self):
  for config,on_owner,on_timer in (
    (b"vs1protocol = True",True,True),
    (b"vs1protocol = False",False,True),
    (b"vs1protocol = False",True,False),
    (b"vs1protocol = False",True,True)):
   with self.subTest(config=config),self.assertRaises(m.Refused):
    m.verify_host(config,on_owner,on_timer)

 def test_reply_parser_stops_wrong_addresses_partial_payload_writer(self):
  c=m.PAIRS[0][1]
  valid=m.parse_response(c,fixture()(c))
  self.assertEqual(valid["data"],"8013109105100040")
  self.assertEqual((valid["fc_raw"],valid["fc_low5"],valid["sequence_hi3"]),(5,5,0))
  high=m.parse_response(m.PAIRS[0][2],fixture()(m.PAIRS[0][2]))
  self.assertEqual((high["fc_raw"],high["fc_low5"],high["sequence_hi3"]),(101,5,3))
  for raw in (
    c+" <- openv/resp: 1;0x1;8013109105100040",
    c+" <- openv/resp: 1;0x0;8013",
    c+" <- openv/resp: 5;0x0;8013109105100040",
    c+" <- openv/resp: 3;0x0;"+"ff"*17,
    "request;6;0x0000;8 <- openv/resp: 1;0x0;8013109105100040",
  ):
   with self.subTest(raw=raw),self.assertRaises(m.Refused):
    m.parse_response(c,raw)
  err=m.parse_response(c,c+" <- openv/resp: 3;0x0;3101")
  self.assertIsNone(err["data"])
  self.assertEqual(err["error_diag"],"3101")

 def test_alias_stable_positive_cannot_establish_controller_dispatcher(self):
  report=m.capture(fixture())
  self.assertEqual(report["controller_request_count"],30)
  self.assertEqual(report["controller_writes"],0)
  self.assertTrue(report["all_five_pairs_repeated_exactly_equal"])
  self.assertEqual(len(report["rows"]),30)
  self.assertEqual(report["pairs"][0]["base_2_data"],["8013109105100040"]*2)
  self.assertEqual(report["pairs"][-1]["base_2_data"],["ff230f64"]*2)
  self.assertTrue(all(x["two_repeat_AB_BA_exactly_equal"] for x in report["pairs"]))
  self.assertFalse(any(x["same_dispatcher_proven_by_equality"] for x in report["pairs"]))
  self.assertFalse(report["ROM_bank_page_copy_monitor_detected"])

 def test_high_sequence_different_cannot_claim_rom(self):
  report=m.capture(fixture(alias=False))
  self.assertFalse(report["all_five_pairs_repeated_exactly_equal"])
  self.assertEqual(len([x for x in report["pairs"]
      if not x["two_repeat_AB_BA_exactly_equal"]]),5)
  self.assertFalse(report["ROM_bank_page_copy_monitor_detected"])
  self.assertEqual(report["controller_writes"],0)

 def test_errors_are_recorded_not_data(self):
  pair=m.PAIRS[2]
  report=m.capture(fixture(errors=(pair[2],)))
  target=report["pairs"][2]
  self.assertEqual(target["high_seq_2_status"],[3,3])
  self.assertEqual(target["high_seq_2_data"],[None,None])
  self.assertFalse(target["both_devices_successful_and_stable"])
  self.assertFalse(target["two_repeat_AB_BA_exactly_equal"])
  self.assertFalse(report["all_five_pairs_repeated_exactly_equal"])

 def test_fail_closed_before_first_test_if_wrong_identity_or_guards(self):
  seen=[]
  def wrong_id(cmd):
   seen.append(cmd)
   return f"{cmd} <- openv/resp: 1;0xf8;1111111111111111"
  with self.assertRaises(m.Refused):m.capture(wrong_id)
  self.assertEqual(seen,[m.ID])
  seen=[]
  def wrong_guard(cmd):
   seen.append(cmd)
   return fixture(bad_guard=True)(cmd)
  with self.assertRaises(m.Refused):m.capture(wrong_guard)
  self.assertEqual(seen,[m.ID,m.CONTROLS[0]])


if __name__=="__main__":unittest.main()
