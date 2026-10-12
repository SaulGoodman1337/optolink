"""Attested two-original-binary comparison; no PE image ever executed."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest

P = Path(__file__).resolve().parents[1] / "tools/wb2a-optolinklogger-crossversion-rom-gate.py"
s = importlib.util.spec_from_file_location("historical_openv_net_crossversion_unit", P)
m = importlib.util.module_from_spec(s)
sys.modules[s.name] = m
s.loader.exec_module(m)


class CrossVersion(unittest.TestCase):
    def test_exact_two_source_versions_only(self):
        self.assertEqual(set(m.SOURCES), {"2010-02-06_v0.0.1",
                                          "2011-01-23_v0.0.4"})
        self.assertEqual(sum(k["size"] for k in m.SOURCES.values()), 249856)

    def test_both_accessor_definitions_contain_8bit_mask(self):
        for version, profile in m.SOURCES.items():
            self.assertEqual(len(bytes.fromhex(profile["methods"]["SetReadAddr"])), 33)
            self.assertEqual(len(bytes.fromhex(profile["methods"]["GetReadAddr"])), 22)
            self.assertEqual(len(bytes.fromhex(profile["methods"]["SetReadLen"])), 16)
            self.assertEqual(profile["methods"]["SetReadAddr"].count("20ff0000005fd29c"), 2)
            self.assertEqual(profile["methods"]["SetReadLen"].count("20ff0000005fd29c"), 1)

    def test_exact_historical_binary_audit_if_available(self):
        if not all(x["path"].is_file() for x in m.SOURCES.values()):
            self.skipTest("Historic OpenV 2010/2011 binaries only on LXC")
        report = m.audit()
        self.assertEqual(report["audit"], "PASS")
        self.assertEqual(report["original_revisions_attested"], 2)
        self.assertFalse(report["rom_transfer_with_optolinklogger_achievable"])
        self.assertEqual(report["controller_rom_bytes_extracted"], 0)
        for data in report["revisions"].values():
            self.assertTrue(data["method_setters_exact_source_backed"])
            self.assertTrue(data["dump_via_vs1_only"])
            self.assertEqual(data["max_direct_vs1_address"], "0xFFFF")
            self.assertEqual(data["request_address_bits"], 16)
            self.assertEqual(data["read_length_bits"], 8)
            self.assertEqual(data["chunk_limit_literal"], 254)
            self.assertEqual(list(data["accessor_call_counts_in_dump"].values()), [1]*4)

    def test_tampered_original_rejected(self):
        if not all(x["path"].is_file() for x in m.SOURCES.values()):
            self.skipTest("Historic OpenV 2010/2011 binaries only on LXC")
        a = {tag: v["path"].read_bytes() for tag, v in m.SOURCES.items()}
        altered = bytearray(a["2010-02-06_v0.0.1"])
        altered[-22] ^= 0x01
        a["2010-02-06_v0.0.1"] = bytes(altered)
        with self.assertRaises(m.CrossVersionRejected):
            m.audit(lambda name: a[name])

    def test_both_original_sha_are_unique(self):
        hashes = [x["sha"] for x in m.SOURCES.values()]
        self.assertEqual(len(set(hashes)), 2)

    def test_20bit_rom_addresses_alias_low16_via_original_setter(self):
        for address, low in ((0xE0000, "0x0000"), (0xF23FF, "0x23FF"),
                             (0xFFFFF, "0xFFFF")):
            data = m.model_original_vs1_address_setter(address, 8)
            self.assertEqual(data["actual_wire_address"], low)
            self.assertTrue(data["source_upper_4_bits_lost"])
            self.assertEqual(len(bytes.fromhex(data["actual_address_and_length_field_hex"])), 3)

    def test_unbounded_20bit_or_bad_length_refused(self):
        for addr, size in ((0x100000, 8), (-1, 8), (0xE0000, 0), (0xE0000, 255)):
            with self.assertRaises(m.CrossVersionRejected):
                m.model_original_vs1_address_setter(addr, size)

    def test_crossversion_is_offline_only(self):
        src = P.read_text()
        for forbidden in ('serial.Serial(', '/dev/tty', 'systemctl stop',
                          'optolink-debug', 'subprocess.run(', 'os.system('):
            self.assertNotIn(forbidden, src)


if __name__ == "__main__":
    unittest.main()
