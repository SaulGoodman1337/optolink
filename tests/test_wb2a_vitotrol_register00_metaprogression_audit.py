"""CRC provenance, original evidence and early-fail guards for 0A08->0600."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"tools/wb2a-vitotrol-register00-metaprogression-audit.py"
spec=importlib.util.spec_from_file_location("vt_reg00_meta_progress_audit_test",SRC)
m=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=m
spec.loader.exec_module(m)
NEW=Path("/tmp/wb2a-vitotrol-reg00-metaprogress-live-20261011.json")
PREVIOUS=Path("/tmp/wb2a-vitotrol-natural-event-live-20261011.json")
ARCHIVE=Path("/root/p300-trial-work/research-bundles/p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz")


class ProgressAuditTests(unittest.TestCase):
    def test_master_register00_crc_reference(self):
        f=bytes.fromhex(m.CURRENT_MASTER.hex())
        self.assertEqual(m.old.crc.crc16_kermit(f),0)
        self.assertEqual(m.CURRENT_MASTER[6],0)
        self.assertEqual(m.CURRENT_SLAVE[6],0)
        self.assertEqual(m.old.crc.crc16_kermit(m.CURRENT_SLAVE),0)
        self.assertEqual(m.old.crc.crc16_kermit(m.NEXT_SLAVE),0)

    def test_forged_source_rejected(self):
        for blob in (b"",b"not origin",b"{}"):
            with self.subTest(blob=blob[:10]),self.assertRaises(m.InvalidEvidence):
                m.validate_source(blob)

    def test_old_evidence_is_independently_pinned(self):
        self.assertEqual(len(m.NEW_SHA),64)
        self.assertEqual(len(m.old.EVENT_SHA),64)
        self.assertEqual(len(m.old.FULL_SHA),64)
        self.assertNotEqual(m.NEW_SHA,m.old.EVENT_SHA)
        self.assertNotEqual(m.NEW_SHA,m.old.FULL_SHA)

    def test_original_private_three_way_provenance_if_accessible(self):
        try:blobs=[path.read_bytes() for path in (NEW,PREVIOUS,ARCHIVE)]
        except (FileNotFoundError,PermissionError):
            self.skipTest("three original private sources not accessible")
        result=m.combine(*blobs)
        self.assertEqual(result["TX_polls"],199)
        self.assertEqual(result["valid_p300_reads"],221)
        self.assertEqual(result["metadata_sequence_8_individual_copies"],
                         ["0a08"]+["0600"]*7)
        self.assertEqual(result["metadata_first_two_response_end_delta_ms"],229.755)
        self.assertEqual(result["observed_166a166b_special_values_in_separate_sessions"],
                         {"historical_snapshot64":"0a04",
                          "previous_short_event85":"0a07",
                          "new_followup_event198":"0a08"})
        self.assertFalse(result["physical_uart1_rx_ISR_proven"])
        self.assertEqual(result["controller_writes"],0)


if __name__=="__main__":unittest.main()
