"""Isolated read-only FC03 overlap-window regression tests."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import types
import unittest

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"tools/wb2a-vitotrol-fused-rx-window.py"
spec=importlib.util.spec_from_file_location("wb2a_vt_fused_rx_tests",SRC)
m=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=m
spec.loader.exec_module(m)


def reply(cmd,*,data=None):
    addr,n=(m.ADDR,m.COUNT) if cmd==m.OVERLAP else m.base.ALLOWED[cmd]
    if data is None:data=(bytes.fromhex(m.base.EXPECTED_ID) if cmd==m.base.IDENTITY[0]
                          else bytes(n))
    return {"command":cmd,"address":f"0x{addr:04x}",
            "valid_read":True,"code":1,"data":data.hex(),"controller_read_only":True}


class Reader:
    def __init__(self,override=None):
        self.overrides=override or {}
        self.seen=[]
    def __call__(self,cmd):
        self.seen.append(cmd)
        return reply(cmd,data=self.overrides.get(cmd))


class Clock:
    def __init__(self):self.now=500.0
    def __call__(self):self.now+=0.25;return self.now


class FusedRxTests(unittest.TestCase):
    def test_single_window_exact_addresses(self):
        self.assertEqual(m.ADDR,0x164b)
        self.assertEqual(m.ADDR+m.COUNT-1,0x166a)
        self.assertEqual(m.COUNT,32)
        self.assertNotIn("request;4;",m.OVERLAP)
        self.assertTrue(all(cmd.startswith(("read;","request;3;"))
                            for cmd in m.ALLOWED))

    def test_isolated_overlap_hex_decoder(self):
        payload=bytes.fromhex("d8")+bytes(30)+bytes.fromhex("06")
        out=types.SimpleNamespace(returncode=0,
            stdout=f"{m.OVERLAP} <- openv/resp: 1;0x164b;{payload.hex()}")
        r=m.read(m.OVERLAP,runner=lambda *args,**kwargs:out)
        self.assertEqual(r["data"],payload.hex())
        self.assertEqual(bytes.fromhex(r["data"])[0],0xd8)
        self.assertEqual(bytes.fromhex(r["data"])[-1],0x06)

    def test_malformed_window_rejected(self):
        for code,data,addr in (
            (1,b"\x00"*31,"0x164b"),
            (1,b"\x00"*32,"0x166a"),
            (5,b"\x00"*32,"0x164b"),
        ):
            out=types.SimpleNamespace(returncode=0,
                 stdout=f"{m.OVERLAP} <- openv/resp: {code};{addr};{data.hex()}")
            with self.subTest(code=code,addr=addr),self.assertRaises(m.Refused):
                m.read(m.OVERLAP,runner=lambda *args,**kwargs:out)

    def test_full_probe_brackets_reads_with_no_writes(self):
        reader=Reader()
        outcome=m.run(cycles=4,reader=reader,clock=Clock())
        self.assertEqual(outcome["requests"],27)
        self.assertEqual(len(reader.seen),27)
        self.assertEqual(len(outcome["cycles"]),4)
        self.assertEqual([row["command"] for row in outcome["cycles"][0]["reads"]],
                         [m.OVERLAP,m.RX,m.META,m.OVERLAP])
        self.assertEqual(outcome["controller_writes"],0)
        self.assertTrue(outcome["single_p300_copy_is_not_isr_atomic"])

    def test_preflight_rejects_unknown_target_or_coding(self):
        wrong=Reader({m.base.IDENTITY[0]:bytes(8)})
        with self.assertRaises(m.Refused):
            m.run(cycles=4,reader=wrong,clock=Clock())
        abnormal=Reader({m.base.BASELINE[3][0]:b"\x41"})
        with self.assertRaises(m.Refused):
            m.run(cycles=4,reader=abnormal,clock=Clock())

    def test_only_bounded_sample_counts(self):
        for cycles in (-1,0,3,9,True,2.0):
            with self.subTest(cycles=cycles),self.assertRaises(m.Refused):
                m.run(cycles=cycles,reader=Reader(),clock=Clock())

    def test_disallowed_command_refused(self):
        with self.assertRaises(m.Refused):
            m.read("request;3;0x164b;33")
        with self.assertRaises(m.Refused):
            m.read("request;4;0x164b;32")


if __name__=="__main__":unittest.main()
