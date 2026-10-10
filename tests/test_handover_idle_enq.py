"""Natural-ENQ discriminator: synthetic peers, never a real serial device."""
import contextlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_handover_probe import Clock, FILE, VALID, m
from test_handover_single_enq import Peer as SinglePeer


class IdlePeer(SinglePeer):
    def __init__(self, clock):
        super().__init__(clock)
        self.accept_single_enq = True
        self.idle_delay = .350  # Synthetic test fixture, NOT a WB2A measurement.
        self.idle_reply = b'\x05'
        self.pending_idle = None
        self.warm_reads = 0
        self.missing_on_warm = None

    def write(self, data):
        self.queue = [q for q in self.queue if q is not self.pending_idle]
        self.pending_idle = None
        result = super().write(data)
        if data == m.VS1_ID:
            self.warm_reads += 1
        is_vs1 = data in (b'\x01' + m.VS1_ID, m.VS1_ID, m.VS1_SOFTWARE, *m.GFA.values())
        if is_vs1 and self.idle_reply is not None and self.warm_reads != self.missing_on_warm:
            item = [self.clock.now() + .020 + self.idle_delay, bytearray(self.idle_reply)]
            self.queue.append(item)
            self.queue.sort(key=lambda q: q[0])
            self.pending_idle = item
        return result

    def read(self, n):
        is_idle = bool(self.queue and self.queue[0] is self.pending_idle
                       and self.queue[0][0] <= self.clock.now())
        data = super().read(n)
        if is_idle and data == b'\x05':
            self.mode = 'detect'
            self.enqs = 1
        return data


class IdleEnqWireTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.peer = IdlePeer(self.clock)
        self.wire = m.Wire(self.peer, self.clock.now, self.clock.sleep)

    def warm(self):
        self.wire.enter_vs1(2)
        self.wire.vs1(m.VS1_ID, 2, m.IDENT)

    def test_three_rounds_no_eot_before_p300(self):
        rows = self.wire.experiment(1, idle_enq=True)
        self.assertEqual(len(rows), 3)
        self.assertEqual(self.peer.sync_enq_counts, [2, 1, 1, 1])
        self.assertEqual(self.peer.sent.count(b'\x04'), 4)  # Setup + three returns only.
        for i, frame in enumerate(self.peer.sent):
            if frame == b'\x16\x00\x00':
                self.assertEqual(self.peer.sent[i-1], m.VS1_ID)
        for row in rows:
            self.assertEqual(row['p300']['entry_mode'], 'natural-enq-no-eot')
            self.assertIs(row['p300']['eot_sent'], False)
            self.assertAlmostEqual(row['p300']['last_vs1_rx_to_enq_ms'], 350, delta=3)
            self.assertLess(row['p300']['enq_ms'], row['p300']['last_vs1_rx_to_enq_ms'])
            self.assertEqual(row['vs1']['enq_count'], 1)
            self.assertEqual(row['gfa']['P80'], '20')

    def test_no_rx_buffer_purge_in_idle_entry(self):
        self.warm()
        with patch.object(self.peer, 'reset_input_buffer', side_effect=AssertionError('purged')):
            self.assertIs(self.wire.enter_p300_idle()['eot_sent'], False)

    def test_no_fresh_identity_no_io(self):
        with self.assertRaisesRegex(m.ProbeError, 'warm VS1 identity'):
            self.wire.enter_p300_idle()
        self.assertEqual(self.peer.sent, [])

    def test_intervening_request_invalidates_proof(self):
        self.warm()
        self.wire.vs1(m.VS1_SOFTWARE, 2, m.SOFTWARE)
        before = list(self.peer.sent)
        with self.assertRaises(m.ProbeError): self.wire.enter_p300_idle()
        self.assertEqual(before, self.peer.sent)

    def test_stale_identity_refused_without_tx(self):
        self.warm()
        self.clock.sleep(.251)
        before = list(self.peer.sent)
        with self.assertRaises(m.ProbeError): self.wire.enter_p300_idle()
        self.assertEqual(before, self.peer.sent)

    def test_missing_enq_no_start_no_fallback(self):
        self.peer.idle_reply = None
        with self.assertRaisesRegex(m.ProbeError, 'deadline'):
            self.wire.experiment(1, idle_enq=True)
        self.assertNotIn(b'\x16\x00\x00', self.peer.sent)
        self.assertEqual(self.peer.sent.count(b'\x04'), 1)
        self.assertEqual(self.wire.samples, [])

    def test_unexpected_control_or_data_is_not_skipped(self):
        for value in (b'\x06', b'\x15', b'\x00', b'\x41'):
            with self.subTest(value=value):
                self.setUp()
                self.peer.idle_reply = value
                with self.assertRaisesRegex(m.ProbeError, 'unexpected control/data'):
                    self.wire.experiment(1, idle_enq=True)
                self.assertNotIn(b'\x16\x00\x00', self.peer.sent)
                self.assertEqual(self.peer.sent.count(b'\x04'), 1)

    def test_start_nack_no_hidden_reset(self):
        self.warm()
        self.peer.fault = 'bad_start'
        with self.assertRaises(m.ProbeError): self.wire.enter_p300_idle()
        self.assertEqual(self.peer.sent.count(b'\x04'), 1)
        self.assertEqual(self.peer.sent.count(b'\x16\x00\x00'), 1)
        self.assertNotIn(m.P300_ID, self.peer.sent)

    def test_all_existing_p300_checks_still_apply(self):
        for fault in ('checksum', 'wrong_address', 'wrong_function', 'controller_error',
                      'wrong_length', 'wrong_message', 'oversized', 'timeout'):
            with self.subTest(fault=fault):
                self.setUp(); self.warm(); self.peer.fault = fault
                with self.assertRaises(m.ProbeError): self.wire.enter_p300_idle()
                self.assertEqual(self.peer.sent.count(b'\x16\x00\x00'), 1)
                self.assertNotIn(m.P300_SOFTWARE, self.peer.sent)

    def test_wrong_identity_and_software_stop(self):
        for field, value in (('controller', b'\x20\xcb'), ('software', b'\x01\x04')):
            with self.subTest(field=field):
                self.setUp(); self.warm(); setattr(self.peer, field, value)
                with self.assertRaises(m.ProbeError): self.wire.enter_p300_idle()

    def test_failure_preserves_completed_rounds(self):
        self.peer.missing_on_warm = 2
        with self.assertRaises(m.ProbeError): self.wire.experiment(1, idle_enq=True)
        self.assertEqual(len(self.wire.samples), 1)
        self.assertEqual(self.peer.sent.count(b'\x16\x00\x00'), 1)

    def test_invalid_variant_denied_before_io(self):
        for count, idle in ((2, True), (1, 1), (1, 'yes'), (1, None), (True, True)):
            with self.subTest(count=count, idle=idle):
                with self.assertRaises(m.ProbeError): self.wire.experiment(count, idle_enq=idle)
        self.assertEqual(self.peer.sent, [])

    def test_fixed_tx_allowlist_unchanged(self):
        expected = {bytes.fromhex(x) for x in (
            '04', '160000', '06', '01f700f802', 'f700f802', 'f7778c02',
            '4105000100f80200', '41050001778c020b', '6b405001', '6b400601',
            '6b400901', '6b405701')}
        self.assertEqual(m.TX_ALLOWLIST, expected)
        self.wire.experiment(1, idle_enq=True)
        self.assertTrue(all(frame in expected for frame in self.peer.sent))


