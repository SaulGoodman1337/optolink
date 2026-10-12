"""Offline mutation tests for independently pinned GWG source/evidence gate.

Tiny synthetic fixtures model historical declarations but are NOT passed off as
the original ROM dump or source archive. Real source+capture integration is
executed separately via sudo and pinned SHA256 on the research LXC.
"""
from __future__ import annotations
import copy
import importlib.util
import pathlib
import sys
import unittest

P = pathlib.Path(__file__).resolve().parents[1] / "tools" / "wb2a-gwg-source-and-rom-boundary-audit.py"
spec = importlib.util.spec_from_file_location("gwg_source_boundary_test", P)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def sources():
    return {
        "wiki": (b"VIRTUAL READ | 01 | C7\n"
                 b"EEPROM READ | 05 | AE\n"
                 b"PHYSICAL PORT READ | 51 | 6E\n"
                 b"PHYSICAL XRAM READ | 49 | C5\n"
                 b"PHYSICAL READ | 03 | CB\n"
                 b"PHYSICAL BE READ | 53 | 9E\n"),
        "vito": b'''<vito><commands>
          <command name="getBrennerStunden1">
            <device ID="2053" protocmd="geteaddr"><addr>17</addr><len>2</len></device>
          </command>
          <command name="getVentilStatus" protocmd="getpaddr">
            <device ID="2053"><addr>01</addr><len>1</len></device>
          </command>
        </commands></vito>''',
        "protocol": b'''<V-Control><protocol name="GWG"><macros>
          <macro name="GETVADDR"><command>SEND 01 C7</command></macro>
          <macro name="GETEADDR"><command>SEND 01 AE</command></macro>
          <macro name="GETPADDR"><command>SEND 01 6E</command></macro>
        </macros></protocol></V-Control>''',
        "re_notes": (b"GWG protocol is no longer supported by the Vitosoft 300 application.\n"
                     b"The reply should be `0x20,0x53` or `0x20,0x54` to detect GWG hardware.\n"),
    }


def c7():
    return {"audit": "PASS", "reads": 7, "controller_writes": 0,
            "recovered_rom_bytes": 0, "source_sha256": mod.LOGS["c7"][1]}


def legacy():
    return {"audit": "PASS", "reads": 8, "controller_memory_writes": 0,
            "program_rom_bytes_read": 0, "physical_port_semantics_proven": False,
            "eeprom_ae_17_reads": 2, "eeprom_ae_17_responses": 0,
            "port_6e_01_reads": 2, "port_6e_01_hex_replies": ["00", "00"],
            "source_sha256": mod.LOGS["legacy"][1]}


class Sources(unittest.TestCase):
    def test_minimal_valid_archive_and_detect(self):
        result = mod.inspect_sources(sources(), pin=False)
        self.assertEqual(result["historical_vcontrold_device"], "2053")
        self.assertEqual(result["2053_read_frames"]["getVentilStatus"], "016e010104")
        self.assertEqual(result["expected_gwg_identifiers_from_re_notes"], ["2053", "2054"])
        self.assertEqual(result["gwg_address_bits"], 8)

    def test_mismatched_source_sha_fails(self):
        with self.assertRaises(mod.EvidenceRejected):
            mod.inspect_sources(sources(), pin=True)

    def test_missing_source_rejected(self):
        s = sources()
        del s["wiki"]
        with self.assertRaises(mod.EvidenceRejected):
            mod.inspect_sources(s, pin=False)

    def test_wrong_wiki_opcode_rejected(self):
        s = sources()
        s["wiki"] = s["wiki"].replace(b"READ | 01 | C7", b"READ | 01 | C8")
        with self.assertRaises(mod.EvidenceRejected):
            mod.inspect_sources(s, pin=False)

    def test_duplicate_wiki_read_type_rejected(self):
        s = sources()
        s["wiki"] += b"VIRTUAL READ | 01 | C7\n"
        with self.assertRaises(mod.EvidenceRejected):
            mod.inspect_sources(s, pin=False)

    def test_wrong_eeprom_opcode_rejected(self):
        s = sources()
        s["protocol"] = s["protocol"].replace(b"SEND 01 AE", b"SEND 01 AD")
        with self.assertRaises(mod.EvidenceRejected):
            mod.inspect_sources(s, pin=False)

    def test_wrong_port_opcode_rejected(self):
        s = sources()
        s["protocol"] = s["protocol"].replace(b"SEND 01 6E", b"SEND 01 6D")
        with self.assertRaises(mod.EvidenceRejected):
            mod.inspect_sources(s, pin=False)

    def test_wrong_2053_address_rejected(self):
        s = sources()
        s["vito"] = s["vito"].replace(b"<addr>17</addr>", b"<addr>18</addr>")
        with self.assertRaises(mod.EvidenceRejected):
            mod.inspect_sources(s, pin=False)

    def test_wrong_device_profile_rejected(self):
        s = sources()
        s["vito"] = s["vito"].replace(b'ID="2053"', b'ID="20C2"')
        with self.assertRaises(mod.EvidenceRejected):
            mod.inspect_sources(s, pin=False)

    def test_extra_2053_target_rejected(self):
        s = sources()
        s["vito"] = s["vito"].replace(
            b'<device ID="2053" protocmd="geteaddr">',
            b'<device ID="2053" protocmd="geteaddr"><addr>17</addr><len>2</len></device>'
            b'<device ID="2053" protocmd="geteaddr">')
        with self.assertRaises(mod.EvidenceRejected):
            mod.inspect_sources(s, pin=False)

    def test_detector_target_swapped_to_20c2_rejected(self):
        s = sources()
        s["re_notes"] = s["re_notes"].replace(b"0x20,0x53", b"0x20,0xC2")
        with self.assertRaises(mod.EvidenceRejected):
            mod.inspect_sources(s, pin=False)

    def test_vendor_provenance_is_not_assumed(self):
        a = mod.inspect_sources(sources(), pin=False)
        self.assertEqual(a["source_kinds"]["re_notes"],
                         "THIRD_PARTY_VITOSOFT_REVERSE_ENGINEERING_NOT_VENDOR_SOURCE")

    def test_invalid_xml_rejected(self):
        s = sources()
        s["vito"] = b"<not-xml>"
        with self.assertRaises(mod.EvidenceRejected):
            mod.inspect_sources(s, pin=False)


