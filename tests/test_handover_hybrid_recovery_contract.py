"""Regression for the 154-ms real worker crash caused by invalid session prefix.

No serial, MQTT, systemctl or service modifications are performed.
Tests exercise *both* pre-staged and staged Python import/recovery boundaries.
"""
from __future__ import annotations
import contextlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from handover_acceleration import hybrid_acceptance as h


class RecoveryPathRegression(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.session = self.base / 'run-inprocess-test-4321'
        self.session.mkdir(mode=0o700)
        self.fake_live = types.SimpleNamespace(
            verify_session=lambda path: {'version': 'sample', 'source_sha256': {'abc': 'hash'}},
            base=types.SimpleNamespace())

    def test_previous_bad_session_prefix_is_explicitly_rejected(self):
        # The *actual* pinned legacy validator enforces startswith('run-').
        # This is the constraint that 348 earlier tests missed.
        try:
            from handover_acceleration import legacy_probe as legacy
        except ImportError:
            self.skipTest('pinned legacy_probe.py available in official GitHub checkout')
        if not hasattr(legacy, 'validate_session'):
            self.skipTest('local fake legacy module; official checkout includes real validator')
        wrong = self.base / 'inprocess-test-4321'
        wrong.mkdir(mode=0o700)
        with patch.object(legacy, 'ROOT', self.base):
            with self.assertRaisesRegex(legacy.ProbeError, 'invalid session path'):
                legacy.validate_session(wrong)

    def test_fixed_prefix_passes_actual_legacy_validator(self):
        try:
            from handover_acceleration import legacy_probe as legacy
        except ImportError:
            self.skipTest('pinned legacy_probe.py available in official GitHub checkout')
        if not hasattr(legacy, 'validate_session'):
            self.skipTest('local fake legacy module; official checkout includes real validator')
        state = {'services': {name: False for name in legacy.SERVICES}, 'restore': []}
        (self.session / 'state.json').write_text(json.dumps(state))
        # A hosted GitHub runner is non-root. Mock only the uid returned by
        # stat() for this private session; exercise all other real guards.
        real_stat = Path.stat
        def stat_as_root(path, *args, **kwargs):
            actual = real_stat(path, *args, **kwargs)
            if path == self.session:
                return types.SimpleNamespace(st_uid=0, st_mode=actual.st_mode)
            return actual
        with patch.object(legacy, 'ROOT', self.base), patch.object(Path, 'stat', stat_as_root):
            self.assertEqual(legacy.validate_session(self.session), state)

    def test_readonly_staged_import_and_recovery_check_order(self):
        with patch.object(h, '_live', return_value=self.fake_live), \
             patch.object(h, 'verify_stage', return_value={'version': 'v2', 'source_sha256': {'a': 'b'}}):
            r = h.staged_preflight(self.session, self.base)
        self.assertEqual(r['session_version'], 'sample')
        self.assertEqual(r['staged_version'], 'v2')
        self.assertTrue(r['recovery_entry'].endswith('/live_probe.py'))

    def test_staged_preflight_error_refuses_without_systemd(self):
        with patch.object(h, '_live', return_value=self.fake_live), \
             patch.object(h, 'verify_stage', side_effect=h.AcceptanceRejected('invalid hash')):
            with self.assertRaisesRegex(h.AcceptanceRejected, 'invalid hash'):
                h.staged_preflight(self.session, self.base)

    def test_exact_staged_cli_passes_marker_gate(self):
        seen = {}
        def response(args, **kw):
            seen['command'] = args
            seen['cwd'] = kw['cwd']
            return types.SimpleNamespace(returncode=0, stdout='HYBRID_STAGED_PREFLIGHT=PASS\n', stderr='')
        with patch.object(h.subprocess, 'run', side_effect=response):
            h.run_staged_preflight(self.session, self.base, sys.executable)
        self.assertEqual(seen['command'][3:5], ['--staged-preflight', str(self.session)])
        self.assertEqual(seen['cwd'], str(self.base))
        self.assertFalse(any('systemctl' in x or '/dev/tty' in x for x in seen['command']))

    def test_wrong_marker_or_exit_code_prevents_stopping_services(self):
        for rc, stdout in ((1, ''), (0, ''), (0, 'HYBRID_STAGED_PREFLIGHT=FAIL\n')):
            with self.subTest(rc=rc, stdout=stdout), \
                 patch.object(h.subprocess, 'run', return_value=types.SimpleNamespace(
                     returncode=rc, stdout=stdout, stderr='ProbeError: invalid session path')):
                with self.assertRaisesRegex(h.AcceptanceRejected, 'staged worker/recovery preflight failed'):
                    h.run_staged_preflight(self.session, self.base, sys.executable)

    def test_staged_preflight_timeout_is_not_a_success(self):
        with patch.object(h.subprocess, 'run', side_effect=subprocess.TimeoutExpired('python', 15)):
            with self.assertRaisesRegex(h.AcceptanceRejected, 'could not start'):
                h.run_staged_preflight(self.session, self.base, sys.executable)

    def test_preflight_cli_never_accepts_service_pause(self):
        with self.assertRaisesRegex(h.AcceptanceRejected, 'never accepts a service pause'):
            h.main(['--staged-preflight', str(self.session), '--root', str(self.base),
                    '--accept-telemetry-pause'])

    def test_worker_early_stage_validation_failure_still_records_error(self):
        with patch.object(h, '_live', return_value=self.fake_live), \
             patch.object(h, 'verify_stage', side_effect=h.AcceptanceRejected('bad staged checksum')), \
             patch.object(h.subprocess, 'run', side_effect=AssertionError('no subprocess')):
            self.assertEqual(h.worker(self.session), 1)
        report = json.loads((self.session / 'measurement.json').read_text())
        self.assertEqual(report['source_sha256'], {})
        self.assertIn('bad staged checksum', report['errors'][0])
        self.assertFalse(report['experiment_pass'])

    def test_old_session_reports_invalid_path_in_worker_diagnostics(self):
        previous = self.base / 'inprocess-older'
        previous.mkdir(mode=0o700)
        stub = types.SimpleNamespace(verify_session=lambda _: (_ for _ in ()).throw(
            RuntimeError('invalid session path')))
        with patch.object(h, '_live', return_value=stub):
            self.assertEqual(h.worker(previous), 1)
        report = json.loads((previous / 'measurement.json').read_text())
        self.assertIn('invalid session path', report['errors'][0])


if __name__ == '__main__':
    unittest.main()
