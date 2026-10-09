"""Hardware-free tests for the opt-in REAL-test supervisor and worker.

No serial port or systemd command is used. Production and logger paths are
replaced by mocks. The unmodified pinned legacy helper is imported in CI.
"""
import contextlib
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
# The local source workspace lacks the pinned helper; CI has the exact
# vendored original copied from optolink-p300-migration. This placeholder
# is used solely to import the harness before replacing its integrations.
if not (Path(__file__).resolve().parents[1] / 'tools/handover_acceleration/legacy_probe.py').exists():
    placeholder = types.ModuleType('handover_acceleration.legacy_probe')
    placeholder.ProbeError = type('ProbeError', (RuntimeError,), {})
    placeholder.ROOT = Path('/unused')
    placeholder.UNIT = 'unused'
    placeholder.MAIN = 'optolink-splitter.service'
    placeholder.unit_state = lambda name: {'ActiveState': 'inactive'}
    sys.modules['handover_acceleration.legacy_probe'] = placeholder
from handover_acceleration import live_probe as m
from test_handover_acceleration import FakePort, expect_vs1, expect_p300, p300_reply
from handover_acceleration.coordinator import DEVICE_ID, ACK, GFA, P300_ID


class LiveGuardTests(unittest.TestCase):
    def test_default_cli_inert(self):
        with patch.object(sys, 'argv', ['live_probe.py']):
            with patch.object(m, 'execute', side_effect=AssertionError('must not execute')):
                self.assertEqual(m.main(), 0)

    def test_execute_requires_explicit_pause_acceptance(self):
        with patch.object(sys, 'argv', ['live_probe.py', '--execute']):
            with patch.object(m, 'execute', side_effect=AssertionError('must not execute')):
                with self.assertRaisesRegex(m.base.ProbeError, 'telemetry'):
                    m.main()

    def test_internal_modes_need_systemd(self):
        with patch.dict(os.environ, {'INVOCATION_ID': ''}):
            with patch.object(sys, 'argv', ['live_probe.py', '--worker', '/tmp/fake']):
                with patch.object(m, 'worker', side_effect=AssertionError('must not execute')):
                    # non-root is an explicit refusal; on root systemd env
                    # exists but the call would be allowed, so force no ID.
                    with patch.dict(os.environ, {}, clear=True):
                        with self.assertRaisesRegex(m.base.ProbeError, 'systemd'):
                            m.main()

    def test_running_rpm_logger_blocks_preflight(self):
        def unit_state(unit):
            return {'ActiveState': 'active' if 'rpm-trigger' in unit else 'inactive'}
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(m.base.ProbeError, 'rpm-trigger'):
                m.guard_other_research(unit_state=unit_state, proc_root=Path(td))

    def test_logger_process_blocks_even_if_unit_inactive(self):
        with tempfile.TemporaryDirectory() as td:
            proc = Path(td) / '88888'
            proc.mkdir()
            (proc / 'cmdline').write_bytes(b'python3\x00/root/test/tools/wb2a-p300-rpm-trigger.py\x00--worker\x00')
            with self.assertRaisesRegex(m.base.ProbeError, 'RESEARCH_PROCESS_ACTIVE'):
                m.guard_other_research(unit_state=lambda _: {'ActiveState': 'inactive'}, proc_root=Path(td))

    def test_unrelated_process_permitted(self):
        with tempfile.TemporaryDirectory() as td:
            proc = Path(td) / '88888'
            proc.mkdir()
            (proc / 'cmdline').write_bytes(b'python3\x00optolink-live-acceptance\x00')
            m.guard_other_research(unit_state=lambda _: {'ActiveState': 'inactive'}, proc_root=Path(td))

    def test_enq_trace_distinguishes_individual_bytes(self):
        ev = [dict(direction='TX', hex='04', t_monotonic=1.0),
              dict(direction='RX', hex='05', t_monotonic=2.998),
              dict(direction='RX', hex='05', t_monotonic=5.236),
              dict(direction='TX', hex='0100', t_monotonic=5.240),
              dict(direction='RX', hex='05', t_monotonic=5.245),  # data, not ENQ
              dict(direction='TX', hex='04', t_monotonic=10.0),
              dict(direction='RX', hex='05', t_monotonic=11.998)]
        result = m.enq_trace(ev)
        self.assertEqual([len(x['enq_wait_ms']) for x in result], [2,1])
        self.assertAlmostEqual(result[0]['enq_wait_ms'][0], 1998.0)
        self.assertAlmostEqual(result[0]['enq_wait_ms'][1], 4236.0)

    def test_unknown_service_state_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(m.base.ProbeError, 'RUNNING_OR_UNKNOWN'):
                m.guard_other_research(unit_state=lambda _: {'ActiveState': 'activating'}, proc_root=Path(td))

    def test_research_guard_precedes_production_checks(self):
        with patch.object(m.os, 'geteuid', return_value=0), \
             patch.object(m, 'guard_other_research', side_effect=m.base.ProbeError('RUNNING')), \
             patch.object(m.base, 'preflight', side_effect=AssertionError('must not preflight'), create=True):
            with self.assertRaisesRegex(m.base.ProbeError, 'RUNNING'):
                m.preflight()

    def test_source_manifest_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td)
            (dest / 'coordinator.py').write_text('safe')
            with self.assertRaisesRegex(m.base.ProbeError, 'staged source changed'):
                m.ensure_hashes(dest, {'source_sha256': {'coordinator.py': '0' * 64}})


class LiveWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.session = Path(self.temp.name)
        self.settings = types.SimpleNamespace(read_text=lambda: 'safe-settings')
        self.state = {'port': '/dev/MOCK-NO-DEVICE', 'services': {m.base.MAIN: True},
                      'restore': [], 'source_sha256': {'fake': 'hash'}}
        self.base_state = lambda unit: {'WorkingDirectory': '/opt/optolink',
                                         'ActiveState': 'active' if unit == m.base.MAIN else 'inactive'}
        self.fake_port = FakePort(expect_vs1(2) + expect_p300() +
                                  expect_vs1(1) + [(GFA['P09'], b'\x0a'),
                                                   (GFA['P87'], b'\x00')])
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        def set_(obj, name, replacement):
            self.stack.enter_context(patch.object(obj, name, replacement, create=True))
        self.set_ = set_
        set_(m, 'verify_session', lambda _: self.state)
        set_(m, 'guard_other_research', lambda *a, **k: None)
        set_(m.base, 'read_settings', lambda _: {'port_optolink': self.state['port']})
        set_(m.base, 'SETTINGS', self.settings)
        set_(m.base, 'unit_state', self.base_state)
        set_(m.base, 'pause_services', lambda *a, **kw: None)
        set_(m.base, 'assert_no_owner', lambda _: None)
        set_(m.base, 'open_serial', lambda _: self.fake_port)
        set_(m.base, 'atomic_json', lambda path, value: path.write_text(json.dumps(value)))
        set_(m.base, 'locks', lambda: contextlib.nullcontext())

    def test_one_real_wire_shape_via_fake_port(self):
        with patch.object(m, 'PortLease') as lease:
            lease.return_value.acquire.return_value = None
            lease.return_value.release.return_value = None
            self.assertEqual(m.worker(self.session), 0)
        evidence = json.loads((self.session / 'measurement.json').read_text())
        self.assertTrue(evidence['experiment_pass'])
        self.assertTrue(evidence['vs1_link_restored'])
        self.assertEqual(evidence['gfa']['P80'], '20')
        self.assertEqual(evidence['gfa']['P06'], '00')
        self.assertEqual([v for kind, v in evidence['history'] if kind == 'vs1'],
                         ['verified:2', 'verified:1'])
        self.assertEqual(sum(x == b'\x04' for x in self.fake_port.writes), 3)
        self.assertTrue(self.fake_port.closed)
        self.assertFalse(self.fake_port.script)
        self.assertIn('roundtrip_with_gfa', evidence['phases_ms'])
        self.assertEqual(evidence['gfa']['P09'], '0a')
        self.assertEqual(len([w for w in self.fake_port.writes if w == P300_ID]), 1)
        self.assertEqual(len([w for w in self.fake_port.writes if w == GFA['P80']]), 2)
        self.assertEqual([len(x['enq_wait_ms']) for x in evidence['enq_trace']], [2, 1, 1])
        self.assertEqual(len([x for x in evidence['events'] if x['direction'] == 'RX' and x['hex'] == '05']), 4)

    def test_bad_p300_response_never_reports_fast_success(self):
        self.fake_port = FakePort(expect_vs1(2) + expect_p300(bad_crc=True) +
                                  expect_vs1(2))
        with patch.object(m, 'PortLease') as lease:
            self.assertEqual(m.worker(self.session), 1)
        evidence = json.loads((self.session / 'measurement.json').read_text())
        self.assertFalse(evidence['experiment_pass'])
        self.assertTrue(evidence['errors'])
        self.assertNotIn('verified:1', [v for key,v in evidence['history'] if key == 'vs1'])
        self.assertIn(('vs1', 'verified:2'), [tuple(row) for row in evidence['history']])
        self.assertTrue(self.fake_port.closed)

    def test_worker_refuses_new_logger_before_pausing_services(self):
        def no():
            raise m.base.ProbeError('new logger detected')
        self.set_(m, 'guard_other_research', no)
        with patch.object(m.base, 'pause_services', side_effect=AssertionError('service must not stop')):
            self.assertEqual(m.worker(self.session), 1)
        data = json.loads((self.session / 'measurement.json').read_text())
        self.assertIn('new logger detected', data['errors'][0])


class IndependentRestoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.session = Path(self.temp.name)
        self.state = {'port': '/dev/FAKE', 'services': {m.base.MAIN: True},
                      'restore': [m.base.MAIN], 'source_sha256': {'fake':'hash'}}

    def test_successful_worker_skips_duplicate_eot(self):
        (self.session / 'measurement.json').write_text(json.dumps({
            'experiment_pass': True, 'vs1_link_restored': True}))
        with patch.object(m.base, 'open_serial', side_effect=AssertionError('do not open'), create=True):
            result = m.link_restore(self.session, self.state)
        self.assertTrue(result['verified'])
        self.assertFalse(result['attempted'])

    def test_crash_without_measurement_uses_independent_two_enq(self):
        class FakeWire:
            def __init__(self, port):
                self.port = port
                self.enq_counts = []
            def enter_vs1(self, count):
                self.enq_counts.append(count)
            def vs1(self, request, count, expected=None):
                return b'\x00' if expected is None else expected
        port = types.SimpleNamespace(close=lambda: None)
        with patch.object(m, 'guard_other_research', lambda: None), \
             patch.object(m.base, 'assert_no_owner', lambda _: None, create=True), \
             patch.object(m.base, 'open_serial', lambda _: port, create=True), \
             patch.object(m.base, 'Wire', FakeWire, create=True), \
             patch.object(m.base, 'VS1_SOFTWARE', b'\x00', create=True), \
             patch.object(m.base, 'SOFTWARE', b'\x00', create=True), \
             patch.object(m.base, 'GFA', {'P80': b'\x00','P06': b'\x00'}, create=True):
            r = m.link_restore(self.session, self.state)
        self.assertTrue(r['attempted'])
        self.assertTrue(r['verified'])

    def test_failed_serial_recovery_still_attempts_original_main(self):
        def fake_recover(session):
            (session / 'recovery.json').write_text(json.dumps({'services_restored':True,'errors':[]}))
            return 0
        with patch.object(m, 'verify_session', lambda _: self.state), \
             patch.object(m, 'guard_other_research', lambda: None), \
             patch.object(m, 'link_restore', lambda *a: {'attempted':True,'verified':False,'error':'bad port'}), \
             patch.object(m.base, 'locks', lambda: contextlib.nullcontext(), create=True), \
             patch.object(m.base, 'recover', fake_recover, create=True), \
             patch.object(m.base, 'atomic_json', lambda p,v: p.write_text(json.dumps(v)), create=True):
            code = m.recover(self.session)
        self.assertEqual(code, 1)
        saved = json.loads((self.session / 'recovery.json').read_text())
        self.assertFalse(saved['overall_verified'])
        self.assertTrue(saved['services_restored'])



