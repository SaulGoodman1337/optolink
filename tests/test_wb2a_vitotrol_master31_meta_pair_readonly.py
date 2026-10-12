"""No-I/O tests for the fixed P300 whole-master/metapair windows."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import types
import unittest

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"tools/wb2a-vitotrol-master31-meta-pair-readonly.py"
spec=importlib.util.spec_from_file_location("wb2a_master31_pair_test",SRC)
m=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=m
spec.loader.exec_module(m)


class Clock:
    def __init__(self):self.t=100
    def __call__(self):self.t+=0.7;return self.t


def good(cmd):
    data=(bytes.fromhex(m.fused.base.EXPECTED_ID) if cmd==m.IDENTITY
          else bytes(m.WIDTH[cmd]))
    return {"command":cmd,"address":f"0x{m.ADDR[cmd]:04x}",
            "data":data.hex(),"valid_read":True}


class Tests(unittest.TestCase):
    def test_readonly_window_bounds(self):
        self.assertEqual(m.ALLOWED,
          {m.TX,m.FUSED,m.METAPAIR,m.IDENTITY,*(r[0] for r in m.STATUS),*m.EXTRA})
        self.assertTrue(all(k.startswith(("read;","request;3;")) for k in m.ALLOWED))
        self.assertEqual(0x164c+30,0x166a)
        self.assertEqual(0x164c+31,0x166b)
        self.assertEqual(0x161a+31,0x1639)

    def test_known_whitelist_rejects_writes(self):
        for c in ("request;4;0x166a;2;0a04","request;3;0x164c;33",
                  "request;99;0x166a;2"):
            with self.subTest(c=c),self.assertRaises(m.Refused):
                m.reader(c,old=good)

    def test_one_combined_metapair_request(self):
        src=bytes(30)+bytes.fromhex("0a04")
        out=types.SimpleNamespace(returncode=0,
          stdout=f"{m.METAPAIR} <- openv/resp: 1;0x164c;{src.hex()}")
        found=m.reader(m.METAPAIR,runner=lambda *a,**k:out)
        self.assertEqual(bytes.fromhex(found["data"])[30:32],b"\x0a\x04")

    def test_exact_response_and_length(self):
        for status,addr,payload in [
            (5,"0x164c",bytes(32)),
            (1,"0x164d",bytes(32)),
            (1,"0x164c",bytes(31))]:
            r=types.SimpleNamespace(returncode=0,
                stdout=f"{m.METAPAIR} <- openv/resp: {status};{addr};{payload.hex()}")
            with self.subTest(status=status,addr=addr),self.assertRaises(m.Refused):
                m.reader(m.METAPAIR,runner=lambda *a,**kw:r)

    def test_bounded_8_cycles_and_no_hardware_write(self):
        seen=[]
        def observe(cmd):
            seen.append(cmd)
            return good(cmd)
        result=m.run(cycles=8,read_fn=observe,clock=Clock())
        self.assertEqual(result["samples"],8)
        self.assertEqual(result["total_commands"],51)
        self.assertEqual(len(seen),51)
        self.assertEqual([x["command"] for x in result["rounds"][0]["rows"]],
                         [m.TX,m.FUSED,m.METAPAIR,m.FUSED,m.TX])
        self.assertEqual(result["controller_writes"],0)
        self.assertFalse(result["uart1_ISR_or_KM_PHY_sampled"])

    def test_wrong_target_or_coding_rejected(self):
        for cmd,value in [(m.IDENTITY,b"\x00"*8),
                          (m.STATUS[0][0],b"\x01"),
                          (m.STATUS[3][0],b"\x81")]:
            def bad(query):
                result=good(query)
                if query==cmd:result["data"]=value.hex()
                return result
            with self.subTest(cmd=cmd),self.assertRaises(m.Refused):
                m.run(cycles=4,read_fn=bad,clock=Clock())

    def test_unbounded_cycles_rejected(self):
        for n in (0,3,9,-1,True,4.5):
            with self.subTest(n=n),self.assertRaises(m.Refused):
                m.run(cycles=n,read_fn=good,clock=Clock())


if __name__=="__main__":unittest.main()
