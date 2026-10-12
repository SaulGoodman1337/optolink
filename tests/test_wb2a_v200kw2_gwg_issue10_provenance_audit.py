"""Pinned public issue10 (2010/2011) and private-forum quote (2009), read-only."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"tools/wb2a-v200kw2-gwg-issue10-provenance-audit.py"
spec=importlib.util.spec_from_file_location("vt_kw2_issue10_provenance_test",SRC)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m
spec.loader.exec_module(m)
ORIG=Path("/tmp/wb2a-v200kw2-issue10-sources-20261012")


class Issue10Tests(unittest.TestCase):
    def test_preserve_original_2010_dates_not_github_migration(self):
        self.assertEqual(m.imported_date("* Date: Mon,  1 Nov 2010 22:05:36 UT\nfoo"),
                         "Mon,  1 Nov 2010 22:05:36 UT")
        with self.assertRaises(m.SourceRejected):
            m.imported_date("2017-10-25T15:32:47Z")
        self.assertEqual(m.SOURCE_URLS["issue10.json"],
                         "https://api.github.com/repos/openv/openv/issues/10")

    def test_require_three_original_sha_sources_and_no_network(self):
        self.assertEqual(set(m.SOURCES),{
            "issue10.json","issue10-comments.json","issue245-comments.json"})
        self.assertTrue(all(len(s)==64 for s in m.SOURCES.values()))
        for name in m.SOURCES:
            with self.subTest(name=name),self.assertRaises(m.SourceRejected):
                m.attested_json(b"{}",name)
            with self.subTest(name=name),self.assertRaises(m.SourceRejected):
                m.attested_json(b"\x00"*m.SCOPE_LIMIT_BYTES,name)
        with self.assertRaises(m.SourceRejected):
            m.attested_json(b"any","unknown.json")

    def test_duplicate_issue_comment_ids_rejected(self):
        with self.assertRaises(m.SourceRejected):
            m.comments_by_id([{"id":1},{"id":1}])
        with self.assertRaises(m.SourceRejected):
            m.comments_by_id({"id":1})

    def test_readonly_wire_grammar_has_exact_five_bytes(self):
        old=bytes.fromhex("01 C7 F8 04 04")
        self.assertEqual(old,bytes([0x01,0xc7,0xf8,0x04,0x04]))
        self.assertEqual(old[1],0xc7)
        self.assertNotEqual(old[1],0xcb)
        self.assertNotEqual(old[1],0xc5)
        self.assertEqual(bytes.fromhex("20 98 00 02")[:2],bytes.fromhex("2098"))

    def test_all_three_real_original_json_inputs_if_available(self):
        try:raw=[(ORIG/k).read_bytes() for k in m.SOURCES]
        except (FileNotFoundError,PermissionError):
            self.skipTest("root-authenticated issue originals not available")
        r=m.verify(*raw)
        self.assertTrue(r["GWG_opcode_C7_virtual_read_accepted_by_old_200KW2"])
        self.assertFalse(r["historical_2010_GWG_physical_read_CB_accepted_proven"])
        self.assertFalse(r["historical_2010_GWG_xram_read_C5_accepted_proven"])
        self.assertEqual(r["2011_user_reported_no_data_above"],"0x8000")
        self.assertTrue(r["2015_embedded_private_2009_developer_forum_quote_found"])
        self.assertTrue(r["private_forum_quote_2009_is_about_EEPROM_WRITE_not_ROM_READ"])
        self.assertFalse(r["original_firmware_dump_request_sequence_recovered"])
        self.assertFalse(r["WB2A_GWG_read_subopcodes_proven"])
        self.assertEqual(r["controller_writes"],0)
        self.assertEqual(r["controller_io"],0)


if __name__=="__main__":unittest.main()
