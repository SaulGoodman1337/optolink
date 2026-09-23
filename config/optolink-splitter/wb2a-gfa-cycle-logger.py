#!/usr/bin/env python3
"""Bounded WB2A GFA observation using the locally demonstrated VS1 session.

No parameter writes and no automatic burner start. Only P06/P09/P10/P84 and
P80 guards; P300 00F8/2 before/after. No flame, pump or temperature polling.
Requires unchanged SHA256-pinned P80 and session helpers in this directory.
Default: plan only. --execute deliberately pauses normal splitter/party service
for --seconds (30..600, default 300), plus entry, last round and restoration.
No fixed sample rate; no automatic retry; no guarantee against SIGKILL/power loss.
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

VERSION = '1.0.0'
SESSION_NAME = 'wb2a-gfa-session-probe.py'
SESSION_SHA256 = '32351e07cb0d661c00f7bcb7851d8103aca0b9cbc2f339041202e48b760d6da2'
MAX_SECONDS = 600
ROUND_GRACE_SECONDS = 6.0
MAX_ROUNDS = 3000


def load_session():
    path = Path(__file__).resolve().with_name(SESSION_NAME)
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != SESSION_SHA256:
        raise RuntimeError('Session helper hash mismatch; no service/serial operation.')
    module = types.ModuleType('wb2a_session_pinned')
    module.__file__ = str(path)
    exec(compile(data, str(path), 'exec'), module.__dict__)
    return module


try:
    session = load_session()  # Also checks the existing P80 helper's exact hash.
except Exception as exc:
    print('ERROR: cannot load pinned helpers: ' + str(exc), file=sys.stderr)
    raise SystemExit(2)

base = session.base
ProbeError = base.ProbeError
SPLITTER, PARTY = base.SPLITTER, base.PARTY
REGISTERS, P80 = session.REGISTERS, session.P80
ABORT_SIGNALS = base.ABORT_SIGNALS


def duration_arg(value: str) -> int:
    try:
        seconds = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError('Seconds must be an integer from 30 to 600.') from exc
    if not 30 <= seconds <= MAX_SECONDS:
        raise argparse.ArgumentTypeError('Seconds must be from 30 to 600.')
    return seconds


class Capture:
    """Raw text plus guarded JSONL rounds, both root-only and never overwritten.

    Disk errors are recorded, not raised by diagnostic logging during cleanup.
    Session/checkpoint writes check the recorded error and abort acquisition.
    """
    def __init__(self, prefix: Path):
        self.path = prefix.with_suffix('.log')
        self.json_path = prefix.with_suffix('.jsonl')
        self.error = None
        self.files = []
        try:
            for path in (self.path, self.json_path):
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                self.files.append(os.fdopen(fd, 'w', encoding='utf-8', buffering=1))
        except BaseException:
            for file in self.files:
                file.close()
            raise

    def __call__(self, message: str):
        text = dt.datetime.now().astimezone().isoformat(timespec='milliseconds') + ' ' + message
        try:
            self.files[0].write(text + '\n')
        except OSError as exc:
            self.error = 'Capture log write failed: ' + str(exc)
        if not message.startswith(('TX ', 'RX ', 'SAMPLE ', 'GUARD ')):
            try:
                print(text, flush=True)
            except (BrokenPipeError, OSError):
                pass

    def ensure_ok(self):
        if self.error:
            raise ProbeError(self.error)

    def emit(self, record: dict):
        self.ensure_ok()
        try:
            self.files[1].write(json.dumps(record, ensure_ascii=True, allow_nan=False) + '\n')
        except OSError as exc:
            self.error = 'JSONL write failed: ' + str(exc)
            raise ProbeError(self.error) from exc

    def close(self):
        errors = []
        for file in self.files:
            try:
                file.close()
            except OSError as exc:
                errors.append(str(exc))
        if errors:
            self.error = 'Capture close failed: ' + '; '.join(errors)
            raise ProbeError(self.error)


class Wire(session.Wire):
    """Unchanged serial framing, response handling, timing and allowlist.

    Only observation duration and guarded result recording are extended.
    The final already-started round gets at most six extra seconds; no new
    round begins after the nominal deadline. No long idle sleep is inserted.
    """
    def __init__(self, serial_port, log, clock=time.monotonic, *, seconds=300, emit=None):
        if isinstance(seconds, bool) or not isinstance(seconds, int) or not 30 <= seconds <= MAX_SECONDS:
            raise ProbeError('Invalid bounded observation duration.')
        super().__init__(serial_port, log, clock)
        self.seconds = seconds
        self.emit = emit if emit is not None else (lambda record: None)
        self.observation_complete = False
        self.nonzero_rounds = 0
        self.phase_changes = 0
        self.elapsed = 0.0

    def _check_session(self):
        check = getattr(self.log, 'ensure_ok', None)
        if check is not None:
            check()
        super()._check_session()

    def observe(self):
        self._check_session()
        started = self.clock()
        stop_at = started + self.seconds
        self.deadline = stop_at + ROUND_GRACE_SECONDS
        self.emit({'kind': 'observation_start', 'version': VERSION,
                   'seconds_requested': self.seconds, 'simultaneous': False,
                   'flame_polled': False, 'fixed_sampling_rate': False})
        self.log(f'OBSERVATION_START seconds={self.seconds}; no flame sensor; no burner command.')
        self.read_session(P80, 0)
        previous = None
        while self.clock() < stop_at:
            if self.rounds >= MAX_ROUNDS:
                raise ProbeError('Round safety cap reached before time window completed.')
            number = self.rounds + 1
            rows = [self.read_session(address, number) for address in REGISTERS]
            guard = self.read_session(P80, number)
            values = {row['address']: row['raw'] for row in rows}
            span_ms = (rows[-1]['rx_mono'] - rows[0]['rx_mono']) * 1000
            changes = []
            if previous is not None:
                for row in rows:
                    old = previous[row['address']]
                    if old['raw'] != row['raw']:
                        changes.append({'parameter': session.LABELS[row['address']],
                                        'old_raw': old['raw'], 'new_raw': row['raw'],
                                        'previous_rx_time': old['rx_time'], 'rx_time': row['rx_time']})
            def sample(row):
                return {'parameter': session.LABELS.get(row['address'], 'P80'),
                        'address': f'0x{row["address"]:04x}', 'raw': row['raw'],
                        'raw_hex': f'{row["raw"]:02x}', 'rx_time': row['rx_time'],
                        'tx_elapsed_s': round(row['tx_mono']-started, 6),
                        'rx_elapsed_s': round(row['rx_mono']-started, 6),
                        'reply_latency_ms': round(row['latency_ms'], 3)}
            record = {'kind': 'round', 'round': number, 'guard_passed': True,
                      'sample_span_ms': round(span_ms, 3), 'samples': [sample(r) for r in rows],
                      'guard': sample(guard),
                      'decoded': {'fan_actual_rpm': values[0x4006] * 30,
                                  'modulation_setpoint_pct': round(values[0x4009]*0.3922, 4),
                                  'fan_pwm_setpoint_pct': round(values[0x400A]*0.4, 1),
                                  'phase_raw': values[0x4054]},
                      'changes': changes}
            self.emit(record)  # No unguarded/partial round becomes a JSONL measurement.
            self.rounds = number
            self.elapsed = self.clock() - started
            self.nonzero_rounds += int(any(values.values()))
            self.phase_changes += sum(c['parameter'] == 'P84' for c in changes)
            self.log(f'ROUND {number} t={rows[0]["rx_mono"]-started:.3f}s '
                     f'rpm={values[0x4006]*30} mod={values[0x4009]*0.3922:.4f}% '
                     f'pwm={values[0x400A]*0.4:.1f}% phase=0x{values[0x4054]:02x} '
                     f'span_ms={span_ms:.1f} guard=20')
            for change in changes:
                if change['parameter'] == 'P84':
                    self.log(f'PHASE_RAW_CHANGE 0x{change["old_raw"]:02x}->0x{change["new_raw"]:02x} '
                             f'between={change["previous_rx_time"]}..{change["rx_time"]}')
            previous = {row['address']: row for row in rows}
            self.samples.clear()  # Guarded data is on disk; avoid ever-growing memory.
        self.elapsed = self.clock() - started
        if not self.rounds or self.elapsed > self.seconds + ROUND_GRACE_SECONDS:
            raise ProbeError('Observation window incomplete or final-round budget exceeded.')
        self.observation_complete = True
        self.log(f'OBSERVATION_COMPLETE=yes seconds={self.elapsed:.3f} '
                 f'CONFIRMED_ROUNDS={self.rounds} RUNTIME_SAMPLES={self.rounds*4} '
                 f'NONZERO_ROUNDS={self.nonzero_rounds} PHASE_CHANGES={self.phase_changes}')


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
    summary = {'kind': 'summary', 'result': 'PASS' if passed else 'FAIL',
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
    log('RESULT=' + ('PASS' if passed else 'FAIL'))
    log('PASS means bounded observation and recovery; not proof of a complete burner cycle or flame timing.')
    return 0 if passed else 1


def self_test() -> int:
    """Simulated I/O and clock only, including the 56 dependency tests."""
    import tempfile
    import unittest
    if session.self_test() != 0:
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
        def case(self, port=None, services=None, emit_hook=None, log_hook=None, kind=Wire, opener=None):
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
            rc = run_guarded(s, opener or (lambda: p), log, emit, seconds=30, wire_factory=factory)
            return rc, p, s, logs, records, wires
        def recovered_failure(self, result):
            self.assertEqual(result[0], 1)
            self.assertTrue(result[1].closed)
            self.assertTrue(all(result[2].active.values()))
            self.assertIn('P300_RESTORED=yes', result[3])
        def test_window_and_complete_rounds(self):
            rc,p,s,logs,rows,wires = self.case()
            self.assertEqual(rc,0)
            w=wires[0]
            self.assertGreaterEqual(w.elapsed,30)
            self.assertLessEqual(w.elapsed,36)
            measurements=[r for r in rows if r['kind']=='round']
            self.assertEqual(len(measurements),w.rounds)
            self.assertGreater(w.rounds,10)
            self.assertTrue(all(len(r['samples'])==4 and r['guard_passed'] for r in measurements))
            self.assertEqual(rows[-1]['result'],'PASS')
            self.assertFalse(rows[-1]['flame_polled'])
            self.assertFalse(rows[-1]['full_burner_cycle_verified'])
            self.assertTrue(p.closed)
            self.assertTrue(all(s.active.values()))
        def test_no_new_transmissions(self):
            rc,p,*_=self.case()
            self.assertEqual(rc,0)
            self.assertTrue(all(frame in session.ALLOWED_TX for frame in p.tx))
            self.assertEqual(p.independent,3)
        def test_decode_and_sequential_timestamps(self):
            rows=self.case()[4]
            row=next(r for r in rows if r['kind']=='round')
            self.assertEqual(row['decoded'],{'fan_actual_rpm':4110,'modulation_setpoint_pct':48.2406,
                                            'fan_pwm_setpoint_pct':41.2,'phase_raw':6})
            t=[r['rx_elapsed_s'] for r in row['samples']]
            self.assertEqual(t,sorted(set(t)))
            self.assertGreater(row['guard']['rx_elapsed_s'],t[-1])
        def test_all_zero_is_no_activity_not_failure(self):
            p=Port()
            p.values.update({a:0 for a in REGISTERS})
            case=self.case(p)
            self.assertEqual(case[0],0)
            self.assertEqual(case[4][-1]['nonzero_rounds'],0)
        def test_phase_changes_are_raw_and_bracketed(self):
            # 1 initial guard, then 4 runtime + 1 guard per round. Second P84 is bare #10.
            case=self.case(Port({10:b'\x07'}))
            changes=[c for r in case[4] if r['kind']=='round' for c in r['changes'] if c['parameter']=='P84']
            self.assertEqual([(c['old_raw'],c['new_raw']) for c in changes],[(6,7),(7,6)])
            self.assertTrue(all('previous_rx_time' in c and 'rx_time' in c for c in changes))
        def test_invalid_guard_never_emits_partial_round(self):
            case=self.case(Port({6:b'\x05'}))
            self.recovered_failure(case)
            self.assertFalse(any(r['kind']=='round' for r in case[4]))
        def test_timeout_no_retry_and_prior_round_retained(self):
            case=self.case(Port({8:None}))
            self.recovered_failure(case)
            self.assertEqual(case[1].bare,8)
            self.assertEqual(sum(r['kind']=='round' for r in case[4]),1)
        def test_json_disk_error_enters_cleanup(self):
            def fail(row,p):
                if row['kind']=='round':
                    raise OSError('simulated full disk')
            self.recovered_failure(self.case(emit_hook=fail))
        def test_slow_round_recording_aborts_before_next_tx(self):
            def stall(row,p):
                if row['kind']=='round':
                    p.t+=0.4
            case=self.case(emit_hook=stall)
            self.recovered_failure(case)
            self.assertEqual(case[1].bare,6)
        def test_interruption_recovers(self):
            self.recovered_failure(self.case(Port({8:KeyboardInterrupt()})))
        def test_ctor_failure_closes_port_and_restarts(self):
            class Bad(Wire):
                def __init__(self,*args,**kw):
                    raise RuntimeError('simulated constructor failure')
            rc,p,s,*_=self.case(kind=Bad)
            self.assertEqual(rc,1)
            self.assertTrue(p.closed)
            self.assertTrue(all(s.active.values()))
        def test_opener_failure_restarts(self):
            def fail():
                raise OSError('simulated open failure')
            rc,p,s,*_=self.case(opener=fail)
            self.assertEqual(rc,1)
            self.assertTrue(all(s.active.values()))
        def test_accepted_stop_failure_restarts(self):
            class Fail(Services):
                def stop(self,unit):
                    super().stop(unit)
                    if unit==SPLITTER:
                        raise ProbeError('simulated accepted stop timeout')
            rc,p,s,*_=self.case(services=Fail())
            self.assertEqual(rc,1)
            self.assertTrue(all(s.active.values()))
        def test_recovery_failure_still_restarts(self):
            class Fail(Wire):
                calls=0
                def p300_ident(self):
                    self.calls+=1
                    if self.calls>1:
                        raise ProbeError('simulated P300 loss')
                    return super().p300_ident()
            rc,p,s,logs,*_=self.case(kind=Fail)
            self.assertEqual(rc,1)
            self.assertTrue(p.closed)
            self.assertTrue(all(s.active.values()))
            self.assertIn('P300_RESTORED=NOT_VERIFIED',logs)
        def test_close_error_still_restarts(self):
            class Fail(Port):
                def close(self):
                    super().close()
                    raise OSError('simulated close failure')
            case=self.case(Fail())
            self.assertEqual(case[0],1)
            self.assertTrue(all(case[2].active.values()))
        def test_restart_error_not_pass(self):
            class Fail(Services):
                def start(self,unit):
                    if unit==SPLITTER:
                        raise ProbeError('simulated restart failure')
                    super().start(unit)
            case=self.case(services=Fail())
            self.assertEqual(case[0],1)
            self.assertTrue(case[2].active[PARTY])
        def test_inactive_party_stays_inactive(self):
            case=self.case(services=Services(False))
            self.assertEqual(case[0],0)
            self.assertFalse(case[2].active[PARTY])
        def test_duration_rejected_before_services(self):
            for value in (0,29,601,True,30.5):
                s=Services()
                with self.assertRaises(ProbeError):
                    run_guarded(s,lambda:None,lambda _:None,lambda _:None,seconds=value)
                self.assertEqual(s.calls,[])
        def test_argument_bounds(self):
            for v in ('0','29','601','NaN','30.5','-1'):
                with self.assertRaises(argparse.ArgumentTypeError):
                    duration_arg(v)
            self.assertEqual(duration_arg('300'),300)
        def test_stopped_splitter_refused(self):
            s=Services()
            s.active[SPLITTER]=False
            with self.assertRaises(ProbeError):
                self.case(services=s)
            self.assertEqual(s.calls,[])
        def test_capture_files_private_no_overwrite(self):
            with tempfile.TemporaryDirectory() as d:
                prefix=Path(d)/'capture'
                cap=Capture(prefix)
                cap.emit({'kind':'test'})
                cap.close()
                self.assertEqual(stat.S_IMODE(cap.path.stat().st_mode),0o600)
                self.assertEqual(stat.S_IMODE(cap.json_path.stat().st_mode),0o600)
                with self.assertRaises(FileExistsError):
                    Capture(prefix)
                self.assertEqual(json.loads(cap.json_path.read_text()),{'kind':'test'})
        def test_closing_identity_must_match(self):
            class Bad(Wire):
                count=0
                def p80(self):
                    self.count+=1
                    value=super().p80()
                    return 0x21 if self.count==3 else value
            case=self.case(kind=Bad)
            self.recovered_failure(case)
            self.assertFalse(case[4][-1]['P80_confirmed'])
        def test_initial_non_gfa_blocks_runtime(self):
            class Wrong(Wire):
                def p80(self):
                    super().p80()
                    return 0x21
            case=self.case(kind=Wrong)
            self.recovered_failure(case)
            self.assertEqual(case[1].bare,0)
        def test_wrong_p300_baseline_blocks_gfa(self):
            class Wrong(Wire):
                count=0
                def p300_ident(self):
                    result=super().p300_ident()
                    self.count+=1
                    return b'\x20\xcb' if self.count==1 else result
            case=self.case(kind=Wrong)
            self.recovered_failure(case)
            self.assertEqual(case[1].independent,0)
        def test_guard_zero_fails_before_runtime(self):
            case=self.case(Port({1:b'\x00'}))
            self.recovered_failure(case)
            self.assertEqual(case[1].bare,1)
        def test_overshoot_stall_is_not_pass(self):
            def stall(row,p):
                if row['kind']=='round' and row['round']==1:
                    p.t+=40
            case=self.case(emit_hook=stall)
            self.recovered_failure(case)
            self.assertFalse(case[4][-1]['observation_complete'])
        def test_summary_io_failure_is_not_pass(self):
            def fail(row,p):
                if row['kind']=='summary':
                    raise OSError('simulated final data write failure')
            case=self.case(emit_hook=fail)
            self.recovered_failure(case)
        def test_raw_log_failure_detected_before_continuation(self):
            class Sink:
                error=None
                def __call__(self,msg):
                    pass
                def ensure_ok(self):
                    if self.error:
                        raise ProbeError(self.error)
            p,log=Port(),Sink()
            w=Wire(p,log,p.clock,seconds=30)
            self.assertEqual(w.p80(),32)
            n=len(p.tx)
            log.error='simulated raw log failure'
            with self.assertRaises(ProbeError):
                w.observe()
            self.assertEqual(len(p.tx),n)
        def test_phase_control_byte_is_not_filtered(self):
            p=Port()
            p.values[0x4054]=5
            case=self.case(p)
            self.assertEqual(case[0],0)
            self.assertEqual(next(r for r in case[4] if r['kind']=='round')['decoded']['phase_raw'],5)
        def test_guard_failure_retains_prior_round(self):
            case=self.case(Port({11:b'\x22'}))
            self.recovered_failure(case)
            self.assertEqual(sum(r['kind']=='round' for r in case[4]),1)
        def test_capture_failure_remembered(self):
            with tempfile.TemporaryDirectory() as d:
                cap=Capture(Path(d)/'capture')
                class BadFile:
                    def write(self,s):
                        raise OSError('simulated disk error')
                    def close(self):
                        pass
                cap.files[0].close()
                cap.files[0]=BadFile()
                cap('TX test suppressed on console')
                with self.assertRaises(ProbeError):
                    cap.ensure_ok()
                cap.close()
        def test_600_second_window_simulated(self):
            p=Port()
            w=Wire(p,lambda _:None,p.clock,seconds=600)
            self.assertEqual(w.p80(),32)
            w.observe()
            self.assertTrue(w.observation_complete)
            self.assertGreaterEqual(w.elapsed,600)
            self.assertLessEqual(w.elapsed,606)
            self.assertLess(w.rounds,MAX_ROUNDS)
        def test_300_second_window_simulated(self):
            p=Port()
            w=Wire(p,lambda _:None,p.clock,seconds=300)
            self.assertEqual(w.p80(),32)
            w.observe()
            self.assertTrue(w.observation_complete)
            self.assertGreaterEqual(w.elapsed,300)
            self.assertLessEqual(w.elapsed,306)
            self.assertGreater(w.rounds,400)

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
        print(f'WB2A GFA observation {VERSION}: no action without --execute.\n'
              f'{args.seconds} seconds response-paced P06/P09/P10/P84 with P80 after every round.\n'
              'Known protocol/addresses only; no polling through the paused splitter; no flame sensor.\n'
              'No parameter writes, burner start, settings edits or automatic retry.\n'
              'Entry, last-round completion (max 6 extra seconds) and restoration are outside the nominal window.\n'
              'Raw .log plus guarded .jsonl; signals enter cleanup, no independent watchdog.')
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
        cap=Capture(Path('/root')/f'wb2a-gfa-cycle-{stamp}-{os.getpid()}')
        cap(f'WB2A GFA observation {VERSION}; LOG={cap.path}; JSONL={cap.json_path}')
        cap(f'Configured port: {port}; resolved: {os.path.realpath(port)}; 4800 8E2.')
        cap(f'Explicit service pause for {args.seconds}s observation plus entry/recovery. HA data is not live during pause.')
        cap('No burner command or parameter writes. Pausing the party emulator can change externally maintained requests.')
        cap('Natural operation only. No contemporaneous flame, temperature, pump or 55DC data is collected.')
        cap.emit({'kind':'metadata','version':VERSION,'seconds':args.seconds,
                  'session_sha256':SESSION_SHA256,'p80_sha256':session.BASE_SHA256,
                  'session_hardware_evidence':'2026-09-23T22:55:37+02:00; 10 rounds; 6.359s',
                  'parameter_writes':False,'flame_polled':False})
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
