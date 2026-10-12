"""Adversarial offline tests of OEM VitoSoft ROM-vs-routing wire semantics."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace as NS

SRC = Path(__file__).resolve().parents[1] / "tools" / "wb2a-vitosoft-oem-rom-wire-audit.py"
spec = importlib.util.spec_from_file_location("wb2a_oem_rom_wire_unit", SRC)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def op(name, value=None):
    if name in ("ldc.i4", "ldc.i4.s"):
        return NS(opcode=NS(name=name), operand=value)
    return NS(opcode=NS(name=name), operand=NS(value=value) if value is not None else None)


def rpc_example():
    # Synthetic oracle: real OEM SHA + method bodies checked by optional real test.
    return ([op("ldc.i4", 0xA400), op("ldc.i4", 0xA401)]
            + [op("callvirt", 0x060000E7)] * 2
            + [op("call", 0x0A0000F9)] * 2
            + [op("callvirt", 0x060000E8)] * 2
            + [op("ldc.i4.3")] * 3
            + [op("newarr")] * 2)


class OEMAddressAudit(unittest.TestCase):
    def test_real_source_hashes_expected(self):
        self.assertEqual(m.INSTALLER_SIZE, 425114319)
        self.assertEqual(m.CORE_SIZE, 368640)
        self.assertEqual(len(m.METHODS), 8)
        self.assertEqual(len(set(m.METHODS.values())), 8)

    def test_synthetic_alias_below_and_above_64k(self):
        for value, result, lost in (
            (0, "0x0000", False), (0xFFFF, "0xFFFF", False),
            (0xE0000, "0x0000", True), (0xF23FF, "0x23FF", True),
            (0xFFFFF, "0xFFFF", True),
        ):
            r = m.address_model(value)
            self.assertEqual(r["actual_ldap_address"], result)
            self.assertEqual(r["upper_bank_nibble_lost"], lost)
            self.assertEqual(len(bytes.fromhex(r["ldap_address_and_length_fields_hex"])), 3)

    def test_invalid_rom_address_and_length_rejected(self):
        for a, l in ((0x100000, 8), (-1, 8), (0xE0000, 255),
                     (0xF0000, -1), ("0xE0000", 8), (0xF0000, 0)):
            with self.assertRaises(m.OemAuditRejected):
                m.address_model(a, l)

    def test_correct_field_token_ownership(self):
        for label, group in (("VS1", m.VS1_FIELDS),
                             ("LDAP", m.LDAP_FIELDS),
                             ("RDAP", m.RDAP_FIELDS)):
            self.assertTrue(m.check_field_contract(dict(group), group, label))

    def test_mutated_field_token_rejected(self):
        fields = dict(m.RDAP_FIELDS)
        fields["AddressLength"] ^= 0x01
        with self.assertRaises(m.OemAuditRejected):
            m.check_field_contract(fields, m.RDAP_FIELDS, "RDAP")

    def test_ldap_serializer_contains_2byte_address(self):
        result = m.check_serializer_instructions(
            [op("ldfld", n) for n in m.LDAP_FIELDS.values()], kind="ldap")
        self.assertEqual(result["address_field_bytes"], 2)
        self.assertEqual(result["length_field_bytes"], 1)

    def test_ldap_must_not_use_rdap_routing_address(self):
        refs = list(m.LDAP_FIELDS.values()) + [m.RDAP_FIELDS["AddressLength"]]
        with self.assertRaises(m.OemAuditRejected):
            m.check_serializer_instructions([op("ldfld", n) for n in refs], kind="ldap")

    def test_missing_ldap_high_byte_is_not_accepted(self):
        refs = [v for k, v in m.LDAP_FIELDS.items() if k != "ADDRHighByte"]
        with self.assertRaises(m.OemAuditRejected):
            m.check_serializer_instructions([op("ldfld", n) for n in refs], kind="ldap")

    def test_vs1_correct_fixed_serializer(self):
        r = m.check_serializer_instructions(
            [op("ldfld", n) for n in m.VS1_FIELDS.values()], kind="vs1")
        self.assertEqual(r["address_field_bytes"], 2)

    def test_rdap_is_fieldbus_route_not_controller_rom_source(self):
        r = m.check_serializer_instructions(
            [op("ldfld", n) for n in m.RDAP_FIELDS.values()], kind="rdap")
        self.assertTrue(r["fieldbus_address_is_byte_array"])
        self.assertTrue(r["rdap_route_not_mcu_memory_address_proven"])

    def test_rdap_conflating_ldap_and_routing_rejected(self):
        refs = list(m.RDAP_FIELDS.values()) + [m.LDAP_FIELDS["ADDRHighByte"]]
        with self.assertRaises(m.OemAuditRejected):
            m.check_serializer_instructions([op("ldfld", n) for n in refs], kind="rdap")

    def test_correct_vitosorp_int16_rpc_contract(self):
        r = m.check_vitosorp_reads(
            rpc_example(),
            method_signature=bytes.fromhex("200007"),
            getbytes_signature=bytes.fromhex("00011d0507"),
        )
        self.assertEqual(r["rpc_code_read_hex"], "0xA400")
        self.assertEqual(r["rpc_code_write_hex"], "0xA401")
        self.assertEqual(r["address_bytes"], 2)
        self.assertFalse(r["controller_program_rom_source_address_supported_proven"])

    def test_vitosorp_wider_address_signature_rejected(self):
        with self.assertRaises(m.OemAuditRejected):
            m.check_vitosorp_reads(rpc_example(),
                                  method_signature=bytes.fromhex("200008"),
                                  getbytes_signature=bytes.fromhex("00011d0507"))

    def test_vitosorp_wider_bitconverter_overload_rejected(self):
        with self.assertRaises(m.OemAuditRejected):
            m.check_vitosorp_reads(rpc_example(),
                                  method_signature=bytes.fromhex("200007"),
                                  getbytes_signature=bytes.fromhex("00011d0508"))

    def test_vitosorp_other_rpc_code_rejected(self):
        fake = rpc_example()
        fake[0] = op("ldc.i4", 0xA499)
        with self.assertRaises(m.OemAuditRejected):
            m.check_vitosorp_reads(fake,
                                  method_signature=bytes.fromhex("200007"),
                                  getbytes_signature=bytes.fromhex("00011d0507"))

    def test_vitosorp_missing_address_conversion_rejected(self):
        fake = rpc_example()
        fake = [x for x in fake if not (x.opcode.name == "call" and
                                       getattr(x.operand, "value", None) == 0x0A0000F9)]
        with self.assertRaises(m.OemAuditRejected):
            m.check_vitosorp_reads(fake,
                                  method_signature=bytes.fromhex("200007"),
                                  getbytes_signature=bytes.fromhex("00011d0507"))

    def test_unknown_serializer_rejected(self):
        with self.assertRaises(m.OemAuditRejected):
            m.check_serializer_instructions([], kind="unreviewed")

    def test_fake_or_modified_original_rejected(self):
        with tempfile.TemporaryDirectory(prefix="wb2a-oem-fake-") as td:
            p = Path(td) / "fake.dll"
            p.write_bytes(b"MZ" + bytes(254))
            with self.assertRaises(m.OemAuditRejected):
                m.sha_ok(p, m.CORE_SIZE, m.CORE_SHA)

    def test_private_original_integrity_and_all_2490_real_il_methods(self):
        if not (m.CORE.is_file() and m.INSTALLER.is_file() and m.LIBS.is_dir()):
            self.skipTest("Official private OEM original is not available in CI")
        report = m.audit()
        self.assertEqual(report["audit"], "PASS")
        self.assertEqual(report["oem_core_clr_typedefs"], 206)
        self.assertEqual(report["oem_core_clr_methoddefs"], 2571)
        self.assertEqual(report["actual_cil_methods_parsed"], 2490)
        self.assertEqual(len(report["attested_method_bodies"]), 8)
        self.assertEqual(len(report["rdap_fieldbus_routing_methods"]), 2)
        self.assertEqual(report["firmware_bytes_extracted"], 0)

    def test_source_does_not_execute_heater_or_windows_binaries(self):
        source = SRC.read_text()
        for bad in ("subprocess.run(", "os.system(", "serial.Serial(",
                    "/dev/tty", "systemctl stop", "writeraw;", "execv(", "subprocess.Popen("):
            self.assertNotIn(bad, source)


if __name__ == "__main__":
    unittest.main()
