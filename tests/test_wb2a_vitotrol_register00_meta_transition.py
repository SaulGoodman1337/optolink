"""Deterministic safety and temporal RX-meta follow-up logic."""
from __future__ import annotations
import importlib.util
import sys
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"tools/wb2a-vitotrol-register00-meta-transition.py"
spec=importlib.util.spec_from_file_location("vt_reg00_meta_progress_tests",SRC)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m
spec.loader.exec_module(m)


class Clock:
    def __init__(self):self.t=1000.
    def __call__(self):self.t+=.1;return self.t


NORMAL_TX=bytes.fromhex("0100b10a010101055c03")
TARGET_TX=bytes.fromhex("0100310901010027fa")
RX_REG00=bytes.fromhex("0001b10a010100004353")
RX_NORMAL=bytes.fromhex("0001b10a01011000d2c6")


class Client:
    def __init__(self,fire_at=17):
        self.fire=fire_at;self.t=1000.;self.txcalls=0
        self.metacalls=0;self.rxcalls=0;self.request_log=[]
    def request(self,cmd):
        addr,n=m.base.ALLOWED[cmd];raw=bytearray(n)
        if cmd==m.base.IDENTITY:raw[:]=bytes.fromhex(m.base.VALID_ID)
        if cmd==m.base.MASTER:
            self.txcalls+=1
            frame=TARGET_TX if self.txcalls==self.fire else NORMAL_TX
            raw[:len(frame)]=frame
        if cmd==m.base.FULL_RX:
            self.rxcalls+=1
            frame=RX_REG00 if self.rxcalls==1 else RX_NORMAL
            raw[2:2+len(frame)]=frame
        if cmd==m.base.META:
            variants=["0a07","0a07","0a04","0a04","0a04","0600","0600","0600"]
            pair=variants[self.metacalls]
            self.metacalls+=1
            raw[-2:]=bytes.fromhex(pair)
        if cmd=="read;0x089c;1":raw[0]=3
        self.t+=.23
        row={"command":cmd,"data":raw.hex(),"address":f"0x{addr:04x}",
             "valid_read":True,"mono_start":self.t,
             "mono_response":self.t+.2,"duration_ms":200}
        self.request_log.append(row)
        return row


class MetaTests(unittest.TestCase):
    def test_trigger_and_eight_ordered_meta_copies(self):
        c=Client()
        result=m.measure(c,max_polls=32,clock=Clock())
        self.assertTrue(result["event_found"])
        self.assertEqual(result["TX_polls"],17)
        self.assertEqual(result["event"]["metadata_166a166b_seq"],
                         ["0a07","0a07","0a04","0a04","0a04","0600","0600","0600"])
        self.assertEqual(result["event"]["rx_first_decoded"]["frame_hex"],RX_REG00.hex())
        self.assertTrue(result["event"]["rx_first_decoded"]["crc_valid"])
        self.assertTrue(result["event"]["master_after_decoded"]["full_crc_valid"])
        self.assertEqual(result["controller_writes"],0)
        self.assertFalse(result["event"]["physical_trigger_or_UART_ISR_proven"])

    def test_no_matching_event_returns_safely(self):
        c=Client(fire_at=500)
        r=m.measure(c,max_polls=32,clock=Clock())
        self.assertFalse(r["event_found"])
        self.assertEqual(r["TX_polls"],32)
        self.assertEqual(r["total_read_count"],43)
        self.assertEqual(r["controller_writes"],0)

    def test_rejects_unbounded_or_bool_polls(self):
        for n in (0,31,257,True,32.0):
            with self.subTest(n=n),self.assertRaises(m.Refused):
                m.measure(Client(),max_polls=n)

    def test_real_frame_crcs_and_registers(self):
        good=m.master(TARGET_TX.ljust(32,b"\x00"))
        self.assertTrue(good["full_crc_valid"])
        self.assertEqual(good["frame_hex"],m.REQ31_00.hex())
        b=m.rx_frame((b"\x00\x00"+RX_REG00).ljust(32,b"\x00"))
        self.assertTrue(b["crc_valid"])
        self.assertFalse(b["class11_is_vitotrol"])

    def test_corrupt_master_no_trigger(self):
        class Corrupt(Client):
            def request(self,cmd):
                r=super().request(cmd)
                if cmd==m.base.MASTER and self.txcalls==17:
                    b=bytearray.fromhex(r["data"]);b[8]^=1;r["data"]=b.hex()
                return r
        c=Corrupt()
        r=m.measure(c,max_polls=32,clock=Clock())
        self.assertFalse(r["event_found"])

    def test_bad_device_or_coding_fails_closed(self):
        class Bad(Client):
            def __init__(self,bad):
                super().__init__();self.bad=bad
            def request(self,cmd):
                r=super().request(cmd)
                if cmd==self.bad:r["data"]="00"*8 if cmd==m.base.IDENTITY else "01"
                return r
        for target in (m.base.IDENTITY,m.base.CHECKS[0]):
            with self.subTest(target=target),self.assertRaises(m.Refused):
                m.measure(Bad(target),max_polls=32,clock=Clock())


if __name__=="__main__":unittest.main()
