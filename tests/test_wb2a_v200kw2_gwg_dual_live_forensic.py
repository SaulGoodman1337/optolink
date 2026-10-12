"""Live WB2A original C7/CB/C5 two-window SHA attestation with no new IO."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest

BASE=Path(__file__).resolve().parents[1]
P=BASE/"tools/wb2a-v200kw2-gwg-followup-original-audit.py"
spec=importlib.util.spec_from_file_location("wb2a_gwg_double_live_attested_audit_tests",P)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
FIRST=Path(m.first.ORIGINAL)
SECOND=Path(m.FOLLOWUP_PATH)


class TwoWindows(unittest.TestCase):
    def test_expected_original_digests_and_wire_families(self):
        self.assertEqual(len(m.first.SHA),64)
        self.assertEqual(len(m.FOLLOWUP_SHA),64)
        self.assertEqual(len(m.ROWS),6)
        self.assertEqual(sum(len(v[1]) for v in m.ROWS.values()),8)
        self.assertEqual(m.ROWS["gwg_c7_f8_8bytes"][1],["20c2000300000103"])
        self.assertEqual(m.ROWS["gwg_c7_f9_3bytes"][1],["c20003"])
        for k,(wire,_) in m.ROWS.items():
            with self.subTest(case=k):
                self.assertIn(bytes.fromhex(wire)[1],(0xf7,0xc7,0xcb,0xc5))
                self.assertNotIn(bytes.fromhex(wire)[1],(0xf4,0xc4,0xc8,0xc3,0xad))

    def test_corrupted_or_missing_source_must_fail(self):
        with self.assertRaises(m.first.Refused):
            m.audit(b"{}",b"{}")
        try:first=FIRST.read_bytes()
        except (FileNotFoundError,PermissionError):self.skipTest("root original absent")
        with self.assertRaises(m.Refused):
            m.audit(first,b"{}")
        with self.assertRaises(m.Refused):
            m.audit(first,b"X"*32001)

    def test_original_two_verified_controller_sessions_if_accessible(self):
        try:first=FIRST.read_bytes();second=SECOND.read_bytes()
        except (FileNotFoundError,PermissionError):self.skipTest("private capture originals absent")
        r=m.audit(first,second)
        self.assertEqual(r["original_authenticated_controller_read_requests"],16)
        self.assertTrue(r["former_2010_C7_exact_bytes_reproduced_in_WB2A"])
        self.assertTrue(r["C7_at_F8_8_bytes_matches_KW_VIRTUAL_READ"])
        self.assertTrue(r["C7_at_F9_3_bytes_matches_KW_VIRTUAL_READ"])
        self.assertTrue(r["C7_8bit_virtual_address_space_overlaps_known_KW_00F8"])
        for k in ("legacy_CB_no_response_6F","legacy_C5_no_response_6F",
                  "legacy_CB_no_response_F8","legacy_C5_no_response_F8"):
            self.assertTrue(r[k])
        self.assertFalse(r["unsupported_C5_CB_globally_proven"])
        self.assertFalse(r["ROM_dump_obtained"])
        self.assertEqual(r["controller_writes_in_sources"],0)
        self.assertEqual(r["new_controller_io_for_offline_audit"],0)


if __name__=="__main__":unittest.main()