class IdleEnqOrchestrationTests(unittest.TestCase):
    def test_inert_plan(self):
        r = subprocess.run([sys.executable, str(FILE), '--idle-enq'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('PLAN ONLY', r.stdout)
        self.assertIn('IDLE ENQ: no EOT or TX', r.stdout)

    def test_flags_exclusive_and_internal_override_denied(self):
        for args in (['--idle-enq', '--single-enq'], ['--worker', '/invalid', '--idle-enq'],
                     ['--recover', '/invalid', '--idle-enq']):
            with self.subTest(args=args):
                r = subprocess.run([sys.executable, str(FILE)] + args, capture_output=True, text=True)
                self.assertEqual(r.returncode, 2)

    def test_launch_records_flag_and_distinct_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            states = {u: u == m.MAIN for u in m.SERVICES}
            def run(args, check):
                session = Path(args[-1]); state = json.loads((session/'state.json').read_text())
                self.assertIs(state['idle_enq'], True)
                self.assertEqual(state['vs1_enq_count'], 1)
                m.atomic_json(session/'measurement.json', {'variant': m.IDLE_VARIANT,
                              'experiment_pass': True, 'vs1_link_restored': True, 'samples': []})
                m.atomic_json(session/'recovery.json', {'services_restored': True})
                return subprocess.CompletedProcess(args, 0)
            with patch.object(m, 'ROOT', root), patch.object(m, 'locks', contextlib.nullcontext), \
                 patch.object(m, 'preflight', return_value=({'port_optolink':'/dev/test'}, states)), \
                 patch.object(m.subprocess, 'run', side_effect=run), patch('builtins.print') as output:
                self.assertEqual(m.launch(1, idle_enq=True), 0)
            self.assertIn(('RESULT=PASS_READ_ONLY_IDLE_ENQ',), [c.args for c in output.call_args_list])

    def test_worker_failure_restores_two_enq_without_hiding_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp); settings = session/'settings.py'; settings.write_text(VALID)
            state = {'port': '/dev/serial/by-id/example', 'vs1_enq_count': 1, 'idle_enq': True,
                     'services': {u: True for u in m.SERVICES}, 'restore': []}
            clock = Clock(); peer = IdlePeer(clock); peer.idle_reply = None; peer.close = lambda: None
            wire = m.Wire(peer, clock.now, clock.sleep)
            with patch.object(m, 'validate_session', return_value=state), \
                 patch.object(m, 'SETTINGS', settings), patch.object(m, 'locks', contextlib.nullcontext), \
                 patch.object(m, 'unit_state', return_value={'WorkingDirectory':'/opt/optolink','ActiveState':'active'}), \
                 patch.object(m, 'pause_services'), patch.object(m, 'open_serial', return_value=peer), \
                 patch.object(m, 'Wire', return_value=wire), patch.object(m.signal, 'signal'):
                self.assertEqual(m.worker(session), 1)
            report = json.loads((session/'measurement.json').read_text())
            self.assertFalse(report['experiment_pass'])
            self.assertTrue(report['vs1_link_restored'])
            self.assertEqual(report['variant'], m.IDLE_VARIANT)
            self.assertEqual(report['recovery_enq_count'], 2)
            self.assertEqual(peer.sync_enq_counts, [2, 2])
            self.assertTrue(report['errors'])

    def test_invalid_recorded_flag_stops_before_pause(self):
        state = {'vs1_enq_count': 1, 'idle_enq': 'yes'}
        with patch.object(m, 'validate_session', return_value=state), patch.object(m, 'pause_services') as pause:
            with self.assertRaises(m.ProbeError): m.worker(Path('/unused'))
            pause.assert_not_called()


if __name__ == '__main__': unittest.main()
