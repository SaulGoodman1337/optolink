"""Safety and protocol read-only test with simulated CP2102, no real serial."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest

P=Path(__file__).resolve().parents[1]/"tools/wb2a-v200kw2-gwg-live-readonly.py"
spec=importlib.util.spec_from_file_location("wb2a_gwg_live_readonly_synthetic_test",P)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)


class FakePort:
    def __init__(self,behavior=None):
        self.behavior=behavior or {}
        self.tx=[]
        self.received=bytearray()
        self.connected=True
    def reset_input_buffer(self):
        self.received.clear()
    def write(self,wire):
        self.tx.append(bytes(wire))
        if wire==b"\x04":
            self.received.extend(b"\x05")
        else:
            self.received.extend(self.behavior.get(bytes(wire),b""))
        return len(wire)
    def flush(self):
        pass
    def read(self,n):
        b=self.received[:n];del self.received[:n];return bytes(b)
    def read_all(self):
        return self.read(len(self.received))


class Tests(unittest.TestCase):
    def test_plan_safely_rejects_write_opcode(self):
        r=m.plan()
        self.assertEqual(r["controller_writes"],0)
        self.assertEqual(r["controller_eeprom_writes"],0)
        self.assertEqual(set(m.PROBE_CASES.values()),{
            bytes.fromhex("01 f7 00 f8 04"),bytes.fromhex("01 c7 f8 04 04"),
            bytes.fromhex("01 cb 6f 01 04"),bytes.fromhex("01 c5 6f 01 04")})
        self.assertTrue(all(v[1] in {0xF7,0xC7,0xCB,0xC5}
                            for v in m.PROBE_CASES.values()))
        self.assertEqual(sum(m.REPEATS.values()),8)
        with self.assertRaises(m.Refused):
            m.sync_and_probe(FakePort(),bytes.fromhex("01 c4 f8 04 04"),4)
        with self.assertRaises(m.Refused):
            m.sync_and_probe(FakePort(),bytes.fromhex("01 c8 6f 01 04"),1)

    def test_host_needs_root_original_sha_independent_timer_no_port_owner(self):
        ok=lambda *cmd:cmd[-1]==m.TIMER
        cfg=b"vs1protocol = True\n"
        with self.assertRaises(m.Refused):
            m.validate_host(execute=False,systemctl=ok,config=cfg,root=True,port_exists=True)
        with self.assertRaises(m.Refused):
            m.validate_host(execute=True,systemctl=ok,config=cfg,root=True,port_exists=True)
        with self.assertRaises(m.Refused):
            m.validate_host(execute=True,systemctl=ok,config=cfg,root=False,port_exists=True)
        with self.assertRaises(m.Refused):
            m.validate_host(execute=True,systemctl=ok,config=cfg,root=True,port_exists=False)

    def test_exact_gwg_c7_on_simulated_cooperative_device(self):
        sim=FakePort({
            m.PROBE_CASES["kw_baseline_before"]:m.EXPECTED_ID,
            m.PROBE_CASES["historical_2010_gwg_c7_id"]:m.EXPECTED_ID,
            m.PROBE_CASES["gwg_cb_legacy_outside_temp_example"]:b"\x14",
            m.PROBE_CASES["gwg_c5_legacy_xram_6f"]:b"\x19",
        })
        r=m.run(sim)
        self.assertEqual(r["status"],"BOUNDED_READONLY_COMPLETED")
        self.assertEqual(r["actual_io"],8)
        self.assertTrue(r["real_WB2A_GWG_C7_direct_read_confirmed"])
        self.assertFalse(r["GWG_CB_read_family_supported_proven"])
        self.assertFalse(r["GWG_C5_read_family_supported_proven"])
        self.assertFalse(r["actual_program_ROM_bytes_recovered"])
        self.assertEqual([x.hex() for x in sim.tx[0::2]],
                         ["04"]*8)
        self.assertEqual([x.hex() for x in sim.tx[1::2]],[
           m.PROBE_CASES[name].hex()
           for name in m.PROBE_CASES for _ in range(m.REPEATS[name])])

    def test_mismatching_baseline_must_stop_before_legacy(self):
        sim=FakePort({m.PROBE_CASES["kw_baseline_before"]:b"\x20\x98\x00\x02"})
        with self.assertRaisesRegex(m.Refused,"baseline failed"):
            m.run(sim)
        self.assertEqual(len(sim.tx),2)

    def test_gwg_empty_response_is_not_success_or_firmware(self):
        sim=FakePort({m.PROBE_CASES["kw_baseline_before"]:m.EXPECTED_ID})
        r=m.run(sim)
        self.assertFalse(r["real_WB2A_GWG_C7_direct_read_confirmed"])
        self.assertFalse(r["ROM_20bit_bank_access_proven"])
        self.assertEqual(r["other_legacy_responses"]["gwg_cb_legacy_outside_temp_example"],
                         ["",""])


if __name__=="__main__":unittest.main()
