"""Only classify literal LE16 occurrences; never imply code pointers."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"tools/wb2a-vitotrol-rx-meta-pointer-xref.py"
spec=importlib.util.spec_from_file_location("vt_meta_pointer_xref_tests",SRC)
m=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=m
spec.loader.exec_module(m)
ARCH=Path("/root/p300-trial-work/research-bundles/p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz")


class PointerXrefTests(unittest.TestCase):
    def test_little_endian_non_aligned_search(self):
        b=bytearray(20480)
        for addr,target in ((0x400,0x166a),(0x401,0x166b),(0x540,0x1642)):
            raw=target.to_bytes(2,"little")
            b[addr-0x400:addr-0x400+2]=raw
        rows=m.literal_hits(bytes(b))
        self.assertIn(0x401,rows["0x166b"])
        self.assertIn(0x540,rows["0x1642"])
        # 0x166a was overwritten by unaligned 166b at +1.
        self.assertNotIn(0x400,rows["0x166a"])

    def test_bad_memory_width_rejected(self):
        with self.assertRaises(m.InvalidArchive):
            m.literal_hits(bytes(32))
        with self.assertRaises(m.InvalidArchive):
            m.literal_hits(bytes(20480),(0x60000,))

    def test_forged_archive_rejected(self):
        with self.assertRaises(m.InvalidArchive):
            m.scan(b"not actual source")

    def test_private_original_if_available(self):
        try:blob=ARCH.read_bytes()
        except (FileNotFoundError,PermissionError):
            self.skipTest("original private fullram not accessible")
        report=m.scan(blob)
        self.assertEqual(report["samples"],79)
        self.assertEqual(report["targets"]["0x166a"]["positions_observed_79_of_79"],
                         ["0x2185","0x51a1"])
        self.assertEqual(report["targets"]["0x166b"]["distinct_hit_addresses"],0)
        self.assertEqual(report["targets"]["0x1642"]["positions_observed_79_of_79"],
                         ["0x0b6d","0x33a3"])
        self.assertFalse(report["literal_hit_proves_pointer"])
        self.assertEqual(report["controller_writes"],0)


if __name__=="__main__":unittest.main()
