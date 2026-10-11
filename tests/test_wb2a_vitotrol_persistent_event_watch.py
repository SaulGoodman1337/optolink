"""Synthetic gate/bounds/CRC and original source tests; no device access."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"tools/wb2a-vitotrol-persistent-event-watch.py"
spec=importlib.util.spec_from_file_location("wb2a_vt_eventwatch_test",SRC)
m=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=m;spec.loader.exec_module(m)

MASTER_B1=bytes.fromhex("0100b10a01010106c731")
MASTER_31=bytes.fromhex("01003109010110a6ea")
MASTER_B3=bytes.fromhex("2000b30cee0110c21100aaf1")
FRAME_B1=bytes.fromhex("0001b10a01011000d2c6")


class Fake:
    def __init__(self):
        self.count=0;self.t=1000.0;self.request_log=[]
    def request(self,cmd):
        size=m.fast.ALLOWED[cmd][1]
        data=bytearray(size)
        if cmd==m.fast.IDENTITY:
            data[:]=bytes.fromhex(m.fast.VALID_ID)
        if cmd==m.fast.MASTER:
            self.count+=1
            frame=MASTER_31 if self.count%11==0 else (
                  MASTER_B3 if self.count%7==0 else MASTER_B1)
            data[:len(frame)]=frame
        if cmd==m.fast.FULL_RX:
            data[2:2+len(FRAME_B1)]=FRAME_B1
        if cmd==m.fast.META:
            data[-2:]=bytes.fromhex("0600")
        if cmd=="read;0x089c;1":data[0]=3
        self.t+=0.32
        out={"command":cmd,"address":f"0x{m.fast.ALLOWED[cmd][0]:04x}",
             "data":data.hex(),"valid_read":True,"controller_read_only":True,
             "mono_start":self.t,"mono_response":self.t+.2,
             "duration_ms":200.0}
        self.request_log.append(out)
        return out


class WatchTests(unittest.TestCase):
    def test_triggers_include_discovery_register_not_ordinary(self):
        self.assertEqual(m.TRIGGERS,{"010031","2000b3","110033"})
        self.assertNotIn("0100b1",m.TRIGGERS)
        self.assertTrue(all(x.startswith(("read;","request;3;"))
                            for x in m.fast.P300_ONLY))

    def test_capture_readonly_and_bounded(self):
        f=Fake();out=m.capture(f,polls=32)
        self.assertEqual(out["controller_writes"],0)
        self.assertEqual(out["master_read_count"],32)
        self.assertGreater(len(out["followups"]),1)
        self.assertLessEqual(len(out["followups"]),m.LIMIT_EVENT_EXTRA)
        self.assertEqual(out["master_crc_validity"],{"VALID":32})
        self.assertEqual(out["read_count"],len(f.request_log))
        self.assertTrue(all(x["master_rx_meta_sequential"] for x in out["followups"]))
        self.assertFalse(out["km_bus_physical_onwire_or_uart_ISR_proven"])
        for item in out["followups"]:
            self.assertTrue(item["rx_decoded"]["crc_valid"])
            self.assertEqual(item["metadata_166a_166b"],"0600")

    def test_no_unknown_cycles(self):
        for polls in (0,31,97,True,95.5):
            with self.subTest(polls=polls),self.assertRaises(m.Refused):
                m.capture(Fake(),polls=polls)

    def test_frame_crc_and_split_copy(self):
        src=bytes(32)
        bad=m.parse_rx({"data":src.hex()})
        self.assertFalse(bad["crc_valid"])
        good=m.master({"data":MASTER_31.ljust(32,b"\x00").hex()})
        self.assertTrue(good["crc_valid"])
        self.assertEqual(good["header"],"010031")
        self.assertFalse(good["physical_master_bus_transmitted_proven"])
        invalid=m.master({"data":MASTER_31[:-1].ljust(32,b"\x00").hex()})
        self.assertFalse(invalid["crc_valid"])

    def test_wrong_identity_or_fault_refused(self):
        class Wrong(Fake):
            def request(self,cmd):
                r=super().request(cmd)
                if cmd==m.fast.IDENTITY:r["data"]="00"*8
                return r
        with self.assertRaises(m.Refused):
            m.capture(Wrong(),polls=32)
        class Fault(Fake):
            def request(self,cmd):
                r=super().request(cmd)
                if cmd==m.fast.CHECKS[0]:r["data"]="01"
                return r
        with self.assertRaises(m.Refused):
            m.capture(Fault(),polls=32)


if __name__=="__main__":unittest.main()
