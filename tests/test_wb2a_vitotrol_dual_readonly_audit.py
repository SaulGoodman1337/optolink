"""Regression tests: strict offline audit of both P300 read paths."""
from __future__ import annotations
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/"tools/wb2a-vitotrol-dual-readonly-audit.py"
spec=importlib.util.spec_from_file_location("wb2a_dual_readonly_audit_fixture",P)
m=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=m
spec.loader.exec_module(m)
LIVE=(
 Path("/tmp/wb2a-vitotrol-dual-readonly-live-20261011.json"),
 Path("/tmp/wb2a-vitotrol-dual-readonly-high-live-20261011.json"),
 Path("/tmp/wb2a-vitotrol-dual-readonly-aba-live-20261011.json"),
)
MAIN_CMDS=[
 "request;3;0x0b40;32", "request;3;0x0b60;32", "request;3;0x161a;32",
 "request;3;0x1640;32", "request;3;0x0054;1",
 "request;3;0x03ac;2", "read;0x0a5c;4", "read;0x089c;1"
]
BASELINE=[f"read;0x{a:04x};1" for a in (0x27A0,0x27B0,0x7342,0x5738)]


def row(command, data=None):
    n=int(command.split(";")[-1])
    if data is None:data=bytes(n)
    return dict(command=command,code=1,data=data.hex(),valid_read=True)


def make_doc(mode="READ_ONLY_NATIVE_P300"):
    ret={"target":"20C2/0103","mode":mode,"controller_writes":0,
         "identity":row("read;0x00f8;8",bytes.fromhex("20c2000300000103")),
         "baseline":[row(x) for x in BASELINE],
         "after":[row(x) for x in BASELINE]}
    if mode=="READ_ONLY_NATIVE_P300":
        def make_sample(i):
            a=[]
            for cmd in MAIN_CMDS:
                raw=bytearray(int(cmd.split(";")[-1]))
                if cmd=="request;3;0x0b60;32":
                    raw[13:17]=bytes.fromhex("42160afe")
                if cmd=="request;3;0x03ac;2":
                    raw[:]=bytes.fromhex("1d07")
                a.append(row(cmd,bytes(raw)))
            return {"index":i,"rows":a}
        ret.update(rx_samples=[make_sample(0)],
                   rom_service=[row(f"request;3;0x{addr:04x};16") for addr in m.HIGH],
                   indirect_service=[row(f"request;99;0x{addr:04x};2") for addr in m.HIGH],
                   copy_context=[])
    else:
        arr=[]
        for addr in m.HIGH:
            arr.extend([row(f"request;3;0x{addr:04x};16"),
                        row(f"request;99;0x{addr:04x};2"),
                        row(f"request;99;0x{addr+2:04x};2")])
        ret["windows"]=[dict(index=0,rows=arr),dict(index=1,rows=copy.deepcopy(arr))]
    return ret


class AuditorTests(unittest.TestCase):
    def test_original_hardware_samples_when_available(self):
        if not all(p.is_file() for p in LIVE):
            self.skipTest("the three private original P300 live JSON files are unavailable")
        r=m.summarize(*[json.loads(p.read_text()) for p in LIVE])
        self.assertEqual(r["request_count"],123)
        self.assertEqual(len(r["high_address_ab_a"]),9)
        self.assertEqual(len(r["rx_samples"]),4)
        self.assertEqual(sum(x["same_first_two"] for x in r["high_address_ab_a"]),3)
        self.assertTrue(r["all_rx_descriptors_stable"])
        self.assertFalse(r["proven_20bit_rom_ingress"])
        self.assertFalse(r["any_physical_rx_irq_seen"])
        self.assertFalse(r["proven_vitotrol_registration"])
        self.assertFalse(r["any_room_sensor_valid_seen"])
        self.assertFalse(r["any_participant_swindex_seen"])
        self.assertTrue(all(x["same_bytes_at_separate_times"] for x in r["low_indirect_vs_ram"].values()))

    def test_synthetic_positive_pipeline_does_not_claim_rom(self):
        report=m.summarize(make_doc(),make_doc(),make_doc("HIGH_FC03_FC99_ABA_READ_ONLY"))
        self.assertFalse(report["proven_20bit_rom_ingress"])
        self.assertFalse(report["proven_firmware_dispatcher_entry"])
        self.assertEqual(len(report["rx_samples"]),2)

    def test_bad_identity_rejected(self):
        d=make_doc()
        d["identity"]["data"]="00"*8
        with self.assertRaises(m.EvidenceRejected):m.validate(d)

    def test_bad_controller_fault_rejected(self):
        d=make_doc()
        d["after"][-1]["data"]="41"
        with self.assertRaises(m.EvidenceRejected):m.validate(d)

    def test_unknown_write_rejected(self):
        d=make_doc()
        d["rom_service"].append(row("writeraw;0x27a0;1"))
        with self.assertRaises(m.EvidenceRejected):m.validate(d)

    def test_missing_uart_state_rejected(self):
        d=make_doc()
        d["rx_samples"][0]["rows"]=[x for x in d["rx_samples"][0]["rows"]
                                   if x["command"]!="request;3;0x03ac;2"]
        with self.assertRaises(m.EvidenceRejected):m.validate(d)

    def test_bad_high_aba_rejected(self):
        d=make_doc("HIGH_FC03_FC99_ABA_READ_ONLY")
        d["windows"][0]["rows"].pop()
        with self.assertRaises(m.EvidenceRejected):m.validate(d)

    def test_bad_length_rejected(self):
        d=make_doc()
        d["rx_samples"][0]["rows"][0]["data"]="00"
        with self.assertRaises(m.EvidenceRejected):m.validate(d)

    def test_no_device_transport_import(self):
        import ast
        src=ast.parse(P.read_text())
        imports=set()
        for node in ast.walk(src):
            if isinstance(node,ast.Import):
                imports.update(x.name.split(".")[0] for x in node.names)
            elif isinstance(node,ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        self.assertFalse(imports & {"serial","subprocess","socket","paho"})


if __name__=="__main__":
    unittest.main()
