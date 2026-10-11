"""Regression for SHA-attested static far-source/low-RAM copy-looking pairs."""
from __future__ import annotations
import ast
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "tools" / "wb2a-vitotrol-rom-copy-candidates-offline.py"
spec = importlib.util.spec_from_file_location("wb2a_vitotrol_copy_offline_tests", P)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)

ARCHIVE = Path("/root/p300-trial-work/research-bundles/p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz")


def image():
    b=bytearray(m.SIZE)
    b[0x1DE5-m.BASE:0x1DED-m.BASE] = bytes.fromhex("aba20e0133001d00")
    b[0x1E6A-m.BASE:0x1E72-m.BASE] = bytes.fromhex("0507007db20f0700")
    b[0x3301-m.BASE:0x3301-m.BASE+29] = bytes(range(29))
    b[0x0705-m.BASE:0x0705-m.BASE+7] = bytes.fromhex("64646464646464")
    return bytes(b)


class CopyCandidatesOfflineTests(unittest.TestCase):
    def test_fixed_20bit_pattern_and_static_targets(self):
        r=m.inspect([image()]*3)
        a=r["candidate_findings"]["A_1de5_to_3301_29"]
        b=r["candidate_findings"]["B_1e6a_to_0705_7"]
        self.assertEqual((a["raw_source_20bit"],a["dest_low_ram"],a["count"]),
                         ("0xea2ab","0x3301",29))
        self.assertEqual((b["raw_source_20bit"],b["dest_low_ram"],b["count"]),
                         ("0xfb27d","0x0705",7))
        self.assertEqual(b["target_all_bytes_64_samples"],3)
        self.assertEqual(a["target_all_bytes_64_samples"],0)
        self.assertEqual(b["neighbor_window_different_count"],1)
        self.assertTrue(a["matches_previous_reported_tuple"])
        self.assertFalse(r["any_verified_controller_copy_service"])
        self.assertFalse(r["any_rom_contents_acquired"])

    def test_candidate_target_is_not_proof_of_copy(self):
        x=bytearray(image())
        x[0x3301-m.BASE] ^= 1
        r=m.inspect([image(),bytes(x)])
        c=r["candidate_findings"]["A_1de5_to_3301_29"]
        self.assertEqual(c["target_contents_distinct"],2)
        self.assertFalse(c["controller_side_copy_operation_proven"])

    def test_adjacent_task_state_can_vary_independently(self):
        x=bytearray(image())
        x[0x1E62-m.BASE] = 0x77
        r=m.inspect([image(),bytes(x)])
        a=r["candidate_findings"]["A_1de5_to_3301_29"]
        b=r["candidate_findings"]["B_1e6a_to_0705_7"]
        self.assertEqual(b["neighbor_window_different_count"],2)
        self.assertEqual(a["neighbor_window_different_count"],1)
        self.assertEqual(b["different_tuple_count"],1)

    def test_source_is_candidate_not_confirmed_code(self):
        x=bytearray(image())
        x[0x1DE5-m.BASE:0x1DE8-m.BASE]=(0x00123).to_bytes(3,"little")
        r=m.inspect([image(),bytes(x)])
        a=r["candidate_findings"]["A_1de5_to_3301_29"]
        self.assertEqual(a["different_tuple_count"],2)
        self.assertTrue(a["source_in_assumed_program_rom"])
        self.assertFalse(a["data_prove_rom_copy"])

    def test_invalid_size_type_count_target(self):
        with self.assertRaises(m.InvalidEvidence):m.inspect([])
        with self.assertRaises(m.InvalidEvidence):m.inspect([bytearray(image())])
        with self.assertRaises(m.InvalidEvidence):m.inspect([image()[:1024]])
        with self.assertRaises(m.InvalidEvidence):m.inspect([image()]*80)
        x=bytearray(image())
        x[0x1DE8-m.BASE:0x1DEB-m.BASE]=(0x80000).to_bytes(3,"little")
        with self.assertRaises(m.InvalidEvidence):m.inspect([bytes(x)])
        with self.assertRaises(m.InvalidEvidence):m.from_manifest_attested_tar(b"bad data")

    def test_archive_sha_recheck_when_available(self):
        try:
            original = ARCHIVE.read_bytes()
        except (FileNotFoundError, PermissionError):
            self.skipTest("private original archive unavailable to current user")
        r=m.from_manifest_attested_tar(original)
        self.assertEqual(r["samples"],79)
        self.assertEqual(r["source_archive_sha256"],m.ARCHIVE_SHA256)
        self.assertTrue(r["manifest_sha256s_all_verified"])
        for name in m.CANDIDATES:
            rec=r["candidate_findings"][name]
            self.assertEqual(rec["modal_tuple_occurrences"],79)
            self.assertEqual(rec["different_tuple_count"],1)
            self.assertEqual(rec["target_contents_distinct"],1)
        self.assertEqual(r["candidate_findings"]["B_1e6a_to_0705_7"]["target_all_bytes_64_samples"],79)
        self.assertEqual(r["candidate_findings"]["B_1e6a_to_0705_7"]["neighbor_window_different_count"],75)
        self.assertFalse(r["any_verified_controller_copy_service"])

    def test_no_transport_or_controller_write_dependencies(self):
        tree=ast.parse(P.read_text())
        imports=set()
        for n in ast.walk(tree):
            if isinstance(n,ast.Import):
                imports.update(a.name.split(".")[0] for a in n.names)
            if isinstance(n,ast.ImportFrom) and n.module:
                imports.add(n.module.split(".")[0])
        self.assertFalse(imports & {"serial","subprocess","socket","paho","requests"})
        self.assertFalse(m.inspect([image()])["live_io_requested"])


if __name__=="__main__":
    unittest.main()
