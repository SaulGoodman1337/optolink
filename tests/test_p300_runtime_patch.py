"""P300 runtime patcher: watchdog/keep-alive for both protocols, GFA items skipped under P300."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


patcher = _load("p300_runtime_patch", TOOLS / "optolink-apply-p300-runtime-patch.py")
linkrec = _load("link_recovery_patch_for_p300", TOOLS / "optolink-apply-link-recovery-patch.py")


class P300RuntimePatchTest(unittest.TestCase):
    def test_selftest_passes(self):
        self.assertEqual(patcher.self_test(), 0)

    def test_watchdog_anchor_matches_link_recovery_output(self):
        # The anchor this patcher replaces must be exactly what link recovery inserts.
        watchdog_old = patcher.SWITCH_REPLACEMENTS[2][1]
        self.assertIn(watchdog_old, linkrec.WATCHDOG)
        self.assertIn(patcher.SWITCH_REPLACEMENTS[1][1], linkrec.CONSTANTS_NEW)

    def test_keepalive_does_not_duplicate_hybrid_keepalive_anchor(self):
        new = patcher.SWITCH_REPLACEMENTS[2][2]
        self.assertNotIn("read_datapoint_ext(0xf8, 2, serOptolink)", new)
        for anchor in patcher.HYBRID_ANCHORS:
            self.assertNotIn(anchor.strip(), new)

    def test_vs1_watchdog_semantics_unchanged(self):
        # VS1 refreshed the timestamp in the success branch before; still does.
        new = patcher.SWITCH_REPLACEMENTS[0][2]
        self.assertIn("last_vs1_comm = time.monotonic()", new)
        self.assertIn("vs12_adapter.reset_vs1sync()", new)


if __name__ == "__main__":
    unittest.main()
