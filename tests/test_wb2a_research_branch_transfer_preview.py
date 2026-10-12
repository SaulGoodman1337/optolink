"""Tests for selective READ-ONLY optolink-research transfer planning.

These tests build ephemeral synthetic Git repositories in /tmp. They never
merge, modify or checkout the real research branch.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SRC = Path(__file__).resolve().parents[1] / "tools" / "wb2a-research-branch-transfer-preview.py"
spec = importlib.util.spec_from_file_location("wb2a_transfer_readonly", SRC)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def git(repo, *args):
    x = subprocess.run(["git", "-C", str(repo), *args],
                       capture_output=True, text=True, check=True)
    return x.stdout.strip()


class SyntheticGit(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="research-transfer-test-")
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.name", "Synthetic Offline Test")
        git(self.repo, "config", "user.email", "noreply@example.invalid")
        self.write("README.md", "original only\n")
        self.commit("initial")
        self.root = git(self.repo, "rev-parse", "HEAD")

    def write(self, name, content):
        file = self.repo / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content)

    def commit(self, message):
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", message)

    def branch(self, name, start="HEAD"):
        git(self.repo, "checkout", "-q", "-B", name, start)

    def generate(self, source_extra=None, target_extra=None):
        self.branch("optolink-research", self.root)
        self.write("docs/wb2a-gwg-mutual.md", "base\n")
        self.write("docs/README.md", "research-index\n")
        self.commit("research basic")
        ancestor = git(self.repo, "rev-parse", "HEAD")
        if target_extra:
            for path, value in target_extra.items():
                self.write(path, value)
            self.commit("research only changes")
        self.branch("feature", ancestor)
        self.write("docs/wb2a-gwg-mutual.md", "feature\n")
        self.write("tools/wb2a-gwg-legacy-feature.py", "reader = True\n")
        self.write("docs/README.md", "production-index-must-not-transfer\n")
        self.write("config/optolink-splitter/prod-config.py", "not research\n")
        if source_extra:
            for path, value in source_extra.items():
                self.write(path, value)
        self.commit("feature ROM results")
        return m.preview(self.repo, "feature", "optolink-research")


class TransferPreviewTests(SyntheticGit):
    def test_selective_artifacts_only(self):
        p = self.generate()
        self.assertEqual(p["kind"], "READ_ONLY_BRANCH_IMPORT_PLAN_NOT_A_MERGE")
        self.assertFalse(p["merge_performed"])
        self.assertEqual(p["candidate_file_count"], 2)
        self.assertEqual(p["new_files"], 1)
        self.assertEqual(p["review_replacements"], 1)
        self.assertEqual(p["conflicts"], 0)
        self.assertEqual({x["path"] for x in p["files"]},
                         {"docs/wb2a-gwg-mutual.md", "tools/wb2a-gwg-legacy-feature.py"})
        self.assertEqual(p["docs_index_requires_manual_review"], "docs/README.md")

    def test_source_and_target_independent_changes_alert(self):
        p = self.generate(target_extra={"docs/wb2a-gwg-mutual.md": "research edited\n"})
        bypath = {x["path"]: x for x in p["files"]}
        self.assertEqual(bypath["docs/wb2a-gwg-mutual.md"]["decision"],
                         "CONFLICT_BOTH_SIDES_CHANGED")
        self.assertEqual(p["conflicts"], 1)
        self.assertEqual(p["target_only_commits"], 1)

    def test_staging_preview_does_not_move_refs_or_modify_index(self):
        self.generate()
        before = {branch: git(self.repo, "rev-parse", branch)
                  for branch in ("feature", "optolink-research")}
        status = git(self.repo, "status", "--porcelain")
        m.preview(self.repo, "feature", "optolink-research")
        after = {branch: git(self.repo, "rev-parse", branch)
                 for branch in ("feature", "optolink-research")}
        self.assertEqual(before, after)
        self.assertEqual(git(self.repo, "status", "--porcelain"), status)

    def test_identical_target_candidate(self):
        p = self.generate(target_extra={"tools/wb2a-gwg-legacy-feature.py": "reader = True\n"})
        bypath = {x["path"]: x for x in p["files"]}
        self.assertEqual(bypath["tools/wb2a-gwg-legacy-feature.py"]["decision"], "IDENTICAL")

    def test_unsafe_source_ref_injection_refused(self):
        self.generate()
        with self.assertRaises(m.UnsafePreview):
            m.preview(self.repo, "--upload-now", "optolink-research")

    def test_missing_target_ref_refused(self):
        self.generate()
        with self.assertRaises(m.UnsafePreview):
            m.preview(self.repo, "feature", "unknown_branch")

    def test_symlink_selected_candidate_rejected(self):
        self.generate()
        link = self.repo / "tools/wb2a-gwg-dangling.py"
        link.symlink_to("/etc/passwd")
        self.commit("synthetic symlink")
        with self.assertRaises(m.UnsafePreview):
            m.preview(self.repo, "feature", "optolink-research")

    def test_disallowed_production_path_not_enrolled(self):
        p = self.generate(source_extra={
            "apps/optolink-web/data.txt": "web-state",
            "install/optolink-splitter-install.sh": "installer",
            "ct/optolink-web.sh": "proxmox",
            "README.md": "different main index",
        })
        self.assertEqual(p["candidate_file_count"], 2)

    def test_real_repository_counters_optional(self):
        repo = SRC.parents[1]
        try:
            r = m.preview(repo, "HEAD", "origin/optolink-research")
        except m.UnsafePreview:
            self.skipTest("Live research branch refs are not available in CI")
        self.assertFalse(r["merge_performed"])
        self.assertGreaterEqual(r["candidate_file_count"], 35)
        self.assertGreaterEqual(r["source_only_commits"], 1)

    def test_transfer_plan_includes_own_reproducibility_tool_and_test(self):
        for artifact in (
            "tools/wb2a-research-branch-transfer-preview.py",
            "tests/test_wb2a_research_branch_transfer_preview.py",
            "docs/wb2a-c5-f9-fault-incident-2026-10-12.md",
            "docs/wb2a-optolinklogger-2010-2011-cli-rom-gate-2026-10-12.md",
            "docs/wb2a-vitosoft-oem-rom-wire-provenance-2026-10-12.md",
            "tools/wb2a-vitosoft-oem-rom-wire-audit.py",
            "tests/test_wb2a_vitosoft_oem_rom_wire_audit.py",
            "tools/wb2a-optolinklogger-cli-metadata-audit.py",
            "tools/wb2a-optolinklogger-crossversion-rom-gate.py",
            "tests/test_wb2a_optolinklogger_cli_metadata_audit.py",
            "tests/test_wb2a_optolinklogger_crossversion_rom_gate.py",
            "tools/wb2a-experiment-fault-gate.py",
            "tools/wb2a-experiment-with-fault-gate.sh",
            "tools/wb2a-c5-f9-incident-audit-offline.py",
            "tests/test_wb2a_experiment_fault_gate.py",
            "tests/test_wb2a_experiment_fault_wrapper_offline.py",
            "tests/test_wb2a_c5_f9_incident_audit_offline.py",
        ):
            self.assertTrue(
                any(m.fnmatch.fnmatchcase(artifact, rule) for rule in m.PREFIXES),
                artifact + " omitted from research transfer",
            )
        self.assertFalse(
            any(m.fnmatch.fnmatchcase("docs/README.md", rule)
                for rule in m.PREFIXES)
        )

    def test_transfer_script_has_no_ref_write_subprocess(self):
        src = SRC.read_text()
        for phrase in ('"git", "-C", str(repo), "push"',
                       '"checkout",', '"merge",', '"reset",', '"cherry-pick",'):
            self.assertNotIn(phrase, src)


if __name__ == "__main__":
    unittest.main()
