"""SHA-attested cross-era 32-byte RX last-CRC / first-meta correlation."""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"tools/wb2a-vitotrol-fused-rx-crossarchive.py"
spec=importlib.util.spec_from_file_location("wb2a_vt_fused_cross_tests",SRC)
m=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=m
spec.loader.exec_module(m)
CAPTURE=Path("/tmp/wb2a-vitotrol-fused-rx-live-20261011.json")
ARCHIVE=Path("/root/p300-trial-work/research-bundles/p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz")


class CrossArchiveTests(unittest.TestCase):
    def test_two_addresses_differ_but_same_32byte_copy(self):
        common=bytes.fromhex("c6")+bytes(30)+b"\x06"
        rare=bytes.fromhex("53")+bytes(30)+b"\x0a"
        a={rare.hex():[64],(bytes.fromhex("d8")+bytes(30)+b"\x06").hex():list(range(1,64))}
        r=m.compare_windows(a,[common]*15+[rare])
        self.assertEqual(r["live_total_32byte_samples"],16)
        self.assertEqual(r["live_unique_patterns"],2)
        self.assertEqual(r["identical_32byte_archive_and_live_patterns"][0]["archive_snapshot_ids"],[64])
        self.assertEqual(r["live_pattern_differences"][0]["different_addresses_from_modal_live"],
                         ["0x164b","0x166a"])
        self.assertTrue(r["two_bytes_in_one_copy_not_full_uart_ISR_atomicity"])

    def test_wrong_window_len_rejected(self):
        with self.assertRaises(m.InvalidEvidence):
            m.compare_windows({"00"*32:[1]},[b"\x00"*31])
        with self.assertRaises(m.InvalidEvidence):
            m.compare_windows({},[bytes(32)])

    def test_capture_provenance_rejected(self):
        with self.assertRaises(m.InvalidEvidence):
            m.run(b"not a valid original",b"not an archive")

    def test_original_evidence_when_authorized(self):
        try:
            capture=CAPTURE.read_bytes()
            historic=ARCHIVE.read_bytes()
        except (FileNotFoundError,PermissionError):
            self.skipTest("private original ROM research evidence unavailable")
        r=m.run(capture,historic)
        self.assertEqual(r["historical_rare_image"],64)
        self.assertEqual(r["historic_rare_crc_valid_frame"],"0001b10a010100004353")
        self.assertEqual(r["historic_rare_meta_triple"],"0a0401")
        self.assertEqual(r["old_complete_images"],79)
        self.assertEqual(len(r["crosscheck"]["identical_32byte_archive_and_live_patterns"]),1)
        self.assertEqual(r["crosscheck"]["identical_32byte_archive_and_live_patterns"][0]["live_count"],1)
        self.assertFalse(r["sample_causality_or_interrupt_state_proven"])
        self.assertEqual(r["controller_writes"],0)


if __name__=="__main__":unittest.main()
