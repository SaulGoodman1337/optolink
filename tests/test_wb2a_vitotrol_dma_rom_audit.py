"""Checks the read-only DMA ROM-bridge gate using synthetic and private live input."""
from __future__ import annotations
from pathlib import Path
import importlib.util
import sys
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "tools" / "wb2a-vitotrol-dma-rom-audit.py"
spec = importlib.util.spec_from_file_location("wb2a_dma_rom_readonly_audit", P)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)
LIVE=Path("/tmp/wb2a-vitotrol-dma-rom-occupancy-live-20261011.json")


def row(command, data: bytes):
    parts=command.split(";")
    adr=int(parts[2 if parts[0]=="request" else 1],16)
    return {"command":command,"address":f"0x{adr:04x}","data":data.hex(),
            "code":1,"valid_read":True}


def fake_document():
    a=bytearray(32)
    a[0:3]=(0x161b).to_bytes(3,"little")
    a[4:7]=(0x03aa).to_bytes(3,"little")
    a[8:10]=(8).to_bytes(2,"little")
    a[12]=0x15
    a[16:19]=(0x19af).to_bytes(3,"little")
    a[20:23]=(0x03a2).to_bytes(3,"little")
    a[24:26]=(8).to_bytes(2,"little")
    a[28]=0x15
    s={"target":"20C2/0103","mode":"M16C_DMA_ROM_BRIDGE_OCCUPANCY_READ_ONLY",
       "identity":row("read;0x00f8;8",bytes.fromhex(m.IDENTITY)),
       "controller_writes":0,"dma_triggered":False,
       "baseline":[row(c,bytes(1)) for c in m.BASELINE],
       "after":[row(c,bytes(1)) for c in m.BASELINE],
       "dma_snapshots":[]}
    for i in range(2):
        v=bytearray(a)
        v[8]=8+i
        s["dma_snapshots"].append({"index":i,
            "reads":[row(m.DMA_REG,bytes(v)),
                     row(m.DMA_TRIG,bytes.fromhex("0f000a00")),
                     row(m.SENSOR,bytes.fromhex("03")),
                     row(m.SWINDEX,bytes(4))]})
    return s


class DMAROMAuditorTests(unittest.TestCase):
    def test_synthetic_capture_cannot_authorize_dma_write(self):
        out=m.audit(fake_document())
        self.assertEqual(len(out["samples"]),2)
        self.assertTrue(out["all_channels_must_be_treated_as_owned"])
        self.assertFalse(out["viable_safe_live_dma_write_plan"])
        self.assertFalse(out["rom_data_obtained"])
        self.assertFalse(out["channels"][0]["dma_enabled_samples"])
        self.assertTrue(out["channels"][0]["nonconstant_transfer_count"])

    def test_live_captured_sfr_state_when_available(self):
        if not LIVE.is_file():
            self.skipTest("private Optolink hardware source unavailable")
        o=m.audit(json.loads(LIVE.read_text()))
        self.assertEqual(len(o["samples"]),5)
        self.assertEqual(o["channels"][0]["source_set"],["0x0161b","0x01621"])
        self.assertEqual(o["channels"][0]["dest_set"],["0x003aa"])
        self.assertEqual(o["channels"][1]["source_set"],["0x019af"])
        self.assertEqual(o["channels"][1]["dest_set"],["0x003a2"])
        self.assertEqual(o["channels"][0]["dma_enabled_samples"],1)
        self.assertEqual(o["channels"][1]["dma_enabled_samples"],0)
        self.assertEqual(o["channels"][0]["selectors"],["0x0f"])
        self.assertEqual(o["channels"][1]["selectors"],["0x0a"])
        self.assertTrue(all(r["remote_index"]=="00000000" and
                            r["sensor_status"]=="03" for r in o["samples"]))
        self.assertFalse(o["viable_safe_live_dma_write_plan"])

    def test_reject_nonread_control(self):
        x=fake_document()
        for attr,val in (("controller_writes",1),("dma_triggered",True)):
            bad=json.loads(json.dumps(x))
            bad[attr]=val
            with self.assertRaises(m.InvalidCapture):
                m.audit(bad)

    def test_reject_wrong_signature(self):
        x=fake_document()
        x["identity"]["data"]="00"*8
        with self.assertRaises(m.InvalidCapture):
            m.audit(x)

    def test_reject_wrong_baseline(self):
        x=fake_document()
        x["after"][3]["data"]="42"
        with self.assertRaises(m.InvalidCapture):
            m.audit(x)

    def test_reject_extra_command_or_short_read(self):
        x=fake_document()
        x["dma_snapshots"][0]["reads"][0]["data"]="00"
        with self.assertRaises(m.InvalidCapture):
            m.audit(x)
        x=fake_document()
        x["dma_snapshots"][0]["reads"][0]["command"]="request;4;0x0020;32"
        with self.assertRaises(m.InvalidCapture):
            m.audit(x)

    def test_reject_reserved_sar_bits(self):
        x=fake_document()
        src=x["dma_snapshots"][0]["reads"][0]
        content=bytearray.fromhex(src["data"])
        content[2]=0xF1
        src["data"]=bytes(content).hex()
        with self.assertRaises(m.InvalidCapture):
            m.audit(x)

    def test_reject_snapshot_overlap_and_address_mismatch(self):
        x=fake_document()
        x["dma_snapshots"][0]["index"]=1
        with self.assertRaises(m.InvalidCapture):
            m.audit(x)
        x=fake_document()
        x["dma_snapshots"][0]["reads"][0]["address"]="0x1234"
        with self.assertRaises(m.InvalidCapture):
            m.audit(x)

    def test_no_hardware_execution_modules(self):
        import ast
        tree=ast.parse(P.read_text())
        names=set()
        for n in ast.walk(tree):
            if isinstance(n,ast.Import):
                names.update(x.name.split(".")[0] for x in n.names)
            elif isinstance(n,ast.ImportFrom) and n.module:
                names.add(n.module.split(".")[0])
        self.assertFalse(names & {"subprocess","serial","socket","paho"})


if __name__=="__main__":
    unittest.main()
