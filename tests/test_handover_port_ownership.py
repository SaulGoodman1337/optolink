"""Exact cross-service port-lock contract, no serial access or systemctl."""
from __future__ import annotations

from pathlib import Path
import os
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from handover_acceleration.port_ownership import (
    PUMP_SERVICE, OwnershipRejected, pump_lease, require_pump_inactive,
)


class PumpOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.lock = Path(self.tmp.name) / 'physical-ram-snapshot.lock'

    def test_only_inactive_or_failed_service_can_be_accepted(self):
        for state in ('inactive', 'failed', 'not-found'):
            with self.subTest(state=state):
                require_pump_inactive(lambda name: {'ActiveState': state})
        for state in ('active', 'activating', 'deactivating', 'reloading',
                      None, 'unknown'):
            with self.subTest(state=state):
                with self.assertRaises(OwnershipRejected):
                    require_pump_inactive(lambda name: {'ActiveState': state})

    def test_reject_missing_or_malformed_service_state(self):
        for bad in (None, False, [], {}, 'active'):
            with self.subTest(state=bad):
                with self.assertRaises(OwnershipRejected):
                    require_pump_inactive(lambda _: bad)
        seen = []
        require_pump_inactive(lambda name: (seen.append(name), {'ActiveState': 'inactive'})[1])
        self.assertEqual(seen, [PUMP_SERVICE])

    def test_nonblocking_lock_refuses_competing_pump_owner(self):
        with pump_lease(self.lock):
            self.assertTrue(self.lock.is_file())
            self.assertEqual(stat.S_IMODE(self.lock.stat().st_mode), 0o600)
            with self.assertRaisesRegex(OwnershipRejected, 'busy'):
                with pump_lease(self.lock):
                    self.fail('second port owner entered')
        with pump_lease(self.lock):
            pass

    def test_lock_always_released_after_exception(self):
        with self.assertRaisesRegex(RuntimeError, 'simulate'):
            with pump_lease(self.lock):
                raise RuntimeError('simulate')
        with pump_lease(self.lock):
            pass

    def test_symlink_and_loose_permissions_refused(self):
        target = Path(self.tmp.name) / 'target'
        target.write_text('unchanged')
        self.lock.symlink_to(target)
        with self.assertRaises(OwnershipRejected):
            with pump_lease(self.lock):
                pass
        self.assertEqual(target.read_text(), 'unchanged')
        self.lock.unlink()
        self.lock.write_bytes(b'')
        self.lock.chmod(0o666)
        with self.assertRaisesRegex(OwnershipRejected, 'owner-only'):
            with pump_lease(self.lock):
                pass

    def test_directory_and_relative_path_refused(self):
        with self.assertRaises(OwnershipRejected):
            with pump_lease(Path('not-absolute.lock')):
                pass
        self.lock.mkdir()
        with self.assertRaises(OwnershipRejected):
            with pump_lease(self.lock):
                pass


if __name__ == '__main__':
    unittest.main()
