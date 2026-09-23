#!/usr/bin/env python3
"""WB2A GFA single snapshot; no parameter, setpoint or process writes.

Needs the SHA256-pinned wb2a-gfa-p80-probe.py in the same directory.
Default: print a plan. --self-test: simulated I/O. --execute: explicitly pause
services, confirm 20C2 and P80=20, read P06/P09/P10/P84 once, restore P300.
Every GFA read uses the independently synchronized, hardware-tested P80 flow.
This is NOT a high-rate logger and the four measurements are NOT simultaneous.
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
FRAMES = {address: bytes((0x01, 0x6B, address >> 8, address & 255, 0x01))
          for address in REGISTERS}
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
    def send(self, data: bytes):
        if data not in ALLOWED_TX:
            raise ProbeError('TX blocked by snapshot fixed read-only allowlist.')
        self.log('TX ' + data.hex(' '))
        self.touched = True
        if self.port.write(data) != len(data):
            raise ProbeError('Partial serial write; no automatic retransmission.')

    def snapshot_read(self, address: int) -> int:
        if address not in FRAMES:
            raise ProbeError('Only P06/P09/P10/P84 are enabled.')
        self.discard_stale()
        self.send(b'\x04')
        self.control(5)
        self.log('Waiting for fresh VS1 synchronization ENQ.')
        self.control(5)
        start = self.clock()
        self.send(FRAMES[address])
        value = self.exact(1)[0]
        latency_ms = (self.clock() - start) * 1000
        tail = self.port.read(1)
        if tail:
            self.log('RX unexpected trailing ' + tail.hex(' '))
            raise ProbeError('Snapshot reply has unexpected trailing data.')
        # Every byte value may be a valid raw sample. Do not reject 05 solely
        # because it can ALSO mean ENQ in another context, or clamp percentages.
        self.log(f'SAMPLE {LABELS[address]} address=0x{address:04x} '
                 f'raw=0x{value:02x} raw_dec={value} {describe(address, value)} '
                 f'reply_latency_ms={latency_ms:.1f}')
        return value


def run_guarded(services, opener, log, wire_factory=Wire) -> int:
    """Same restoration policy as P80 helper, with a bounded observation stage."""
    state = services.state(SPLITTER)
    if (state.get('LoadState'), state.get('ActiveState'), state.get('SubState')) != ('loaded', 'active', 'running'):
        raise ProbeError('Require the splitter to be loaded and running before this test.')
    party = services.state(PARTY)
    party_active = party.get('LoadState') == 'loaded' and party.get('ActiveState') == 'active'
    if party.get('ActiveState') in ('activating', 'deactivating', 'reloading'):
        raise ProbeError('Party emulator is in transition; no service change performed.')
    to_stop = ([PARTY] if party_active else []) + [SPLITTER]
    changed, identities, failures, samples = [], [], [], {}
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
        for address in REGISTERS:
            samples[address] = wire.snapshot_read(address)
        identities.append(wire.p80())
        if identities[-1] != 0x20:
            raise ProbeError('Closing P80 differs; snapshot not confirmed.')
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
    complete = len(samples) == len(REGISTERS) and identities == [0x20] * 3
    log('SNAPSHOT_READS=' + str(len(samples)) + '/' + str(len(REGISTERS)))
    log('P80_CONFIRMED=' + ('0x20 GFA' if identities == [0x20] * 3 else 'NOT_CONFIRMED'))
    log('P300_RESTORED=' + ('yes' if restored else 'NOT_VERIFIED'))
    log('SPLITTER_RESTARTED=' + ('yes' if SPLITTER in restarted else 'NOT_VERIFIED'))
    passed = complete and restored and not failures
    log('RESULT=' + ('PASS' if passed else 'FAIL'))
    log('PASS means bounded reads/restoration succeeded, not validated runtime semantics or simultaneous samples.')
    for failure in failures:
        log('ERROR: ' + failure)
    return 0 if passed else 1


def self_test() -> int:
    import unittest
    if base.self_test() != 0:
        return 1

    class Port:
        def __init__(self, identities=(0x20, 0x20, 0x20), raw=(100, 166, 160, 5)):
            self.identities = iter(identities)
            self.raw = iter(raw)
            self.rx, self.tx = bytearray(), []
            self.enq, self.closed, self.t = False, False, 0.0
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
            elif data == base.P80_REQUEST or data in FRAMES.values():
                self.enq = False
                value = next(self.identities if data == base.P80_REQUEST else self.raw)
                if value is not None:
                    self.rx.extend(bytes((value,)))
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
        def exercise(self, port=None, service=None, opener=None):
            p, s, lines = port or Port(), service or Services(), []
            result = run_guarded(s, opener or (lambda: p), lines.append,
                                 lambda port, log: Wire(port, log, port.clock))
            return result, p, s, lines
        def test_exact_frames(self):
            self.assertEqual([v.hex() for v in FRAMES.values()],
                             ['016b400601', '016b400901', '016b400a01', '016b405401'])
        def test_scaling(self):
            self.assertEqual(describe(0x4006, 100), 'fan_actual_rpm=3000')
            self.assertEqual(describe(0x4009, 166), 'modulation_setpoint_pct=65.1052')
            self.assertEqual(describe(0x400A, 160), 'fan_pwm_setpoint_pct=64.0')
        def test_no_clamp(self):
            self.assertEqual(describe(0x400A, 255), 'fan_pwm_setpoint_pct=102.0')
            self.assertEqual(describe(0x4009, 255), 'modulation_setpoint_pct=100.0110')
        def test_unknown_phase_kept_raw(self):
            self.assertIn('phase_raw=0xff', describe(0x4054, 255))
        def test_allowlist(self):
            p = Port()
            w = Wire(p, lambda _: None, p.clock)
            for data in (bytes.fromhex('016840060100'), bytes.fromhex('01f440060100'),
                         bytes.fromhex('016b401101'), bytes.fromhex('6b400601'),
                         bytes.fromhex('016b400604')):
                with self.assertRaises(ProbeError):
                    w.send(data)
            self.assertEqual(p.tx, [])
        def test_unknown_register_before_touch(self):
            p = Port()
            with self.assertRaises(ProbeError):
                Wire(p, lambda _: None, p.clock).snapshot_read(0x4011)
            self.assertFalse(p.tx)
        def test_happy_path(self):
            code, p, s, lines = self.exercise()
            self.assertEqual(code, 0)
            self.assertTrue(p.closed)
            self.assertTrue(all(s.active.values()))
            self.assertEqual(p.tx.count(base.P80_REQUEST), 3)
            self.assertEqual([x for x in p.tx if x in FRAMES.values()], list(FRAMES.values()))
            self.assertTrue(all(x in ALLOWED_TX for x in p.tx))
            self.assertIn('SNAPSHOT_READS=4/4', lines)
            self.assertIn('P300_RESTORED=yes', lines)
        def test_non_gfa_stops_before_runtime(self):
            code, p, s, _ = self.exercise(Port(identities=(0x21,)))
            self.assertEqual(code, 1)
            self.assertFalse(any(x in FRAMES.values() for x in p.tx))
            self.assertTrue(all(s.active.values()))
        def test_second_identity_changed(self):
            code, p, _, _ = self.exercise(Port(identities=(0x20, 0x21)))
            self.assertEqual(code, 1)
            self.assertFalse(any(x in FRAMES.values() for x in p.tx))
        def test_closing_identity_changed(self):
            code, _, _, lines = self.exercise(Port(identities=(0x20, 0x20, 0x21)))
            self.assertEqual(code, 1)
            self.assertIn('P80_CONFIRMED=NOT_CONFIRMED', lines)
            self.assertIn('P300_RESTORED=yes', lines)
        def test_runtime_timeout_aborts_no_other_register(self):
            code, p, s, lines = self.exercise(Port(raw=(None,)))
            self.assertEqual(code, 1)
            self.assertEqual([x for x in p.tx if x in FRAMES.values()], [FRAMES[0x4006]])
            self.assertIn('P300_RESTORED=yes', lines)
            self.assertTrue(all(s.active.values()))
        def test_trailing_runtime_rejected(self):
            class Tail(Port):
                def write(self, data):
                    n = super().write(data)
                    if data == FRAMES[0x4006]:
                        self.rx.extend(b'\x99')
                    return n
            code, _, _, lines = self.exercise(Tail())
            self.assertEqual(code, 1)
            self.assertIn('P300_RESTORED=yes', lines)
        def test_zero_values_valid(self):
            self.assertEqual(self.exercise(Port(raw=(0, 0, 0, 0)))[0], 0)
        def test_interrupt_during_runtime(self):
            class Interrupted(Port):
                def write(self, data):
                    if data == FRAMES[0x4009]:
                        raise KeyboardInterrupt()
                    return super().write(data)
            code, p, s, lines = self.exercise(Interrupted())
            self.assertEqual(code, 1)
            self.assertTrue(p.closed)
            self.assertTrue(all(s.active.values()))
            self.assertIn('P300_RESTORED=yes', lines)
        def test_close_failure_still_restarts(self):
            class BadClose(Port):
                def close(self):
                    raise OSError('close failed')
            code, _, s, _ = self.exercise(BadClose())
            self.assertEqual(code, 1)
            self.assertTrue(all(s.active.values()))
        def test_stop_failure_still_restores(self):
            class BadStop(Services):
                def stop(self, unit):
                    super().stop(unit)
                    if unit == SPLITTER:
                        raise ProbeError('stop timeout after acceptance')
            code, _, s, _ = self.exercise(service=BadStop())
            self.assertEqual(code, 1)
            self.assertTrue(all(s.active.values()))
        def test_recovery_failure_still_restarts(self):
            class Recovery(Port):
                def write(self, data):
                    if data == b'\x04' and self.tx.count(base.P80_REQUEST) == 3:
                        raise OSError('recovery failed')
                    return super().write(data)
            code, p, s, lines = self.exercise(Recovery())
            self.assertEqual(code, 1)
            self.assertTrue(p.closed)
            self.assertTrue(all(s.active.values()))
            self.assertIn('P300_RESTORED=NOT_VERIFIED', lines)
        def test_restart_failure_reported(self):
            class BadStart(Services):
                def start(self, unit):
                    if unit == SPLITTER:
                        raise ProbeError('restart failed')
                    super().start(unit)
            code, _, s, lines = self.exercise(service=BadStart())
            self.assertEqual(code, 1)
            self.assertIn('SPLITTER_RESTARTED=NOT_VERIFIED', lines)
            self.assertTrue(s.active[PARTY])
        def test_inactive_party_unchanged(self):
            code, _, s, _ = self.exercise(service=Services(party=False))
            self.assertEqual(code, 0)
            self.assertFalse(s.active[PARTY])
            self.assertNotIn(('start', PARTY), s.calls)
        def test_open_failure_still_restarts(self):
            def fail():
                raise OSError('open failed')
            code, _, s, _ = self.exercise(opener=fail)
            self.assertEqual(code, 1)
            self.assertTrue(all(s.active.values()))
        def test_stopped_splitter_refused(self):
            s = Services()
            s.active[SPLITTER] = False
            with self.assertRaises(ProbeError):
                self.exercise(service=s)
            self.assertFalse(s.calls)
        def test_no_enq_sends_no_gfa(self):
            class NoENQ(Port):
                def read(self, count):
                    self.t += 0.5
                    return b''
            code, p, s, _ = self.exercise(NoENQ())
            self.assertEqual(code, 1)
            self.assertFalse(any(x in FRAMES.values() or x == base.P80_REQUEST for x in p.tx))
            self.assertTrue(all(s.active.values()))
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--execute', action='store_true', help='Pause services and perform the bounded live snapshot.')
    group.add_argument('--self-test', action='store_true', help='Offline base + snapshot tests only.')
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if not args.execute:
        print(f'WB2A GFA snapshot {VERSION}: no action without --execute.\n'
              'P300 baseline; two P80=20 guards; P06/P09/P10/P84 once each; closing P80=20;\n'
              'verified P300 restoration; restart previously running services.\n'
              'Independent synchronization per read. Sequential samples, not a fast logger.\n'
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
        log = base.Log(Path('/root') / f'wb2a-gfa-snapshot-{stamp}-{os.getpid()}.log')
        log(f'WB2A GFA snapshot {VERSION}; LOG={log.path}')
        log(f'Configured port: {port}; resolved: {os.path.realpath(port)}; 4800 8E2.')
        log('No parameter writes. MQTT/TCP polling and the running party emulator are paused.')
        log('P06/P09/P10/P84 are sequential samples; phase names are not yet verified.')
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
