"""Check observed WB2A 0x166A/B offset invariant on SHA-pinned sources."""
from __future__ import annotations
import ast
import importlib.util
import sys
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"tools/wb2a-vitotrol-rx-metadata-invariant.py"
spec=importlib.util.spec_from_file_location("wb2a_meta_invariant_tests",SRC)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m
spec.loader.exec_module(m)
FULL=Path("/root/p300-trial-work/research-bundles/p300-fullram-run-20261009T083607Z-144293-bundle.tar.gz")
EARLY=Path("/tmp/wb2a-vitotrol-fused-rx-live-20261011.json")
LATER=Path("/tmp/wb2a-vitotrol-master31-pair-live-20261011.json")


class MetaInvariantTests(unittest.TestCase):
    def test_known_pairs_difference(self):
        normal=m.verify_pair(6,0)
        rare=m.verify_pair(10,4)
        self.assertEqual(normal["difference_mod_256"],6)
        self.assertEqual(rare["difference_mod_256"],6)
        self.assertTrue(normal["first_is_second_plus_6"])
        self.assertTrue(rare["first_is_second_plus_6"])
        self.assertFalse(rare["firmware_owner_proven"])

    def test_not_all_pairs_have_difference_six(self):
        for x,y in ((10,0),(6,4),(0,0),(255,250)):
            with self.subTest(x=x,y=y):
                self.assertFalse(m.verify_pair(x,y)["first_is_second_plus_6"])
        # modulo 256 wrap is defined explicitly, but never observed on this WB2A.
        self.assertTrue(m.verify_pair(0,250)["first_is_second_plus_6"])

    def test_out_of_bound_or_bad_metadata_rejected(self):
        for x,y in ((-1,0),(0,-1),(256,0),(0,256),(True,0),(6,None)):
            with self.subTest(x=x,y=y),self.assertRaises(m.UntrustedEvidence):
                m.verify_pair(x,y)

    def test_wrong_source_sha_rejected(self):
        with self.assertRaises(m.UntrustedEvidence):
            m.evaluate(b"corrupt",b"corrupt",b"corrupt")
        with self.assertRaises(m.UntrustedEvidence):
            m.check_sha(b"x","00"*32,128)

    def test_real_original_attestation_if_available(self):
        try:inp=[q.read_bytes() for q in (FULL,EARLY,LATER)]
        except (FileNotFoundError,PermissionError):
            self.skipTest("root-only original 2026 captures unavailable")
        r=m.evaluate(*inp)
        self.assertEqual(r["total_pair_samples"],87)
        self.assertEqual(r["historical_166a166b_counts"],{"0600":78,"0a04":1})
        self.assertEqual(r["new_same_fc03_166a166b_counts"],{"0600":8})
        self.assertEqual(r["previous_crc_end_to_166a_single_copy_counts"],
                         {"53|0a":1,"c6|06":15})
        self.assertEqual(r["new_crc_end_to_166a_single_copy_counts"],
                         {"53|06":1,"c6|06":15})
        self.assertTrue(r["all_observed_166a_minus_166b_mod_256_is_6"])
        self.assertFalse(r["meta_pair_is_ring_buffer_or_ISR_flag_proven"])
        self.assertEqual(r["controller_writes"],0)

    def test_pure_offline_no_active_connection(self):
        imports=set()
        for node in ast.walk(ast.parse(SRC.read_text())):
            if isinstance(node,ast.Import):
                imports.update(x.name.split(".")[0] for x in node.names)
            elif isinstance(node,ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        self.assertFalse(imports & {"serial","subprocess","socket","requests","paho"})


if __name__=="__main__":unittest.main()
