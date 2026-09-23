#!/usr/bin/env python3
"""WB2A bounded GFA session test; no parameter, setpoint or process writes.

Needs the SHA256-pinned wb2a-gfa-p80-probe.py in the same directory.
Default: print a plan. --self-test: simulated I/O. --execute: explicitly pause
services, confirm 20C2 and P80=20, then test 10 response-paced rounds of
P06/P09/P10/P84 plus P80 guards in one VS1 session. Restore P300 afterwards.
No arbitrary address, duration, write or automatic retry option.
This new same-session sequence is NOT hardware-validated yet.
Samples are sequential, not simultaneous. No flame sensor is collected.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import os
from pathlib import Path
import signal
import stat
import sys
import time
import types

VERSION = '1.0.0'
BASE_NAME = 'wb2a-gfa-p80-probe.py'
BASE_SHA256 = '6de883c422a09c821b342d12e5bb71dd3d518d8115ec2495bdfb202f5a7f50cb'
REGISTERS = (0x4006, 0x4009, 0x400A, 0x4054)
LABELS = {0x4006: 'P06', 0x4009: 'P09', 0x400A: 'P10', 0x4054: 'P84'}


def load_base():
    """Verify exact bytes of our own known helper BEFORE executing its code."""
    path = Path(__file__).resolve().with_name(BASE_NAME)
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != BASE_SHA256:
        raise RuntimeError('Base helper hash mismatch. No service/serial action performed.')
    module = types.ModuleType('wb2a_p80_pinned')
    module.__file__ = str(path)
    exec(compile(data, str(path), 'exec'), module.__dict__)
    return module


try:
    base = load_base()
except Exception as exc:
    print('ERROR: cannot load pinned base helper: ' + str(exc), file=sys.stderr)
    raise SystemExit(2)

ProbeError = base.ProbeError
SPLITTER, PARTY = base.SPLITTER, base.PARTY
ABORT_SIGNALS = base.ABORT_SIGNALS
ROUNDS = 10
HOST_GAP_LIMIT = 0.30  # Conservative helper guard, NOT a measured device timeout.
BURST_LIMIT = 20.0    # Cooperative time budget, not a process/systemd watchdog.
P80 = 0x4050
FRAMES = {address: bytes((0x6B, address >> 8, address & 255, 0x01))
          for address in (*REGISTERS, P80)}
ALLOWED_TX = base.ALLOWED_TX | frozenset(FRAMES.values())


def describe(address: int, raw: int) -> str:
    if address not in REGISTERS or not 0 <= raw <= 255:
        raise ProbeError('Invalid snapshot address/raw byte.')
    if address == 0x4006:
        return f'fan_actual_rpm={raw * 30}'
    if address == 0x4009:
        return f'modulation_setpoint_pct={raw * 0.3922:.4f}'
    if address == 0x400A:
        return f'fan_pwm_setpoint_pct={raw * 0.4:.1f}'
    return f'phase_raw=0x{raw:02x} (no validated phase-name table)'


class Wire(base.Wire):
    """Use the known independent P80 synchronization only for entry/exit.

    In a session, transmit the source-defined four-byte GFA_READ command,
    without another STX/EOT. Abort on excess host idle time or queued traffic;
    never silently resynchronize and call that a successful persistent test.
    """
    def __init__(self, serial_port, log, clock=time.monotonic):
        super().__init__(serial_port, log, clock)
        self.active = False
        self.last_reply = None
        self.deadline = None
        self.samples = []
        self.rounds = 0

    def exact(self, count, timeout=2.0):
        until = self.clock() + timeout
        data = bytearray()
        while len(data) < count and self.clock() < until:
            chunk = self.port.read(count-len(data))
            if chunk:
                data.extend(chunk)
                self.last_reply = self.clock()
                self.last_wall = dt.datetime.now().astimezone().isoformat(timespec='milliseconds')
        if data:
            self.log('RX ' + data.hex(' '))
        if len(data) != count:
            raise ProbeError(f'RX timeout: expected {count} byte(s), got {len(data)}.')
        return bytes(data)

    def _check_session(self):
        now = self.clock()
        if not self.active or self.last_reply is None:
            raise ProbeError('No confirmed active GFA session.')
        if now - self.last_reply > HOST_GAP_LIMIT:
            raise ProbeError('Host idle gap exceeded 300 ms; no blind session continuation.')
        if self.deadline is not None and now >= self.deadline:
            raise ProbeError('Bounded session budget exhausted; entering recovery.')
        if self.port.in_waiting:
            raise ProbeError('Unexpected queued RX bytes; session alignment not trusted.')

    def send(self, data: bytes):
        if data not in ALLOWED_TX:
            raise ProbeError('TX blocked by fixed read-only session allowlist.')
        bare = data in FRAMES.values()
        if bare:
            self._check_session()
        else:
            self.active = False
            self.deadline = None
        self.log('TX ' + data.hex(' '))
        if bare:
            self._check_session()  # Logging/scheduling must not hide an idle gap.
        self.touched = True
        if self.port.write(data) != len(data):
            raise ProbeError('Partial serial write; no automatic retransmission.')

    def p80(self) -> int:
        self.active = False
        self.deadline = None
        value = super().p80()
        self.active = value == 0x20
        return value

    def read_session(self, address: int, round_number: int) -> dict:
        if address not in FRAMES:
            raise ProbeError('Only P80/P06/P09/P10/P84 are enabled.')
        try:
            self._check_session()
            start = self.clock()
            self.send(FRAMES[address])
            value = self.exact(1, timeout=1.0)[0]
            received = self.last_reply
            wall = self.last_wall
            if self.deadline is not None and received >= self.deadline:
                raise ProbeError('Reply exceeded the session time budget.')
            # An additional 50-ms read catches immediate echoes/trailing bytes.
            tail = self.port.read(1)
            if tail:
                self.log('RX unexpected trailing ' + tail.hex(' '))
                raise ProbeError('Unexpected trailing session data; not continuing.')
            record = dict(round=round_number, address=address, raw=value,
                          tx_mono=start, rx_mono=received, rx_time=wall,
                          latency_ms=(received-start)*1000)
            if address == P80:
                if value != 0x20:
                    raise ProbeError(f'Session P80 guard is 0x{value:02x}, expected 0x20.')
                self.log(f'GUARD round={round_number} P80=0x20 '
                         f'reply_latency_ms={record["latency_ms"]:.1f}')
            else:
                # 05 and 06 are also legitimate one-byte data values here.
                # A following P80 guard helps detect loss of framing, but is not a CRC.
                self.samples.append(record)
                self.log(f'SAMPLE round={round_number} {LABELS[address]} '
                         f'address=0x{address:04x} raw=0x{value:02x} '
                         f'raw_dec={value} {describe(address, value)} '
                         f'rx_time={wall} reply_latency_ms={record["latency_ms"]:.1f} '
                         'round_guard=pending')
            return record
        except BaseException:
            self.active = False
            raise

    def burst(self):
        self._check_session()
        start = self.clock()
        self.deadline = start + BURST_LIMIT
        self.read_session(P80, 0)  # Prove continuation before any runtime read.
        for number in range(1, ROUNDS+1):
            rows = [self.read_session(address, number) for address in REGISTERS]
            self.read_session(P80, number)
            self.rounds = number
            span = rows[-1]['rx_mono'] - rows[0]['rx_mono']
            self.log(f'ROUND_CONFIRMED={number}/{ROUNDS} P80=0x20 '
                     f'sample_span_ms={span*1000:.1f}')
        elapsed = self.clock() - start
        self.log(f'BURST_SECONDS={elapsed:.3f} RUNTIME_SAMPLES={len(self.samples)} '
                 'simultaneous=no fixed_sampling_rate=no')


def run_guarded(services, opener, log, wire_factory=Wire) -> int:
    """Same restoration policy as P80 helper, with a fixed same-session transport test."""
    state = services.state(SPLITTER)
    if (state.get('LoadState'), state.get('ActiveState'), state.get('SubState')) != ('loaded', 'active', 'running'):
        raise ProbeError('Require the splitter to be loaded and running before this test.')
    party = services.state(PARTY)
    party_active = party.get('LoadState') == 'loaded' and party.get('ActiveState') == 'active'
    if party.get('ActiveState') in ('activating', 'deactivating', 'reloading'):
        raise ProbeError('Party emulator is in transition; no service change performed.')
    to_stop = ([PARTY] if party_active else []) + [SPLITTER]
    changed, identities, failures = [], [], []
    restarted = set()
    wire = None
    restored = False
    try:
        for unit in to_stop:
            # Record intent first: systemd can accept a stop before a timeout.
            changed.append(unit)
            log('Stopping ' + unit)
            services.stop(unit)
        wire = wire_factory(opener(), log)
        if wire.p300_ident() != b'\x20\xc2':
            raise ProbeError('Baseline device is not 20C2; no GFA command sent.')
        for _ in range(2):
            identities.append(wire.p80())
            if identities[-1] != 0x20:
                raise ProbeError('Expected GFA variant 0x20; no runtime reads for other variants.')
        wire.burst()
        identities.append(wire.p80())
        if identities[-1] != 0x20:
            raise ProbeError('Closing P80 differs; session test not confirmed.')
    except BaseException as exc:
        failures.append(str(exc) or type(exc).__name__)
        log('PROBE FAILED: ' + failures[-1])
    finally:
        previous = {sig: signal.signal(sig, signal.SIG_IGN) for sig in ABORT_SIGNALS}
        try:
            if wire is not None:
                try:
                    if wire.touched:
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
                finally:
                    try:
                        wire.port.close()
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
    completed = wire.rounds if wire is not None else 0
    complete = completed == ROUNDS and identities == [0x20] * 3
    log(f'SESSION_ROUNDS={completed}/{ROUNDS}')
    log('P80_CONFIRMED=' + ('0x20 GFA' if identities == [0x20] * 3 else 'NOT_CONFIRMED'))
    log('P300_RESTORED=' + ('yes' if restored else 'NOT_VERIFIED'))
    log('SPLITTER_RESTARTED=' + ('yes' if SPLITTER in restarted else 'NOT_VERIFIED'))
    passed = complete and restored and not failures
    log('RESULT=' + ('PASS' if passed else 'FAIL'))
    log('PASS means bounded same-session reads and recovery worked; not a complete burner-cycle validation.')
    for failure in failures:
        log('ERROR: ' + failure)
    return 0 if passed else 1



def self_test() -> int:
    """All ports, systemd calls and timing below are simulated."""
    import unittest
    if base.self_test() != 0:
        return 1

    class Port:
        def __init__(self, identities=(0x20, 0x20, 0x20), answers=None):
            self.identities = iter(identities)
            self.answers = answers or {}
            self.rx, self.tx = bytearray(), []
            self.enq, self.closed, self.t = False, False, 0.0
            self.bare_count = 0
            self.runtime = {0x4006: 137, 0x4009: 123, 0x400A: 103, 0x4054: 6, P80: 32}
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
                self.rx.extend(bytes((next(self.identities),)))
            elif data in FRAMES.values():
                self.bare_count += 1
                answer = self.answers.get(self.bare_count, bytes((self.runtime[int.from_bytes(data[1:3], 'big')],)))
                if isinstance(answer, BaseException):
                    raise answer
                if answer is not None:
                    self.rx.extend(answer)
            return len(data)
        def read(self, count):
            self.t += 0.05
            if not self.rx and self.enq:
                self.rx.extend(b'\x05')
            result = bytes(self.rx[:count])
            del self.rx[:count]
            return result
        def close(self):
            self.closed = True

    class Services:
        def __init__(self, party=True):
            self.active, self.calls = {SPLITTER: True, PARTY: party}, []
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
        def run_case(self, port=None, services=None, wire_type=Wire, logger=None, opener=None):
            p = port or Port()
            s = services or Services()
            messages = []
            def log(message):
                messages.append(message)
                if logger:
                    logger(message, p)
            made = []
            def factory(connection, log):
                w = wire_type(connection, log, p.clock)
                made.append(w)
                return w
            result = run_guarded(s, opener or (lambda: p), log, factory)
            return result, p, s, messages, made
        def check_recovered(self, case):
            rc, p, s, msgs, made = case
            self.assertEqual(rc, 1)
            self.assertTrue(p.closed)
            self.assertTrue(s.active[SPLITTER])
            self.assertTrue(s.active[PARTY])
            self.assertIn('P300_RESTORED=yes', msgs)
        def live_wire(self):
            p, log = Port(), []
            w = Wire(p, log.append, p.clock)
            self.assertEqual(w.p80(), 32)
            return p, w, log
        def test_happy_path_and_fixed_sequence(self):
            rc, p, s, msgs, made = self.run_case()
            self.assertEqual(rc, 0)
            expected = [FRAMES[P80]] + [FRAMES[a] for a in (*REGISTERS, P80)] * ROUNDS
            self.assertEqual([x for x in p.tx if x in FRAMES.values()], expected)
            first = p.tx.index(FRAMES[P80])
            self.assertEqual(p.tx[first:first+len(expected)], expected)
            self.assertEqual(len(made[0].samples), 40)
            self.assertEqual(made[0].rounds, 10)
            self.assertIn('P300_RESTORED=yes', msgs)
            self.assertTrue(p.closed)
            self.assertTrue(all(s.active.values()))
        def test_exact_frame_bytes(self):
            self.assertEqual(FRAMES[0x4006], bytes.fromhex('6b400601'))
            self.assertEqual(FRAMES[0x4009], bytes.fromhex('6b400901'))
            self.assertEqual(FRAMES[0x400A], bytes.fromhex('6b400a01'))
            self.assertEqual(FRAMES[0x4054], bytes.fromhex('6b405401'))
            self.assertEqual(FRAMES[P80], bytes.fromhex('6b405001'))
        def test_allowlist_rejects_write_and_unknown_address(self):
            p, w, _ = self.live_wire()
            n = len(p.tx)
            for frame in (b'\x68\x40\x06\x01\x64', b'\xf4\x27\xe7\x01\x64',
                          b'\x6b\x40\x51\x01', b'\x6b\x40\x06\x02', b'\x01'):
                with self.assertRaises(ProbeError):
                    w.send(frame)
            self.assertEqual(len(p.tx), n)
        def test_unknown_read_has_no_tx(self):
            p, w, _ = self.live_wire()
            n = len(p.tx)
            with self.assertRaises(ProbeError):
                w.read_session(0x4051, 1)
            self.assertEqual(len(p.tx), n)
        def test_no_continuation_without_session(self):
            p = Port()
            w = Wire(p, lambda _: None, p.clock)
            with self.assertRaises(ProbeError):
                w.read_session(P80, 0)
            self.assertEqual(p.tx, [])
        def test_first_guard_timeout_aborts_before_runtime(self):
            case = self.run_case(Port(answers={1: None}))
            self.check_recovered(case)
            self.assertEqual(case[1].bare_count, 1)
        def test_first_guard_enq_rejected(self):
            case = self.run_case(Port(answers={1: b'\x05'}))
            self.check_recovered(case)
            self.assertEqual(case[1].bare_count, 1)
        def test_first_guard_other_variant_rejected(self):
            case = self.run_case(Port(answers={1: b'\x21'}))
            self.check_recovered(case)
            self.assertEqual(case[1].bare_count, 1)
        def test_runtime_timeout_no_retry(self):
            case = self.run_case(Port(answers={3: None}))
            self.check_recovered(case)
            self.assertEqual(case[1].bare_count, 3)
            self.assertEqual(case[4][0].rounds, 0)
        def test_runtime_trailing_byte_aborts(self):
            case = self.run_case(Port(answers={2: b'\x89\x00'}))
            self.check_recovered(case)
            self.assertEqual(case[1].bare_count, 2)
        def test_round_guard_failure_invalidates_round(self):
            case = self.run_case(Port(answers={6: b'\x05'}))
            self.check_recovered(case)
            self.assertEqual(case[4][0].rounds, 0)
            self.assertEqual(case[1].bare_count, 6)
        def test_late_guard_failure_preserves_completed_rounds(self):
            case = self.run_case(Port(answers={11: b'\x22'}))
            self.check_recovered(case)
            self.assertEqual(case[4][0].rounds, 1)
        def test_no_runtime_for_other_initial_variant(self):
            case = self.run_case(Port(identities=(0x21,)))
            self.check_recovered(case)
            self.assertEqual(case[1].bare_count, 0)
        def test_second_initial_identity_guard(self):
            case = self.run_case(Port(identities=(0x20, 0x22)))
            self.check_recovered(case)
            self.assertEqual(case[1].bare_count, 0)
        def test_closing_independent_identity(self):
            case = self.run_case(Port(identities=(0x20, 0x20, 0x21)))
            self.check_recovered(case)
            self.assertEqual(case[4][0].rounds, 10)
        def test_zero_idle_data(self):
            p = Port()
            p.runtime.update({a: 0 for a in REGISTERS})
            self.assertEqual(self.run_case(p)[0], 0)
        def test_control_valued_data_is_valid_in_data_context(self):
            p = Port()
            p.runtime.update({0x4006: 5, 0x4009: 6, 0x400A: 21, 0x4054: 5})
            self.assertEqual(self.run_case(p)[0], 0)
        def test_scaling_and_no_clamp(self):
            self.assertEqual(describe(0x4006,137), 'fan_actual_rpm=4110')
            self.assertEqual(describe(0x4009,123), 'modulation_setpoint_pct=48.2406')
            self.assertEqual(describe(0x400A,103), 'fan_pwm_setpoint_pct=41.2')
            self.assertIn('0x06', describe(0x4054,6))
            self.assertIn('102.0', describe(0x400A,255))
        def test_queued_bytes_block_continuation(self):
            p, w, _ = self.live_wire()
            n = len(p.tx)
            p.rx.extend(b'\x05')
            with self.assertRaises(ProbeError):
                w.read_session(P80,0)
            self.assertEqual(len(p.tx), n)
        def test_idle_gap_blocks_continuation(self):
            p, w, _ = self.live_wire()
            n = len(p.tx)
            p.t += 0.5
            with self.assertRaises(ProbeError):
                w.read_session(P80,0)
            self.assertEqual(len(p.tx), n)
        def test_slow_tx_log_rechecked_before_write(self):
            p, w, _ = self.live_wire()
            n = len(p.tx)
            w.log = lambda _: setattr(p,'t',p.t+0.4)
            with self.assertRaises(ProbeError):
                w.read_session(P80,0)
            self.assertEqual(len(p.tx), n)
        def test_slow_rx_log_does_not_hide_idle_gap(self):
            def logger(msg,p):
                if p.bare_count == 1 and msg.startswith('RX '):
                    p.t += 0.4
            case = self.run_case(logger=logger)
            self.check_recovered(case)
            self.assertEqual(case[1].bare_count, 1)
        def test_deadline_blocks_next_tx(self):
            p, w, _ = self.live_wire()
            n = len(p.tx)
            w.deadline = p.t
            with self.assertRaises(ProbeError):
                w.read_session(P80,0)
            self.assertEqual(len(p.tx),n)
        def test_slow_device_hits_budget(self):
            class Slow(Port):
                def read(self,count):
                    if self.rx and self.bare_count and not self.enq:
                        self.t += 0.45
                    return super().read(count)
            case = self.run_case(Slow())
            self.check_recovered(case)
            self.assertLess(case[4][0].rounds,ROUNDS)
        def test_interrupt_enters_recovery(self):
            case = self.run_case(Port(answers={3: KeyboardInterrupt()}))
            self.check_recovered(case)
        def test_partial_write_aborts(self):
            class Partial(Port):
                def write(self,data):
                    n=super().write(data)
                    return n-1 if data==FRAMES[0x4006] else n
            case=self.run_case(Partial())
            self.check_recovered(case)
            self.assertEqual(case[1].bare_count,2)
        def test_p300_recovery_failure_still_starts_services(self):
            class FailRestore(Wire):
                def p300_ident(self):
                    if self.rounds:
                        raise ProbeError('simulated recovery failure')
                    return super().p300_ident()
            case=self.run_case(wire_type=FailRestore)
            self.assertEqual(case[0],1)
            self.assertTrue(case[1].closed)
            self.assertTrue(all(case[2].active.values()))
            self.assertIn('P300_RESTORED=NOT_VERIFIED',case[3])
        def test_close_failure_still_starts_services(self):
            class FailClose(Port):
                def close(self):
                    self.closed=True
                    raise OSError('simulated close failure')
            case=self.run_case(FailClose())
            self.assertEqual(case[0],1)
            self.assertTrue(all(case[2].active.values()))
        def test_open_failure_still_restarts(self):
            def fail():
                raise OSError('simulated open failure')
            case=self.run_case(opener=fail)
            self.assertEqual(case[0],1)
            self.assertTrue(all(case[2].active.values()))
        def test_accepted_stop_then_error_is_restored(self):
            class FailedStop(Services):
                def stop(self,unit):
                    super().stop(unit)
                    if unit==SPLITTER:
                        raise ProbeError('simulated timeout after stop acceptance')
            case=self.run_case(services=FailedStop())
            self.assertEqual(case[0],1)
            self.assertTrue(all(case[2].active.values()))
        def test_restart_failure_reported(self):
            class FailedStart(Services):
                def start(self,unit):
                    if unit==SPLITTER:
                        raise ProbeError('simulated restart failure')
                    super().start(unit)
            case=self.run_case(services=FailedStart())
            self.assertEqual(case[0],1)
            self.assertTrue(case[2].active[PARTY])
            self.assertIn('SPLITTER_RESTARTED=NOT_VERIFIED',case[3])
        def test_inactive_party_stays_inactive(self):
            case=self.run_case(services=Services(party=False))
            self.assertEqual(case[0],0)
            self.assertFalse(case[2].active[PARTY])
            self.assertNotIn(('start',PARTY),case[2].calls)
        def test_initially_inactive_splitter_refused(self):
            s=Services()
            s.active[SPLITTER]=False
            with self.assertRaises(ProbeError):
                self.run_case(services=s)
            self.assertEqual(s.calls,[])

    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    return 0 if result.wasSuccessful() else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--execute', action='store_true', help='Pause services and perform the bounded same-session test.')
    group.add_argument('--self-test', action='store_true', help='Offline base + session tests only.')
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if not args.execute:
        print(f'WB2A GFA session test {VERSION}: no action without --execute.\n'
              'P300 baseline; two P80=20 guards; 10 same-session P06/P09/P10/P84 rounds with P80 guards; closing P80=20;\n'
              'verified P300 restoration; restart previously running services.\n'
              'Sequential response-paced samples; 20-second burst budget; no retry or arbitrary registers.\n'
              'No settings edits, no parameter writes, no automatic burner start.')
        return 0
    if os.geteuid() != 0:
        print('ERROR: --execute requires root.', file=sys.stderr)
        return 1
    log, lock_fd, previous = None, None, {}
    try:
        import serial
        port = base.read_settings(base.SETTINGS)
        if not stat.S_ISCHR(os.stat(port).st_mode):
            raise ProbeError('Configured port is not a character device.')
        # Deliberately share the old helper lock to block concurrent probe runs.
        lock_fd = os.open('/run/lock/wb2a-gfa-p80-probe.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        stamp = dt.datetime.now().strftime('%Y%m%d-%H%M%S')
        log = base.Log(Path('/root') / f'wb2a-gfa-session-{stamp}-{os.getpid()}.log')
        log(f'WB2A GFA session test {VERSION}; LOG={log.path}')
        log(f'Configured port: {port}; resolved: {os.path.realpath(port)}; 4800 8E2.')
        log('No parameter writes. MQTT/TCP polling and the running party emulator are paused.')
        log('Ten fixed rounds; same-session continuation is NEW and not yet hardware-validated.')
        log('Cooperative 20-second burst budget; not a full-cycle logger or simultaneous acquisition.')
        def abort(signum, _frame):
            raise ProbeError('Interrupted by signal ' + str(signum) + '; entering cleanup.')
        previous = {sig: signal.signal(sig, abort) for sig in ABORT_SIGNALS}
        return run_guarded(base.Services(), lambda: base.open_port(port, serial), log)
    except Exception as exc:
        if log:
            log('ERROR: ' + str(exc))
        else:
            print('ERROR: ' + str(exc), file=sys.stderr)
        return 1
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        if lock_fd is not None:
            os.close(lock_fd)
        if log is not None:
            log('LOG=' + str(log.path))
            log.close()


if __name__ == '__main__':
    raise SystemExit(main())
