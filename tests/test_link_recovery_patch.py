"""Link-recovery patcher: keeps the splitter alive while the boiler is away.

The synthetic dispatcher below reproduces the exact upstream fragments the
patcher (and the hybrid dispatcher seam) anchor on, with CRLF line endings
like upstream optolinkvs2_switch.py.
"""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


patcher = _load("link_recovery_patch", TOOLS / "optolink-apply-link-recovery-patch.py")

SAMPLE = (
    "import requests_util\n"
    "import utils\n"
    "import time\n"
    "num_vicon_tries = 0\n"
    "num_restarts = 0\n"
    "last_vs1_comm = 0\n"
    "def main():\n"
    "    global num_restarts, num_vicon_tries, progr_exit_flag\n"
    "    while True:\n"
    "        try:\n"
    "            logger.info(\"enter main loop\")\n"
    "            while not utils.restart_event.is_set():\n"
    "                if(settings.vs1protocol):\n"
    "                    if(time.monotonic() > last_vs1_comm + 0.5):\n"
    "                        retcode,_,_ = vs12_adapter.read_datapoint_ext(0xf8, 2, serOptolink)     # type: ignore\n"
    "                # let cpu take a breath if there was nothing to do\n"
    "                time.sleep(0.005)\n"
    "        finally:\n"
    "            close_everything()\n"
    "            if utils.shutdown_event.is_set():\n"
    "                return\n"
    "            elif num_restarts >= settings.max_restarts:\n"
    "                logger.error(\"too many restarts - exit script\")\n"
    "                return\n"
    "            else:\n"
    "                logger.info(f\"waiting {settings.restart_delay}s before re-start...\")\n"
    "                time.sleep(settings.restart_delay)\n"
).replace("\n", "\r\n")


class LinkRecoveryPatchTest(unittest.TestCase):
    def test_never_exits_after_max_restarts(self):
        out = patcher.patch_switch(SAMPLE)
        self.assertNotIn("too many restarts - exit script", out)
        self.assertIn("restart_backoff_delay(num_restarts", out)
        self.assertEqual(out.count("\n"), out.count("\r\n"))

    def test_watchdog_requests_soft_restart(self):
        out = patcher.patch_switch(SAMPLE).replace("\r\n", "\n")
        watchdog = out.index("VS1 link watchdog")
        self.assertLess(watchdog, out.index("# let cpu take a breath"))
        self.assertIn("utils.restart_event.set()", out[watchdog:])
        self.assertIn("last_vs1_comm = time.monotonic()", out)

    def test_idempotent(self):
        out = patcher.patch_switch(SAMPLE)
        self.assertEqual(patcher.patch_switch(out), out)

    def test_apply_refuses_unknown_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / patcher.TARGET
            path.write_text("print('unexpected')\n")
            with self.assertRaises(patcher.PatchError):
                patcher.apply(Path(tmp))
            self.assertEqual(path.read_text(), "print('unexpected')\n")

    def test_backoff_is_bounded(self):
        ns = {}
        exec(patcher.CONSTANTS_NEW, ns)
        delays = [ns["restart_backoff_delay"](n, 10, 5) for n in range(0, 40)]
        self.assertEqual(delays[:5], [10] * 5)
        self.assertEqual(max(delays), ns["RESTART_BACKOFF_MAX_SECONDS"])
        self.assertEqual(delays, sorted(delays))

    def test_unit_restarts_always(self):
        unit = (ROOT / "config/optolink-splitter/optolink-splitter.service").read_text()
        self.assertIn("Restart=always", unit)
        self.assertIn("StartLimitIntervalSec=0", unit)


if __name__ == "__main__":
    unittest.main()