class ProductionHealthParserTests(unittest.TestCase):
    """Regression: real optolink-debug produces a banner plus an arrow reply."""
    CMD80 = 'gfaread;0x4050;1;raw;False'
    CMD06 = 'gfaread;0x4006;1;raw;False'

    @staticmethod
    def output(command, reply):
        return ('Connecting as user mqtt to MQTT broker local-host:1883.\\n'
                ' MQTT connected successfully.\\n' +
                f'{command} <- Vito/resp: {reply}\\n')

    def test_real_debug_banner_and_gfa_p80_are_valid(self):
        actual = self.output(self.CMD80, '1;0x4050;20')
        r = m.parse_debug_health(actual, self.CMD80, 0x4050, 'P80')
        self.assertTrue(r['valid'])
        self.assertEqual(r['response'], '1;0x4050;20')
        self.assertNotIn('Connecting', r['response'])

    def test_real_debug_banner_and_zero_rpm_valid(self):
        r = m.parse_debug_health(self.output(self.CMD06, '1;0x4006;00'),
                                  self.CMD06, 0x4006, 'P06')
        self.assertTrue(r['valid'])
        self.assertEqual(r['reason'], 'OK')

    def test_success_exit_with_timeout_output_is_not_success(self):
        r = m.parse_debug_health(f'{self.CMD80} <- timeout\\n',
                                  self.CMD80, 0x4050, 'P80')
        self.assertFalse(r['valid'])
        self.assertEqual(r['reason'], 'NO_MQTT_REPLY_OR_TIMEOUT')

    def test_failed_status_and_wrong_p80_are_rejected(self):
        for reply in ('0;0x4050;20', '1;0x4050;21',
                      '1;0x4050;ff', '1;0x4050;1234'):
            with self.subTest(reply=reply):
                self.assertFalse(m.parse_debug_health(
                    self.output(self.CMD80, reply),
                    self.CMD80, 0x4050, 'P80')['valid'])

    def test_wrong_address_rejected(self):
        r = m.parse_debug_health(self.output(self.CMD80, '1;0x4006;20'),
                                  self.CMD80, 0x4050, 'P80')
        self.assertEqual(r['reason'], 'WRONG_ADDRESS')

    def test_duplicated_mqtt_reply_rejected(self):
        r = m.parse_debug_health(self.output(self.CMD80, '1;0x4050;20') * 2,
                                  self.CMD80, 0x4050, 'P80')
        self.assertEqual(r['reason'], 'MISSING_OR_MULTIPLE_REPLY_LINES')

    def test_read_health_parses_actual_debug_output_and_no_banner_stored(self):
        def fake_run(args, **kwargs):
            cmd = args[2]
            reply = '1;0x4050;20' if '4050' in cmd else '1;0x4006;00'
            return types.SimpleNamespace(
                returncode=0, stdout=self.output(cmd, reply))
        with patch.object(m.subprocess, 'run', side_effect=fake_run):
            h = m.read_health()
        self.assertTrue(all(x['valid'] for x in h.values()))
        self.assertEqual(h['P06']['response'], '1;0x4006;00')
        self.assertNotIn('broker', json.dumps(h).lower())

    def test_read_health_debug_client_exit_nonzero_is_failure(self):
        with patch.object(m.subprocess, 'run',
                          return_value=types.SimpleNamespace(
                              returncode=1,
                              stdout=self.output(self.CMD80, '1;0x4050;20'))):
            r = m.read_health()
        self.assertFalse(r['P80']['valid'])
        self.assertEqual(r['P80']['reason'], 'DEBUG_CLIENT_EXIT_NONZERO')

    def test_health_only_refuses_when_original_service_not_running(self):
        with patch.object(m, 'guard_other_research'), \
             patch.object(m.base, 'unit_state', return_value={'ActiveState': 'inactive'}), \
             patch.object(m, 'read_health', side_effect=AssertionError('must not read')):
            with self.assertRaisesRegex(m.base.ProbeError, 'not confirmed active'):
                m.health_only()

    def test_health_only_requires_no_research_conflict(self):
        with patch.object(m, 'guard_other_research',
                          side_effect=m.base.ProbeError('research busy')), \
             patch.object(m, 'read_health', side_effect=AssertionError('must not read')):
            with self.assertRaisesRegex(m.base.ProbeError, 'research busy'):
                m.health_only()

    def test_health_only_no_serial_and_no_service_stop(self):
        with patch.object(m, 'guard_other_research'), \
             patch.object(m.base, 'unit_state',
                          return_value={'ActiveState':'active', 'SubState':'running',
                                        'WorkingDirectory':'/opt/optolink'}), \
             patch.object(m.base, 'pause_services',
                          side_effect=AssertionError('must not stop')), \
             patch.object(m.base, 'open_serial',
                          side_effect=AssertionError('must not open port')), \
             patch.object(m, 'read_health', return_value={
                 'P80': {'valid': True}, 'P06': {'valid': True}}):
            self.assertEqual(m.health_only(), 0)

    def test_health_only_cli_dispatch_is_isolated(self):
        with patch.object(sys, 'argv', ['live_probe.py', '--health-only']), \
             patch.object(m, 'health_only', return_value=0), \
             patch.object(m, 'execute', side_effect=AssertionError('must not execute')):
            self.assertEqual(m.main(), 0)

if __name__ == '__main__':
    unittest.main()
