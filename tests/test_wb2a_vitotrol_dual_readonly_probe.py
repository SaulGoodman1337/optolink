"""Tests for fixed read-only real-P300 candidate probe; never talk to device."""
from __future__ import annotations
from pathlib import Path
import importlib.util
import sys
import types
import unittest

SRC = Path(__file__).resolve().parents[1] / "tools/wb2a-vitotrol-dual-readonly-probe.py"
spec = importlib.util.spec_from_file_location("wb2a_dual_readonly_probe_tests", SRC)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def fake(cmd: str, *, code=1, data=None):
    assert cmd in m.ALLOWED
    addr, size = m.ALLOWED[cmd]
    if data is None:
        data = bytes(size)
    return f"{cmd} <- openv/resp: {code};0x{addr:04x};{data.hex()}"


class DualReadOnlyTests(unittest.TestCase):
    def test_strict_operation_allowlist(self):
        self.assertTrue(any(c.startswith("request;99;") for c in m.ALLOWED))
        self.assertFalse(any(("writeraw;" in c or "request;4;" in c)
                             for c in m.ALLOWED))
        with self.assertRaises(m.Rejected):
            m.decode("request;4;0x1642;1;00", "", 0)

    def test_success_and_length_and_controller_error(self):
        cmd = m.RX_PROBES[0][0]
        self.assertTrue(m.decode(cmd, fake(cmd), 0)["valid_read"])
        with self.assertRaises(m.Rejected):
            m.decode(cmd, fake(cmd, data=b"\x00"), 0)
        out = m.decode(cmd, fake(cmd, code=5, data=b"\x05"), 0)
        self.assertFalse(out["valid_read"])
        with self.assertRaises(m.Rejected):
            m.hard(out)

    def test_reject_missing_duplicate_and_wrong_address(self):
        cmd = m.RX_PROBES[0][0]
        with self.assertRaises(m.Rejected):
            m.decode(cmd, "", 0)
        with self.assertRaises(m.Rejected):
            m.decode(cmd, fake(cmd) + fake(cmd), 0)
        with self.assertRaises(m.Rejected):
            m.decode(cmd, fake(cmd).replace("0x0b40", "0x0b41"), 0)
        with self.assertRaises(m.Rejected):
            m.decode(cmd, fake(cmd), 1)

    def test_read_only_full_mock(self):
        seen=[]
        def invoke(command):
            seen.append(command)
            if command == m.IDENTITY[0]:
                data=bytes.fromhex(m.EXPECTED_ID)
            else:
                data=bytes(m.ALLOWED[command][1])
            addr,size=m.ALLOWED[command]
            return m.decode(command, fake(command,data=data), 0)
        outcome=m.run(invoke_fn=invoke, cycles=2)
        self.assertEqual(outcome["controller_writes"],0)
        self.assertEqual(len(outcome["rx_samples"]),2)
        self.assertEqual(len(seen),1+4+4+len(m.ROM_READS)+len(m.INDIRECT_READS)+len(m.COPY_PROBES)+2*len(m.RX_PROBES))
        self.assertFalse(outcome["code_execution_or_rom_mapping_proven"])
        self.assertFalse(outcome["received_vitotrol_proven"])

    def test_indirect_failure_does_not_imply_rom_or_abort(self):
        def invoke(command):
            data=(bytes.fromhex(m.EXPECTED_ID) if command==m.IDENTITY[0]
                  else bytes(m.ALLOWED[command][1]))
            error=command in {x[0] for x in m.INDIRECT_READS[1:]}
            return m.decode(command,fake(command,code=5 if error else 1,
                                           data=b"\x05" if error else data),0)
        outcome=m.run(invoke_fn=invoke,cycles=1)
        self.assertEqual([x["valid_read"] for x in outcome["indirect_service"]],
                         [True] + [False]*(len(m.INDIRECT_READS)-1))
        self.assertFalse(outcome["code_execution_or_rom_mapping_proven"])

    def test_preflight_rejects_misidentified_or_active_remote(self):
        for wrong in ("identity","a0","fault"):
            def invoke(command):
                data=bytes(m.ALLOWED[command][1])
                if command==m.IDENTITY[0]:
                    data=bytes.fromhex(m.EXPECTED_ID)
                    if wrong=="identity":data=b"\x00"*8
                if command==m.BASELINE[0][0] and wrong=="a0":data=b"\x02"
                if command==m.BASELINE[3][0] and wrong=="fault":data=b"\x41"
                return m.decode(command,fake(command,data=data),0)
            with self.subTest(wrong=wrong),self.assertRaises(m.Rejected):
                m.run(invoke_fn=invoke,cycles=1)

    def test_high_only_aba_fixtures_are_not_rom_proof(self):
        seen=[]
        def inv(command):
            seen.append(command)
            data=(bytes.fromhex(m.EXPECTED_ID) if command==m.IDENTITY[0]
                  else bytes(m.ALLOWED[command][1]))
            return m.decode(command, fake(command,data=data),0)
        d=m.run_high(invoke_fn=inv,cycles=3)
        self.assertEqual(len(d["windows"]),3)
        self.assertEqual(len(seen),1+8+3*len(m.HIGH_PAIR_PROBES))
        self.assertFalse(d["rom_program_code_verified"])
        self.assertFalse(d["20bit_address_transported"])
        self.assertEqual(d["controller_writes"],0)
        for n in (0,1,5):
            with self.assertRaises(m.Rejected):
                m.run_high(cycles=n)

    def test_dma_occupancy_is_read_only_and_cannot_authorize_dma_reconfiguration(self):
        commands=[]
        def inv(cmd):
            commands.append(cmd)
            data=bytes.fromhex(m.EXPECTED_ID) if cmd==m.IDENTITY[0] else bytes(m.ALLOWED[cmd][1])
            return m.decode(cmd, fake(cmd,data=data), 0)
        report=m.run_dma(invoke_fn=inv,cycles=2)
        self.assertEqual(len(report["dma_snapshots"]),2)
        self.assertEqual(len(commands),1+2*len(m.BASELINE)+2*len(m.DMA_PROBES))
        self.assertEqual(report["controller_writes"],0)
        self.assertFalse(report["dma_triggered"])
        self.assertFalse(report["channel_reassignment_allowed"])
        for cmd in commands:
            self.assertNotIn("request;4;",cmd)
        for n in (1,7,-1,True,2.0):
            with self.assertRaises(m.Rejected):
                m.run_dma(cycles=n)

    def test_no_unbounded_cycles(self):
        for value in (0,4,1.0,True,-1):
            with self.assertRaises(m.Rejected):
                m.run(cycles=value)

    def test_source_has_no_write_transport(self):
        import ast
        tree=ast.parse(SRC.read_text())
        literals={n.value for n in ast.walk(tree)
                  if isinstance(n, ast.Constant) and isinstance(n.value,str)}
        self.assertFalse(any(s.startswith("writeraw;") or s.startswith("request;4;")
                             for s in literals))
        self.assertFalse(any(s=="serial" or s=="paho.mqtt.client" for s in literals))


if __name__ == "__main__":
    unittest.main()
