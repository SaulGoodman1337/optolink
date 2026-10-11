"""CRC/ordering/tamper tests for first natural Master31/00-RX-B1/00 correlation."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"tools/wb2a-vitotrol-master31-register00-event-audit.py"
spec=importlib.util.spec_from_file_location("vt_register00_audit_tests",SRC)
m=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=m
spec.loader.exec_module(m)
SOURCE=Path("/tmp/wb2a-vitotrol-natural-event-live-20261011.json")
FULL=Path("/root/p300-trial-work/research-bundles/p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz")


def make():
    master=bytes.fromhex(m.KNOWN_MASTER).ljust(32,b"\x00")
    slave=bytes.fromhex("0000"+m.KNOWN_REPLY).ljust(32,b"\x00")
    metadata=(bytes.fromhex("fa01fb0122d1")+bytes(24)+bytes.fromhex("0a07"))
    later=bytes.fromhex("0100b10a010101055c03").ljust(32,b"\x00")
    def record(addr,raw,st):
        return {"address":f"0x{addr:04x}","data":raw.hex(),
                "valid_read":True,"controller_read_only":True,
                "mono_start":st,"mono_response":st+.2,
                "duration_ms":200.0}
    return {"index":85,
            "master_before":record(0x161a,master,1.0),
            "rx_immediate":record(0x1640,slave,1.21),
            "metadata_raw_read":record(0x164c,metadata,1.42),
            "master_after":record(0x161a,later,1.63)}


class OriginalCorrelationTests(unittest.TestCase):
    def test_synthetic_register00_crc_and_meta(self):
        report=m.validate_event(make())
        self.assertEqual(report["master_class31_register00"],m.KNOWN_MASTER)
        self.assertEqual(report["slave_class01_b1_register00"],m.KNOWN_REPLY)
        self.assertEqual(report["metadata_166a166b_from_single_copy"],"0a07")
        self.assertEqual(report["matching_register_byte"],0)
        self.assertTrue(report["master_crc_valid"])
        self.assertFalse(report["onwire_km_master_slave_causality_proven"])

    def test_reg00_master_crc_corruption_rejected(self):
        x=make()
        x["master_before"]["data"]="0100310901010027fb"+("00"*23)
        with self.assertRaises(m.InvalidEvidence):m.validate_event(x)

    def test_false_rx_response_crc_rejected(self):
        x=make()
        payload=bytearray.fromhex(x["rx_immediate"]["data"])
        payload[10]^=1
        x["rx_immediate"]["data"]=payload.hex()
        with self.assertRaises(m.InvalidEvidence):m.validate_event(x)

    def test_meta_unexpected_or_temporal_overlap_rejected(self):
        x=make()
        x["metadata_raw_read"]["data"]=(bytes(30)+bytes.fromhex("0a04")).hex()
        with self.assertRaises(m.InvalidEvidence):m.validate_event(x)
        x=make()
        x["rx_immediate"]["mono_start"]=1.1
        with self.assertRaises(m.InvalidEvidence):m.validate_event(x)

    def test_address_or_size_refused(self):
        x=make()
        x["master_before"]["address"]="0x1642"
        with self.assertRaises(m.InvalidEvidence):m.validate_event(x)
        x=make()
        x["rx_immediate"]["data"]="00"*31
        with self.assertRaises(m.InvalidEvidence):m.validate_event(x)

    def test_original_source_hash_and_one_byte_difference_if_accessible(self):
        try:src=SOURCE.read_bytes();full=FULL.read_bytes()
        except (PermissionError,FileNotFoundError):
            self.skipTest("root-only original historical archive unavailable")
        r=m.inspect(src,full)
        self.assertEqual(r["historic_live_identical_bytes_out_of_32"],31)
        self.assertEqual(r["historical_to_live_changed_ram_byte_addresses"],["0x166b"])
        self.assertEqual(r["event"]["host_gap_after_master_ms"],0.311)
        self.assertTrue(r["prior_six_byte_difference_invariant_disproven"])
        self.assertFalse(r["vitotrol_enrolled"])
        self.assertEqual(r["controller_writes"],0)

    def test_bad_attestation_rejected(self):
        with self.assertRaises(m.InvalidEvidence):
            m.inspect(b"not original",b"not original")


if __name__=="__main__":unittest.main()
