"""Original 2010/2018/2026 KM-Bus evidence; independent of MCU identity."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import subprocess
import unittest

SOURCE=Path(__file__).resolve().parents[1]/"tools/wb2a-vitotrol-kw2-crossgeneration-wire-audit.py"
spec=importlib.util.spec_from_file_location("vt_kw2_crossgen_replay_test",SOURCE)
m=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=m;spec.loader.exec_module(m)
V300=Path("/tmp/wb2a-vitotrol-public-sources-20261010/original-vitotrol300-log.zip")
WB2A=Path("/tmp/wb2a-vitotrol-natural-event-live-20261011.json")


class Tests(unittest.TestCase):
    def test_all_reference_crcs_valid_and_declared_length(self):
        rows=(
            m.MASTER_WIKI_CLASS11_SLOT3,m.MASTER_WIKI_CLASS01_SLOT1,
            m.MASTER_SLOT1_DERIVED,m.WB2A_REAL_MASTER,m.WB2A_REAL_RX_CLASS01,
            m.V300_REAL_ID,m.V300_REAL_B1,m.V300_REAL_PONG)
        for row in rows:
            with self.subTest(frame=row.hex()):
                self.assertEqual(m.crc16(row),0)
                self.assertEqual(row[3],len(row))
        self.assertEqual(m.MASTER_WIKI_CLASS11_SLOT3[4],3)
        self.assertEqual(m.MASTER_SLOT1_DERIVED[4],1)

    def test_slot1_derived_from_old_wiki_slot3_no_new_wire_test(self):
        wiki=m.MASTER_WIKI_CLASS11_SLOT3
        no_crc=wiki[:4]+b"\x01"+wiki[5:8]
        new=no_crc+m.crc16(no_crc).to_bytes(2,"little")
        self.assertEqual(new.hex(),"1100330a0101f80449ef")
        self.assertNotEqual(new,m.MASTER_WIKI_CLASS11_SLOT3)
        self.assertEqual(new,m.MASTER_SLOT1_DERIVED)

    def test_distinct_200kw2_vs_v300_original_ids_are_expected(self):
        self.assertEqual(m.V300_REAL_ID[2],0xb3)
        self.assertEqual(bytes(m.V300_REAL_ID[i] for i in (7,9,11,13)),
                         bytes.fromhex("1138010a"))
        self.assertEqual(m.WB2A_REAL_RX_CLASS01[1],1)
        self.assertEqual(m.V300_REAL_ID[1],0x11)

    def test_refuse_unpinned_or_tampered_sources(self):
        with self.assertRaises(m.EvidenceRejected):
            m.check_karlkoch_source(b"a dummy wiki")
        with self.assertRaises(m.EvidenceRejected):
            m.check_v300(b"bad ZIP")
        with self.assertRaises(m.EvidenceRejected):
            m.check_wb2a_event(b"fake json")
        with self.assertRaises(m.EvidenceRejected):
            m.verify_all(b"bad",b"bad",b"bad")

    def test_real_2010_wiki_2018_vitotrol_2026_wb2a_sources(self):
        try:
            src=m.wiki_2010_source()
            remote=V300.read_bytes()
            device=WB2A.read_bytes()
        except (FileNotFoundError,PermissionError,subprocess.CalledProcessError):
            self.skipTest("2010 git wiki or original research captures not on this machine")
        result=m.verify_all(src,remote,device)
        self.assertTrue(result["common_classes_slots_idformats_and_opcode_grammar_supported"])
        self.assertTrue(result["CRC16_KERMIT_full_frame_remainder_zero_for_all_reference_frames"])
        self.assertEqual(result["2018_real_V300"]["CRC_valid_uninterrupted_slave_frames"],448)
        self.assertEqual(result["2010_openv"]["KM_class11_slots"],[1,2,3])
        self.assertEqual(result["2010_openv"]["KM_class11_ids"],[0x34,0x38])
        self.assertEqual(result["slot1_class11_master_discovery_derived_only"],
                         "1100330a0101f80449ef")
        self.assertEqual(result["2026_WB2A_controller"]["real_WB2A_native_master_31_00"],
                         "0100310901010027fa")
        self.assertFalse(result["WB2A_ROM_reader_callable_proven"])
        self.assertFalse(result["old_2010_optolink_ROM_transfer_exact_command_known"])
        self.assertFalse(result["WB2A_Vitotrol_enrollment_proven"])
        self.assertTrue(result["off_line_no_new_controller_reads_or_writes"])


if __name__=="__main__":unittest.main()
