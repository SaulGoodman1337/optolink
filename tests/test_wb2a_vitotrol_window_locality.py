"""Purely synthetic regression cases for historic, non-atomic SRAM window comparisons."""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import sys
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / "tools" /
          "wb2a-vitotrol-optolink-rx-context.py")
spec = importlib.util.spec_from_file_location("vitotrol_locality_test", SOURCE)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def fixture_images():
    a = bytearray(20480)
    a[0x0B6D-0x400:0x0B6D-0x400+4] = bytes.fromhex("42160afe")
    a[0x33A3-0x400:0x33A3-0x400+4] = bytes.fromhex("42161c6a")
    b = bytearray(a)
    b[0x0B6D-0x400-2] = 7
    b[0x0B6D-0x400+26] = 8
    b[0x161A-0x400] = 9
    return bytes(a), bytes(b)


class SramWindowLocalityTests(unittest.TestCase):
    def test_distinguishes_dynamic_neighborhood_from_stable_literal(self):
        a, b = fixture_images()
        report = module.window_locality([a, b])
        w = report["windows"]
        self.assertEqual(w["0x0b6d"]["distinct_64byte_windows"], 2)
        self.assertEqual(w["0x0b6d"]["varying_byte_positions"], 2)
        self.assertEqual(w["0x0b6d"]["varying_offsets_from_center"], [-2, 26])
        self.assertEqual(w["0x0b6d"]["varying_positions_near_center_8"], 1)
        self.assertEqual(w["0x0b6d"]["same_four_anchor_bytes_samples"], 2)
        self.assertEqual(w["0x0b6d"]["literal_0x1642_present_samples"], 2)
        self.assertEqual(w["0x33a3"]["distinct_64byte_windows"], 1)
        self.assertEqual(w["0x33a3"]["varying_byte_positions"], 0)
        self.assertEqual(w["0x33a3"]["literal_0x1642_present_samples"], 2)
        self.assertEqual(w["0x161a"]["distinct_64byte_windows"], 2)
        self.assertEqual(w["0x161a"]["varying_byte_positions"], 1)
        self.assertFalse(report["candidate_pointer_or_parser_verified"])
        self.assertTrue(report["no_new_hardware_io"])

    def test_rejects_empty_partial_mutable_and_oversized_images(self):
        a, b = fixture_images()
        for images in ([], [bytearray(a)], [b""], [a[:-1]],
                       [a]*80, [True], "unsupported"):
            with self.subTest(kind=str(type(images)), size=len(images)):
                with self.assertRaises(module.audit.EvidenceRejected):
                    module.window_locality(images)

    def test_control_comparison_does_not_pretend_parser_or_vector_evidence(self):
        a, b = fixture_images()
        r = module.window_locality([a,b])
        self.assertIn("NONATOMIC", r["scope"])
        self.assertFalse(r["candidate_pointer_or_parser_verified"])
        self.assertEqual(module.WINDOW_CENTERS, (0x0B6D,0x33A3,0x161A))
        tree=ast.parse(SOURCE.read_text())
        names=set()
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):
                names.update(alias.name.split(".")[0] for alias in node.names)
            if isinstance(node,ast.ImportFrom) and node.module:
                names.add(node.module.split(".")[0])
        self.assertFalse(names & {"serial","socket","paho","subprocess",
                                  "ctypes","paramiko","requests"})

    def test_candidate_descriptor_matches_two_rx_lengths_not_a_proven_pointer(self):
        base,_=fixture_images()
        a=bytearray(base)
        b=bytearray(base)
        first=bytes.fromhex('0001b10a010110fe23d8')
        rare=bytes.fromhex('0001b10a010100004353')
        a[0x1642-0x400:0x1642-0x400+10]=first
        b[0x1642-0x400:0x1642-0x400+10]=rare
        a[0x0b6b-0x400]=1
        b[0x0b6b-0x400]=10
        r=module.window_locality([bytes(a),bytes(b)])
        e=r['descriptor_0b6d_hypothesis']
        self.assertEqual(e['candidate_raw_four_byte_counts'],{'42160afe':2})
        self.assertEqual(e['candidate_le16_and_third_byte_match_rx_length_samples'],2)
        self.assertEqual(e['sample_count'],2)
        self.assertEqual(e['descriptor_and_crc_frame_counts'],{
            '42160afe|'+first.hex():1, '42160afe|'+rare.hex():1})
        self.assertFalse(e['candidate_type_or_firmware_owner_verified'])
        self.assertFalse(e['rx_isr_and_state_commit_verified'])
        self.assertFalse(e['controller_write_authorized'])

    def test_tampered_descriptor_length_not_promoted_to_controller_rx(self):
        raw,_=fixture_images()
        v=bytearray(raw)
        v[0x1642-0x400:0x1642-0x400+10]=bytes.fromhex('0001b10a010110fe23d8')
        v[0x0b6f-0x400]=11  # incorrect length for even a valid B1
        report=module.window_locality([bytes(v)])
        e=report['descriptor_0b6d_hypothesis']
        self.assertEqual(e['candidate_le16_and_third_byte_match_rx_length_samples'],0)
        self.assertFalse(e['candidate_type_or_firmware_owner_verified'])
        self.assertFalse(e['controller_write_authorized'])

    def test_descriptor_rx_contingency_is_descriptive_not_causal(self):
        base, _ = fixture_images()
        descriptor_offset = 0x0B6B - 0x0400
        rx_offset = 0x1642 - 0x0400
        usual = bytes.fromhex("0001b10a010110fe")
        rare = bytes.fromhex("0001b10a01010000")
        images = []
        for flag, frame in ((1, usual), (10, usual),
                            (11, usual), (1, rare)):
            snapshot = bytearray(base)
            snapshot[descriptor_offset] = flag
            snapshot[rx_offset:rx_offset+8] = frame
            images.append(bytes(snapshot))
        report = module.window_locality(images)
        paired = report["non_atomic_candidate_rx_sample_counts"]
        self.assertEqual(paired["descriptor_minus2_address"], "0x0b6b")
        self.assertEqual(paired["rx_prefix_address"], "0x1642")
        self.assertEqual(paired["rx_prefix_bytes"], 8)
        self.assertEqual(paired["descriptor_minus2_counts"],
                         {"01": 2, "0a": 1, "0b": 1})
        self.assertEqual(paired["rx_prefix_counts"],
                         {usual.hex(): 3, rare.hex(): 1})
        self.assertEqual(paired["paired_counts"], {
            "01|" + usual.hex(): 1,
            "01|" + rare.hex(): 1,
            "0a|" + usual.hex(): 1,
            "0b|" + usual.hex(): 1,
        })
        self.assertFalse(paired["sampling_order_and_causality_proven"])
        self.assertFalse(report["candidate_pointer_or_parser_verified"])
        self.assertTrue(report["no_new_hardware_io"])


if __name__ == "__main__":
    unittest.main()
