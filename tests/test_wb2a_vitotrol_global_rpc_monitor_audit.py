"""Global VitoSoft multi-byte RPC prefix audit (never invokes a controller)."""
from __future__ import annotations
import ast
from pathlib import Path
import importlib.util
import json
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/"tools/wb2a-vitotrol-global-rpc-monitor-audit.py"
spec=importlib.util.spec_from_file_location("wb2a_global_monitor_prefix_audit",P)
m=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=m
spec.loader.exec_module(m)
EVENTS=Path("/home/chatgpt-admin/research/vitosoft-lfs/ecnEventType.xml")
PROFILE=Path("/tmp/wb2a-globalrpc-exact-20c2-20261011.json")


def fake_xml(*rows):
    root=ET.Element("EventTypes")
    for item in rows:
        el=ET.SubElement(root,"EventType")
        for k,v in item.items():
            ET.SubElement(el,k).text=str(v)
    return ET.tostring(root)


def row(name,addr,fc="Remote_Procedure_Call",pfx="",wpfx=""):
    return {"ID":name,"Address":addr,"FCRead":fc,
            "FCWrite":fc,"PrefixRead":pfx,"PrefixWrite":wpfx}


def sample():
    return fake_xml(
        row("mBusRPCReadDataHeader000~0xA095","0xA095",pfx="000000"),
        row("mBusRPCReadDataHeader001~0xA095","0xA095",pfx="000100"),
        row("vlogRPCCreateLONChannel00~0xA066","0xA066",wpfx="0000"),
        row("SM1_Sensor_10_GWG2015~0x0F120","0x0F120",
            fc="Virtual_READ",pfx=""),
        row("ChecksummeROMBerechnet~0x08F0","0x08F0",fc="Virtual_READ"))


class GlobalMonitorAuditTests(unittest.TestCase):
    def test_padded_hex_is_not_20bit_and_3byte_prefix_is_not_rom(self):
        result=m.audit(sample(),sha_verified=False)
        self.assertEqual(result["event_count"],5)
        self.assertEqual(result["rpc_rows"],3)
        self.assertEqual(result["rpc_three_byte_prefix_read_count"],2)
        self.assertEqual(result["rpc_two_byte_prefix_write_count"],1)
        self.assertEqual(result["numeric_event_addresses_above_0xffff"],[])
        self.assertEqual(result["hex_event_addresses_with_leading_padding"][0]["numeric_value"],"0xf120")
        self.assertEqual(result["rpc_three_byte_groups"][0]["id_base"],"mBusRPCReadDataHeader")
        self.assertFalse(result["any_20bit_rom_memory_service_proven"])

    def test_true_over_16bit_hex_is_detected(self):
        r=m.audit(fake_xml(row("Hypothetical","0xF0123")),sha_verified=False)
        self.assertEqual(len(r["numeric_event_addresses_above_0xffff"]),1)
        self.assertEqual(r["numeric_event_addresses_above_0xffff"][0]["value"],0xF0123)
        self.assertFalse(r["any_20bit_rom_memory_service_proven"])

    def test_prefix_validation(self):
        self.assertEqual(m.as_prefix("000100"),bytes.fromhex("000100"))
        self.assertEqual(m.as_prefix("0x0E"),bytes.fromhex("0e"))
        self.assertEqual(m.as_prefix(""),b"")
        self.assertIsNone(m.as_prefix("FFF"))
        self.assertIsNone(m.as_prefix("zz"))

    def test_source_authenticity_enforced(self):
        with self.assertRaises(m.CatalogRejected):
            m.audit(sample())
        with self.assertRaises(m.CatalogRejected):
            m.audit(b"not xml" * 20,sha_verified=False)
        with self.assertRaises(m.CatalogRejected):
            m.audit(b"x"*13_000_000,sha_verified=False)

    def test_duplicate_id_rejected(self):
        p=row("Duplicate","0xA010")
        with self.assertRaises(m.CatalogRejected):
            m.audit(fake_xml(p,p),sha_verified=False)

    def test_wrong_target_profile_join_rejected(self):
        result=m.audit(sample(),sha_verified=False)
        with self.assertRaises(m.CatalogRejected):
            m.join_target_profile(result,{"device":"VDensHO1"})
        result["sha256_verified"]=True
        with self.assertRaises(m.CatalogRejected):
            m.join_target_profile(result,{"device":"VDensHO1","sha256_pinned":True,
               "source_kind":"VITOSOFT_HOST_XML_STATIC_ONLY",
               "device_id":"20C2","target_datapoint_type":60,
               "source_sha256":{"event":"wrong"}})

    def test_attested_real_global_catalog_if_available(self):
        if not EVENTS.is_file():
            self.skipTest("SHA-pinned VitoSoft source unavailable")
        r=m.audit(EVENTS.read_bytes())
        self.assertEqual(r["event_count"],11582)
        self.assertEqual(r["rpc_rows"],1034)
        self.assertEqual(r["rpc_read_rows"],1010)
        self.assertEqual(r["rpc_write_rows"],888)
        self.assertEqual(r["rpc_three_byte_prefix_read_count"],30)
        self.assertEqual(r["rpc_two_byte_prefix_write_count"],16)
        self.assertEqual(r["rpc_three_byte_groups"][0]["address"],"0xa095")
        self.assertEqual(r["rpc_three_byte_groups"][0]["rows"],30)
        self.assertEqual(r["rpc_two_byte_write_groups"][0]["address"],"0xa066")
        self.assertEqual(r["rpc_two_byte_write_groups"][0]["rows"],16)
        self.assertEqual(r["numeric_event_addresses_above_0xffff"],[])
        self.assertEqual(len(r["hex_event_addresses_with_leading_padding"]),1)
        self.assertEqual(r["malformed_prefix_count"],0)
        self.assertEqual(r["unparsed_address_count"],113)
        self.assertFalse(r["any_unknown_firmware_monitor_opcode_tested"])
        if PROFILE.exists():
            p=json.loads(PROFILE.read_text())
            linked=m.join_target_profile(r,p)["exact_target_profile"]
            self.assertEqual(linked["event_count"],581)
            self.assertEqual(linked["rpc_rows"],22)
            self.assertFalse(linked["mbus_a095_membership"])
            self.assertFalse(linked["any_rom_copy_monitor_label"])
            self.assertEqual(linked["rpc_addresses"],
                             ["0xa009","0xa010","0xa029","0xa050","0xa051"])

    def test_offline_static_only(self):
        imports=set()
        for node in ast.walk(ast.parse(P.read_text())):
            if isinstance(node,ast.Import):
                imports.update(n.name.split(".")[0] for n in node.names)
            elif isinstance(node,ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        self.assertFalse(imports & {"subprocess","serial","socket","paho","requests"})


if __name__=="__main__":
    unittest.main()
