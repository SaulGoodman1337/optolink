"""Fused FC03 CRC-tail/meta audit against synthetic and original evidence."""
from __future__ import annotations
import importlib.util
import sys
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"tools/wb2a-vitotrol-fused-rx-audit.py"
spec=importlib.util.spec_from_file_location("wb2a_fused_rx_audit_test",SRC)
m=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=m
spec.loader.exec_module(m)

FRAME_A=bytes.fromhex("0001b10a010110fe23d8")
FRAME_B=bytes.fromhex("0001b10a01011000d2c6")
LIVE=Path("/tmp/wb2a-vitotrol-fused-rx-live-20261011.json")


class Clock:
    def __init__(self):self.t=300.0
    def __call__(self):self.t+=0.5;return self.t


def source(*,switch=False):
    counter=[0]
    def reply(cmd):
        p=m.protocol
        addr,length=(p.ADDR,p.COUNT) if cmd==p.OVERLAP else p.base.ALLOWED[cmd]
        data=bytearray(length)
        if cmd==p.base.IDENTITY[0]:data[:]=bytes.fromhex(p.base.EXPECTED_ID)
        elif cmd==p.OVERLAP:
            if counter[0]%2==0:
                counter[0]+=1
            frame=FRAME_B if switch and counter[0]>2 else FRAME_A
            data[0]=frame[-1]
            data[-1]=0x06
            if counter[0]%2:
                counter[0]+=1
        elif cmd==p.RX:
            # Match the late/early bracket selected by 2 overlap reads.
            frame=FRAME_B if switch and counter[0]>=5 else FRAME_A
            data[2:2+len(frame)]=frame
        elif cmd==p.META:data[10:13]=bytes.fromhex("060001")
        elif cmd==p.FINAL[1]:data[0]=3
        return {"command":cmd,"address":f"0x{addr:04x}",
                "valid_read":True,"code":1,"data":data.hex()}
    return m.protocol.run(cycles=4,reader=reply,clock=Clock())


class OfflineAuditTests(unittest.TestCase):
    def test_evidence_structure_and_metadata(self):
        r=m.inspect(source())
        self.assertEqual(r["full_cycles"],4)
        self.assertEqual(r["total_validated_reads"],27)
        self.assertEqual(r["individual_overlapped_fc03_reads"],8)
        self.assertEqual(r["metadata_166a_counts"],{"06":8})
        self.assertEqual(r["crc_last_byte_counts"],{"d8":8})
        self.assertEqual(r["fused_crc_tail_to_metadata_byte_counts"],{"d8|06":8})
        self.assertEqual(r["vitotrol_swindex_0a5c"],"00000000")
        self.assertFalse(r["copy_atomic_on_sfr_or_isr_level_proven"])

    def test_wrong_source_and_controller_state_rejected(self):
        for key in ("target","mode","controller_writes"):
            d=source()
            d[key]="WRONG" if key!="controller_writes" else 1
            with self.subTest(field=key),self.assertRaises(m.EvidenceRejected):
                m.inspect(d)
        d=source()
        d["baseline"][0]["response"]["data"]="01"
        with self.assertRaises(m.EvidenceRejected):m.inspect(d)

    def test_tampered_time_and_reply_rejected(self):
        d=source()
        d["cycles"][0]["reads"][0]["response"]["data"]="00"
        with self.assertRaises(m.EvidenceRejected):m.inspect(d)
        d=source()
        d["cycles"][0]["reads"][1]["begin"]=0.0
        with self.assertRaises(m.EvidenceRejected):m.inspect(d)

    def test_real_original_if_available(self):
        if not LIVE.is_file():
            self.skipTest("private live P300 capture unavailable")
        import json
        r=m.inspect(json.loads(LIVE.read_bytes()))
        self.assertEqual(r["full_cycles"],8)
        self.assertEqual(r["total_validated_reads"],43)
        self.assertEqual(r["individual_overlapped_fc03_reads"],16)
        self.assertEqual(r["fused_crc_tail_to_metadata_byte_counts"],
                         {"53|0a":1,"c6|06":15})
        self.assertEqual(r["cycles_with_full_rx_crc_tail_mismatch_vs_bracketing_overlaps"],1)
        self.assertEqual(r["vitotrol_swindex_0a5c"],"00000000")
        self.assertFalse(r["vitotrol_enrollment_accepted_proven"])
        self.assertEqual(r["controller_writes"],0)


if __name__=="__main__":unittest.main()
