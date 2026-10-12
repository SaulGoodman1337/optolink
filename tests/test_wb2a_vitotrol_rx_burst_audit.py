"""Regression for timestamped FC03 RX burst forensic decoding."""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/"tools/wb2a-vitotrol-rx-burst-audit.py"
spec=importlib.util.spec_from_file_location("wb2a_burst_audit_tests",P)
m=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=m
spec.loader.exec_module(m)

NORMAL=bytes.fromhex("0001b10a010110fe23d8")
CHANGED=bytes.fromhex("0001b10a01011000d2c6")
MASTER=bytes.fromhex("0100b10a01010106c731")


class Clock:
    def __init__(self):self.t=100.0
    def __call__(self):self.t+=0.6;return self.t


def example(change=False):
    count=[0]
    def fake(cmd):
        addr,n=m.recorder.base.ALLOWED[cmd]
        raw=bytearray(n)
        if cmd==m.recorder.base.IDENTITY[0]:
            raw[:]=bytes.fromhex(m.recorder.base.EXPECTED_ID)
        elif cmd==m.recorder.RX[0]:
            frame=CHANGED if change and count[0]>=2 else NORMAL
            raw[2:2+len(frame)]=frame;count[0]+=1
        elif cmd==m.recorder.RX[1]:
            raw[10:13]=bytes.fromhex("060001")
        elif cmd==m.recorder.NEIGHBOR[0]:
            raw[11]=1
            raw[13:17]=bytes.fromhex("42160afe")
        elif cmd==m.recorder.NEIGHBOR[1]:
            raw[:len(MASTER)]=MASTER
        elif cmd==m.recorder.STATUS[1]:
            raw[0]=3
        return {"command":cmd,"address":f"0x{addr:04x}",
                "data":raw.hex(),"valid_read":True}
    return m.recorder.run(cycles=4,execute=fake,clock=Clock())


class BurstAuditTests(unittest.TestCase):
    def test_four_rounds_and_exact_frame_crc(self):
        r=m.evaluate(example())
        self.assertEqual(r["samples"],4)
        self.assertEqual(r["complete_verified_requests"],33)
        self.assertEqual(r["rx_frame_and_crc_counts"],
            [{"frame":NORMAL.hex(),"crc_valid":True,"n":4}])
        self.assertEqual(r["metadata_counts"],{"060001":4})
        self.assertEqual(r["descriptor_counts"],{"42160afe":4})
        self.assertEqual(r["sensor_089c"],{"03":4})
        self.assertEqual(r["swindex_0a5c"],{"00000000":4})
        self.assertTrue(all(x["rx_meta_midpoint_separation_ms"]>0 for x in r["cycle_events"]))
        self.assertTrue(r["tx_rx_samples_sequential_non_atomic"])
        self.assertFalse(r["controller_uart_rx_consumer_proven"])

    def test_frame_changed_without_metadata_change(self):
        r=m.evaluate(example(True))
        self.assertEqual(len(r["rx_frame_transitions"]),1)
        self.assertEqual(r["rx_frame_transitions"][0]["metadata_pair"],["060001","060001"])
        self.assertFalse(r["rx_frame_transitions"][0]["consumer_trigger_proven"])

    def test_status_violation_rejected(self):
        x=example();x["baseline"][0]["result"]["data"]="01"
        with self.assertRaises(m.InvalidEvidence):m.evaluate(x)
        x=example();x["identity"]["result"]["data"]="00"*8
        with self.assertRaises(m.InvalidEvidence):m.evaluate(x)

    def test_nonatomic_order_violation_rejected(self):
        x=example();x["rounds"][0]["order"].reverse()
        with self.assertRaises(m.InvalidEvidence):m.evaluate(x)
        x=example();x["rounds"][0]["atomic"]=True
        with self.assertRaises(m.InvalidEvidence):m.evaluate(x)
        x=example();x["rounds"][0]["reads"][1]["mono_start"]=0
        with self.assertRaises(m.InvalidEvidence):m.evaluate(x)

    def test_bad_payload_and_bad_scope_rejected(self):
        x=example();x["rounds"][0]["reads"][0]["result"]["data"]="00"
        with self.assertRaises(m.InvalidEvidence):m.evaluate(x)
        x=example();x["controller_writes"]=1
        with self.assertRaises(m.InvalidEvidence):m.evaluate(x)


if __name__=="__main__":unittest.main()
