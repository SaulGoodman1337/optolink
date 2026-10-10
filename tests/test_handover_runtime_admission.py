"""Offline integration contract: one owner, explicit multi-message quiescence."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from handover_acceleration.coordinator import ACK, DEVICE_ID, EOT, P300_ID, PortLease
from handover_acceleration.phase_planner import Budget
from handover_acceleration.runtime_admission import (
    AdmissionRejected, DispatcherSnapshot, RuntimeAdmissionGate,
)
from test_handover_acceleration import (
    FakeClock, FakePort, expect_vs1, expect_attached_vs1, expect_p300, p300_reply,
)
from test_handover_fc03_fixed import response


class RuntimeAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clock = FakeClock()
        self.gate = RuntimeAdmissionGate(clock=self.clock.monotonic)
        self.budget = Budget(max_vs1_unavailable_ms=8000.0,
                             max_p06_age_ms=9000.0,
                             max_queue_wait_ms=8000.0)
        self.safe = DispatcherSnapshot(
            mqtt_pending=0, tcp_pending=0, forced_polls_pending=0,
            pending_readbacks=0, frame_idle=True,
            external_writers_quiesced=True, queue_admission_paused=True,
            legacy_vs1_verified=True, nearest_writer_deadline_ms=12000.0)
        self.events = []

    def test_requires_every_external_writer_and_queue_barrier(self):
        self.assertTrue(self.gate.decide(self.safe, self.budget).admitted)
        changes = {
            'mqtt_pending': 1, 'tcp_pending': 1,
            'forced_polls_pending': 1, 'pending_readbacks': 1,
            'frame_idle': False, 'external_writers_quiesced': False,
            'queue_admission_paused': False, 'legacy_vs1_verified': False,
            'nearest_writer_deadline_ms': 4000.0,
        }
        for key, value in changes.items():
            with self.subTest(key=key):
                report = self.gate.decide(replace(self.safe, **{key: value}),
                                          self.budget)
                self.assertFalse(report.admitted)
                self.assertNotEqual(report.reason, 'ALL_PRODUCERS_FENCED')

    def test_bad_fake_evidence_refused_even_if_truthy(self):
        for kwargs in ({'mqtt_pending': True}, {'tcp_pending': -1},
                       {'frame_idle': 1}, {'queue_admission_paused': 1},
                       {'nearest_writer_deadline_ms': float('nan')},
                       {'nearest_writer_deadline_ms': float('inf')}):
            with self.subTest(kwargs=kwargs), self.assertRaises(AdmissionRejected):
                replace(self.safe, **kwargs)
        for min_wait in (4.9, float('nan'), -1, True):
            with self.assertRaises(AdmissionRejected):
                RuntimeAdmissionGate(min_write_settle_s=min_wait)
        for spacing in (10, float('inf'), True):
            with self.assertRaises(AdmissionRejected):
                RuntimeAdmissionGate(min_batch_interval_s=spacing)

    def test_multi_message_writes_hold_fence_until_explicit_ack_and_settle(self):
        for cmd in ('write;0x2303;1;1', 'writeraw;0x27d4;2a',
                    'raw;4105000100f80200', '4105000100f80200',
                    'request;0x01;0x00f8;2'):
            gate = RuntimeAdmissionGate(clock=self.clock.monotonic)
            with self.subTest(command=cmd):
                gate.observe_legacy(cmd)
                self.assertEqual(gate.decide(self.safe, self.budget).reason,
                                 'WRITE_READBACK_NOT_ACKNOWLEDGED')
                self.clock.sleep(60)
                self.assertFalse(gate.decide(self.safe, self.budget).admitted)
                with self.assertRaises(AdmissionRejected):
                    gate.acknowledge_external_transaction(producer_confirmed=False)
                gate.acknowledge_external_transaction(producer_confirmed=True)
                self.assertTrue(gate.decide(self.safe, self.budget).admitted)

    def test_ack_does_not_erase_delayed_ha_settle(self):
        self.gate.observe_legacy('w;0x2303;1;1')
        self.gate.acknowledge_external_transaction(producer_confirmed=True)
        self.assertEqual(self.gate.decide(self.safe, self.budget).reason,
                         'DELAYED_HA_READBACK_SETTLE')
        self.clock.sleep(5.249)
        self.assertFalse(self.gate.decide(self.safe, self.budget).admitted)
        self.clock.sleep(0.001)
        self.assertTrue(self.gate.decide(self.safe, self.budget).admitted)

    def test_read_only_mqtt_and_poll_do_not_create_a_write_fence(self):
        for cmd in ('read;0x2303;1;raw;False',
                    'r;0x2303;1;raw;False',
                    'gfaread;0x4006;1;raw;False',
                    ['FAST', '0x4006', 1, 'gfa:30', False]):
            self.gate.observe_legacy(cmd)
        self.assertTrue(self.gate.decide(self.safe, self.budget).admitted)

    def test_wrong_thread_never_admits_or_calls_legacy(self):
        errors = []
        def invoke():
            for fn in (lambda: self.gate.observe_legacy('w;1;1;1'),
                       lambda: self.gate.decide(self.safe, self.budget)):
                try:
                    fn()
                    errors.append('missing rejection')
                except AdmissionRejected as exc:
                    errors.append(str(exc))
        thread = threading.Thread(target=invoke)
        thread.start(); thread.join(timeout=2)
        self.assertEqual(len(errors), 2)
        self.assertTrue(all('serial-owner' in s for s in errors))

    def test_declined_batch_performs_no_io_or_lease_acquisition(self):
        class ExplodingPort:
            def write(self, data):
                raise AssertionError('no serial write permitted')
        blocked = replace(self.safe, external_writers_quiesced=False)
        result = self.gate.run_readonly_batch(
            blocked, self.budget, port=ExplodingPort(),
            legacy_dispatch=lambda *_: self.fail('no legacy call'),
            resume_vs1=lambda: self.fail('no resume'),
            lease=PortLease(Path(self.tmp.name)/'lease'))
        self.assertIsNone(result)
        self.assertFalse((Path(self.tmp.name)/'lease').exists())

    def _port(self, *, corrupt=False):
        from test_handover_acceleration import DEVICE_ID
        script = (expect_attached_vs1() + expect_p300()
                  + [(P300_ID, p300_reply(0xf8, DEVICE_ID)), (ACK, b'')])
        if corrupt:
            script += response('ram_0f20_32', bad_crc=True)[:1] + expect_vs1(2)
        else:
            script += (response('ram_0f20_32') + response('ram_1c60_32')
                       + expect_vs1(1, p06=b'\x53'))
        return FakePort(script)

    def _legacy(self, invalid_p80=False):
        def dispatch(request, port):
            self.events.append(request)
            if '4050' in request:
                payload = b'\x21' if invalid_p80 else b'\x20'
            else:
                payload = b'\x53'
            return 1, bytearray(payload), payload.hex(), 'test'
        return dispatch

    def test_verified_fixed_fc03_batch_borrows_only_existing_serial_handle(self):
        port = self._port()
        result = self.gate.run_readonly_batch(
            self.safe, self.budget, port=port, legacy_dispatch=self._legacy(),
            resume_vs1=lambda: self.events.append('vs1_sync_reset'),
            lease=PortLease(Path(self.tmp.name)/'lease'),
            clock=self.clock.monotonic, sleep=self.clock.sleep)
        self.assertTrue(result.verified_vs1)
        self.assertEqual(result.p300_windows, 1)
        self.assertEqual([name for name, _ in result.reads],
                         ['p300_device', 'ram_0f20_32', 'ram_1c60_32'])
        self.assertEqual(len(result.reads[1][1]), 64)
        self.assertEqual(result.p80_hex, '20')
        self.assertEqual(result.p06_hex, '53')
        self.assertEqual(port.writes.count(EOT), 2)
        self.assertEqual(port.script, [])
        self.assertFalse(port.closed)
        self.assertEqual(self.events, ['vs1_sync_reset',
                                     'gfaread;0x4050;1;raw;False',
                                     'gfaread;0x4006;1;raw;False'])
        self.assertEqual(self.gate.completed_windows, 1)
        self.assertEqual(self.gate.decide(self.safe, self.budget).reason,
                         'BATCH_COOLDOWN')
        self.clock.sleep(120)
        self.assertTrue(self.gate.decide(self.safe, self.budget).admitted)

    def test_incorrect_fc03_crc_fails_closed_after_conservative_vs1_restore(self):
        port = self._port(corrupt=True)
        with self.assertRaises(Exception):
            self.gate.run_readonly_batch(
                self.safe, self.budget, port=port,
                legacy_dispatch=self._legacy(),
                resume_vs1=lambda: self.fail('do not resume invalid window'),
                lease=PortLease(Path(self.tmp.name)/'lease'),
                clock=self.clock.monotonic, sleep=self.clock.sleep)
        self.assertTrue(self.gate.failed_closed)
        self.assertFalse(port.closed)
        self.assertEqual(port.script, [])
        self.assertFalse(self.gate.decide(self.safe, self.budget).admitted)
        self.assertFalse(self.events)

    def test_invalid_legacy_p80_after_return_is_not_success(self):
        port = self._port()
        with self.assertRaisesRegex(AdmissionRejected, 'P80'):
            self.gate.run_readonly_batch(
                self.safe, self.budget, port=port,
                legacy_dispatch=self._legacy(invalid_p80=True),
                resume_vs1=lambda:None,
                lease=PortLease(Path(self.tmp.name)/'lease'),
                clock=self.clock.monotonic, sleep=self.clock.sleep)
        self.assertTrue(self.gate.failed_closed)
        self.assertEqual(self.gate.completed_windows, 0)
        self.assertFalse(port.closed)


if __name__ == '__main__':
    unittest.main()
