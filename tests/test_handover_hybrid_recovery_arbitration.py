"""Independent ExecStopPost must reacquire the legacy physical pump lock.

Fake services only: no serial, real systemd, MQTT or production writes.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from handover_acceleration import hybrid_recovery as h
from handover_acceleration.port_ownership import OwnershipRejected


class IndependentHybridRecoveryTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.folder = Path(td.name)
        self.events = []
        self.locked = False

        def verify_session(session):
            self.events.append('validate')
            if session != self.folder:
                raise ValueError('invalid private session')
            return {'port': '/dev/NOT_USED'}

        def unit_state(unit):
            self.events.append('unit_state:' + unit)
            return {'ActiveState': 'inactive'}

        def legacy_recover(session):
            self.assertTrue(self.locked)
            self.events.append('original_recover')
            (session/'recovery.json').write_text(
                json.dumps({'overall_verified': True, 'services_restored': True}))
            return 0

        self.live = types.SimpleNamespace(
            verify_session=verify_session,
            recover=legacy_recover,
            base=types.SimpleNamespace(
                unit_state=unit_state,
                atomic_json=lambda p, value: p.write_text(json.dumps(value)),
            ))
        patcher = patch.object(h, '_live', lambda: self.live)
        patcher.start()
        self.addCleanup(patcher.stop)

        @contextmanager
        def locked():
            self.events.append('pump_lease_acquire')
            self.locked = True
            try:
                yield
            finally:
                self.locked = False
                self.events.append('pump_lease_release')

        self.lease = locked
        patcher = patch.object(h, 'pump_lease', self.lease)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_independent_recovery_reacquires_pump_lease_first(self):
        self.assertEqual(h.recover(self.folder), 0)
        self.assertEqual(self.events, [
            'validate', 'pump_lease_acquire',
            'unit_state:optolink-pump-override.service',
            'original_recover', 'pump_lease_release'])
        record = json.loads((self.folder/'recovery.json').read_text())
        self.assertTrue(record['overall_verified'])

    def test_restarted_pump_daemon_blocks_independent_port_restore(self):
        self.live.base.unit_state = lambda _unit: {'ActiveState': 'active'}
        self.assertEqual(h.recover(self.folder), 1)
        self.assertNotIn('original_recover', self.events)
        result = json.loads((self.folder/'recovery.json').read_text())
        self.assertEqual(result['pump_arbitration'], 'FAILED_CLOSED')
        self.assertFalse(result['services_restored'])
        self.assertFalse(result['overall_verified'])

    def test_competing_pump_lock_prevents_restoring_over_existing_owner(self):
        @contextmanager
        def competing_lock():
            raise OwnershipRejected('physical pump lease busy')
            yield

        with patch.object(h, 'pump_lease', competing_lock):
            self.assertEqual(h.recover(self.folder), 1)
        self.assertNotIn('original_recover', self.events)
        evidence = json.loads((self.folder/'recovery.json').read_text())
        self.assertIn('physical pump lease busy', evidence['errors'][0])
        self.assertFalse(evidence['independent_link_restore']['verified'])

    def test_invalid_session_cannot_create_recovery_file_or_acquire_port(self):
        with self.assertRaisesRegex(ValueError, 'invalid private session'):
            h.recover(self.folder/'other')
        self.assertEqual(self.events, ['validate'])
        self.assertFalse((self.folder/'recovery.json').exists())

    def test_existing_recovery_evidence_is_not_overwritten_by_lock_failure(self):
        path = self.folder/'recovery.json'
        path.write_text('{"previous":"preserve"}')
        self.live.base.unit_state = lambda _: {'ActiveState': 'activating'}
        self.assertEqual(h.recover(self.folder), 1)
        self.assertEqual(json.loads(path.read_text()), {'previous': 'preserve'})

    def test_execstoppost_entry_requires_root_and_real_systemd_invocation(self):
        with patch.object(h.os, 'geteuid', return_value=1000):
            with self.assertRaisesRegex(h.RecoveryRejected, 'root-owned'):
                h.main(['--recover', str(self.folder)])
        with patch.object(h.os, 'geteuid', return_value=0), \
             patch.dict(os.environ, {'INVOCATION_ID': ''}):
            with self.assertRaisesRegex(h.RecoveryRejected, 'root-owned'):
                h.main(['--recover', str(self.folder)])
        self.assertEqual(self.events, [])

    def test_recovery_cli_preserves_success_exit_zero(self):
        # A prior broad SystemExit catcher would have converted a perfectly
        # successful independent ExecStopPost into systemd exit status 1.
        with patch.object(h, 'main', return_value=0):
            self.assertEqual(h._entrypoint(), 0)
        with patch.object(h, 'main', return_value=1):
            self.assertEqual(h._entrypoint(), 1)
        with patch.object(h, 'main', side_effect=h.RecoveryRejected('bad session')):
            self.assertEqual(h._entrypoint(), 1)

    def test_authorized_systemd_entry_calls_exact_validated_recovery(self):
        with patch.object(h.os, 'geteuid', return_value=0), \
             patch.dict(os.environ, {'INVOCATION_ID': 'fake-tests-only'}):
            self.assertEqual(h.main(['--recover', str(self.folder)]), 0)
        self.assertIn('original_recover', self.events)


if __name__ == '__main__':
    unittest.main()
