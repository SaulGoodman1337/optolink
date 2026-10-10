"""Supervised one-window hardware profile: admission and independent evidence."""
from __future__ import annotations
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from handover_acceleration import continuous_canary as c


class DemandCanaryTests(unittest.TestCase):
    def setUp(self):
        td=tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root=Path(td.name)
        self.session=self.root/"run-20261010T120000Z-111"
        self.session.mkdir()
        self.event={
            "canary_session":self.session.name,
            "status":"VERIFIED_SWITCH",
            "vs1_p80":"20","vs1_p06":"00","elapsed_ms":3300.0,
            "p300_fixed":{"p300_ram_0f20_32":"ab"*32},
            "on_demand_raw":[{
                "sequence":1,"kind":"p300_ram_0f20_32",
                "raw_hex":"ab"*32,
                "origin":"P300_RAW_DIAGNOSTIC_NOT_ACTUAL_RPM"
            }],
        }

    def collect(self,row,*,profile="demand-one"):
        msg="HYBRID_RUNTIME_VERIFIED_SWITCH "+json.dumps(row)+"\n"
        with patch.object(c.subprocess,"run",return_value=subprocess.CompletedProcess(
                [],0,msg,"")):
            return c._collect_events(self.session,1234,profile=profile)

    def test_one_bounded_canary_profile_never_long_soak(self):
        n,watch,maximum,result=c.profile_limits("demand-one")
        self.assertEqual(n,1)
        self.assertLessEqual(watch,120)
        self.assertLessEqual(maximum,240)
        self.assertGreater(maximum,watch)
        self.assertEqual(result,"PASS_ONE_VERIFIED_DEMAND_WINDOW")

    def test_pinned_canary_session_must_enforce_single_allowlisted_read(self):
        content=c._extra_content(self.session,demand_one=True)
        self.assertIn("OPTO_HYBRID_RUNTIME_AUTO=fenced-ondemand",content)
        self.assertIn("OPTO_HYBRID_DEMAND_SELFTEST=ram_0f20_32",content)
        self.assertNotIn("fenced-readonly",content)
        self.assertIn(self.session.name,content)
        with self.assertRaises(c.ContinuousCanaryRejected):
            c._extra_content(self.session,demand_one="yes")

    def test_standard_canary_has_no_injected_demand(self):
        content=c._extra_content(self.session)
        self.assertIn("fenced-readonly",content)
        self.assertNotIn("DEMAND_SELFTEST",content)

    def test_one_request_journal_matches_genuine_vs1_and_raw(self):
        event,refusals=self.collect(self.event)
        self.assertEqual(len(event),1)
        self.assertEqual(refusals,[])
        self.assertEqual(event[0]["on_demand_raw"][0]["raw_hex"],"ab"*32)

    def test_wrong_profile_or_missing_demand_never_counts(self):
        with self.assertRaises(c.ContinuousCanaryRejected):
            self.collect(self.event,profile="standard")
        with self.assertRaises(c.ContinuousCanaryRejected):
            self.collect(self.event,profile="arbitrary")
        row=dict(self.event)
        row.pop("on_demand_raw")
        with self.assertRaises(c.ContinuousCanaryRejected):
            self.collect(row)

    def test_invalid_result_or_p06_blocks_canary_success(self):
        variants=[]
        for field,value in (("vs1_p80","21"),("vs1_p06","ff"),
                            ("elapsed_ms",9001),("canary_session","invalid")):
            row=dict(self.event)
            row[field]=value
            variants.append(row)
        for row in variants[:3]:
            with self.assertRaises(c.ContinuousCanaryRejected):
                self.collect(row)
        self.assertEqual(self.collect(variants[3])[0],[])

    def test_never_misreport_partial_or_forged_raw_as_success(self):
        cases=[]
        row=json.loads(json.dumps(self.event))
        row["on_demand_raw"][0]["raw_hex"]="22"*32
        cases.append(row)
        row=json.loads(json.dumps(self.event))
        row["on_demand_raw"][0]["origin"]="P300_ACTUAL_RPM"
        cases.append(row)
        row=json.loads(json.dumps(self.event))
        row["on_demand_raw"][0]["kind"]="raw;w;0x4006"
        cases.append(row)
        row=json.loads(json.dumps(self.event))
        row["p300_fixed"]["p300_ram_1c60_32"]="00"*32
        cases.append(row)
        row=json.loads(json.dumps(self.event))
        row["on_demand_raw"][0]["sequence"]=True
        cases.append(row)
        for row in cases:
            with self.subTest(row=row),self.assertRaises(c.ContinuousCanaryRejected):
                self.collect(row)

    def test_parser_requires_explicit_pause_ack_even_for_new_profile(self):
        with patch.object(c.sh,"main",return_value=0):
            with self.assertRaises(c.ContinuousCanaryRejected):
                c.main(["--launch",str(self.root), "--demand-one"])
        with self.assertRaises(c.ContinuousCanaryRejected):
            c.main(["--plan",str(self.root),"--demand-one"])


if __name__=="__main__":
    unittest.main()
