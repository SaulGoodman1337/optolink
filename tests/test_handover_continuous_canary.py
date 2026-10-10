"""Independent supervised continuous canary and ExecStopPost offline tests."""
from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from handover_acceleration import continuous_canary as c


class ContinuousCanaryTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.base = Path(td.name)
        self.session = self.base / "run-20261010T101010Z-777"
        self.session.mkdir()
        self.release = self.base / "release"
        self.release.mkdir()
        self.extra = self.base / "extra.conf"
        self.manifest = self.base / "enrollment.json"
        self.data = {"release": str(self.release), "phase": "AUTO_HARDWARE_CANARY",
                     "before": {name: "active" for name in c.sh.ALL}}

    def _event(self, *, session=None):
        return {
            "canary_session": session or self.session.name,
            "status": "VERIFIED_SWITCH",
            "vs1_p80": "20", "vs1_p06": "53", "elapsed_ms": 5333.0,
            "p300_fixed": {
                "p300_device": "20c2", "ram_0f20_32": "ab"*32,
                "ram_1c60_32": "cd"*32,
            },
        }

    def test_bounded_real_journal_events_are_pinned_to_session(self):
        lines = (
            "2026 INFO: HYBRID_RUNTIME_REFUSAL HA_READBACK_PENDING\n"
            "2026 INFO: HYBRID_RUNTIME_VERIFIED_SWITCH "
            + json.dumps(self._event(session="run-20261010T111111Z-8"))
            + "\n2026 INFO: HYBRID_RUNTIME_VERIFIED_SWITCH "
            + json.dumps(self._event()) + "\n"
        )
        result = subprocess.CompletedProcess([], 0, lines, "")
        with patch.object(c.subprocess, "run", return_value=result) as mocked:
            events, refused = c._collect_events(self.session, 1234)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["p300_fixed"]["p300_device"], "20c2")
        self.assertEqual(refused, ["HA_READBACK_PENDING"])
        self.assertIn("@1234", mocked.call_args.args[0])
        self.assertIn("--grep=HYBRID_RUNTIME_", mocked.call_args.args[0])

    def test_live_evidence_must_have_genuine_gfa_and_two_fixed_fc03_blocks(self):
        for change in (
            {"vs1_p80": "21"},
            {"vs1_p06": "ff"},
            {"elapsed_ms": 9000.0},
            {"p300_fixed": {"p300_device": "20c2"}},
        ):
            with self.subTest(change=change):
                row = self._event()
                row.update(change)
                output = "HYBRID_RUNTIME_VERIFIED_SWITCH " + json.dumps(row)
                completed = subprocess.CompletedProcess([], 0, output, "")
                with patch.object(c.subprocess, "run", return_value=completed):
                    with self.assertRaises(c.ContinuousCanaryRejected):
                        c._collect_events(self.session, 1234)

    def test_forged_session_id_fails_early(self):
        for name in ("../bad", "other", "run-abc", "run-20261010T101010Z-x"):
            with self.subTest(name=name), self.assertRaises(c.ContinuousCanaryRejected):
                c._extra_content(self.base/name)

    def test_crash_recovery_removes_auto_and_manifest_before_original_restore(self):
        self.extra.write_text(c._extra_content(self.session))
        self.manifest.write_bytes(b'approved-source-manifest\n')
        stages = []
        def old_restore(s):
            self.assertEqual(s, self.session)
            self.assertFalse(self.extra.exists())
            self.assertFalse(self.manifest.exists())
            stages.append("original_recovery")
            return 0
        with patch.object(c.sh, "load", return_value=self.data), \
             patch.object(c, "_extra_path", return_value=self.extra), \
             patch.object(c, "MANIFEST_PATH", self.manifest), \
             patch.object(c, "_expected_manifest", return_value=b'approved-source-manifest\n'), \
             patch.object(c.sh, "recover", side_effect=old_restore):
            self.assertEqual(c.recover(self.session), 0)
        self.assertEqual(stages, ["original_recovery"])

    def test_crash_before_any_override_still_runs_independent_original_recovery(self):
        with patch.object(c.sh, "load", return_value=self.data), \
             patch.object(c, "_extra_path", return_value=self.extra), \
             patch.object(c, "MANIFEST_PATH", self.manifest), \
             patch.object(c.sh, "recover", return_value=0) as recovered:
            self.assertEqual(c.recover(self.session), 0)
            recovered.assert_called_once_with(self.session)

    def test_unreviewed_auto_dropin_is_never_followed_by_original_restart(self):
        self.extra.write_text("EXPERIMENTAL TAMPER")
        with patch.object(c.sh, "load", return_value=self.data), \
             patch.object(c, "_extra_path", return_value=self.extra), \
             patch.object(c, "MANIFEST_PATH", self.manifest), \
             patch.object(c.sh, "recover", side_effect=AssertionError("no unsafe restart")):
            self.assertEqual(c.recover(self.session), 1)
        self.assertTrue(self.extra.is_file())

    def test_corrupt_enrollment_reports_failure_but_restores_original_vs1(self):
        self.extra.write_text(c._extra_content(self.session))
        self.manifest.write_text("UNKNOWN")
        calls = []
        with patch.object(c.sh, "load", return_value=self.data), \
             patch.object(c, "_extra_path", return_value=self.extra), \
             patch.object(c, "MANIFEST_PATH", self.manifest), \
             patch.object(c, "_expected_manifest", return_value=b'approved\n'), \
             patch.object(c.sh, "recover", side_effect=lambda _: calls.append(1) or 0):
            self.assertEqual(c.recover(self.session), 1)
        self.assertFalse(self.extra.exists())
        self.assertTrue(self.manifest.exists())
        self.assertEqual(calls, [1])

    def test_worker_activates_auto_only_after_live_attestation(self):
        from types import SimpleNamespace
        calls=[]
        def status(unit):
            return "inactive" if unit == "optolink-pump-override.service" else "active"
        def save(path, value):
            path.write_text(json.dumps(value))
        with patch.object(c.sh, "load", return_value=self.data), \
             patch.object(c.sh, "worker", return_value=0), \
             patch.object(c.sh, "save", side_effect=save), \
             patch.object(c, "_write_enrollment", side_effect=lambda _:calls.append("enrolled")), \
             patch.object(c, "verify_enrollment", return_value=SimpleNamespace(accepted=True)), \
             patch.object(c, "_extra_path", return_value=self.extra), \
             patch.object(c.sh, "call", side_effect=lambda argv,*a,**k:(
                 "123" if "--property=MainPID" in argv
                 else calls.append(argv) or "")), \
             patch.object(c.sh, "status", side_effect=status), \
             patch.object(c.sh, "gfa", return_value={"P80":"20","P06":"53"}), \
             patch.object(c, "_collect_events", return_value=([self._event()]*3, [])), \
             patch.object(c.os, "geteuid", return_value=0), \
             patch.object(c.os, "chown", return_value=None), \
             patch.dict(c.os.environ, {"INVOCATION_ID":"test-invocation"}):
            self.assertEqual(c.worker(self.session),0)
        self.assertEqual(calls[0],"enrolled")
        self.assertEqual(calls[1],["systemctl","daemon-reload"])
        self.assertEqual(calls[2],["systemctl","restart",c.sh.MAIN])
        self.assertIn("fenced-readonly",self.extra.read_text())
        data=json.loads((self.session/"continuous-measurement.json").read_text())
        self.assertEqual(data["event_count"],3)
        self.assertEqual(data["result"],"PASS_THREE_VERIFIED_CONTINUOUS_WINDOWS")

    def test_worker_refuses_auto_if_real_producer_enrollment_rejected(self):
        from types import SimpleNamespace
        with patch.object(c.sh, "load", return_value=self.data), \
             patch.object(c.sh, "worker", return_value=0), \
             patch.object(c.sh, "save", return_value=None), \
             patch.object(c, "_write_enrollment", return_value=None), \
             patch.object(c, "verify_enrollment", return_value=SimpleNamespace(
                 accepted=False, reason="wrong process source hash")), \
             patch.object(c, "_extra_path", return_value=self.extra), \
             patch.object(c.os, "geteuid", return_value=0), \
             patch.object(c.os, "chown", return_value=None), \
             patch.dict(c.os.environ, {"INVOCATION_ID":"test-invocation"}):
            with self.assertRaisesRegex(c.ContinuousCanaryRejected,"wrong process source hash"):
                c.worker(self.session)
        self.assertFalse(self.extra.exists())

    def test_liveness_watcher_allows_only_bounded_active_p300_marker(self):
        from types import SimpleNamespace
        unverified=SimpleNamespace(
            accepted=False, reason="producer lease unsafe or failure latched")
        with patch.object(c.sh,"call",return_value="123"), \
             patch.object(c,"verify_enrollment",return_value=unverified), \
             patch.object(c,"_read_lease_marker",return_value=b"P300_ACTIVE"):
            self.assertEqual(c.verify_live_canary_epoch(123,None,100),100)
            self.assertEqual(c.verify_live_canary_epoch(123,100,108),100)
            with self.assertRaisesRegex(c.ContinuousCanaryRejected,"beyond"):
                c.verify_live_canary_epoch(123,100,113)
        with patch.object(c.sh,"call",return_value="123"), \
             patch.object(c,"verify_enrollment",return_value=unverified), \
             patch.object(c,"_read_lease_marker",return_value=b"P300_FAILED"):
            with self.assertRaises(c.ContinuousCanaryRejected):
                c.verify_live_canary_epoch(123,None,100)
        with patch.object(c.sh,"call",return_value="124"), \
             patch.object(c,"verify_enrollment",return_value=unverified):
            with self.assertRaisesRegex(c.ContinuousCanaryRejected,"PID changed"):
                c.verify_live_canary_epoch(123,None,100)

    def test_successful_idle_epoch_releases_previous_active_marker_timer(self):
        from types import SimpleNamespace
        attested=SimpleNamespace(accepted=True,reason="ALL_FIVE_PRODUCERS_ATTESTED")
        with patch.object(c.sh,"call",return_value="123"), \
             patch.object(c,"verify_enrollment",return_value=attested):
            self.assertIsNone(c.verify_live_canary_epoch(123,98,100))

    def test_extended_soak_has_fixed_conservative_limits(self):
        count, window, runtime, passed = c.profile_limits("soak-eight")
        self.assertEqual(count, 8)
        self.assertGreaterEqual(window, count * 60 + 60)
        self.assertGreater(runtime, window)
        self.assertEqual(passed, "PASS_EIGHT_VERIFIED_CONTINUOUS_WINDOWS")
        self.assertEqual(c.profile_limits("standard")[0], 3)
        for name in ("soak-nine", "forever", "../bad", ""):
            with self.subTest(name=name), self.assertRaises(c.ContinuousCanaryRejected):
                c.profile_limits(name)

    def test_soak_worker_requires_eight_independent_journal_records(self):
        from types import SimpleNamespace
        self.data["canary_profile"] = "soak-eight"
        def status(unit):
            return "inactive" if unit == "optolink-pump-override.service" else "active"
        def save(path, value):
            path.write_text(json.dumps(value))
        with patch.object(c.sh, "load", return_value=self.data), \
             patch.object(c.sh, "worker", return_value=0), \
             patch.object(c.sh, "save", side_effect=save), \
             patch.object(c, "_write_enrollment", return_value=None), \
             patch.object(c, "verify_enrollment", return_value=SimpleNamespace(accepted=True)), \
             patch.object(c, "_extra_path", return_value=self.extra), \
             patch.object(c.sh, "call", side_effect=lambda argv,*a,**k:(
                 "123" if "--property=MainPID" in argv else "")), \
             patch.object(c.sh, "status", side_effect=status), \
             patch.object(c.sh, "gfa", return_value={"P80":"20","P06":"53"}), \
             patch.object(c, "_collect_events", return_value=([self._event() for _ in range(8)], [])), \
             patch.object(c.os, "geteuid", return_value=0), \
             patch.object(c.os, "chown", return_value=None), \
             patch.dict(c.os.environ, {"INVOCATION_ID":"test-invocation"}):
            self.assertEqual(c.worker(self.session), 0)
        result=json.loads((self.session/"continuous-measurement.json").read_text())
        self.assertEqual(result["result"], "PASS_EIGHT_VERIFIED_CONTINUOUS_WINDOWS")
        self.assertEqual(result["event_count"], 8)

    def test_soak_launch_pins_systemd_watchdog_and_root_session_profile(self):
        import types
        expected=[]
        sessions=self.base/"sessions"
        release=self.base/"release"
        preflight={"release":str(release),"before":{},"phase":"PREPARED"}
        def fake_run(argv,*,check=False):
            expected.append(argv)
            return types.SimpleNamespace(returncode=1)
        with patch.object(c.sh,"SESSIONS",sessions), \
             patch.object(c.sh,"preflight",return_value=preflight), \
             patch.object(c.os,"geteuid",return_value=0), \
             patch.object(c.subprocess,"run",side_effect=fake_run):
            self.assertEqual(c.launch(release,profile="soak-eight"),1)
        self.assertEqual(len(expected),1)
        args=expected[0]
        self.assertIn("--property=RuntimeMaxSec=800",args)
        self.assertIn("--property=KillMode=control-group",args)
        self.assertTrue(any(x.startswith("--property=ExecStopPost=") for x in args))
        dirs=list(sessions.glob("run-*"))
        self.assertEqual(len(dirs),1)
        contents=json.loads((dirs[0]/"state.json").read_text())
        self.assertEqual(contents["canary_profile"],"soak-eight")

    def test_systemd_runtime_watchdog_and_execstop_are_mandatory(self):
        self.assertLess(c.WATCH_SECONDS, c.MAX_RUNTIME_SECONDS)
        self.assertEqual(c.TARGET_WINDOWS, 3)
        self.assertEqual(c.UNIT, "optolink-hybrid-continuous-canary.service")
        import inspect
        source = inspect.getsource(c.launch)
        self.assertIn("RuntimeMaxSec", source)
        self.assertIn("ExecStopPost", source)
        self.assertIn("KillMode", source)
        self.assertIn("accept", inspect.getsource(c.main))

    def test_worker_refuses_untrusted_unprivileged_or_unsupervised_entry(self):
        with patch.object(c.sh, "load", return_value=self.data), \
             patch.object(c.os, "geteuid", return_value=1000):
            with self.assertRaises(c.ContinuousCanaryRejected):
                c.worker(self.session)

    def test_journalctl_grep_no_match_exit_one_means_no_windows_yet(self):
        # Real Debian 13 systemd 257 returns 1 for --grep with zero matches.
        empty = subprocess.CompletedProcess([], 1, "", "")
        with patch.object(c.subprocess, "run", return_value=empty):
            self.assertEqual(c._collect_events(self.session, 0), ([], []))

    def test_lost_journal_never_counts_as_a_real_vs1_return(self):
        bad = subprocess.CompletedProcess([], 1, "", "no journal")
        with patch.object(c.subprocess, "run", return_value=bad):
            with self.assertRaises(c.ContinuousCanaryRejected):
                c._collect_events(self.session, 0)


if __name__ == "__main__":
    unittest.main()
