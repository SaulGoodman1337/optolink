"""Adversarial offline tests of real GWG dispatcher evidence validation."""
from __future__ import annotations
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

SRC = Path(__file__).resolve().parents[1] / "tools" / "wb2a-gwg-c7-dispatcher-original-audit.py"
spec = importlib.util.spec_from_file_location("wb2a_gwg_c7_original_audit", SRC)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

T0 = "2026-10-12T09:08:28.524002+00:00"
T1 = "2026-10-12T09:08:43.021181+00:00"


def base():
    return {
        "device": "WB2A/VDensHO1 20C2/0103",
        "configuration_sha256": "e9a120ef37fe17236a7505ee713c8dd338d98d5093ed75dfb34629d7e8f5c42d",
        "complete": True, "controller_writes": 0, "at_utc": T0, "ended_utc": T1,
        "requests": [
            {"case": name, "command": cmd, "reply": rx, "status": 1, "elapsed_seconds": 2.01}
            for name, cmd, tx, rx in mod.EXPECTED
        ],
        "raw_uart_events": [
            item
            for name, cmd, tx, rx in mod.EXPECTED
            for item in [
                {"time_utc": T0, "direction": "tx", "bytes": "04"},
                {"time_utc": T0, "direction": "rx", "bytes": "05"},
                {"time_utc": T0, "direction": "tx", "bytes": tx},
                {"time_utc": T0, "direction": "rx", "bytes": rx},
            ]
        ],
    }


def run_case(obj):
    return mod.audit(json.dumps(obj).encode(), pinned=False)


class GWGDispatcherEvidence(unittest.TestCase):
    def test_positive_golden_simulation(self):
        answer = run_case(base())
        self.assertEqual(answer["audit"], "PASS")
        self.assertEqual(answer["tx_frames"], 14)
        self.assertEqual(answer["sync_pairs"], 7)
        self.assertEqual(answer["controller_writes"], 0)

    def test_real_original_capture_optional(self):
        if not mod.CAPTURE.exists() or not mod.CAPTURE.is_file():
            self.skipTest("Root-owned original not present on this host")
        try:
            contents = mod.CAPTURE.read_bytes()
        except PermissionError:
            self.skipTest("Original root-only capture not readable")
        answer = mod.audit(contents, pinned=True)
        self.assertEqual(answer["source_sha256"], mod.ORIGINAL_SHA)

    def test_modified_sha_rejected(self):
        with self.assertRaises(mod.EvidenceRejected):
            mod.audit(json.dumps(base()).encode(), pinned=True)

    def test_controller_write_rejected(self):
        x = base()
        x["controller_writes"] = 1
        with self.assertRaises(mod.EvidenceRejected):
            run_case(x)

    def test_wrong_device_rejected(self):
        x = base()
        x["device"] = "20CB"
        with self.assertRaises(mod.EvidenceRejected):
            run_case(x)

    def test_source_hash_rejected(self):
        x = base()
        x["configuration_sha256"] = "0" * 64
        with self.assertRaises(mod.EvidenceRejected):
            run_case(x)

    def test_failed_acceptance_rejected(self):
        x = base()
        x["complete"] = False
        with self.assertRaises(mod.EvidenceRejected):
            run_case(x)

    def test_bad_dispatcher_data_rejected(self):
        x = base()
        x["requests"][1]["reply"] = "00000000"
        with self.assertRaises(mod.EvidenceRejected):
            run_case(x)

    def test_bad_dispatcher_status_rejected(self):
        x = base()
        x["requests"][1]["status"] = 0xFF
        with self.assertRaises(mod.EvidenceRejected):
            run_case(x)

    def test_wrong_command_rejected(self):
        x = base()
        x["requests"][1]["command"] = "gwgwrite;0xF8;4"
        with self.assertRaises(mod.EvidenceRejected):
            run_case(x)

    def test_extra_tx_rejected(self):
        x = base()
        x["raw_uart_events"].append({"time_utc": T1, "direction": "tx", "bytes": "01c8f80104"})
        with self.assertRaises(mod.EvidenceRejected):
            run_case(x)

    def test_tx_order_rejected(self):
        x = base()
        x["raw_uart_events"][2]["bytes"] = "01c7f80404"
        with self.assertRaises(mod.EvidenceRejected):
            run_case(x)

    def test_missing_enq_rejected(self):
        x = base()
        del x["raw_uart_events"][1]
        with self.assertRaises(mod.EvidenceRejected):
            run_case(x)

    def test_duplicate_enq_rejected(self):
        x = base()
        x["raw_uart_events"].insert(1, copy.deepcopy(x["raw_uart_events"][1]))
        with self.assertRaises(mod.EvidenceRejected):
            run_case(x)

    def test_rx_evidence_mismatch_rejected(self):
        x = base()
        x["raw_uart_events"][3]["bytes"] = "20c20000"
        with self.assertRaises(mod.EvidenceRejected):
            run_case(x)

    def test_unexpected_trace_event_rejected(self):
        x = base()
        x["raw_uart_events"][2]["direction"] = "bogus"
        with self.assertRaises(mod.EvidenceRejected):
            run_case(x)

    def test_missing_read_rejected(self):
        x = base()
        x["requests"].pop()
        with self.assertRaises(mod.EvidenceRejected):
            run_case(x)

    def test_unbounded_duration_rejected(self):
        x = base()
        x["ended_utc"] = "2026-10-12T09:15:00+00:00"
        with self.assertRaises(mod.EvidenceRejected):
            run_case(x)

    def test_bad_hex_rejected(self):
        x = base()
        x["raw_uart_events"][3]["bytes"] = "20zz"
        with self.assertRaises(mod.EvidenceRejected):
            run_case(x)

    def test_invalid_json_rejected(self):
        with self.assertRaises(mod.EvidenceRejected):
            mod.audit(b"not-json")

    def test_otp_no_controller_write_in_read_modes(self):
        assert len(mod.EXPECTED) == 7
        self.assertTrue(all(bytes.fromhex(frame)[1] in (0xC7, 0xF7)
                            for _, _, frame, _ in mod.EXPECTED))
        self.assertTrue(all(frame in mod.EXPECTED_TX for _, _, frame, _ in mod.EXPECTED))


if __name__ == "__main__":
    unittest.main()
