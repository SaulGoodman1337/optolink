"""Mutational tests of original OpenV .NET CLR/IL ROM-dump boundary audit."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest

P = Path(__file__).resolve().parents[1] / "tools/wb2a-optolinklogger-cli-metadata-audit.py"
s = importlib.util.spec_from_file_location("netcli_original_tools_unit", P)
m = importlib.util.module_from_spec(s)
sys.modules[s.name] = m
s.loader.exec_module(m)


class NETCliOffline(unittest.TestCase):
    def test_compressed_one_byte(self):
        self.assertEqual(m.compressed(bytes((0x2A,)), 0), (42, 1))

    def test_compressed_two_byte(self):
        self.assertEqual(m.compressed(bytes((0x81, 0x03)), 0), (259, 2))

    def test_compressed_four_byte(self):
        self.assertEqual(m.compressed(bytes((0xC0, 0x01, 0x00, 0x00)), 0),
                         (65536, 4))

    def test_invalid_compressed_uint_rejected(self):
        with self.assertRaises(m.MetadataRejected):
            m.compressed(bytes((0xE2,)), 0)

    def test_truncated_compressed_uint_rejected(self):
        with self.assertRaises(m.MetadataRejected):
            m.compressed(bytes((0xC0,)), 0)

    def test_valid_user_string(self):
        # 5 bytes raw: 'OK' UTF16LE + terminal one-byte flag.
        self.assertEqual(m.user_string(b"\x00\x05O\x00K\x00\x00", 0x70000001), "OK")

    def test_wrong_user_string_token_rejected(self):
        with self.assertRaises(m.MetadataRejected):
            m.user_string(b"\x00\x05O\x00K\x00\x00", 0x06000001)

    def test_invalid_user_string_bounds_rejected(self):
        with self.assertRaises(m.MetadataRejected):
            m.user_string(b"\x00\x20A", 0x70000001)

    def test_false_binary_not_pe(self):
        with self.assertRaises(m.MetadataRejected):
            m.file_rva_reader(b"ABCD" + bytes(256))

    def test_missing_original_rom_dump_methods_rejected(self):
        with self.assertRaises(m.MetadataRejected):
            m.validate_2011_dump_contract([], strict=True)

    def test_exact_set_read_addr_two_wire_bytes(self):
        self.assertEqual(len(m.ADDR_IL), 33)
        self.assertEqual(m.ADDR_IL.count(bytes.fromhex("20ff0000005fd29c")), 2)
        self.assertEqual(len(m.LEN_IL), 16)
        self.assertEqual(m.LEN_IL.count(bytes.fromhex("20ff0000005fd29c")), 1)

    def test_source_file_no_execution_or_heater_transport(self):
        source = P.read_text()
        for keyword in ("subprocess.run(", "os.system(", "serial.Serial(",
                        "/dev/tty", "optolink-debug request", "systemctl stop"):
            self.assertNotIn(keyword, source)

    def test_optional_original_binary_sha_and_true_contract(self):
        if not m.DEFAULT.is_file():
            self.skipTest("Private historic .NET original not available in CI")
        payload = m.DEFAULT.read_bytes()
        r = m.audit(payload, pinned=True)
        self.assertEqual(r["audit"], "PASS")
        self.assertTrue(r["vs1_dump_guard_literally_referenced"])
        self.assertTrue(r["verified_dump_wire_contract"]["address_setter_exact_original_il"])
        self.assertEqual(r["verified_dump_wire_contract"]["vs1_primitive_wire_address_bytes"], 2)
        self.assertTrue(r["verified_dump_wire_contract"]["high_20bit_cpu_address_not_transmitted"])
        self.assertEqual(r["program_rom_dump_bytes"], 0)

    def test_optional_falsified_real_binary_rejected(self):
        if not m.DEFAULT.is_file():
            self.skipTest("Private historic .NET original not available in CI")
        b = bytearray(m.DEFAULT.read_bytes())
        b[8000] ^= 0x01
        with self.assertRaises(m.MetadataRejected):
            m.audit(bytes(b), pinned=True)

    def test_optional_original_method_il_modified_rejected(self):
        if not m.DEFAULT.is_file():
            self.skipTest("Private historic .NET original not available in CI")
        b = bytearray(m.DEFAULT.read_bytes())
        r, st, _ = m.file_rva_reader(b)
        rows, _ = m.method_directory(st)
        setter = next(row for row in rows if row["name"] == "SetReadAddr")
        location = r(setter["rva"])
        head = (b[location] >> 2) * 4 if b[location] & 3 == 3 else 1
        self.assertGreater(len(b), location + head + 12)
        b[location + head + 12] ^= 0x01
        with self.assertRaises(m.MetadataRejected):
            m.audit(bytes(b), pinned=True)


if __name__ == "__main__":
    unittest.main()
