"""Manually requested single-window canary; immutable systemd recovery."""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from handover_acceleration import continuous_canary as c


class ManualCanaryTests(unittest.TestCase):
    def setUp(self):
        td=tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root=Path(td.name)
        self.session=self.root/"run-20261010T210000Z-333"
        self.session.mkdir()
        self.release=self.root/"release"
        self.release.mkdir()
        self.extra=self.root/"manual.conf"
        self.data={
            "release":str(self.release),
            "canary_profile":"demand-manual",
            "phase":"RUNNING_SHADOW_NO_AUTO",
            "before":{unit:"active" for unit in c.sh.ALL},
        }
        self.event={
            "canary_session":self.session.name,
            "status":"VERIFIED_SWITCH",
            "vs1_p80":"20","vs1_p06":"00",
            "elapsed_ms":5350.0,
            "p300_fixed":{"p300_ram_0f20_32":"aa"*32},
            "on_demand_raw":[{
                "sequence":1,"kind":"p300_ram_0f20_32",
                "raw_hex":"aa"*32,
                "origin":"P300_RAW_DIAGNOSTIC_NOT_ACTUAL_RPM"
            }],
        }

    def test_profile_is_one_session_and_bounded(self):
        count,watch,deadline,result=c.profile_limits("demand-manual")
        self.assertEqual(count,1)
        self.assertLessEqual(watch,150)
        self.assertLessEqual(deadline,240)
        self.assertEqual(result,"PASS_ONE_VERIFIED_DEMAND_WINDOW")
        self.assertGreater(deadline,watch)

    def test_manual_overlay_root_sock_without_auto_ticket(self):
        dropin=c._extra_content(self.session,demand_manual=True)
        self.assertIn("fenced-ondemand",dropin)
        self.assertIn("OPTO_HYBRID_DEMAND_SOCKET=",dropin)
        self.assertIn("RuntimeDirectory=optolink-hybrid",dropin)
        self.assertIn("RuntimeDirectoryMode=0700",dropin)
        self.assertNotIn("DEMAND_SELFTEST",dropin)
        self.assertIn(self.session.name,dropin)
        for bad in (
            {"demand_one":True,"demand_manual":True},
            {"demand_manual":"yes"},
        ):
            with self.assertRaises(c.ContinuousCanaryRejected):
                c._extra_content(self.session,**bad)

    def test_canary_selftest_keeps_exact_one_startup_ticket(self):
        dropin=c._extra_content(self.session,demand_one=True)
        self.assertIn("DEMAND_SELFTEST=ram_0f20_32",dropin)
        self.assertIn("OPTO_HYBRID_DEMAND_SOCKET=",dropin)

    def test_manual_evidence_is_strictly_same_raw_and_return(self):
        line="HYBRID_RUNTIME_VERIFIED_SWITCH "+json.dumps(self.event)
        with patch.object(c.subprocess,"run",return_value=subprocess.CompletedProcess(
                [],0,line,"")):
            events,_=c._collect_events(self.session,33,profile="demand-manual")
        self.assertEqual(events,[self.event])
        changed=json.loads(json.dumps(self.event))
        changed["on_demand_raw"][0]["raw_hex"]="bb"*32
        with patch.object(c.subprocess,"run",return_value=subprocess.CompletedProcess(
                [],0,"HYBRID_RUNTIME_VERIFIED_SWITCH "+json.dumps(changed),"")):
            with self.assertRaises(c.ContinuousCanaryRejected):
                c._collect_events(self.session,33,profile="demand-manual")

    def _worker(self, events):
        self.extra.unlink(missing_ok=True)
        def save(path,record):
            path.write_text(json.dumps(record))
        def status(unit):
            return "inactive" if unit=="optolink-pump-override.service" else "active"
        def call(argv,*a,**kw):
            if "--property=MainPID" in argv:
                return "123"
            return ""
        with patch.object(c.sh,"load",return_value=self.data),\
             patch.object(c.sh,"worker",return_value=0),\
             patch.object(c.sh,"save",side_effect=save),\
             patch.object(c,"_write_enrollment",return_value=None),\
             patch.object(c,"verify_enrollment",
                          return_value=SimpleNamespace(accepted=True)),\
             patch.object(c,"_extra_path",return_value=self.extra),\
             patch.object(c.sh,"call",side_effect=call),\
             patch.object(c.sh,"status",side_effect=status),\
             patch.object(c.sh,"gfa",return_value={"P80":"20","P06":"00"}),\
             patch.object(c,"_collect_events",return_value=(events,[])),\
             patch.object(c,"verify_live_canary_epoch",return_value=None),\
             patch.object(c.os,"geteuid",return_value=0),\
             patch.object(c.os,"chown",return_value=None),\
             patch.object(c.time,"sleep",return_value=None) as sleepers,\
             patch.dict(c.os.environ,{"INVOCATION_ID":"test-unit"}):
            if len(events)!=1:
                with self.assertRaises(c.ContinuousCanaryRejected):
                    c.worker(self.session)
            else:
                self.assertEqual(c.worker(self.session),0)
        return sleepers

    def test_manual_worker_grants_bounded_result_collection_grace(self):
        sleeps=self._worker([self.event])
        self.assertEqual(sleeps.call_count,4)
        measurement=json.loads((self.session/"continuous-measurement.json").read_text())
        self.assertEqual(measurement["event_count"],1)
        self.assertEqual(measurement["result"],"PASS_ONE_VERIFIED_DEMAND_WINDOW")
        self.assertIn("RuntimeDirectoryMode=0700",self.extra.read_text())
        self.assertNotIn("DEMAND_SELFTEST",self.extra.read_text())

    def test_multiple_physical_windows_are_not_accepted_as_one(self):
        self._worker([self.event,self.event])
        measurement=json.loads((self.session/"continuous-measurement.json").read_text())
        self.assertEqual(measurement["event_count"],2)
        self.assertEqual(measurement["result"],"NO_VERIFIED_CONTINUOUS_WINDOWS")

    def test_recovery_requires_exact_manual_overlay_and_runs_original(self):
        self.extra.write_text(c._extra_content(self.session,demand_manual=True))
        original=[]
        with patch.object(c.sh,"load",return_value=self.data),\
             patch.object(c,"_extra_path",return_value=self.extra),\
             patch.object(c,"MANIFEST_PATH",self.root/"not-present"),\
             patch.object(c.sh,"recover",side_effect=lambda _:original.append(1) or 0):
            self.assertEqual(c.recover(self.session),0)
        self.assertEqual(original,[1])
        self.assertFalse(self.extra.exists())

    def test_parser_disallows_unapproved_or_mixed_manual_profile(self):
        with self.assertRaises(c.ContinuousCanaryRejected):
            c.main(["--launch",str(self.root),"--demand-manual"])
        with self.assertRaises(c.ContinuousCanaryRejected):
            c.main(["--plan",str(self.root),"--demand-manual"])
        with self.assertRaises(c.ContinuousCanaryRejected):
            c.main(["--launch",str(self.root),"--accept-telemetry-pause",
                    "--demand-one","--demand-manual"])


if __name__=="__main__":
    unittest.main()
