"""Opt-in single-ENQ tests. Synthetic peer, no device/service access."""
import contextlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from test_handover_probe import Clock, Peer as BaselinePeer, FILE, VALID, m


class Peer(BaselinePeer):
    def __init__(self, clock):
        super().__init__(clock)
        self.accept_single_enq = False
        self.sync_enq_counts = []
        self.single_identity = None

    def write(self, data):
        if data[:1] == b'\x01':
            self.sync_enq_counts.append(self.enqs)
            if self.enqs == 1:
                self.sent.append(bytes(data))
                if self.accept_single_enq:
                    self.queue = []
                    self.mode = 'vs1'
                    result = self.single_identity if self.single_identity is not None else self.controller
                    self.schedule(.020, result)
                return len(data)  # Otherwise keep waiting: models a two-ENQ-only peer.
        return super().write(data)


class SingleEnqWireTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.peer = Peer(self.clock)
        self.wire = m.Wire(self.peer, self.clock.now, self.clock.sleep)

    def test_single_enq_three_rounds_and_conservative_setup(self):
        self.peer.accept_single_enq = True
        rows = self.wire.experiment(1)
        self.assertEqual(self.peer.sync_enq_counts, [2, 1, 1, 1])
        self.assertEqual(len(rows), 3)
        for row in rows:
            self.assertEqual(row['vs1']['enq_count'], 1)
            self.assertEqual(row['vs1']['additional_enq_ms'], 0.0)
            self.assertEqual(row['gfa']['P80'], '20')
        self.assertTrue(all(data in m.TX_ALLOWLIST for data in self.peer.sent))

    def test_default_still_uses_two_enqs_everywhere(self):
        rows = self.wire.experiment()
        self.assertEqual(self.peer.sync_enq_counts, [2, 2, 2, 2])
        self.assertTrue(all(row['vs1']['enq_count'] == 2 for row in rows))

    def test_single_enq_does_not_wait_for_second(self):
        self.peer.accept_single_enq = True
        self.peer.fault = 'one_enq_only'
        result = self.wire.enter_vs1(1)
        self.assertEqual(result['additional_enq_ms'], 0.0)
        self.assertEqual(self.peer.sync_enq_counts, [1])

    def test_single_enq_rejection_has_no_hidden_fallback(self):
        with self.assertRaises(m.ProbeError):
            self.wire.experiment(1)
        self.assertEqual(self.peer.sync_enq_counts, [2, 1])
        self.assertEqual(self.peer.sent.count(b'\x16\x00\x00'), 1)
        self.assertEqual(self.wire.samples, [])

    def test_single_enq_still_requires_correct_identity(self):
        self.peer.accept_single_enq = True
        self.peer.single_identity = b'\x20\xcb'
        with self.assertRaises(m.ProbeError):
            self.wire.experiment(1)
        self.assertEqual(self.wire.samples, [])
        self.assertEqual(self.peer.sync_enq_counts, [2, 1])

    def test_invalid_enq_counts_rejected_without_io(self):
        for value in (0, 3, -1, '1', True, 1.0, None):
            with self.subTest(value=value):
                with self.assertRaises(m.ProbeError): self.wire.enter_vs1(value)
                with self.assertRaises(m.ProbeError): self.wire.experiment(value)
        self.assertEqual(self.peer.sent, [])



class SingleEnqOrchestrationTests(unittest.TestCase):
    def test_single_enq_plan_inert(self):
        result = subprocess.run([sys.executable, str(FILE), '--single-enq'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('single-ENQ', result.stdout)
        self.assertIn('Setup and recovery always use two ENQs', result.stdout)

    def test_single_enq_flag_cannot_override_internal_session(self):
        for mode in ('--worker', '--recover'):
            result = subprocess.run([sys.executable, str(FILE), mode, '/invalid', '--single-enq'],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn('recorded session', result.stderr)

    def test_launch_persists_variant_and_reports_distinct_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            states = {unit: unit == m.MAIN for unit in m.SERVICES}
            def run(args, check):
                session = Path(args[-1])
                state = json.loads((session / 'state.json').read_text())
                self.assertEqual(state['vs1_enq_count'], 1)
                m.atomic_json(session / 'measurement.json',
                              {'variant': 'single-enq-comparison', 'experiment_pass': True,
                               'vs1_link_restored': True, 'samples': []})
                m.atomic_json(session / 'recovery.json', {'services_restored': True})
                return subprocess.CompletedProcess(args, 0)
            with patch.object(m, 'ROOT', root), patch.object(m, 'locks', contextlib.nullcontext), \
                 patch.object(m, 'preflight', return_value=({'port_optolink': '/dev/test'}, states)), \
                 patch.object(m.subprocess, 'run', side_effect=run), patch('builtins.print') as output:
                self.assertEqual(m.launch(1), 0)
            self.assertIn(('RESULT=PASS_READ_ONLY_SINGLE_ENQ',), [c.args for c in output.call_args_list])

    def test_worker_recovers_with_two_enqs_after_single_enq_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp)
            settings = session / 'settings.py'; settings.write_text(VALID)
            state = {'port': '/dev/serial/by-id/example', 'vs1_enq_count': 1,
                     'services': {u: True for u in m.SERVICES}, 'restore': []}
            clock = Clock(); peer = Peer(clock); peer.close = lambda: None
            wire = m.Wire(peer, clock.now, clock.sleep)
            with patch.object(m, 'validate_session', return_value=state), \
                 patch.object(m, 'SETTINGS', settings), patch.object(m, 'locks', contextlib.nullcontext), \
                 patch.object(m, 'unit_state', return_value={'WorkingDirectory': '/opt/optolink', 'ActiveState': 'active'}), \
                 patch.object(m, 'pause_services'), patch.object(m, 'open_serial', return_value=peer), \
                 patch.object(m, 'Wire', return_value=wire), patch.object(m.signal, 'signal'):
                self.assertEqual(m.worker(session), 1)
            report = json.loads((session / 'measurement.json').read_text())
            self.assertFalse(report['experiment_pass'])
            self.assertTrue(report['vs1_link_restored'])
            self.assertEqual(report['variant'], 'single-enq-comparison')
            self.assertEqual(report['recovery_enq_count'], 2)
            self.assertEqual(peer.sync_enq_counts, [2, 1, 2])
            self.assertTrue(report['errors'])



if __name__ == '__main__': unittest.main()
