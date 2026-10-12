"""Mutation and provenance tests for source-locked GWG legacy read-type capture."""
from __future__ import annotations
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

SRC = Path(__file__).resolve().parents[1] / "tools" / "wb2a-gwg-legacy-readtypes-original-audit.py"
spec = importlib.util.spec_from_file_location("wb2a_gwg_legacy_readtypes_audit", SRC)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

T0 = "2026-10-12T09:18:24.000000+00:00"
T1 = "2026-10-12T09:18:42.000000+00:00"


def original_like():
    return {
        "mode": "GWG_2053_READ_OPCODE_COMPARISON_ON_WB2A",
        "device": "WB2A VDensHO1 20C2/0103",
        "at_utc": T0, "ended_utc": T1,
        "controller_memory_writes": 0, "completed": True,
        "records": [
            {
                "case": name, "frame": tx, "reply": rx, "outcome": outcome,
                "requested_length": int(tx[8:10], 16) if tx.startswith("01f7")
                                    else int(tx[6:8], 16),
                "sync": True, "time_utc": T0,
                "raw_tx": ["04", tx],
                "raw_rx": ["05"] + ([rx] if rx else []),
            }
            for name, tx, rx, outcome in mod.EXPECTED
        ],
    }


def analyze(obj):
    return mod.analyze(json.dumps(obj).encode(), pin=False)


class LegacyReadTypeProvenance(unittest.TestCase):
    def test_successful_golden_fixture(self):
        result = analyze(original_like())
        self.assertEqual(result["audit"], "PASS")
        self.assertEqual(result["reads"], 8)
        self.assertEqual(result["synchronized_frames"], 8)
        self.assertEqual(result["port_6e_01_hex_replies"], ["00", "00"])
        self.assertEqual(result["eeprom_ae_17_responses"], 0)
        self.assertEqual(result["program_rom_bytes_read"], 0)
        self.assertFalse(result["physical_port_semantics_proven"])

    def test_real_original_root_optional(self):
        try:
            data = mod.CAPTURE.read_bytes()
        except (PermissionError, FileNotFoundError):
            self.skipTest("Original root-only evidence not readable on this runner")
        self.assertEqual(mod.analyze(data, pin=True)["source_sha256"], mod.ORIGINAL_SHA)

    def test_pinning_rejects_synthetic(self):
        with self.assertRaises(mod.AuditRejected):
            mod.analyze(json.dumps(original_like()).encode(), pin=True)

    def test_wrong_controller(self):
        d = original_like()
        d["device"] = "2053"
        with self.assertRaises(mod.AuditRejected): analyze(d)

    def test_memory_write_rejected(self):
        d = original_like()
        d["controller_memory_writes"] = 1
        with self.assertRaises(mod.AuditRejected): analyze(d)

    def test_error_flag_rejected(self):
        d = original_like()
        d["error"] = "transport_failure"
        with self.assertRaises(mod.AuditRejected): analyze(d)

    def test_incomplete_capture_rejected(self):
        d = original_like()
        d["completed"] = False
        with self.assertRaises(mod.AuditRejected): analyze(d)

    def test_fabricated_port_value_rejected(self):
        d = original_like()
        d["records"][3]["reply"] = "01"
        with self.assertRaises(mod.AuditRejected): analyze(d)

    def test_fabricated_eeprom_response_rejected(self):
        d = original_like()
        d["records"][2]["reply"] = "0011"
        with self.assertRaises(mod.AuditRejected): analyze(d)

    def test_raw_reply_tampering_rejected(self):
        d = original_like()
        d["records"][4]["raw_rx"][1] = "ee"
        with self.assertRaises(mod.AuditRejected): analyze(d)

    def test_missing_enq_rejected(self):
        d = original_like()
        d["records"][6]["raw_rx"] = ["20c20003"]
        with self.assertRaises(mod.AuditRejected): analyze(d)

    def test_missing_eot_rejected(self):
        d = original_like()
        d["records"][0]["raw_tx"] = [d["records"][0]["frame"]]
        with self.assertRaises(mod.AuditRejected): analyze(d)

    def test_unknown_write_frame_rejected(self):
        d = original_like()
        d["records"][3]["frame"] = "016d010104"
        with self.assertRaises(mod.AuditRejected): analyze(d)

    def test_unexpected_response_length_rejected(self):
        d = original_like()
        d["records"][2]["requested_length"] = 5
        with self.assertRaises(mod.AuditRejected): analyze(d)

    def test_partial_collection_rejected(self):
        d = original_like()
        d["records"].pop()
        with self.assertRaises(mod.AuditRejected): analyze(d)

    def test_swapped_order_rejected(self):
        d = original_like()
        d["records"][3], d["records"][4] = d["records"][4], d["records"][3]
        with self.assertRaises(mod.AuditRejected): analyze(d)

    def test_duration_gate(self):
        d = original_like()
        d["ended_utc"] = "2026-10-12T09:24:00+00:00"
        with self.assertRaises(mod.AuditRejected): analyze(d)

    def test_invalid_json(self):
        with self.assertRaises(mod.AuditRejected):
            mod.analyze(b"\x00NO", pin=False)

    def test_no_unknown_legacy_types(self):
        self.assertEqual([x[1] for x in mod.EXPECTED if x[1].startswith("01ae")],
                         ["01ae170204", "01ae170204"])
        self.assertEqual([x[1] for x in mod.EXPECTED if x[1].startswith("016e")],
                         ["016e010104", "016e010104"])


if __name__ == "__main__":
    unittest.main()
