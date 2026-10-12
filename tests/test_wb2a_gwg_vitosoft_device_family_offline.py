"""Offline synthetic and optional real-source VitoSoft device-family tests."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

SRC = Path(__file__).resolve().parents[1] / "tools" / "wb2a-gwg-vitosoft-device-family-offline.py"
spec = importlib.util.spec_from_file_location("gwg_vitosoft_family", SRC)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def fixture():
    pairs = (
        ("60", "VDensHO1"),
        ("208", "VDensHO1_4"),
        ("76", "GWG_VBEM_00"),
        ("148", "HV_GWG"),
        ("39", "GWG_VBEM_36"),
        ("49", "GWG_VBT2_21"),
    )
    return ("<root>" + "".join(
        f'<ecnDatapointType><Id>{ident}</Id><Address>{name}</Address></ecnDatapointType>'
        for ident, name in pairs
    ) + "</root>").encode()


class VitosoftDeviceFamilies(unittest.TestCase):
    def test_synthetic_separates_host_families(self):
        out = m.parse_rows(fixture(), pinned=False)
        self.assertEqual(out["vdensho1_type_id"], "60")
        self.assertEqual(out["gwg_vbem_00_type_id"], "76")
        self.assertTrue(out["VDensHO1_is_not_GWG_host_profile"])
        self.assertEqual(out["gwg_prefixed_type_count"], 3)
        self.assertFalse(out["GWG_2053_correspondence_to_a_specific_VitoSoft_type_proven"])
        self.assertFalse(out["MCU_ROM_access_inferred"])

    def test_duplicate_ids_rejected(self):
        s = fixture().replace(b"<Id>208</Id>", b"<Id>60</Id>")
        with self.assertRaises(m.CatalogRejected):
            m.parse_rows(s, pinned=False)

    def test_duplicate_profile_names_rejected(self):
        s = fixture().replace(b"GWG_VBEM_36", b"GWG_VBEM_00")
        with self.assertRaises(m.CatalogRejected):
            m.parse_rows(s, pinned=False)

    def test_wb2a_falsely_labeled_as_gwg_rejected(self):
        s = fixture().replace(b"VDensHO1_4", b"GWG_VBEM_21")
        with self.assertRaises(m.CatalogRejected):
            m.parse_rows(s, pinned=False)

    def test_missing_vbem_family_rejected(self):
        s = fixture().replace(b"GWG_VBEM_00", b"GWG_VBEM_01")
        with self.assertRaises(m.CatalogRejected):
            m.parse_rows(s, pinned=False)

    def test_fake_vdensho1_type_number_rejected(self):
        s = fixture().replace(b"<Id>60</Id>", b"<Id>55</Id>")
        with self.assertRaises(m.CatalogRejected):
            m.parse_rows(s, pinned=False)

    def test_corrupted_xml_rejected(self):
        s = fixture().replace(b"</Id>", b"</WrongTag>")
        with self.assertRaises(m.CatalogRejected):
            m.parse_rows(s, pinned=False)

    def test_unknown_pinned_revision_refused(self):
        with tempfile.TemporaryDirectory(prefix="gwg-vitosoft-synth-") as t:
            p = Path(t) / "DPDefinitions.xml"
            p.write_bytes(fixture())
            with self.assertRaises(m.CatalogRejected):
                m.audit(p, verify_sha=True)

    def test_synthetic_unpinned_audit_labels_source(self):
        with tempfile.TemporaryDirectory(prefix="gwg-vitosoft-synth-") as t:
            p = Path(t) / "DPDefinitions.xml"
            p.write_bytes(fixture())
            report = m.audit(p, verify_sha=False)
            self.assertEqual(report["audit"], "PASS")
            self.assertEqual(report["controller_writes"], 0)
            self.assertEqual(report["program_rom_bytes_read"], 0)
            self.assertEqual(report["source_kind"],
                             "VITOSOFT_HOST_CATALOG_NOT_CONTROLLER_FIRMWARE")

    def test_real_source_optional(self):
        if not m.DP.is_file():
            self.skipTest("Private 186-MB VitoSoft source not present in CI")
        result = m.audit(m.DP, verify_sha=True)
        self.assertEqual(result["source_sha256"], m.DP_SHA)
        self.assertEqual(result["host_profile_rows"], 399)
        self.assertEqual(result["gwg_prefixed_type_count"], 21)
        self.assertEqual(result["gwg_vbem_type_count"], 5)

    def test_program_never_uses_live_optolink(self):
        s = SRC.read_text()
        for fragment in ("serial.Serial(", "/dev/tty", "systemctl stop",
                         "optolink-debug", "socket.socket(", "subprocess.run("):
            self.assertNotIn(fragment, s)


if __name__ == "__main__":
    unittest.main()
