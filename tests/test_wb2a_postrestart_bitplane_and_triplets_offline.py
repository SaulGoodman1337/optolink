"""Adversarial offline tests for the authenticated real P300 restart contrast."""
from __future__ import annotations

import hashlib
import importlib.util
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SRC=Path(__file__).resolve().parents[1]/"tools"/"wb2a-postrestart-bitplane-and-triplets-offline.py"
spec=importlib.util.spec_from_file_location("postrestart_triplets_reader_offline",SRC)
m=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=m
spec.loader.exec_module(m)


def synthetic():
    old=bytes([0]*m.FRAME)
    new=bytearray(old)
    for i,mask in zip(m.KNOWN_DIFF_OFFSETS,m.KNOWN_MASKS):
        new[i]^=mask
    return old,bytes(new)


class TripletOfflineControls(unittest.TestCase):
    def test_known_source_constants_and_no_hardware(self):
        self.assertEqual(m.KNOWN_DIFF_OFFSETS,(4,6,9,12,21,24,27))
        self.assertEqual(m.KNOWN_MASKS,(0x80,0x10,0x40,0x40,0x80,0x80,0x24))
        self.assertEqual(m.FRAME,30)
        self.assertEqual(m.BASE_ADDR,0x3301)
        self.assertEqual(m.PERIODS,(2,3,4,5,6,7,8))
        self.assertEqual(len(m.FAULT_SOURCES),4)

    def test_seven_changes_are_eight_flipped_bits(self):
        old,new=synthetic()
        r=m.bitplane_report(old,new)
        self.assertEqual(r["changed_byte_count"],7)
        self.assertEqual(r["total_flipped_bits"],8)
        self.assertEqual(r["unchanged_byte_count"],23)
        self.assertEqual(r["bit_plane_counts"],
            {"0":0,"1":0,"2":1,"3":0,"4":1,"5":1,"6":2,"7":3})

    def test_three_byte_record_boundary(self):
        old,new=synthetic()
        r=m.bitplane_report(old,new)
        self.assertEqual(r["complete_24bit_triplets_from_0x3301"],10)
        self.assertEqual(r["hypothetical_copy_descriptor_count_bytes"],29)
        self.assertTrue(r["30byte_triplet_frame_exceeds_hypothetical_29byte_copy_by_one_byte"])
        self.assertEqual(r["changed_triplets"],7)
        self.assertEqual(r["changed_triplets_with_multiple_byte_changes"],0)
        self.assertTrue(r["all_third_bytes_unchanged"])
        self.assertEqual(r["changed_byte_positions_mod3"],{0:6,1:1})
        self.assertFalse(r["three_byte_record_schema_proven"])

    def test_triple_deltas_preserve_individual_bit_offsets(self):
        old,new=synthetic()
        r=m.bitplane_report(old,new)
        expected={1:32768,2:16,3:64,4:64,7:128,8:128,9:36}
        actual={x["record"]:x["least_significant_word_delta"]
                for x in r["triplets"] if x["changed_byte_positions"]}
        self.assertEqual(actual,expected)
        self.assertEqual(r["p300_observed_program_ROM_bytes"],0)

    def test_fake_another_modified_byte_rejected(self):
        old,new=synthetic()
        b=bytearray(new);b[3]=2
        with self.assertRaises(m.BadSource):m.bitplane_report(old,bytes(b))

    def test_fake_xor_bit_rejected(self):
        old,new=synthetic()
        b=bytearray(new);b[6]^=0x40
        with self.assertRaises(m.BadSource):m.bitplane_report(old,bytes(b))

    def test_truncated_capture_rejected(self):
        old,new=synthetic()
        with self.assertRaises(m.BadSource):m.bitplane_report(old,new[:29])
        with self.assertRaises(m.BadSource):m.bitplane_report(old[:29],new)

    def test_exact_fixed_stride3_tail(self):
        r=m.residue_statistics(m.KNOWN_DIFF_OFFSETS)
        self.assertEqual(r["period_2_through_8_phase_counts"]["3"][0]["hits"],6)
        self.assertAlmostEqual(
            r["fixed_period3_6of7_any_phase_exact_tail_fraction"],
            12960/math.comb(30,7),places=8)
        self.assertAlmostEqual(
            m.exact_hypergeom_tail(30,10,7,6),
            (math.comb(10,6)*math.comb(20,1)+math.comb(10,7))/math.comb(30,7),
            places=11)

    def test_stride2_to8_selection_includes_multiple_testing(self):
        r=m.residue_statistics(m.KNOWN_DIFF_OFFSETS)
        self.assertEqual(r["best_posthoc_unadjusted_single_phase"]["period"],3)
        self.assertEqual(r["best_posthoc_unadjusted_single_phase"]["phase"],0)
        self.assertLess(r["best_posthoc_unadjusted_single_phase"]["tail_fraction"],0.01)
        self.assertTrue(r["fixed_period3_6of7_any_phase_fraction_is_posthoc_descriptive"])

    def test_permutation_reproducibility(self):
        a=m.multiscan_permutation(m.KNOWN_DIFF_OFFSETS,500)
        b=m.multiscan_permutation(m.KNOWN_DIFF_OFFSETS,500)
        self.assertEqual(a,b)
        self.assertEqual(a["permutations"],500)
        self.assertTrue(a["source_selected_after_observing_candidate"])
        self.assertFalse(a["formal_independent_p_value"])
        self.assertGreater(a["scan_adjusted_descriptive_tail_fraction"],0)

    def test_permutation_out_of_budget_rejected(self):
        with self.assertRaises(m.BadSource):
            m.multiscan_permutation(m.KNOWN_DIFF_OFFSETS,499)
        with self.assertRaises(m.BadSource):
            m.multiscan_permutation(m.KNOWN_DIFF_OFFSETS,100001)

    def test_changed_positions_duplicate_and_oob_rejected(self):
        for seq in ((4,4,6,9,12,21,24),(4,-1,6,9,12,21,24),
                    (4,6,9,12,21,24,30),()):
            with self.assertRaises(m.BadSource):m.residue_statistics(seq)

    def test_changed_positions_wrong_type_rejected(self):
        with self.assertRaises(m.BadSource):
            m.residue_statistics([4,6,9,12,21,24,27])
        with self.assertRaises(m.BadSource):
            m.residue_statistics(m.KNOWN_DIFF_OFFSETS,length=29)

    def test_hypergeometric_input_invalid_rejected(self):
        for args in ((30,31,7,6),(30,10,-1,6),(30,10,7,-1),
                     (30,10,31,6)):
            with self.assertRaises(m.BadSource):
                m.exact_hypergeom_tail(*args)

    def test_hypergeometric_full_domain(self):
        self.assertEqual(m.exact_hypergeom_tail(30,30,7,7),1)
        self.assertEqual(m.exact_hypergeom_tail(30,0,7,1),0)
        self.assertEqual(m.exact_hypergeom_tail(30,10,7,0),1)

    def test_file_sha_provenance_modified_rejected(self):
        with tempfile.TemporaryDirectory(prefix="wb2a-triplet-src-") as folder:
            p=Path(folder)/"data.json"
            data=b"x"*135
            p.write_bytes(data)
            with self.assertRaises(m.BadSource):
                m.source_read(p,hashlib.sha256(b"x"*134+b"y").hexdigest(),100,200)
            self.assertEqual(m.source_read(p,hashlib.sha256(data).hexdigest(),100,200),data)

    def test_file_symlink_rejected(self):
        with tempfile.TemporaryDirectory(prefix="wb2a-triplet-src-") as folder:
            f=Path(folder)/"original";f.write_bytes(b"x"*130)
            p=Path(folder)/"alias";p.symlink_to(f)
            with self.assertRaises(m.BadSource):
                m.source_read(p,hashlib.sha256(f.read_bytes()).hexdigest(),100,200)

    def test_original_79_sample_size_guards(self):
        with self.assertRaises(m.BadSource):
            m.historic_spatial_control([bytes(20480)]*78)
        with self.assertRaises(m.BadSource):
            m.historic_spatial_control([bytes(200)]*79)

    def test_historical_change_cohort_empty(self):
        originals=[bytes(20480)]*79
        r=m.historic_spatial_control(originals)
        self.assertEqual(r["30byte_overlapping_window_pair_comparisons"],78*(20480-30+1))
        self.assertEqual(r["historical_windows_with_exactly_seven_changed_bytes"],0)
        self.assertEqual(r["historical_windows_with_seven_changes_and_six_at_stride3"],0)

    def test_historical_synthetic_period3_cohort_detected(self):
        originals=[bytes(20480)]*79
        new=bytearray(originals[0])
        for i in m.KNOWN_DIFF_OFFSETS:new[500+i]=1
        originals[21]=bytes(new)
        r=m.historic_spatial_control(originals)
        self.assertGreater(r["historical_windows_with_exactly_seven_changed_bytes"],0)
        self.assertGreater(r["historical_windows_with_seven_changes_and_six_at_stride3"],0)

    def test_original_host_alias_gate_accepts_exact_seven_events(self):
        rows=[{"ID":name,"Address":addr,"BlockLength":str(n),
               "FCRead":"Virtual_READ"}
              for name,addr,n in m.HOST_ALIAS_EXPECTED]
        r=m.parse_host_virtual_alias_rows(rows)
        self.assertEqual(r["WB2A_host_Virtual_READ_event_count_in_numeric_range"],7)
        self.assertFalse(r["host_virtual_0x330x_addresses_equal_P300_FC03_physical_RAM_proven"])
        self.assertFalse(r["main_ROM_origin_discovered"])
        self.assertEqual(sorted(x["length"] for x in r["host_Virtual_READ_events"]),[1,1,1,1,1,8,8])

    def test_mutated_host_virtual_opcode_rejected(self):
        rows=[{"ID":name,"Address":addr,"BlockLength":str(n),
               "FCRead":"Virtual_READ"}
              for name,addr,n in m.HOST_ALIAS_EXPECTED]
        rows[0]["FCRead"]="Physical_READ"
        with self.assertRaises(m.BadSource):m.parse_host_virtual_alias_rows(rows)

    def test_mutated_host_alias_length_rejected(self):
        rows=[{"ID":name,"Address":addr,"BlockLength":str(n),
               "FCRead":"Virtual_READ"}
              for name,addr,n in m.HOST_ALIAS_EXPECTED]
        rows[0]["BlockLength"]="29"
        with self.assertRaises(m.BadSource):m.parse_host_virtual_alias_rows(rows)

    def test_no_virtual_alias_deduced_from_same_numeric_address(self):
        rows=[{"ID":name,"Address":addr,"BlockLength":str(n),
               "FCRead":"Virtual_READ"}
              for name,addr,n in m.HOST_ALIAS_EXPECTED]
        rows.append({"ID":"only_outside","Address":"0x3321","BlockLength":"1",
                     "FCRead":"Virtual_READ"})
        r=m.parse_host_virtual_alias_rows(rows)
        self.assertEqual(len(r["host_Virtual_READ_events"]),7)
        rows[-1]["Address"]="0x330f"
        with self.assertRaises(m.BadSource):m.parse_host_virtual_alias_rows(rows)

    def test_not_an_optolink_live_utility(self):
        text=SRC.read_text(encoding="utf-8")
        for forbidden in ("serial.Serial(", "socket.socket(", "systemctl stop",
                          "systemd-run", "subprocess.run(", "request;3;",
                          "flash_write", "DMA1_ENABLE"):
            self.assertNotIn(forbidden,text)

    def test_all_original_sources_pinned(self):
        self.assertEqual(len(m.FAULT_SOURCES),4)
        self.assertTrue(all(len(sha)==64 for _,sha in m.FAULT_SOURCES.values()))
        self.assertEqual(m.CONTROL_COUNT,100000)