class ROMBoundary(unittest.TestCase):
    def setUp(self):
        self.s = mod.inspect_sources(sources(), pin=False)
        self.c = c7()
        self.l = legacy()

    def test_realistic_crosscomparison_strictly_negative_for_rom(self):
        r = mod.combine(self.s, self.c, self.l)
        self.assertEqual(r["audit"], "PASS")
        self.assertEqual(r["observed_controller_id"], "20c2")
        self.assertFalse(r["legacy_gwg_detector_matches_20c2"])
        self.assertFalse(r["twenty_bit_program_rom_read_supported_by_evidence"])
        self.assertTrue(r["require_separate_20bit_monitor_or_copier_evidence"])
        self.assertFalse(r["native_gwg_stack_implementation_proven"])
        self.assertEqual(r["program_rom_bytes_read"], 0)

    def test_fake_wbg_rom_c7_capture_rejected(self):
        self.c["recovered_rom_bytes"] = 256
        with self.assertRaises(mod.EvidenceRejected):
            mod.combine(self.s, self.c, self.l)

    def test_fake_successful_rom_legacy_capture_rejected(self):
        self.l["program_rom_bytes_read"] = 16
        with self.assertRaises(mod.EvidenceRejected):
            mod.combine(self.s, self.c, self.l)

    def test_6e_semantics_claim_rejected(self):
        self.l["physical_port_semantics_proven"] = True
        with self.assertRaises(mod.EvidenceRejected):
            mod.combine(self.s, self.c, self.l)

    def test_6e_inconsistent_second_read_rejected(self):
        self.l["port_6e_01_hex_replies"] = ["00", "01"]
        with self.assertRaises(mod.EvidenceRejected):
            mod.combine(self.s, self.c, self.l)

    def test_ae_falsely_successful_rejected(self):
        self.l["eeprom_ae_17_responses"] = 2
        with self.assertRaises(mod.EvidenceRejected):
            mod.combine(self.s, self.c, self.l)

    def test_2053_vs_20c2_swap_rejected(self):
        self.s["historical_vcontrold_device"] = "20C2"
        with self.assertRaises(mod.EvidenceRejected):
            mod.combine(self.s, self.c, self.l)

    def test_fabricated_extra_read_rejected(self):
        self.c["reads"] = 8
        with self.assertRaises(mod.EvidenceRejected):
            mod.combine(self.s, self.c, self.l)

    def test_missing_c7_audit_rejected(self):
        self.c["audit"] = "SKIPPED"
        with self.assertRaises(mod.EvidenceRejected):
            mod.combine(self.s, self.c, self.l)

    def test_controller_write_rejected(self):
        self.l["controller_memory_writes"] = 1
        with self.assertRaises(mod.EvidenceRejected):
            mod.combine(self.s, self.c, self.l)

    def test_20bit_field_claim_rejected(self):
        self.s["gwg_address_bits"] = 20
        with self.assertRaises(mod.EvidenceRejected):
            mod.combine(self.s, self.c, self.l)

    def test_both_legacy_detector_ids_must_be_consistent(self):
        self.s["expected_gwg_identifiers_from_re_notes"] = ["20c2"]
        with self.assertRaises(mod.EvidenceRejected):
            mod.combine(self.s, self.c, self.l)

    def test_program_is_offline_only(self):
        src = P.read_text()
        for forbidden in ("serial.Serial(", "/dev/tty", "systemctl stop",
                          "optolink-debug request", "socket.socket("):
            self.assertNotIn(forbidden, src)


if __name__ == "__main__":
    unittest.main()
