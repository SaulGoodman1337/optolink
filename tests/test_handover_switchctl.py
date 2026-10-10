"""Machine-readable operational switch controller, fake supervisor only."""
from __future__ import annotations
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from handover_acceleration import switchctl


class ReadonlySwitchControlTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base=Path(tmp.name)
        self.session=self.base/"run-inprocess-20261010T080000Z-111"
        self.session.mkdir()
        self.boot={
            "status": "PASS_VERIFIED_BORROWED_PORT_FIXED_FC03",
            "phase_count": 1, "identity_hex": "20c2",
            "ram_0f20_32_hex": "ab"*32,
            "ram_1c60_32_hex": "cd"*32,
            "gfa_p80_hex": "20", "gfa_p06_hex": "53",
            "verified_vs1_return": True,
            "no_second_serial_open": True,
            "no_device_write": True,
            "time_ms": {"p300_and_vs1": 4902.278},
        }
        self.summary={
            "result": "PASS_VERIFIED_INPROCESS_FIXED_FC03",
            "unit_rc": 0, "boot_record_verified": True,
            "worker_verified": True, "services_restored": True,
            "production_splitter_running": True,
            "production_health": {
                "P80": {"valid": True, "response": "1;0x4050;20"},
                "P06": {"valid": True, "response": "1;0x4006;53"},
            },
            "worker_errors": [],
        }
        self.recovery={
            "services_restored": True, "overall_verified": True,
            "independent_link_restore": {"attempted":True, "verified":True},
        }
        self.write_reports()
        base_patch=patch.object(switchctl.hybrid_acceptance, "BASE", self.base)
        base_patch.start()
        self.addCleanup(base_patch.stop)

    def write_reports(self):
        for name, data in (("hybrid-result.json",self.boot),
                           ("hybrid-summary.json",self.summary),
                           ("recovery.json",self.recovery)):
            (self.session/name).write_text(json.dumps(data))

    def run_fake(self, *, returncode=0, stdout=None):
        if stdout is None:
            stdout="HYBRID_STAGED_PREFLIGHT=PASS\nHYBRID_SESSION="+str(self.session)+"\n"
        response=subprocess.CompletedProcess(
            ["python"], returncode, stdout=stdout, stderr="")
        with patch.object(switchctl.os,"geteuid",return_value=0), \
             patch.object(switchctl.subprocess,"run",return_value=response) as ran:
            result=switchctl.switch_once()
        self.assertEqual(ran.call_count,1)
        argv=ran.call_args.args[0]
        self.assertEqual(argv[-2:],["--execute","--accept-telemetry-pause"])
        self.assertIn("hybrid_acceptance.py",argv[2])
        return result

    def test_success_is_full_verified_data_after_independent_restore(self):
        outcome=self.run_fake()
        self.assertEqual(outcome["status"],"PASS_VERIFIED_READONLY_SWITCH")
        self.assertTrue(outcome["verified"])
        self.assertTrue(outcome["vs1_restored"])
        self.assertTrue(outcome["services_restored"])
        self.assertEqual(outcome["vs1"],{"P80":"20","P06":"53"})
        self.assertEqual(outcome["p300"]["identity_hex"],"20c2")
        self.assertEqual(outcome["time_ms"]["p300_and_vs1"],4902.278)

    def test_failed_supervisor_exit_cannot_publish_success(self):
        outcome=self.run_fake(returncode=1)
        self.assertEqual(outcome["status"],"FAIL_OR_NOT_VERIFIED")
        self.assertFalse(outcome["verified"])
        self.assertIsNone(outcome["p300"])

    def test_independent_recovery_missing_or_failed_refuses_success(self):
        for value in (False,None):
            with self.subTest(value=value):
                self.recovery["independent_link_restore"]["verified"]=value
                self.write_reports()
                self.assertFalse(self.run_fake()["verified"])

    def test_stale_gfa_and_fake_p300_payload_refuse_success(self):
        self.summary["production_health"]["P06"]["valid"]=False
        self.write_reports()
        self.assertFalse(self.run_fake()["verified"])
        self.summary["production_health"]["P06"]["valid"]=True
        self.boot["ram_0f20_32_hex"]="12"
        self.write_reports()
        self.assertFalse(self.run_fake()["verified"])

    def test_missing_session_or_extra_lines_refused(self):
        for stdout in ("", "HYBRID_SESSION=../../fake\n",
                       ("HYBRID_SESSION="+str(self.session)+"\n") * 2):
            with self.subTest(stdout=stdout):
                result=self.run_fake(stdout=stdout)
                self.assertEqual(result["status"],"NO_VERIFIED_SESSION")
                self.assertFalse(result["verified"])

    def test_nonroot_and_wrong_acceptance_script_are_rejected(self):
        with patch.object(switchctl.os,"geteuid",return_value=1000):
            with self.assertRaisesRegex(switchctl.SwitchctlRejected,"root"):
                switchctl.switch_once()
        with patch.object(switchctl.os,"geteuid",return_value=0):
            with self.assertRaisesRegex(switchctl.SwitchctlRejected,"unreviewed"):
                switchctl.switch_once(cli_file=self.base/"arbitrary.py")

    def test_timeout_reports_no_proven_recovery(self):
        with patch.object(switchctl.os,"geteuid",return_value=0), \
             patch.object(switchctl.subprocess,"run",
                          side_effect=subprocess.TimeoutExpired("test",240)):
            report=switchctl.switch_once()
        self.assertFalse(report["verified"])
        self.assertEqual(report["status"],"NOT_VERIFIED_TIMEOUT")

    def test_read_only_status_reports_real_unit_states_without_opening_port(self):
        fake=types.SimpleNamespace(
            base=types.SimpleNamespace(
                MAIN="optolink-splitter.service",
                unit_state=lambda name:{"ActiveState":"active",
                                        "SubState":"running"}),
            read_health=lambda:{"P80":{"valid":True}, "P06":{"valid":True}},
        )
        with patch.object(switchctl.hybrid_acceptance,"_live",return_value=fake):
            status=switchctl.inspect_status()
        self.assertEqual(status["status"],"HEALTHY_READONLY_STATUS")
        self.assertTrue(status["healthy"])
        self.assertTrue(status["gfa"]["P80"]["valid"])
        self.assertEqual(status["units"]["optolink-splitter.service"]["active"],
                         "active")

    def test_cli_requires_explicit_telemetry_pause(self):
        with self.assertRaisesRegex(switchctl.SwitchctlRejected,
                                    "--accept-telemetry-pause"):
            switchctl.main(["snapshot"])


if __name__ == "__main__":
    unittest.main()
