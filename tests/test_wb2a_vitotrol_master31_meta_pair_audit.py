"""Offline audit fixtures for whole master TX and 166A/B paired metadata."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"tools/wb2a-vitotrol-master31-meta-pair-audit.py"
spec=importlib.util.spec_from_file_location("vt_master31_pair_audit_tests",SRC)
m=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=m
spec.loader.exec_module(m)


class Clock:
    def __init__(self):self.t=100
    def __call__(self):self.t+=0.3;return self.t


VALID_MASTER=bytes.fromhex("01003109010110a6ea")
INVALID_MASTER=bytes.fromhex("01003109010101074e")
NORMAL_MASTER=bytes.fromhex("0100b10a01010106c731")


def mock(*,invalid=False,rare=False):
    def reply(cmd):
        addr,size=m.probe.ADDR[cmd],m.probe.WIDTH[cmd]
        raw=bytearray(size)
        if cmd==m.probe.IDENTITY:raw[:]=bytes.fromhex(m.probe.fused.base.EXPECTED_ID)
        elif cmd==m.probe.TX:
            frame=INVALID_MASTER if invalid else VALID_MASTER
            raw[:len(frame)]=frame
        elif cmd==m.probe.FUSED:
            raw[0]=0x53 if rare else 0xc6
            raw[-1]=0x0a if rare else 0x06
        elif cmd==m.probe.METAPAIR:
            raw[-2:]=bytes.fromhex("0a04" if rare else "0600")
        elif cmd==m.probe.EXTRA[1]:
            raw[0]=3
        return {"command":cmd,"address":f"0x{addr:04x}",
                "data":raw.hex(),"valid_read":True}
    return m.probe.run(cycles=4,read_fn=reply,clock=Clock())


class PairAuditTests(unittest.TestCase):
    def test_real_31_crc_from_one_ram_copy(self):
        v=m.extract_tx(VALID_MASTER.ljust(32,b"\x00"))
        self.assertTrue(v["crc_valid"])
        self.assertEqual(v["register_byte"],"0x10")
        b=m.extract_tx(INVALID_MASTER.ljust(32,b"\x00"))
        self.assertFalse(b["crc_valid"])
        self.assertFalse(b["electrical_bus_transmission_proven"])

    def test_validated_normal_pair(self):
        r=m.inspect(mock())
        self.assertEqual(r["cycles"],4)
        self.assertEqual(r["validated_read_requests"],31)
        self.assertEqual(r["master_0x31_reads_whole_ram_copy"],8)
        self.assertEqual(r["master_tx_single_read_crc_validity"],{"VALID":8})
        self.assertEqual(r["same_fc03_copy_166a166b_counts"],{"0600":4})
        self.assertEqual(r["fused_crc_last_to_166a_counts"],{"c6|06":8})
        self.assertFalse(r["physical_KM_bus_master_0x31_causes_rare_rx_proven"])

    def test_rare_meta_0a04_is_simultaneous_in_one_copy(self):
        r=m.inspect(mock(rare=True))
        self.assertEqual(r["same_fc03_copy_166a166b_counts"],{"0a04":4})
        self.assertEqual(r["fused_crc_last_to_166a_counts"],{"53|0a":8})
        self.assertTrue(r["both_meta_bytes_same_32B_copy"])

    def test_invalid_tx_annotated_not_bad_physical_frame(self):
        r=m.inspect(mock(invalid=True))
        self.assertEqual(r["master_tx_single_read_crc_validity"],{"UNVERIFIED":8})
        self.assertFalse(r["RX_and_master_one_copy"])

    def test_fault_and_source_tampering_fails_closed(self):
        for key in ("device","controller_writes","mode"):
            x=mock()
            x[key]="unknown" if key!="controller_writes" else 1
            with self.subTest(key=key),self.assertRaises(m.InvalidEvidence):
                m.inspect(x)
        x=mock();x["rounds"][0]["read_order"][0]=m.probe.METAPAIR
        with self.assertRaises(m.InvalidEvidence):m.inspect(x)
        x=mock();x["rounds"][0]["rows"][1]["response"]["data"]="00"
        with self.assertRaises(m.InvalidEvidence):m.inspect(x)


if __name__=="__main__":unittest.main()
