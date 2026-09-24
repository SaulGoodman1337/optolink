#!/usr/bin/env python3
"""Bounded WB2A GFA diagnostic with quarantined FF replies and explicit gaps.

Read-only values and known protocol controls only; no burner start or coding
writes. Requires unchanged pinned cycle, session and P80 helpers beside this file.
Default: print a plan. --self-test: offline only. --execute: pause the splitter
and active party emulator. FF rejects the whole current round. Up to three
full P300/P80 re-identifications may open new segments; no blind bare retry.
Other errors remain fatal. Completion with gaps is NOT an uninterrupted PASS.
No independent watchdog; SIGKILL/power/USB loss can prevent restoration.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import sys
import time
import types

VERSION = '1.1.0'
CYCLE_NAME = 'wb2a-gfa-cycle-logger.py'
CYCLE_SHA256 = 'd5d98242e6f9526522a53f3c801d856ba8c1a7fde6349c05b56059fa732a54e3'
MAX_SECONDS = 600
ROUND_GRACE_SECONDS = 6.0
MAX_ROUNDS = 3000
MAX_RECONNECTS = 3
MIN_CLEAN_ROUNDS = 10
RECONNECT_BUDGET_SECONDS = 20.0
RECOVERY_RESERVE_SECONDS = 15.0


def load_cycle():
    path = Path(__file__).resolve().with_name(CYCLE_NAME)
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != CYCLE_SHA256:
        raise RuntimeError('Original cycle helper hash mismatch; no service/serial operation.')
    module = types.ModuleType('wb2a_cycle_pinned')
    module.__file__ = str(path)
    exec(compile(data, str(path), 'exec'), module.__dict__)
    return module


try:
    cycle = load_cycle()  # Recursively verifies the session and P80 helper bytes.
except Exception as exc:
    print('ERROR: cannot load pinned helpers: ' + str(exc), file=sys.stderr)
    raise SystemExit(2)

session, base = cycle.session, cycle.base
SESSION_SHA256 = cycle.SESSION_SHA256
ProbeError = base.ProbeError
SPLITTER, PARTY = base.SPLITTER, base.PARTY
REGISTERS, P80 = session.REGISTERS, session.P80
ABORT_SIGNALS = base.ABORT_SIGNALS
Capture = cycle.Capture
duration_arg = cycle.duration_arg


class SuspectFF(ProbeError):
    """Observed FF is quarantined by policy; its vendor semantics are unknown."""


class Wire(session.Wire):
    """Known read frames with explicit quality gaps and bounded re-identification.

    FF is not a universal protocol error. For these five diagnostic channels it
    is conservatively quarantined. It is never converted or backfilled. A new
    segment requires a checksum-verified P300 identity and two independent P80
    reads plus an in-session guard. Other transport errors remain fatal.
    """
    def __init__(self, serial_port, log, clock=time.monotonic, *, seconds=300, emit=None):
        if isinstance(seconds, bool) or not isinstance(seconds, int) or not 30 <= seconds <= MAX_SECONDS:
            raise ProbeError('Invalid bounded observation duration.')
        super().__init__(serial_port, log, clock)
        self.seconds = seconds
        self.emit = emit if emit is not None else (lambda record: None)
        self.observation_complete = False
        self.nonzero_rounds = self.phase_changes = 0
        self.elapsed = self.last_confirmed_elapsed = 0.0
        self.failure_elapsed = None
        self.started = None
        self.operation_deadline = None
        self.reconnects = self.reconnects_succeeded = 0
        self.rejected_rounds = self.attempts = 0
        self.segment = 1
        self.last_reconnect_round = 0
        self.partial = []
        self.pending = None

    def _check_budget(self):
        if self.operation_deadline is not None and self.clock() >= self.operation_deadline:
            raise ProbeError('Observation/re-identification time budget exhausted.')

    def _check_session(self):
        check = getattr(self.log, 'ensure_ok', None)
        if check is not None:
            check()
        self._check_budget()
        super()._check_session()

    def send(self, data):
        # Cleanup clears operation_deadline before the normal recovery path.
        self._check_budget()
        super().send(data)

    def exact(self, count, timeout=2.0):
        self._check_budget()
        if self.operation_deadline is not None:
            timeout = min(timeout, self.operation_deadline - self.clock())
        value = super().exact(count, timeout)
        self._check_budget()
        return value

    def control(self, expected, timeout=5.0):
        self._check_budget()
        if self.operation_deadline is not None:
            timeout = min(timeout, self.operation_deadline - self.clock())
        super().control(expected, timeout)
        self._check_budget()

    def encode_sample(self, row):
        return {'parameter': session.LABELS.get(row['address'], 'P80'),
                'address': f'0x{row["address"]:04x}',
                'raw': row['raw'], 'raw_hex': f'{row["raw"]:02x}',
                'rx_time': row['rx_time'],
                'tx_elapsed_s': round(row['tx_mono'] - self.started, 6),
                'rx_elapsed_s': round(row['rx_mono'] - self.started, 6),
                'reply_latency_ms': round(row['latency_ms'], 3),
                'quality': row['quality']}

    def read_session(self, address, round_number):
        if address not in session.FRAMES:
            raise ProbeError('Only P80/P06/P09/P10/P84 are enabled.')
        try:
            self._check_session()
            self.pending = {'address': f'0x{address:04x}',
                            'request_hex': session.FRAMES[address].hex(' '),
                            'attempt': round_number, 'stage': 'before_tx'}
            start = self.clock()
            self.send(session.FRAMES[address])
            self.pending['stage'] = 'awaiting_reply'
            value = self.exact(1, timeout=1.0)[0]
            row = {'round': round_number, 'address': address, 'raw': value,
                   'tx_mono': start, 'rx_mono': self.last_reply, 'rx_time': self.last_wall,
                   'latency_ms': (self.last_reply-start)*1000,
                   'quality': 'received_pending_guard'}
            self.partial.append(row)
            self.pending['stage'] = 'received_checking_tail'
            tail = self.port.read(1)  # Same 50-ms trailing-byte check as pinned transport.
            self._check_budget()
            if tail:
                row['quality'] = 'rejected_trailing_data'
                self.log('RX unexpected trailing ' + tail.hex(' '))
                raise ProbeError('Unexpected trailing data; no automatic reconnection.')
            if value == 0xFF:
                row['quality'] = 'suspect_ff_unresolved'
                self.log(f'SUSPECT_FF attempt={round_number} '
                         f'address=0x{address:04x} raw=ff decoded=unavailable '
                         f'rx_time={row["rx_time"]} reply_latency_ms={row["latency_ms"]:.1f}')
                raise SuspectFF(f'FF at 0x{address:04x}; current round quarantined.')
            if address == P80 and value != 0x20:
                row['quality'] = 'rejected_identity'
                raise ProbeError(f'P80 changed to 0x{value:02x}; expected 20. No automatic reconnection.')
            row['quality'] = 'identity_match' if address == P80 else 'received_pending_guard'
            self.pending['stage'] = 'received'
            self.log(f'SAMPLE attempt={round_number} address=0x{address:04x} '
                     f'raw={value:02x} quality={row["quality"]} '
                     f'rx_time={row["rx_time"]} reply_latency_ms={row["latency_ms"]:.1f}')
            return row
        except BaseException:
            self.active = False
            raise

    def reject(self, exc):
        self.rejected_rounds += 1
        self.emit({'kind': 'rejected_round', 'attempt': self.attempts,
                   'segment': self.segment, 'accepted': False, 'decoded': None,
                   'reason': str(exc), 'elapsed_s': round(self.clock()-self.started, 6),
                   'failed_request': dict(self.pending or {}),
                   'samples': [self.encode_sample(r) for r in self.partial],
                   'last_confirmed_elapsed_s': round(self.last_confirmed_elapsed, 6)})
        self.log(f'QUALITY_GAP attempt={self.attempts} segment={self.segment} '
                 f'accepted=no reason={exc}')

    def reconnect(self, stop_at):
        # This is not a same-session retry: terminate and re-identify both layers.
        if self.reconnects >= MAX_RECONNECTS:
            raise ProbeError('Maximum three re-identification attempts reached; stopping.')
        if self.reconnects and self.rounds-self.last_reconnect_round < MIN_CLEAN_ROUNDS:
            raise ProbeError('Another FF before ten accepted rounds; stopping instead of a retry loop.')
        if stop_at-self.clock() < RECOVERY_RESERVE_SECONDS:
            raise ProbeError('Too little observation time remains for a new verified segment.')
        self.reconnects += 1
        began = self.clock()
        old_segment = self.segment
        self.operation_deadline = min(stop_at, began+RECONNECT_BUDGET_SECONDS)
        self.emit({'kind': 'reidentification_start', 'number': self.reconnects,
                   'old_segment': old_segment, 'elapsed_s': round(began-self.started, 6)})
        self.log(f'REIDENTIFICATION_START {self.reconnects}/{MAX_RECONNECTS}; '
                 'P300 identity then two independent P80 checks; no bare retry.')
        self.partial = []
        self.pending = None
        try:
            if self.p300_ident() != b'\x20\xc2':
                raise ProbeError('Re-identification P300 device is not 20C2.')
            for _ in range(2):
                if self.p80() != 0x20:
                    raise ProbeError('Independent re-identification P80 is not 20.')
            self.read_session(P80, self.attempts)
            self._check_budget()
        except BaseException as exc:
            self.emit({'kind': 'reidentification_failed', 'number': self.reconnects,
                       'elapsed_s': round(self.clock()-self.started, 6),
                       'reason': str(exc) or type(exc).__name__,
                       'failed_request': self.pending,
                       'samples': [self.encode_sample(r) for r in self.partial]})
            raise
        self.segment += 1
        self.reconnects_succeeded += 1
        self.last_reconnect_round = self.rounds
        self.emit({'kind': 'reidentification_complete', 'number': self.reconnects,
                   'new_segment': self.segment, 'elapsed_s': round(self.clock()-self.started, 6),
                   'gap_from_last_confirmed_s': round(self.clock()-self.started-self.last_confirmed_elapsed, 6),
                   'duration_s': round(self.clock()-began, 6),
                   'P300_identity': '20c2', 'independent_P80': ['20', '20'],
                   'session_P80': '20', 'continuous_session': False})
        self.log(f'REIDENTIFICATION_COMPLETE segment={self.segment}; measurements resume with a recorded gap.')
        self.operation_deadline = self.deadline = stop_at + ROUND_GRACE_SECONDS
        self.partial = []
        self.pending = None

    def observe(self):
        self._check_session()
        self.started = self.clock()
        stop_at = self.started + self.seconds
        self.operation_deadline = self.deadline = stop_at + ROUND_GRACE_SECONDS
        self.emit({'kind': 'observation_start', 'version': VERSION,
                   'seconds_requested': self.seconds, 'simultaneous': False,
                   'flame_polled': False, 'fixed_sampling_rate': False,
                   'max_reconnections': MAX_RECONNECTS, 'ff_semantics_known': False})
        self.log(f'OBSERVATION_START seconds={self.seconds}; no flame sensor; no burner command.')
        previous = None
        try:
            # A fault at entry is fatal; only a later suspect FF permits a new segment.
            try:
                self.read_session(P80, 0)
            except BaseException as exc:
                self.reject(exc)
                raise
            self.partial = []
            while self.clock() < stop_at:
                if self.attempts >= MAX_ROUNDS:
                    raise ProbeError('Round safety cap reached before window completed.')
                self.attempts += 1
                self.partial, self.pending = [], None
                try:
                    rows = [self.read_session(a, self.attempts) for a in REGISTERS]
                    guard = self.read_session(P80, self.attempts)
                except SuspectFF as exc:
                    self.reject(exc)
                    self.reconnect(stop_at)
                    previous = None  # Never infer a phase transition across a gap.
                    continue
                except BaseException as exc:
                    self.reject(exc)
                    raise
                values = {r['address']: r['raw'] for r in rows}
                span_ms = (rows[-1]['rx_mono']-rows[0]['rx_mono'])*1000
                changes = []
                if previous is not None:
                    for row in rows:
                        old = previous[row['address']]
                        if old['raw'] != row['raw']:
                            changes.append({'parameter': session.LABELS[row['address']],
                                            'old_raw': old['raw'], 'new_raw': row['raw'],
                                            'previous_rx_time': old['rx_time'], 'rx_time': row['rx_time']})
                for row in rows:
                    row['quality'] = 'accepted_by_policy_not_independently_verified'
                number = self.rounds+1
                self.emit({'kind': 'round', 'round': number, 'attempt': self.attempts,
                           'segment': self.segment, 'guard_passed': True,
                           'quality': 'no_ff_and_identity_match', 'physical_validity_proven': False,
                           'sample_span_ms': round(span_ms, 3),
                           'samples': [self.encode_sample(r) for r in rows],
                           'guard': self.encode_sample(guard),
                           'decoded': {'fan_actual_rpm': values[0x4006]*30,
                                       'modulation_setpoint_pct': round(values[0x4009]*0.3922, 4),
                                       'fan_pwm_setpoint_pct': round(values[0x400A]*0.4, 1),
                                       'phase_raw': values[0x4054]}, 'changes': changes})
                self.rounds = number
                self.last_confirmed_elapsed = self.clock()-self.started
                self.nonzero_rounds += int(any(values.values()))
                self.phase_changes += sum(c['parameter']=='P84' for c in changes)
                self.log(f'ROUND {number} attempt={self.attempts} segment={self.segment} '
                         f't={rows[0]["rx_mono"]-self.started:.3f}s '
                         f'rpm={values[0x4006]*30} mod={values[0x4009]*0.3922:.4f}% '
                         f'pwm={values[0x400A]*0.4:.1f}% phase=0x{values[0x4054]:02x} '
                         f'span_ms={span_ms:.1f} guard=20 quality=no_ff_and_identity_match')
                previous = {r['address']: r for r in rows}
                self.partial = []
            if not self.rounds or self.clock()-self.started > self.seconds+ROUND_GRACE_SECONDS:
                raise ProbeError('Window incomplete or final-round budget exceeded.')
            self.observation_complete = True
            self.log(f'OBSERVATION_COMPLETE=yes ACCEPTED_ROUNDS={self.rounds} '
                     f'REJECTED_ROUNDS={self.rejected_rounds} RECONNECTIONS={self.reconnects_succeeded}')
        except BaseException:
            self.failure_elapsed = self.clock()-self.started
            raise
        finally:
            # Actual failure/end time is retained BEFORE cleanup updates the clock.
            self.elapsed = self.clock()-self.started
            self.operation_deadline = None
            self.deadline = None

def run_guarded(services, opener, log, emit, seconds=300, wire_factory=Wire) -> int:
    """Explicit observation, followed by restoration even after acquisition errors."""
    if isinstance(seconds, bool) or not isinstance(seconds, int) or not 30 <= seconds <= MAX_SECONDS:
        raise ProbeError('Duration outside 30..600; no service operation performed.')
    state = services.state(SPLITTER)
    if (state.get('LoadState'), state.get('ActiveState'), state.get('SubState')) != ('loaded', 'active', 'running'):
        raise ProbeError('Require the splitter to be loaded and running before this test.')
    party = services.state(PARTY)
    if party.get('ActiveState') in ('activating', 'deactivating', 'reloading'):
        raise ProbeError('Party emulator is in transition; no service change performed.')
    to_stop = ([PARTY] if party.get('LoadState') == 'loaded' and party.get('ActiveState') == 'active' else []) + [SPLITTER]
    changed, identities, failures = [], [], []
    restarted = set()
    wire = connection = None
    restored = False
    try:
        for unit in to_stop:
            changed.append(unit)
            log('Stopping ' + unit)
            services.stop(unit)
        connection = opener()
        wire = wire_factory(connection, log, seconds=seconds, emit=emit)
        if wire.p300_ident() != b'\x20\xc2':
            raise ProbeError('Baseline is not 20C2; no GFA command sent.')
        for _ in range(2):
            identities.append(wire.p80())
            if identities[-1] != 0x20:
                raise ProbeError('Expected GFA variant 0x20; no runtime reads.')
        wire.observe()
        identities.append(wire.p80())
        if identities[-1] != 0x20:
            raise ProbeError('Closing P80 differs; capture not confirmed.')
    except BaseException as exc:
        failures.append(str(exc) or type(exc).__name__)
        log('OBSERVATION FAILED: ' + failures[-1])
    finally:
        previous = {sig: signal.signal(sig, signal.SIG_IGN) for sig in ABORT_SIGNALS}
        try:
            if wire is not None and wire.touched:
                for attempt in range(1, 3):
                    try:
                        log(f'Restoring P300 and verifying 00F8/2, attempt {attempt}.')
                        restored = wire.p300_ident() == b'\x20\xc2'
                        if not restored:
                            raise ProbeError('Restored P300 identity is not 20C2.')
                        break
                    except Exception as exc:
                        log('P300 restoration attempt failed: ' + str(exc))
                if not restored:
                    failures.append('P300 restoration could not be verified.')
            if connection is not None:
                try:
                    connection.close()
                    log('Serial port closed.')
                except Exception as exc:
                    failures.append('Serial close failed: ' + str(exc))
            for unit in reversed(changed):
                try:
                    log('Restoring running state: ' + unit)
                    services.start(unit)
                    restarted.add(unit)
                    log('SERVICE_RESTORED=' + unit + ' running')
                except Exception as exc:
                    failures.append('Restart failed: ' + unit + ': ' + str(exc))
                    log(failures[-1])
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
    if getattr(log, 'error', None):
        failures.append(log.error)
    complete = wire is not None and wire.observation_complete and identities == [0x20]*3
    passed = bool(complete and restored and SPLITTER in restarted and not failures)
    result_name = ('COMPLETE_WITH_GAPS' if wire.rejected_rounds else 'PASS') if passed else 'FAIL'
    summary = {'kind': 'summary', 'version': VERSION, 'result': result_name,
               'last_confirmed_elapsed_s': round(wire.last_confirmed_elapsed, 6) if wire else 0,
               'failure_elapsed_s': wire.failure_elapsed if wire else None,
               'attempted_rounds': wire.attempts if wire else 0,
               'rejected_rounds': wire.rejected_rounds if wire else 0,
               'reconnections_attempted': wire.reconnects if wire else 0,
               'reconnections_succeeded': wire.reconnects_succeeded if wire else 0,
               'segments': wire.segment if wire else 0,
               'continuous_session': bool(passed and wire.rejected_rounds == 0),
               'quality_policy': 'FF quarantined; other data not independently verified',
               'observation_complete': bool(wire and wire.observation_complete),
               'seconds_requested': seconds, 'observation_elapsed_s': round(wire.elapsed, 6) if wire else 0,
               'rounds_confirmed': wire.rounds if wire else 0,
               'nonzero_rounds': wire.nonzero_rounds if wire else 0,
               'phase_changes': wire.phase_changes if wire else 0,
               'P80_confirmed': identities == [0x20]*3,
               'P300_restored': restored, 'splitter_restarted': SPLITTER in restarted,
               'services_restarted': sorted(restarted), 'errors': list(failures),
               'full_burner_cycle_verified': False, 'flame_polled': False}
    try:
        emit(summary)
    except Exception as exc:
        failures.append('Summary write failed: ' + str(exc))
        passed = False
    log(f'CONFIRMED_ROUNDS={wire.rounds if wire else 0}')
    log('P80_CONFIRMED=' + ('0x20 GFA' if identities == [0x20]*3 else 'NOT_CONFIRMED'))
    log('P300_RESTORED=' + ('yes' if restored else 'NOT_VERIFIED'))
    log('SPLITTER_RESTARTED=' + ('yes' if SPLITTER in restarted else 'NOT_VERIFIED'))
    for failure in failures:
        log('ERROR: ' + failure)
    log('REJECTED_ROUNDS=' + str(wire.rejected_rounds if wire else 0))
    log('RECONNECTIONS=' + str(wire.reconnects_succeeded if wire else 0))
    log('RESULT=' + (result_name if passed else 'FAIL'))
    log('PASS/COMPLETE_WITH_GAPS describes acquisition and recovery, not physical validity or flame timing.')
    return (2 if wire.rejected_rounds else 0) if passed else 1


def self_test() -> int:
    """Simulated I/O and clock only: 89 pinned tests and 20 new policy tests."""
    import tempfile
    import unittest
    if cycle.self_test() != 0:
        return 1

    class Port:
        def __init__(self, overrides=None):
            self.rx, self.tx = bytearray(), []
            self.t, self.bare, self.independent = 0.0, 0, 0
            self.enq, self.closed = False, False
            self.overrides = overrides or {}
            self.values = {0x4006: 137, 0x4009: 123, 0x400A: 103, 0x4054: 6, P80: 32}
        @property
        def in_waiting(self):
            return len(self.rx)
        def clock(self):
            return self.t
        def write(self, data):
            self.tx.append(data)
            if data == b'\x04':
                self.enq = True
                self.rx.extend(b'\x05')
            elif data == b'\x16\x00\x00':
                self.enq = False
                self.rx.extend(b'\x06')
            elif data == base.IDENT_REQUEST:
                self.rx.extend(bytes.fromhex('06 41 07 01 01 00 f8 02 20 c2 e5'))
            elif data == base.P80_REQUEST:
                self.enq = False
                self.independent += 1
                self.rx.extend(bytes((32,)))
            elif data in session.FRAMES.values():
                self.bare += 1
                answer = self.overrides.get(self.bare, bytes((self.values[int.from_bytes(data[1:3], 'big')],)))
                if isinstance(answer, BaseException):
                    raise answer
                if answer is not None:
                    self.rx.extend(answer)
            return len(data)
        def read(self, count):
            self.t += 0.05
            if not self.rx and self.enq:
                self.rx.extend(b'\x05')
            data = bytes(self.rx[:count])
            del self.rx[:count]
            return data
        def close(self):
            self.closed = True

    class Services:
        def __init__(self, party=True):
            self.active = {SPLITTER: True, PARTY: party}
            self.calls = []
        def state(self, unit):
            return {'LoadState': 'loaded', 'ActiveState': 'active' if self.active[unit] else 'inactive',
                    'SubState': 'running' if self.active[unit] else 'dead'}
        def stop(self, unit):
            self.calls.append(('stop', unit))
            self.active[unit] = False
        def start(self, unit):
            self.calls.append(('start', unit))
            self.active[unit] = True

    class Tests(unittest.TestCase):
        def case(self, port=None, services=None, emit_hook=None, log_hook=None, kind=Wire, opener=None, seconds=30):
            p, s = port or Port(), services or Services()
            logs, records, wires = [], [], []
            def log(msg):
                logs.append(msg)
                if log_hook:
                    log_hook(msg, p)
            def emit(row):
                if emit_hook:
                    emit_hook(row, p)
                records.append(row)
            def factory(connection, logger, **kw):
                w = kind(connection, logger, p.clock, **kw)
                wires.append(w)
                return w
            rc = run_guarded(s, opener or (lambda: p), log, emit, seconds=seconds, wire_factory=factory)
            return rc, p, s, logs, records, wires
        def recovered_failure(self, result):
            self.assertEqual(result[0], 1)
            self.assertTrue(result[1].closed)
            self.assertTrue(all(result[2].active.values()))
            self.assertIn('P300_RESTORED=yes', result[3])
        def test_ff_on_each_runtime_channel_is_quarantined(self):
            for request in (2, 3, 4, 5):
                with self.subTest(request=request):
                    rc,p,s,logs,records,wires = self.case(Port({request:b'\xff'}))
                    self.assertEqual(rc,2)
                    self.assertEqual(records[-1]['result'],'COMPLETE_WITH_GAPS')
                    self.assertEqual(records[-1]['reconnections_succeeded'],1)
                    rejected=[r for r in records if r['kind']=='rejected_round']
                    self.assertEqual(len(rejected),1)
                    self.assertIsNone(rejected[0]['decoded'])
                    self.assertEqual(rejected[0]['samples'][-1]['raw'],255)
                    self.assertTrue(all(x['raw']!=255 for r in records if r['kind']=='round' for x in r['samples']))
                    self.assertFalse(any('rpm=7650' in l or 'phase=0xff' in l for l in logs))
                    self.assertTrue(all(s.active.values()))
                    self.assertTrue(p.closed)
        def test_ff_identity_new_segment_does_not_accept_failed_round(self):
            rc,p,s,logs,records,wires=self.case(Port({6:b'\xff'}))
            self.assertEqual(rc,2)
            bad=next(r for r in records if r['kind']=='rejected_round')
            self.assertEqual(len(bad['samples']),5)
            self.assertEqual(bad['samples'][-1]['parameter'],'P80')
            first=next(r for r in records if r['kind']=='round')
            self.assertEqual(first['attempt'],2)
            self.assertEqual(first['segment'],2)
            self.assertEqual(first['changes'],[])
            self.assertEqual(p.independent,5)  # 2 entry, 2 re-entry, 1 closing.
            self.assertEqual(records[-1]['segments'],2)
            self.assertFalse(records[-1]['continuous_session'])
        def test_ff_reidentification_begins_with_eot_not_bare_retry(self):
            rc,p,*_=self.case(Port({2:b'\xff'}))
            self.assertEqual(rc,2)
            index=next(i for i,x in enumerate(p.tx) if x==session.FRAMES[0x4006])
            self.assertEqual(p.tx[index+1],b'\x04')
            self.assertEqual(p.tx[index+2],b'\x16\x00\x00')
            self.assertEqual(p.tx[index+3],base.IDENT_REQUEST)
            self.assertTrue(all(x in session.ALLOWED_TX for x in p.tx))
        def test_ff_entry_guard_is_fatal(self):
            result=self.case(Port({1:b'\xff'}))
            self.recovered_failure(result)
            self.assertEqual(result[1].bare,1)
            self.assertEqual(result[4][-1]['reconnections_attempted'],0)
        def test_ff_during_reentry_guard_is_fatal(self):
            result=self.case(Port({2:b'\xff',3:b'\xff'}))
            self.recovered_failure(result)
            self.assertEqual(result[1].bare,3)
            self.assertTrue(any(r['kind']=='reidentification_failed' for r in result[4]))
            self.assertEqual(result[4][-1]['reconnections_succeeded'],0)
        def test_ff_immediately_after_reentry_does_not_loop(self):
            result=self.case(Port({2:b'\xff',4:b'\xff'}))
            self.recovered_failure(result)
            self.assertEqual(result[1].bare,4)
            self.assertEqual(result[4][-1]['reconnections_attempted'],1)
            self.assertEqual(result[4][-1]['rejected_rounds'],2)
        def test_fourth_ff_after_three_reentries_is_fatal(self):
            result=self.case(Port({2:b'\xff',54:b'\xff',106:b'\xff',158:b'\xff'}),seconds=180)
            self.recovered_failure(result)
            self.assertEqual(result[1].bare,158)
            self.assertEqual(result[4][-1]['reconnections_succeeded'],3)
            self.assertEqual(result[4][-1]['rejected_rounds'],4)
        def test_other_changed_identity_is_not_retried(self):
            for value in (0,5,6,0x21,0x22,0x23):
                result=self.case(Port({6:bytes((value,))}))
                self.recovered_failure(result)
                self.assertEqual(result[4][-1]['reconnections_attempted'],0)
        def test_ff_with_trailing_bytes_is_not_retried(self):
            result=self.case(Port({2:b'\xff\x20'}))
            self.recovered_failure(result)
            self.assertEqual(result[4][-1]['reconnections_attempted'],0)
            self.assertIn('rejected_trailing_data',str(result[4]))
        def test_reentry_wrong_p300_identity_aborts(self):
            class Bad(Wire):
                calls=0
                def p300_ident(self):
                    value=super().p300_ident()
                    self.calls+=1
                    return b'\x20\xcb' if self.calls==2 else value
            result=self.case(Port({2:b'\xff'}),kind=Bad)
            self.recovered_failure(result)
            self.assertEqual(result[1].bare,2)
            self.assertEqual(result[1].independent,2)
        def test_reentry_wrong_independent_p80_aborts(self):
            class Bad(Wire):
                calls=0
                def p80(self):
                    value=super().p80()
                    self.calls+=1
                    return 0x21 if self.calls==3 else value
            result=self.case(Port({2:b'\xff'}),kind=Bad)
            self.recovered_failure(result)
            self.assertEqual(result[1].bare,2)
            self.assertEqual(result[1].independent,3)
        def test_reentry_budget_expiry_still_cleans_up(self):
            class Bad(Wire):
                calls=0
                def p300_ident(self):
                    self.calls+=1
                    if self.calls==2:
                        self.port.t+=21
                    return super().p300_ident()
            result=self.case(Port({2:b'\xff'}),kind=Bad)
            self.recovered_failure(result)
            self.assertEqual(result[4][-1]['reconnections_succeeded'],0)
            self.assertIsNotNone(result[4][-1]['failure_elapsed_s'])
        def test_reentry_needs_remaining_window(self):
            p=Port()
            w=Wire(p,lambda _:None,p.clock,seconds=30)
            w.started=p.clock()
            with self.assertRaisesRegex(ProbeError,'Too little'):
                w.reconnect(p.clock()+10)
            self.assertEqual(p.tx,[])
        def test_failure_time_is_not_last_confirmed_time(self):
            result=self.case(Port({8:None}))
            self.recovered_failure(result)
            summary=result[4][-1]
            self.assertGreater(summary['failure_elapsed_s'],summary['last_confirmed_elapsed_s'])
            self.assertAlmostEqual(summary['failure_elapsed_s'],summary['observation_elapsed_s'],places=5)
            bad=next(r for r in result[4] if r['kind']=='rejected_round')
            self.assertEqual(bad['failed_request']['address'],'0x4009')
            self.assertEqual(len(bad['samples']),1)
        def test_rejected_round_disk_failure_blocks_reentry(self):
            def fail(row,p):
                if row['kind']=='rejected_round':
                    raise OSError('simulated rejection-record write failure')
            result=self.case(Port({2:b'\xff'}),emit_hook=fail)
            self.recovered_failure(result)
            self.assertEqual(result[4][-1]['reconnections_attempted'],0)
        def test_no_phase_transition_inferred_across_gap(self):
            result=self.case(Port({7:b'\xff',12:b'\x07'}))
            self.assertEqual(result[0],2)
            first_new=next(r for r in result[4] if r['kind']=='round' and r['segment']==2)
            self.assertEqual(first_new['decoded']['phase_raw'],7)
            self.assertEqual(first_new['changes'],[])
        def test_gap_free_result_remains_pass(self):
            result=self.case()
            self.assertEqual(result[0],0)
            self.assertTrue(result[4][-1]['continuous_session'])
            self.assertEqual(result[4][-1]['rejected_rounds'],0)
            self.assertFalse(any(r['kind'].startswith('reidentification') for r in result[4]))
        def test_round_numbering_and_attempt_numbering_are_distinct(self):
            result=self.case(Port({7:b'\xff'}))
            self.assertEqual(result[0],2)
            rows=[r for r in result[4] if r['kind']=='round']
            self.assertEqual([r['round'] for r in rows],list(range(1,len(rows)+1)))
            self.assertEqual([rows[0]['attempt'],rows[1]['attempt']],[1,3])
            self.assertEqual(result[4][-1]['attempted_rounds'],len(rows)+1)
        def test_raw_ff_not_silently_replaced_with_zero(self):
            result=self.case(Port({3:b'\xff'}))
            bad=next(r for r in result[4] if r['kind']=='rejected_round')
            self.assertEqual(bad['samples'][-1]['raw_hex'],'ff')
            self.assertEqual(bad['samples'][-1]['quality'],'suspect_ff_unresolved')
            self.assertIsNone(bad['decoded'])
        def test_reentry_interrupt_restores_services(self):
            class Bad(Wire):
                calls=0
                def p80(self):
                    self.calls+=1
                    if self.calls==3:
                        raise KeyboardInterrupt()
                    return super().p80()
            result=self.case(Port({2:b'\xff'}),kind=Bad)
            self.recovered_failure(result)
            self.assertEqual(result[4][-1]['reconnections_attempted'],1)

    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    return 0 if result.wasSuccessful() else 1


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    group=parser.add_mutually_exclusive_group()
    group.add_argument('--execute',action='store_true',help='Deliberately pause services and observe.')
    group.add_argument('--self-test',action='store_true',help='Offline tests; no hardware/systemd.')
    parser.add_argument('--seconds',type=duration_arg,default=300,help='Observation window 30..600; default 300.')
    args=parser.parse_args()
    if args.self_test:
        return self_test()
    if not args.execute:
        print(f'WB2A GFA quality observation {VERSION}: no action without --execute.\n'
              f'{args.seconds} seconds response-paced P06/P09/P10/P84 with P80 after every round.\n'
              'Known protocol/addresses only; no polling through the paused splitter; no flame sensor.\n'
              'No parameter writes, burner start or settings edits; at most three full re-identifications.\n'
              'Entry, last-round completion (max 6 extra seconds) and restoration are outside the nominal window.\n'
              'FF rejects the whole round; raw evidence and gaps retained; other errors remain fatal.\n'
              'COMPLETE_WITH_GAPS exits 2, FAIL exits 1, gap-free PASS exits 0.\n'
              'Raw .log plus quality-marked .jsonl; signals enter cleanup, no independent watchdog.')
        return 0
    if os.geteuid()!=0:
        print('ERROR: --execute requires root.',file=sys.stderr)
        return 1
    cap,lock_fd,previous=None,None,{}
    result=1
    try:
        import serial
        port=base.read_settings(base.SETTINGS)
        if not stat.S_ISCHR(os.stat(port).st_mode):
            raise ProbeError('Configured port is not a character device.')
        lock_fd=os.open('/run/lock/wb2a-gfa-p80-probe.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        fcntl.flock(lock_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        stamp=dt.datetime.now().strftime('%Y%m%d-%H%M%S')
        cap=Capture(Path('/root')/f'wb2a-gfa-quality-{stamp}-{os.getpid()}')
        cap(f'WB2A GFA quality observation {VERSION}; LOG={cap.path}; JSONL={cap.json_path}')
        cap(f'Configured port: {port}; resolved: {os.path.realpath(port)}; 4800 8E2.')
        cap(f'Explicit service pause for {args.seconds}s observation plus entry/recovery. HA data is not live during pause.')
        cap('No burner command or parameter writes. Pausing the party emulator can change externally maintained requests.')
        cap('Natural operation only. No contemporaneous flame, temperature, pump or 55DC data is collected.')
        cap.emit({'kind':'metadata','version':VERSION,'seconds':args.seconds,
                  'session_sha256':SESSION_SHA256,'p80_sha256':session.BASE_SHA256,
                  'session_hardware_evidence':'2026-09-23T22:55:37+02:00; 10 rounds; 6.359s',
                  'parameter_writes':False,'flame_polled':False,
                  'cycle_sha256':CYCLE_SHA256,
                  'max_reconnections':MAX_RECONNECTS, 'quality_policy':'quarantine_ff_full_reidentification',
                  'ff_semantics_known':False, 'new_recovery_policy_live_validated':False})
        cap.ensure_ok()
        def abort(signum,_frame):
            raise ProbeError('Interrupted by signal '+str(signum)+'; entering cleanup.')
        previous={sig:signal.signal(sig,abort) for sig in ABORT_SIGNALS}
        result=run_guarded(base.Services(),lambda:base.open_port(port,serial),cap,cap.emit,args.seconds)
    except Exception as exc:
        if cap:
            cap('ERROR: '+str(exc))
        else:
            print('ERROR: '+str(exc),file=sys.stderr)
        result=1
    finally:
        for sig,handler in previous.items():
            signal.signal(sig,handler)
        if cap:
            cap('LOG='+str(cap.path))
            cap('JSONL='+str(cap.json_path))
            try:
                cap.close()
            except Exception as exc:
                print('ERROR: '+str(exc),file=sys.stderr)
                result=1
            if cap.error:
                result=1
        if lock_fd is not None:
            os.close(lock_fd)
    return result


if __name__=='__main__':
    raise SystemExit(main())
