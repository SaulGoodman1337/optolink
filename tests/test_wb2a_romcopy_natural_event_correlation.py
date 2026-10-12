"""Adversarial and source-attested checks for the historical burner-correlation."""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SRC=Path(__file__).resolve().parents[1] / "tools/wb2a-romcopy-natural-event-correlation.py"
sp=importlib.util.spec_from_file_location("wb2a_natural_burner_context",SRC)
m=importlib.util.module_from_spec(sp)
sys.modules[sp.name]=m
sp.loader.exec_module(m)


def synthetic_images():
    base=m.original.BASE
    a=bytearray(b"\x00"*m.original.IMAGE_SIZE)
    # Emulate the exact two fields using fake contents NOT from the controller.
    a[0x1DE5-base:0x1DE5-base+8]=bytes.fromhex("ab a2 0e 01 33 00 1d 00")
    a[0x1E6A-base:0x1E6A-base+8]=bytes.fromhex("05 07 00 7d b2 0f 07 00")
    a[0x06DF-base:0x0875-base+1]=bytes([0x64])*407
    a[0x3301-base:0x3301-base+29]=bytes(range(1,30))
    return [bytes(a)]*m.original.IMAGE_COUNT


def synthetic_metadata(images):
    out=[]
    for i,b in enumerate(images):
        kind=("STABLE_BRACKET_OFF" if i<48 else
              ("STABLE_BRACKET_RUNNING" if i<59 else
               "TRANSITION_OR_UNKNOWN"))
        out.append({
            "marker":"COMPLETE","complete":True,
            "device_id":"20c2","software":"0103",
            "atomic_ram_image":False,
            "snapshot_id":i+1,
            "classification":kind,
            "flame_seen":i>=48 and i<59,
            "flame_transition_seen":i>=59 and i<67,
            "direction":"ascending" if i%2==0 else "descending",
            "sha256":hashlib.sha256(b).hexdigest(),
        })
    return out


