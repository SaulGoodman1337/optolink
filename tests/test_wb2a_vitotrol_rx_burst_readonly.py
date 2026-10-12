"""Fast RX time-window guard tests, no actual device calls."""
from __future__ import annotations
import ast
import importlib.util
import sys
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"tools/wb2a-vitotrol-rx-burst-readonly.py"
spec=importlib.util.spec_from_file_location("wb2a_vitotrol_rx_burst_test",SRC)
m=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=m
spec.loader.exec_module(m)


class Fake:
    def __init__(self, overrides=None):
        self.overrides=overrides or {}
        self.seen=[]
    def __call__(self,cmd):
        self.seen.append(cmd)
        addr,width=m.base.ALLOWED[cmd]
        default=m.base.EXPECTED_ID if cmd==m.base.IDENTITY[0] else "00"*width
        return {"command":cmd,"address":f"0x{addr:04x}",
                "data":self.overrides.get(cmd,default),"valid_read":True}


class Clock:
    def __init__(self):self.t=100.0
    def __call__(self):
        self.t+=0.03
        return self.t


class BurstTests(unittest.TestCase):
    def test_happy_path_non_atomic_flip(self):
        f=Fake();clk=Clock()
        r=m.run(cycles=4,execute=f,clock=clk)
        self.assertEqual(r["total_reads"],33)
        self.assertEqual(len(f.seen),33)
        self.assertEqual(r["rounds"][0]["order"][:2],list(m.RX))
        self.assertEqual(r["rounds"][1]["order"][:2],list(reversed(m.RX)))
        self.assertEqual(r["controller_writes"],0)
        self.assertTrue(all(not x["atomic"] for x in r["rounds"]))
        self.assertFalse(r["km_bus_rx_isr_verified"])

    def test_identity_and_configuration_fail_closed(self):
        cases=[
            {m.base.IDENTITY[0]:"00"*8},
            {m.base.BASELINE[0][0]:"02"},
            {m.base.BASELINE[3][0]:"80"},
        ]
        for overrides in cases:
            with self.subTest(overrides=overrides),self.assertRaises(m.Refused):
                m.run(cycles=4,execute=Fake(overrides),clock=Clock())

    def test_explicit_write_not_on_whitelist(self):
        for cmd in ("request;4;0x1642;1;00","writeraw;0x0b6b;01",
                    "request;99;0x0000;2","request;3;0xc000;32"):
            with self.subTest(cmd=cmd),self.assertRaises(m.Refused):
                m.invoke_timed(cmd,execute=Fake(),clock=Clock())

    def test_request_response_address_and_width_checked(self):
        cmd=m.RX[0]
        bogus=Fake()
        a=bogus(cmd)
        for bad in (
            {**a,"data":"00"},
            {**a,"address":"0x1642"},
            {**a,"command":"request;3;0x1642;1"},
            {**a,"valid_read":False},
        ):
            with self.subTest(bad=bad),self.assertRaises(m.Refused):
                m.invoke_timed(cmd,execute=lambda x,b=bad:b,clock=Clock())

    def test_timeouts_and_monotonic(self):
        times=iter([200.0,190.0])
        with self.assertRaises(m.Refused):
            m.invoke_timed(m.RX[0],execute=Fake(),clock=lambda:next(times))
        times=iter([100.0,113.0])
        with self.assertRaises(m.Refused):
            m.invoke_timed(m.RX[0],execute=Fake(),clock=lambda:next(times))

    def test_cycle_bounds(self):
        for n in (0,-1,1,3,9,True,2.5):
            with self.subTest(n=n),self.assertRaises(m.Refused):
                m.run(cycles=n,execute=Fake(),clock=Clock())

    def test_source_has_no_controller_write_operation(self):
        for cmd in m.ACCEPT:
            self.assertTrue(cmd.startswith(("request;3;","read;")))
        mod=ast.parse(SRC.read_text())
        imports=set()
        for node in ast.walk(mod):
            if isinstance(node,ast.Import):
                imports.update(x.name.split(".")[0] for x in node.names)
            elif isinstance(node,ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        self.assertFalse(imports & {"serial","socket","paho"})
        self.assertTrue(m.ACCEPT.issubset(m.base.ALLOWED))


if __name__=="__main__":
    unittest.main()
