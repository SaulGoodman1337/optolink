"""Historical Deep/master31-rare RX attribution tests, strictly offline."""
from __future__ import annotations
import ast
import importlib.util
import sys
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"tools/wb2a-vitotrol-class31-rx-correlation.py"
spec=importlib.util.spec_from_file_location("wb2a_vt_class31_rxcorr",SRC)
m=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=m
spec.loader.exec_module(m)
DEEP=Path("/root/p300-trial-work/research-bundles/p300-deep-run-20261009T070505Z-130246-bundle.tar.gz")
FULL=Path("/root/p300-trial-work/research-bundles/p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz")
FUSED=Path("/tmp/wb2a-vitotrol-fused-rx-live-20261011.json")
BURST=Path("/tmp/wb2a-vitotrol-rx-burst-live-20261011.json")


class CorrelationTests(unittest.TestCase):
    def test_class31_historical_split_crc_hypotheses(self):
        row={"master_header":"010031","index":145,
             "composite_master_frame":"01003109010101074e"}
        r=m.crc31_counterfactuals(row)
        self.assertEqual(r["counterfactuals"]["0x00"]["checksum_tail"],"27fa")
        self.assertEqual(r["counterfactuals"]["0x10"]["checksum_tail"],"a6ea")
        self.assertEqual(r["counterfactuals"]["0x01"]["checksum_tail"],"aeeb")
        self.assertFalse(any(x["recorded_crc_tail_matches"] for x in
                             r["counterfactuals"].values()))
        self.assertTrue(r["no_counterfactual_transmitted"])

    def test_wrong_original_class31_row_rejected(self):
        for index,head,body in [(144,"010031","01003109010101074e"),
                                (145,"0100b1","01003109010101074e"),
                                (145,"010031","000000000000000000")]:
            with self.subTest(index=index),self.assertRaises(m.InvalidEvidence):
                m.crc31_counterfactuals({"master_header":head,"index":index,
                                         "composite_master_frame":body})

    def test_known_crc_validity(self):
        self.assertNotEqual(m.crc.crc16_kermit(bytes.fromhex("01003109010101074e")),0)
        self.assertEqual(m.crc.crc16_kermit(bytes.fromhex("01003109010110a6ea")),0)
        self.assertEqual(m.crc.crc16_kermit(bytes.fromhex(m.RARE_B1)),0)

    def test_altered_source_hash_rejected(self):
        with self.assertRaises(m.InvalidEvidence):
            m.run(b"x",b"y",b"z",b"abc")
        with self.assertRaises(m.InvalidEvidence):
            m.pinned(b"x","deadbeef",20)

    def test_private_sha_attested_full_evidence_when_accessible(self):
        try:inputs=[p.read_bytes() for p in (DEEP,FULL,FUSED,BURST)]
        except (FileNotFoundError,PermissionError):
            self.skipTest("original root-only recording access unavailable")
        r=m.run(*inputs)
        self.assertEqual(r["deep"]["total_nonatomic_rx_samples"],295)
        self.assertEqual(r["deep"]["class31_header_instances"],2)
        self.assertEqual(r["deep"]["class31_valid_complete_master_frames_with_rare_rx"],0)
        self.assertEqual(r["historic_fullram"]["rare_images"][0]["index"],64)
        self.assertTrue(r["historic_fullram"]["rare_166b_is_04"])
        self.assertEqual(r["special_snapshot_64_read_timeline"]["read_order"],
                         ["0x1660","0x1640","0x1620","0x1600"])
        self.assertFalse(r["CRC_valid_class31_causes_rare_B1"])
        self.assertFalse(r["unknown_rx_parser_or_ISR_verified"])
        self.assertEqual(r["controller_writes"],0)

    def test_no_active_transport_from_audit(self):
        mods=set()
        for node in ast.walk(ast.parse(SRC.read_text())):
            if isinstance(node,ast.Import):
                mods.update(x.name.split(".")[0] for x in node.names)
            elif isinstance(node,ast.ImportFrom) and node.module:
                mods.add(node.module.split(".")[0])
        self.assertFalse(mods & {"serial","subprocess","socket","requests","paho"})


if __name__=="__main__":unittest.main()
