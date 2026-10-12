"""Second historical GWG F8 address check remains SHA-gated, read only."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest

P=Path(__file__).resolve().parents[1]/"tools/wb2a-v200kw2-gwg-followup-readonly.py"
spec=importlib.util.spec_from_file_location("wb2a_gwg_followup_readonly_synthetic_test",P)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)


class FakePort:
    def __init__(self,answers=None):
        self.answers=answers or {};self.rx=bytearray();self.transmitted=[]
    def reset_input_buffer(self):self.rx.clear()
    def write(self,data):
        self.transmitted.append(bytes(data))
        self.rx.extend(b"\x05" if data==b"\x04" else self.answers.get(bytes(data),b""))
        return len(data)
    def flush(self):pass
    def read(self,n):
        result=self.rx[:n];del self.rx[:n]
        return bytes(result)
    def read_all(self):return self.read(len(self.rx))


class Tests(unittest.TestCase):
    def test_exact_read_opcodes_and_lengths(self):
        self.assertEqual(len(m.CASES),6)
        self.assertEqual(sum(v[2] for v in m.CASES.values()),8)
        self.assertEqual(m.CASES["gwg_cb_f8_1byte"][0],"01cbf80104")
        self.assertTrue(all(bytes.fromhex(s)[1] in (0xf7,0xc7,0xcb,0xc5)
                            for s,_,_ in m.CASES.values()))
        self.assertFalse(any(bytes.fromhex(s)[1] in (0xc4,0xc8,0xc3,0xad)
                             for s,_,_ in m.CASES.values()))
        with self.assertRaises(m.Refused):
            m.one_read(FakePort(),bytes.fromhex("01c8f80104"),1)
        with self.assertRaises(m.Refused):
            m.one_read(FakePort(),bytes.fromhex("01f700f804"),256)

    def test_requires_original_pinned_real_positive_capture(self):
        with self.assertRaises(m.previous.Refused):
            m.prerequisite(b"modified first capture")
        try:raw=Path(m.previous.ORIGINAL).read_bytes()
        except (FileNotFoundError,PermissionError):
            self.skipTest("private first real original absent")
        self.assertEqual(m.prerequisite(raw),m.previous.SHA)

    def test_rejects_unarmed_or_bad_config(self):
        with self.assertRaises(m.Refused):
            m.checks(execute=False,root=True,port_exists=True,
                     original=b"vs1protocol = True",timer=True)
        with self.assertRaises(m.Refused):
            m.checks(execute=True,root=False,port_exists=True,
                     original=b"vs1protocol = True",timer=True)
        with self.assertRaises(m.Refused):
            m.checks(execute=True,root=True,port_exists=True,
                     original=b"vs1protocol = True",timer=False)

    def test_simulated_old_cb_f8_and_c5_f8_no_reply_does_not_prove_rom(self):
        answers={
            bytes.fromhex("01f700f804"):m.EXPECTED_ID,
            bytes.fromhex("01c7f80804"):m.EXPECTED_ID8,
            bytes.fromhex("01c7f90304"):bytes.fromhex("c20003"),
        }
        fake=FakePort(answers)
        r=m.capture(fake,m.previous.SHA)
        self.assertEqual(r["total_read_requests"],8)
        self.assertTrue(r["gwg_c7_8byte_id_matches_vs1"])
        self.assertTrue(r["gwg_c7_f9_3byte_id_matches_vs1"])
        self.assertEqual(r["gwg_cb_f8_responses"],["",""])
        self.assertEqual(r["gwg_c5_f8_responses"],["",""])
        self.assertFalse(r["gwg_cb_c5_proven_20bit_rom_service"])
        self.assertEqual(r["controller_writes"],0)
        self.assertEqual([w.hex() for w in fake.transmitted[::2]],["04"]*8)

    def test_no_bad_baseline_can_reach_gwg(self):
        bad=FakePort({bytes.fromhex("01f700f804"):bytes.fromhex("20980002")})
        with self.assertRaises(m.Refused):
            m.capture(bad,m.previous.SHA)
        self.assertEqual([x.hex() for x in bad.transmitted],
                         ["04","01f700f804"])


if __name__=="__main__":unittest.main()
