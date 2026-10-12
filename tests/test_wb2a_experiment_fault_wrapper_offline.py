"""Offline checks of conservative fault-gated live experiment runner.

No test invokes a whitelisted live session or opens a controller transport.
"""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "tools/wb2a-experiment-with-fault-gate.sh"


class WrapperSafety(unittest.TestCase):
    def run_bad_input(self, *args):
        proc = subprocess.run(["bash", str(WRAPPER), *args],
                              text=True, capture_output=True, timeout=5)
        self.assertNotEqual(proc.returncode, 0)
        return proc

    def test_bash_syntax(self):
        subprocess.run(["bash", "-n", str(WRAPPER)], check=True, timeout=5)

    def test_requires_explicit_execute(self):
        r = self.run_bad_input()
        self.assertIn("Usage:", r.stderr)

    def test_unknown_experiment_rejected_before_precheck(self):
        r = self.run_bad_input("--execute", "tools/fake-write-session.sh")
        self.assertIn("REFUSE_UNREVIEWED_EXPERIMENT", r.stderr)

    def test_path_traversal_rejected_before_precheck(self):
        r = self.run_bad_input("--execute", "../../opt/optolink/evil.sh")
        self.assertIn("REFUSE_UNREVIEWED_EXPERIMENT", r.stderr)

    def test_named_watch_positions_present(self):
        text = WRAPPER.read_text()
        self.assertIn('sleep 300', text)
        self.assertIn('sleep 600', text)
        self.assertIn('sleep 3600', text)
        for mark in ("POSTCHECK_T0", "post-5min.json", "post-15min.json", "post-75min.json"):
            self.assertIn(mark, text)

    def test_preserves_runner_own_restore_and_no_controller_reset(self):
        source = WRAPPER.read_text()
        for forbidden in ("writeraw;", "serial.Serial(", "systemctl stop",
                          "systemctl reboot", "restore.sh", "/dev/tty", "fflash"):
            self.assertNotIn(forbidden, source)
        self.assertIn("independent controller restore", source)
        self.assertIn("sudo -n bash", source)

    def test_no_silent_health_claim_on_interruption(self):
        source = WRAPPER.read_text()
        self.assertIn("POSTWATCH_INCOMPLETE", source)
        self.assertIn("ALARM_UNVERIFIED", source)
        self.assertIn("abnormal-exit-post.json", source)
        self.assertIn("trap on_exit EXIT", source)

    def test_fault_detection_nonzero_and_local_journal(self):
        source = WRAPPER.read_text()
        self.assertIn("FAULT_DETECTED_OR_HEALTH_UNVERIFIED", source)
        self.assertIn('exit 25', source)
        self.assertIn("logger -t wb2a-experiment-fault-gate", source)

    def test_reports_are_private_by_default(self):
        source = WRAPPER.read_text()
        self.assertIn("umask 077", source)
        self.assertIn("mktemp -d /tmp/wb2a-experiment-fault-gate-", source)


if __name__ == "__main__":
    unittest.main()
