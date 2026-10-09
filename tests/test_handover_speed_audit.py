"""Hardware-free checks of the archived trace analyzer and workload counterfactuals."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
import io
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from handover_acceleration.speed_audit import (
    EvidenceError, analyze_measurement, batch_savings, simulate_current_queue, main)


def evidence():
    return {
        "experiment_pass": True, "vs1_link_restored": True, "errors": [],
        "phases_ms": {
            "cold_setup": 4365.844,
            "vs1_to_p300_with_verified_identity": 2175.657,
            "p300_to_vs1_fast_with_verified_gfa": 2295.102,
            "remaining_gfa_block_p09_p87": 195.532,
            "roundtrip_with_gfa": 4666.291,
        },
        "enq_trace": [
            {"name": "cold_vs1_setup", "enq_wait_ms": [1801.262, 4039.479]},
            {"name": "vs1_to_p300", "enq_wait_ms": [2010.961]},
            {"name": "p300_to_vs1", "enq_wait_ms": [1998.460]},
        ]
    }


class MeasuredSpeedOpportunityTests(unittest.TestCase):
    def test_reproduce_real_enq_and_non_enq_budget(self):
        result = analyze_measurement(evidence())
        self.assertAlmostEqual(result["two_enq_waits_total_ms"], 4009.421)
        self.assertAlmostEqual(result["non_enq_total_ms_including_controller_and_line"], 656.870)
        self.assertAlmostEqual(result["cold_second_enq_additional_ms"], 2238.217)
        self.assertFalse(result["software_only_under_4s_by_same_handshake"])

    def test_service_time_is_separate_from_measured_handover(self):
        result = analyze_measurement(evidence(), service_runtime_ms=13607.0)
        timeline = result["supervisor_timeline_ms"]
        self.assertAlmostEqual(timeline["other_runtime_ms_not_attributed"], 4574.865)
        self.assertAlmostEqual(timeline["measured_pre_roundtrip_cold_setup_ms"], 4365.844)

    def test_2_1_s_p06_freshness_incompatible_with_this_full_switch(self):
        result = analyze_measurement(evidence(), p06_max_age_ms=2100.0)
        self.assertFalse(result["p06_freshness_example"]["compatible_with_observed_roundtrip"])

    def test_no_error_shown_as_unverified_run(self):
        e=evidence(); e["experiment_pass"] = False
        self.assertFalse(analyze_measurement(e)["historical_measurement"]["experiment_pass"])

    def test_refuse_missing_and_wrong_order_enq(self):
        for variant in range(3):
            e=evidence()
            if variant==0: e["enq_trace"].pop()
            if variant==1: e["enq_trace"][2]["name"]="wrong"
            if variant==2: e["enq_trace"][0]["enq_wait_ms"][1]=1500
            with self.subTest(variant=variant), self.assertRaises(EvidenceError):
                analyze_measurement(e)

    def test_refuse_inconsistent_budget(self):
        e=evidence();e["phases_ms"]["roundtrip_with_gfa"]=100
        with self.assertRaises(EvidenceError): analyze_measurement(e)

    def test_refuse_boolean_nan_inf_and_negative_timings(self):
        for v in (False,float("nan"),float("inf"),-2):
            e=evidence();e["phases_ms"]["cold_setup"]=v
            with self.subTest(v=v),self.assertRaises(EvidenceError):analyze_measurement(e)

    def test_fairness_can_create_three_windows(self):
        r=simulate_current_queue(12,12,max_same_mode=4)
        self.assertEqual(r["p300_windows_current_fairness"],3)
        self.assertEqual(r["protocol_transitions_including_final_vs1"],6)
        self.assertEqual(r["minimum_p300_windows_if_independent_and_deadline_compatible"],1)
        self.assertEqual(r["mode_runs"],[
            {"mode":"vs1","reads":4}, {"mode":"p300","reads":4},
            {"mode":"vs1","reads":4}, {"mode":"p300","reads":4},
            {"mode":"vs1","reads":4}, {"mode":"p300","reads":4}])

    def test_batching_savings_distinguish_enq_and_profile(self):
        r=batch_savings(4666.291,4009.421,3)
        self.assertEqual(r["avoided_full_roundtrips"],2)
        self.assertAlmostEqual(r["gross_avoided_enq_wait_ms"],8018.842)
        self.assertAlmostEqual(r["gross_avoided_identical_roundtrip_ms"],9332.582)

    def test_ten_roundtrips_are_not_a_sub_four_switch(self):
        r=batch_savings(4666.291,4009.421,10)
        self.assertEqual(r["avoided_full_roundtrips"],9)
        self.assertAlmostEqual(r["gross_avoided_enq_wait_ms"],36084.789)
        self.assertAlmostEqual(r["gross_avoided_identical_roundtrip_ms"],41996.619)

    def test_no_p300_requests_produce_zero_windows(self):
        r=simulate_current_queue(16,0)
        self.assertEqual(r["p300_windows_current_fairness"],0)
        self.assertEqual(r["protocol_transitions_including_final_vs1"],0)

    def test_refuse_unknown_workload_values(self):
        for params in ((-1,3),(2,-1),(0,10001)):
            with self.assertRaises(EvidenceError):simulate_current_queue(*params)
        with self.assertRaises(EvidenceError):simulate_current_queue(2,2,max_same_mode=0)
        with self.assertRaises(EvidenceError):batch_savings(4666.291,4009.421,1,2)

    def test_cli_read_only_and_preserves_original_failed_summary(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)
            (base/"measurement.json").write_text(json.dumps(evidence()))
            (base/"summary.json").write_text(json.dumps({"result":"FAIL_OR_NOT_VERIFIED"}))
            before=(base/"summary.json").read_bytes()
            with redirect_stdout(io.StringIO()) as output:
                rc=main(["--session",d,"--service-runtime-ms","13607",
                         "--p06-max-age-ms","2100"])
            self.assertEqual(rc,0)
            result=json.loads(output.getvalue())
            self.assertEqual(result["original_saved_summary_result"],"FAIL_OR_NOT_VERIFIED")
            self.assertEqual(result["conditional_batched_savings"]["avoided_full_roundtrips"],2)
            self.assertEqual(before,(base/"summary.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
