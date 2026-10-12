"""Strict offline ROM-copy tuple null model with artificial controls."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import unittest

SRC = Path(__file__).resolve().parents[1] / "tools" / "wb2a-romcopy-nullmodel-original.py"
sp = importlib.util.spec_from_file_location("romcopy_nullmodel_archived", SRC)
m = importlib.util.module_from_spec(sp)
sys.modules[sp.name] = m
sp.loader.exec_module(m)


def example_images() -> list[bytes]:
    first = bytearray(b"\x55" * m.IMAGE_SIZE)
    pos = 0x1DE5 - m.BASE
    first[pos:pos + 8] = (
        bytes.fromhex("ab a2 0e 01 33 00 1d 00")
    )
    pos = 0x1E6A - m.BASE
    first[pos:pos + 8] = bytes.fromhex("05 07 00 7d b2 0f 07 00")
    return [bytes(first)] * m.IMAGE_COUNT


class NullModelTests(unittest.TestCase):
    def test_expected_source_archive_signature(self):
        self.assertEqual(m.ARCHIVE_SIZE, 8404258)
        self.assertEqual(len(m.ARCHIVE_SHA256), 64)
        self.assertEqual(m.IMAGE_SIZE, 20480)
        self.assertEqual(m.IMAGE_COUNT, 79)

    def test_oracle_on_artificial_79_identical_snapshots(self):
        images = example_images()
        self.assertEqual(m.stable_mask(images), bytes([1])*m.IMAGE_SIZE)
        hits = m.scan_for_shape(images[0], m.stable_mask(images))
        self.assertEqual(hits, m.EXACT_EXPECTED)

    def test_real_far_value_cannot_be_used_as_only_evidence(self):
        images = example_images()
        result = m.null_model(images, seeds=m.CONTROL_SEEDS[:5])
        self.assertEqual(result["candidate_count"], 2)
        self.assertEqual(result["rom_program_bytes_extracted"], 0)
        self.assertFalse(result["any_program_rom_copy_safely_triggerable_proven"])
        self.assertTrue(result["posthoc_selection_invalidates_formal_p_value"])

    def test_one_changed_tuple_byte_excludes_candidate(self):
        images = example_images()
        changed = bytearray(images[2])
        changed[0x1DE5 - m.BASE] ^= 1
        images[2] = bytes(changed)
        mask = m.stable_mask(images)
        found = m.scan_for_shape(images[0], mask)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0], m.EXACT_EXPECTED[1])
        with self.assertRaises(m.InvalidArchiveOrHypothesis):
            m.null_model(images, seeds=m.CONTROL_SEEDS[:5])

    def test_synthetic_same_shuffle_across_79_observations(self):
        a = example_images()
        source = a[0]
        mask = m.stable_mask(a)
        b,c = m.shuffle_with_correlated_stability(source, mask, m.CONTROL_SEEDS[0])
        self.assertEqual(sorted(b), sorted(source))
        self.assertEqual(sum(c), sum(mask))
        self.assertEqual(len(b), m.IMAGE_SIZE)

    def test_forged_control_seed_rejected(self):
        source = example_images()[0]
        with self.assertRaises(m.InvalidArchiveOrHypothesis):
            m.shuffle_with_correlated_stability(
                source, bytes([1])*m.IMAGE_SIZE, 100)

    def test_invalid_stability_mask_rejected(self):
        source = example_images()[0]
        with self.assertRaises(m.InvalidArchiveOrHypothesis):
            m.scan_for_shape(source, bytes([2])*m.IMAGE_SIZE)

    def test_excessive_count_wont_qualify_as_copy(self):
        images = example_images()
        first = bytearray(images[0])
        at = 0x1DE5 - m.BASE
        first[at+6:at+8] = (33).to_bytes(2,"little")
        x = m.scan_for_shape(bytes(first), bytes([1])*m.IMAGE_SIZE)
        self.assertEqual(len(x), 1)
        self.assertEqual(x[0], m.EXACT_EXPECTED[1])

    def test_incorrect_source_high_region_rejected(self):
        images = example_images()
        first = bytearray(images[0])
        at = 0x1DE5 - m.BASE
        first[at:at+3] = (0x023456).to_bytes(3,"little")
        x = m.scan_for_shape(bytes(first), bytes([1])*m.IMAGE_SIZE)
        self.assertEqual(len(x), 1)

    def test_unexpected_image_count_rejected(self):
        with self.assertRaises(m.InvalidArchiveOrHypothesis):
            m.stable_mask(example_images()[:-1])

    def test_incorrect_image_length_rejected(self):
        with self.assertRaises(m.InvalidArchiveOrHypothesis):
            m.stable_mask([b"\x00"]*m.IMAGE_COUNT)

    def test_bounded_archive_rejects_fake_image(self):
        with self.assertRaises(m.InvalidArchiveOrHypothesis):
            m.attested_images(b"fake-gzip")

    def test_archive_sha_mismatch_is_rejected(self):
        fake=bytearray(b"0" * m.ARCHIVE_SIZE)
        with self.assertRaises(m.InvalidArchiveOrHypothesis):
            m.attested_images(bytes(fake))

    def test_all_original_sha_members_if_accessible(self):
        path = Path("/root/p300-trial-work/research-bundles/p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz")
        if not os.access(path, os.R_OK):
            self.skipTest("Private original root-owned P300 archive only on LXC")
        images = m.attested_images(path.read_bytes())
        r = m.null_model(images)
        self.assertEqual(r["audit"], "PASS")
        self.assertEqual(r["stable_bytes"], 18955)
        self.assertEqual(r["byte_permutation_control_count"], 300)
        self.assertEqual(r["byte_permutation_control_histogram"], {0:249,1:48,2:3})
        self.assertEqual(r["controls_with_at_least_real_count"], 3)
        self.assertEqual(r["candidate_count"], 2)
        self.assertEqual(r["rom_program_bytes_extracted"], 0)
        self.assertFalse(r["actual_rom_source_dereferenced"])

    def test_original_invalidated_byte_rejected_if_accessible(self):
        path = Path("/root/p300-trial-work/research-bundles/p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz")
        if not os.access(path, os.R_OK):
            self.skipTest("Private original root-owned P300 archive only on LXC")
        fake = bytearray(path.read_bytes())
        fake[-15] ^= 0x01
        with self.assertRaises(m.InvalidArchiveOrHypothesis):
            m.attested_images(bytes(fake))

    def test_no_controller_or_process_execution(self):
        src = SRC.read_text()
        for text in ("subprocess.run(", "os.system(", "/dev/tty",
                     "serial.Serial(", "socket.socket(", "systemctl stop",
                     "systemctl start", "writeraw;", "flash_erase"):
            self.assertNotIn(text,src)


if __name__ == "__main__":
    unittest.main()
