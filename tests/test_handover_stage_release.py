"""Local-only release staging contract; never changes installed systemd files."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from handover_acceleration.stage_release import stage, StageRejected
from handover_acceleration.producer_boundary_patch import TARGETS
from test_handover_producer_boundary_patch import source_for
from test_handover_dispatcher_patch import UPSTREAM_EXCERPT


class ReleaseStagingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.srcdir=self.root/"source"
        self.srcdir.mkdir()
        self.source_map={}
        for role in TARGETS:
            p=self.srcdir/(role+".py")
            p.write_text(source_for(role))
            self.source_map[role]=p
        self.main=self.srcdir/"original.py"
        self.main.write_text(UPSTREAM_EXCERPT)
        self.target=self.root/"candidate"

    def stage(self):
        return stage(target=self.target,
                     source_map=self.source_map,
                     original_main=self.main)

    def test_staged_only_generates_exact_five_writers_and_proof_manifest(self):
        manifest=self.stage()
        self.assertEqual(manifest["state"],"STAGED_ONLY_NOT_DEPLOYED")
        self.assertFalse(manifest["prod_services_changed"])
        self.assertIn("main/optolinkvs2_switch.py",manifest["generated_files"])
        self.assertGreaterEqual(len(manifest["generated_files"]),10)
        self.assertEqual(len(manifest["writer_sources"]),5)
        self.assertEqual((self.target/"stage-manifest.json").stat().st_mode & 0o077,0)
        for role,path in self.source_map.items():
            dest=(self.target/("src" if role=="maintenance" else "bin")/path.name)
            self.assertTrue(dest.is_file(),role)
            self.assertIn("# HYBRID_PRODUCER_EPOCH_V1",dest.read_text())
            self.assertNotIn("# HYBRID_PRODUCER_EPOCH_V1",path.read_text())
        self.assertNotIn("RESEARCH_SHIM_V1",self.main.read_text())
        self.assertIn("RESEARCH_SHIM_V1",(self.target/"main/optolinkvs2_switch.py").read_text())
        self.assertEqual(json.loads((self.target/"stage-manifest.json").read_text()),
                         manifest)

    def test_second_stage_refuses_to_overwrite_existing_candidate(self):
        self.stage()
        with self.assertRaisesRegex(StageRejected,"never overwrite"):
            self.stage()

    def test_symlink_writer_and_missing_role_never_create_a_stage(self):
        self.source_map["party"].unlink()
        self.source_map["party"].symlink_to(self.source_map["schedule"])
        with self.assertRaisesRegex(StageRejected,"unsafe writer"):
            self.stage()
        self.assertFalse(self.target.exists())
        self.source_map.pop("party")
        with self.assertRaisesRegex(StageRejected,"exactly five"):
            self.stage()
        self.assertFalse(self.target.exists())


if __name__=="__main__":
    unittest.main()