class NaturalEventsTests(unittest.TestCase):
    def test_exact_occurrences_include_overlaps(self):
        self.assertEqual(m.exact_occurrences(b"AAAAAA",b"AAA"),4)
        self.assertEqual(m.exact_occurrences(b"xyxxxy",b"xy"),2)

    def test_exact_occurrences_empty_pattern_rejected(self):
        with self.assertRaises(m.FalseProvenance):
            m.exact_occurrences(b"abc",b"")

    def test_invalid_cpu_read_bounds_rejected(self):
        with self.assertRaises(m.FalseProvenance):
            m.get(synthetic_images()[0],0x03FF,1)

    def test_synthetic_realistic_phase_strata_but_no_ROM_proof(self):
        b=synthetic_images()
        with patch.object(m,"SHUFFLE_SEEDS",m.SHUFFLE_SEEDS[:3]):
            r=m.classify(b,synthetic_metadata(b))
        self.assertEqual(r["phase_sample_counts"],{
            "STABLE_BRACKET_OFF":48,
            "STABLE_BRACKET_RUNNING":11,
            "TRANSITION_OR_UNKNOWN":20,
        })
        self.assertEqual(r["flame_seen_image_count"],11)
        self.assertEqual(r["flame_transition_seen_image_count"],8)
        self.assertEqual(r["candidate_fields"]["A"]["tuple_variants"],1)
        self.assertEqual(r["candidate_fields"]["B"]["target_variants"],1)
        self.assertEqual(r["candidate_fields"]["B"]["containing_filler_run_length"],407)
        self.assertEqual(r["candidate_fields"]["A"]["control_shuffles_29byte_payload_unique"],0)
        # A synthetic all-zero-heavy image is not a representative shuffled control.
        # The real high-entropy image test separately fixes 300/300 uniqueness.
        self.assertEqual(r["verified_program_ROM_bytes"],0)
        self.assertFalse(r["any_ROM_copy_service_proven"])

    def test_original_A_target_is_only_a_ram_byte_pattern(self):
        b=synthetic_images()[0]
        target=m.get(b,0x3301,29)
        self.assertEqual(target,bytes(range(1,30)))
        self.assertEqual(m.exact_occurrences(b,target),1)
        # Having a unique RAM value cannot reveal which ROM offset created it.
        self.assertFalse(hasattr(m, "dereference_rom_pointer"))

    def test_missing_images_rejected(self):
        b=synthetic_images()
        with self.assertRaises(m.FalseProvenance):
            m.classify(b[:-1],synthetic_metadata(b)[:-1])

    def test_one_target_byte_mutation_rejected(self):
        b=synthetic_images()
        one=bytearray(b[5])
        one[0x3301-m.original.BASE] ^= 1
        b[5]=bytes(one)
        with patch.object(m,"SHUFFLE_SEEDS",m.SHUFFLE_SEEDS[:1]):
            with self.assertRaises(m.FalseProvenance):
                m.classify(b,synthetic_metadata(b))

    def test_invalid_phase_label_rejected(self):
        b=synthetic_images();meta=synthetic_metadata(b)
        meta[0]["classification"]="VERY_STABLE_RUNNING"
        with self.assertRaises(m.FalseProvenance):
            m.classify(b,meta)

    def test_false_running_flag_as_string_rejected(self):
        b=synthetic_images();meta=synthetic_metadata(b)
        meta[0]["flame_seen"]="False"
        with self.assertRaises(m.FalseProvenance):
            m.classify(b,meta)

    def test_swapped_snapshot_metadata_rejected(self):
        b=synthetic_images();meta=synthetic_metadata(b)
        meta[1]["snapshot_id"]=1
        with self.assertRaises(m.FalseProvenance):
            m.classify(b,meta)

    def test_changed_digest_rejected(self):
        b=synthetic_images();meta=synthetic_metadata(b)
        meta[2]["sha256"]="0"*64
        with self.assertRaises(m.FalseProvenance):
            m.classify(b,meta)

    def test_malformed_atomic_claim_rejected(self):
        b=synthetic_images();meta=synthetic_metadata(b)
        meta[0]["atomic_ram_image"]=True
        with self.assertRaises(m.FalseProvenance):
            m.classify(b,meta)

    def test_source_literal_width_exact(self):
        b=synthetic_images()[0]
        for label,c in m.CANDIDATES.items():
            a=c["source_value"]
            self.assertEqual(m.exact_occurrences(b,a.to_bytes(3,"little")),1)
            self.assertEqual(m.exact_occurrences(b,a.to_bytes(4,"little")),0)

    def test_original_source_and_classes_if_present(self):
        p=Path("/root/p300-trial-work/research-bundles/p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz")
        if not os.access(p,os.R_OK):
            self.skipTest("original root-owned controller archive not on CI")
        r=m.study_original_archive(p.read_bytes())
        self.assertEqual(r["audit"],"PASS")
        self.assertEqual(r["stable_byte_positions"],18955)
        self.assertEqual(r["flame_seen_image_count"],26)
        self.assertEqual(r["flame_transition_seen_image_count"],8)
        self.assertEqual(r["phase_sample_counts"],{
            "STABLE_BRACKET_OFF":48,"STABLE_BRACKET_RUNNING":11,
            "TRANSITION_OR_UNKNOWN":20})
        self.assertEqual(r["candidate_fields"]["B"]["containing_filler_run_length"],407)
        self.assertEqual(r["candidate_fields"]["B"]["seven_byte_pattern_occurrences_overlapping"],1296)
        self.assertEqual(r["candidate_fields"]["B"]["neighborhood_consecutive_changes"],78)
        self.assertEqual(r["candidate_fields"]["A"]["fully_stable_29byte_windows"],16697)
        self.assertEqual(r["candidate_fields"]["A"]["stable_29byte_windows_whose_payload_is_unique"],14427)
        self.assertEqual(r["candidate_fields"]["A"]["control_shuffles_29byte_payload_unique"],300)
        self.assertEqual(r["verified_program_ROM_bytes"],0)

    def test_source_code_cannot_query_controller(self):
        source=SRC.read_text()
        for forbidden in ("subprocess.run(", "os.system(", "serial.Serial(",
                          "/dev/tty", "systemctl start", "systemctl stop",
                          "socket.socket(", "flash_erase", "writeraw;"):
            self.assertNotIn(forbidden,source)


if __name__=="__main__":
    unittest.main()