class PinnedPrivateRealityCheck(unittest.TestCase):
    def test_sha_attested_oct9_oct11_oct12_and_fault_archives(self):
        paths=[m.OLD,m.NEW,m.GATE]
        paths.extend(m.EVENT_DIR/name for name,_ in m.FAULT_SOURCES.values())
        try:
            available=all(p.is_file() and os.access(p,os.R_OK) for p in paths)
        except (PermissionError,OSError):
            available=False
        if not available:
            self.skipTest("Private original P300/fault files unavailable to unprivileged CI")
        # Exact originals crossvalidated, but keep CI/lightweight runtime
        # bounded to 800 randomized controls and skip 78-image spatial scan.
        result=m.audit(m.OLD,m.NEW,m.EVENT_DIR,m.EVENT_DIR,permutations=800,history=False)
        self.assertEqual(result["audit"],"PASS")
        self.assertEqual(result["oct9_complete_original_images"],79)
        self.assertEqual(result["oct11_independent_A_target_reads"],4)
        self.assertEqual(result["oct12_new_A_target_reads"],2)
        self.assertEqual(result["bitplane"]["total_flipped_bits"],8)
        self.assertEqual(result["bitplane"]["possible_direct_high_ROM_LITTLE_ENDIAN_values"],0)
        self.assertTrue(result["A_source_pointer_unchanged_from_Oct9_to_Oct12"])
        self.assertEqual(result["verified_program_ROM_bytes"],0)
        self.assertTrue(result["safety_original_complete_archives"]["all_original_fault_archives_sha256_passed"])


if __name__=="__main__":
    unittest.main()
