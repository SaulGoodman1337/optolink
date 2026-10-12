"""Timestamp, CRC, response and source scope checks for fast P300 research."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"tools/wb2a-vitotrol-persistent-rx-audit.py"
spec=importlib.util.spec_from_file_location("vt_fast_rx_audit_tests",SRC)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m
spec.loader.exec_module(m)
REAL=Path("/tmp/wb2a-vitotrol-persistent-p300-live-20261011.json")


class Fake:
    def __init__(self,rare=False):
        self.n=300.0;self.rare=rare
    def request(self,cmd):
        allowed=m.reader.ALLOWED
        addr,n=allowed[cmd]
        data=bytearray(n)
        if cmd==m.reader.IDENTITY:data[:]=bytes.fromhex(m.reader.VALID_ID)
        if cmd==m.reader.RX:
            data[0]=0x53 if self.rare else 0xc6
            data[-1]=0x06
        if cmd==m.reader.META:data[-2:]=bytes.fromhex("0600")
        if cmd==m.reader.MASTER:
            f=bytes.fromhex("0100b10a01010106c731")
            data[:len(f)]=f
        if cmd=="read;0x089c;1":data[0]=3
        self.n+=0.3
        return {
            "command":cmd,"address":f"0x{addr:04x}","valid_read":True,
            "controller_read_only":True,
            "data":data.hex(),"mono_start":round(self.n,6),
            "mono_response":round(self.n+0.12,6),"duration_ms":120.0,
            "drained_before":0,"ignored_other_responses":0,
        }


def sample(rare=False):
    return m.reader.capture(Fake(rare),p300=True,cycles=4)


class ForensicTests(unittest.TestCase):
    def test_synthetic_valid_fixture(self):
        r=m.inspect(sample())
        self.assertEqual(r["validated_reads"],23)
        self.assertEqual(r["metadata_166a166b_single_copy_counts"],{"0600":4})
        self.assertEqual(r["rx_crc_last_and_166a_single_copy_counts"],{"c6|06":4})
        self.assertEqual(r["master_frame_crc_counts"],{"VALID":4})
        self.assertEqual(r["master_header_counts"],{"0100b1":4})
        self.assertEqual(r["crosscopy_166a_disagreements"],0)
        self.assertFalse(r["physical_km_bus_event_or_uart_irq_proven"])

    def test_rare_crc_last_does_not_force_meta_change(self):
        r=m.inspect(sample(rare=True))
        self.assertEqual(r["rx_crc_last_and_166a_single_copy_counts"],{"53|06":4})
        self.assertEqual(r["metadata_166a166b_single_copy_counts"],{"0600":4})

    def test_wrong_source_and_broken_guard_refused(self):
        for prop in ("mode","target","controller_writes","one_serial_owner"):
            x=sample()
            x[prop]=1 if prop=="controller_writes" else "BAD"
            with self.subTest(prop=prop),self.assertRaises(m.InvalidEvidence):
                m.inspect(x)
        x=sample();x["after"][0]["data"]="01"
        with self.assertRaises(m.InvalidEvidence):m.inspect(x)

    def test_corrupt_narrow_or_reordered_data_rejected(self):
        x=sample();x["cycles"][0]["rows"][0]["data"]="00"
        with self.assertRaises(m.InvalidEvidence):m.inspect(x)
        x=sample();x["cycles"][0]["rows"].reverse()
        with self.assertRaises(m.InvalidEvidence):m.inspect(x)
        x=sample();x["cycles"][1]["rows"][0]["mono_start"]=0
        with self.assertRaises(m.InvalidEvidence):m.inspect(x)
        x=sample();x["read_count"]=999
        with self.assertRaises(m.InvalidEvidence):m.inspect(x)

    def test_actual_original_if_available(self):
        try:
            import json
            capture=json.loads(REAL.read_text())
        except (FileNotFoundError,PermissionError):
            self.skipTest("private original fast P300 capture not present")
        r=m.inspect(capture)
        self.assertEqual(r["cycle_count"],32)
        self.assertEqual(r["validated_reads"],107)
        self.assertEqual(r["rx_crc_last_and_166a_single_copy_counts"],{"c6|06":32})
        self.assertEqual(r["metadata_166a166b_single_copy_counts"],{"0600":32})
        self.assertEqual(r["master_frame_crc_counts"],{"VALID":32})
        self.assertEqual(r["master_header_counts"],{"010031":1,"0100b1":21,"2000b3":10})
        self.assertEqual(r["vitotrol_swindex"],"00000000")
        self.assertFalse(r["mqtt_same_address_request_attribution_proven"])
        self.assertTrue(r["zero_controller_writes"])


if __name__=="__main__":unittest.main()
