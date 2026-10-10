"""Produktionsregressionen: keine realen Schreibzugriffe, keine systemd-Mutation."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
TOOL=ROOT/"tools"/"optolink-hybrid.py"
spec=importlib.util.spec_from_file_location("optolink_hybrid_production",TOOL)
cli=importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(cli)


class HybridProductionTests(unittest.TestCase):
    def test_explicit_exactly_twenty_runtime_modules(self):
        items=(ROOT/"tools/optolink-hybrid-modules.txt").read_text().splitlines()
        self.assertEqual(len(items),20)
        self.assertEqual(len(set(items)),20)
        self.assertEqual(items[0],"__init__.py")
        excluded=("campaign","forensics","trace","speed_audit","live_probe",
                  "legacy_probe","hybrid_acceptance","switchctl",
                  "timing_simulator","port_ownership")
        for name in items:
            self.assertRegex(name,r"^[a-z_][a-z0-9_]*\.py$")
            self.assertFalse(any(term in name for term in excluded),name)
            self.assertTrue((ROOT/"tools/handover_acceleration"/name).is_file())

    def test_only_exact_id_and_existing_immutable_release_allowed(self):
        for bad in ("../main","a/b","bad.file","-start","ABC","", " "):
            with self.subTest(bad=bad),self.assertRaises(cli.OperatorRejected):
                cli._validate_release_name(bad)
        with self.assertRaises(cli.OperatorRejected):
            cli._validate_release_name("release-that-does-not-exist")

    def test_real_canary_requires_explicit_telemetry_pause_consent(self):
        with patch.object(cli,"_require_root",return_value=None), \
             patch.object(cli,"_validate_release_name") as check, \
             patch.object(cli.continuous_canary,"launch") as launch:
            with self.assertRaisesRegex(cli.OperatorRejected,"--telemetriepause"):
                cli.canary("valid",acknowledged=False)
            check.assert_not_called()
            launch.assert_not_called()

    def test_approved_canary_never_selects_long_soak(self):
        candidate=Path("/var/lib/optolink-hybrid/releases/approved")
        with patch.object(cli,"_require_root",return_value=None), \
             patch.object(cli,"_validate_release_name",return_value=candidate), \
             patch.object(cli,"_ensure_no_concurrent_canary",return_value=None), \
             patch.object(cli.continuous_canary,"launch",return_value=0) as launch:
            self.assertEqual(cli.canary("approved",acknowledged=True)["ergebnis"],
                             "BESTANDEN")
            launch.assert_called_once_with(candidate,profile="standard")

    def test_busy_canary_refuses_concurrent_prepare(self):
        with patch.object(cli,"_require_root",return_value=None), \
             patch.object(cli.shadow_canary,"status",return_value="active"):
            with self.assertRaisesRegex(cli.OperatorRejected,"aktive Hybrid"):
                cli.prepare("another")

    def test_no_auto_software_or_hardware_actions_in_update_path(self):
        script=(ROOT/"tools/optolink-splitter-update.sh").read_text()
        self.assertIn("install_repo_file tools/optolink-hybrid.py",script)
        self.assertIn("optolink-hybrid-modules.txt",script)
        self.assertIn("hybrid_count",script)
        self.assertIn("is-active --quiet optolink-hybrid-continuous-canary.service",script)
        self.assertNotIn("--accept-telemetry-pause",script)
        self.assertNotIn("OPTO_HYBRID_RUNTIME_AUTO=fenced-readonly",script)
        self.assertNotIn("continuous_canary.launch(",script)
        profile=(ROOT/"tools/optolink-apply-vdensho1-ha-profile.sh").read_text()
        self.assertIn("before-reset-",profile)
        self.assertIn("tracked-files.tar.gz",profile)
        self.assertIn("tracked-changes.patch",profile)
        self.assertLess(profile.index("tracked-changes.patch"),
                        profile.index("reset --hard \"$VALIDATED_UPSTREAM_REF\""))

    def test_all_new_and_modified_svg_are_valid_and_accessible(self):
        for path in (ROOT/"docs/images").glob("*.svg"):
            with self.subTest(svg=path.name):
                tree=ET.parse(path)
                root=tree.getroot()
                ns="{http://www.w3.org/2000/svg}"
                self.assertEqual(root.tag,ns+"svg")
                self.assertIsNotNone(root.find(ns+"title"))
                self.assertIsNotNone(root.find(ns+"desc"))
                self.assertRegex(root.attrib["viewBox"],r"^0 0 \d+ \d+$")
                self.assertGreater(path.stat().st_size,1500)
        svg=(ROOT/"docs/images/vs1-p300-wechsel.svg").read_text()
        self.assertIn("ExecStopPost",svg)
        self.assertIn("P300",svg)
        self.assertIn("VS1",svg)

    def test_modified_docs_do_not_have_broken_relative_links(self):
        names=("README.md","docs/README.md","docs/architecture.md",
               "docs/operations.md","docs/hybrid-protokollwechsel.md",
               "docs/optolink-maintenance.md",
               "docs/optolink-maintenance-api.md")
        for name in names:
            path=ROOT/name
            text=path.read_text()
            for link in re.findall(r"\]\(([^)]+)\)",text):
                if link.startswith(("http://","https://","#","mailto:")):
                    continue
                target=(path.parent/link.partition("#")[0]).resolve()
                with self.subTest(doc=name,link=link):
                    self.assertTrue(target.is_relative_to(ROOT),str(target))
                    self.assertTrue(target.exists(),str(target))

    def test_research_excluded_from_production_documentation(self):
        docs={p.name for p in (ROOT/"docs").iterdir()}
        self.assertFalse(any(name.startswith("handover-") for name in docs))
        self.assertFalse(any(name.startswith("vs1-p300-") for name in docs))
        self.assertFalse((ROOT/"tests/fixtures/real_campaign_20261009.json").exists())

    def test_shell_entrypoints_are_syntax_checked(self):
        for rel in ("tools/optolink-splitter-update.sh",
                    "tools/optolink-apply-vdensho1-ha-profile.sh",
                    "tools/optolink-update-main-umstellen.sh"):
            with self.subTest(script=rel):
                result=subprocess.run(["bash","-n",str(ROOT/rel)],
                                      capture_output=True,text=True,check=False)
                self.assertEqual(result.returncode,0,result.stderr)

    def test_main_channel_is_only_released_with_explicit_command(self):
        helper=(ROOT/"tools/optolink-update-main-umstellen.sh").read_text()
        self.assertIn("--freigeben",helper)
        self.assertIn("COMMUNITY_SCRIPTS_REF=main",helper)
        self.assertIn("cp -p \"$CONF\" \"$backup\"",helper)
        self.assertIn("tools/optolink-hybrid.py",helper)
        self.assertNotIn("bash update",helper)
        self.assertNotIn("\nupdate\n",helper)


if __name__=="__main__":
    unittest.main()
