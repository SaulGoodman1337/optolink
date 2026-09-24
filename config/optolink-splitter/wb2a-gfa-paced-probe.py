#!/usr/bin/env python3
"""Controlled WB2A GFA pacing comparison, not a production logger.

Requires the unchanged SHA256-pinned quality, cycle, session and P80 helpers
beside this file. Only change to live acquisition: at least 150 ms between
host receipt of a VS1 reply and the next same-session read. The existing
300-ms maximum host gap, FF quarantine, three re-identification limit,
read allowlist, service ownership and P300 restoration remain in force.

Default: plan only. --execute: explicit 30..300-second service pause plus
entry/restoration. --self-test: simulated serial/systemd only.
No new addresses, parameter writes, burner command or fixed sample rate.
The pacing is an experimental setting, NOT a recovered vendor requirement.
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
PARENT_NAME = 'wb2a-gfa-quality-logger.py'
PARENT_SHA256 = 'bdd1d829ba2d1387c21ae99e02848755e7ad8045c0b3034ff7430eb555900910'
REPLY_GAP_SECONDS = 0.150
MAX_SECONDS = 300


def load_quality():
    path = Path(__file__).resolve().with_name(PARENT_NAME)
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != PARENT_SHA256:
        raise RuntimeError('Quality helper hash mismatch; no service/serial operation.')
    module = types.ModuleType('wb2a_quality_pinned')
    module.__file__ = str(path)
    exec(compile(data, str(path), 'exec'), module.__dict__)
    return module


try:
    quality = load_quality()
except Exception as exc:
    print('ERROR: cannot load pinned helpers: ' + str(exc), file=sys.stderr)
    raise SystemExit(2)

base, session = quality.base, quality.session
ProbeError = quality.ProbeError


class PacedWire(quality.Wire):
    """Wait only before bare reads; keep the inherited timestamp/timeout checks."""
    def __init__(self, port, log, clock=time.monotonic, *, seconds=300,
                 emit=None, sleeper=time.sleep):
        super().__init__(port, log, clock, seconds=seconds, emit=emit)
        self.sleeper = sleeper

    def read_session(self, address, round_number):
        if address not in session.FRAMES:
            raise ProbeError('Only the unchanged P80/P06/P09/P10/P84 reads are enabled.')
        self.pending = {'address': f'0x{address:04x}',
                        'request_hex': session.FRAMES[address].hex(' '),
                        'attempt': round_number, 'stage': 'pacing_before_tx'}
        before = len(self.partial)
        previous_reply = self.last_reply
        try:
            self._check_session()
            target = previous_reply + REPLY_GAP_SECONDS
            # Do not change last_reply to hide a host stall or consume queued bytes.
            while self.clock() < target:
                self.sleeper(min(target - self.clock(), 0.020))
                self._check_session()
            self._check_session()
            # Parent starts its TX timestamp after pacing, so latency excludes sleep.
            return super().read_session(address, round_number)
        except BaseException:
            self.active = False
            raise
        finally:
            for row in self.partial[before:]:
                row['rx_to_next_tx_gap_ms'] = (row['tx_mono'] - previous_reply) * 1000

    def encode_sample(self, row):
        record = super().encode_sample(row)
        if 'rx_to_next_tx_gap_ms' in row:
            record['rx_to_next_tx_gap_ms'] = round(row['rx_to_next_tx_gap_ms'], 3)
        return record


def duration_arg(text):
    value = quality.duration_arg(text)
    if value > MAX_SECONDS:
        raise argparse.ArgumentTypeError('This comparison is limited to 30..300 seconds.')
    return value


def annotated_emit(emit):
    def wrapped(row):
        record = dict(row)
        record['experiment'] = 'reply_gap_150ms'
        record['experiment_version'] = VERSION
        record['minimum_reply_gap_ms'] = 150
        if row['kind'] == 'summary':
            record['pacing_proves_root_cause'] = False
        emit(record)
    return wrapped


def self_test():
    import unittest
    if quality.self_test() != 0:
        return 1

    class Port:
        def __init__(self, overrides=None):
            self.rx, self.tx = bytearray(), []
            self.t, self.bare = 0.0, 0
            self.enq = self.closed = False
            self.overrides = overrides or {}
            self.values = {0x4006: 137, 0x4009: 123, 0x400A: 103, 0x4054: 6, 0x4050: 32}
        def clock(self):
            return self.t
        def sleep(self, seconds):
            self.t += seconds
        @property
        def in_waiting(self):
            return len(self.rx)
        def write(self, data):
            self.tx.append((self.t, data))
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
                self.rx.extend(b'\x20')
            elif data in session.FRAMES.values():
                self.bare += 1
                answer = self.overrides.get(self.bare, bytes((self.values[int.from_bytes(data[1:3], 'big')],)))
                if isinstance(answer, BaseException):
                    raise answer
                if answer is not None:
                    self.rx.extend(answer)
            elif data == b'\x06':
                pass  # P300 acknowledgement after the identity reply.
            else:
                raise AssertionError('Unexpected TX ' + data.hex())
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
            self.active = {base.SPLITTER: True, base.PARTY: party}
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
        def case(self, port=None, seconds=30, sleep_hook=None, party=True, log_hook=None):
            p, services = port or Port(), Services(party)
            logs, records = [], []
            def log(msg):
                logs.append(msg)
                if log_hook:
                    log_hook(msg, p)
            def factory(connection, logger, **kwargs):
                def sleep(duration):
                    p.sleep(duration)
                    if sleep_hook:
                        sleep_hook(p)
                return PacedWire(connection, logger, p.clock, sleeper=sleep, **kwargs)
            rc = quality.run_guarded(services, lambda: p, log, annotated_emit(records.append),
                                     seconds=seconds, wire_factory=factory)
            return rc, p, services, logs, records
        def assert_restored(self, result):
            self.assertTrue(result[1].closed)
            self.assertTrue(result[4][-1]['P300_restored'])
            self.assertTrue(result[2].active[base.SPLITTER])
        def test_300_seconds_simulated(self):
            result = self.case(seconds=300)
            self.assertEqual(result[0], 0)
            self.assert_restored(result)
            summary = result[4][-1]
            self.assertTrue(summary['observation_complete'])
            self.assertLessEqual(summary['observation_elapsed_s'], 306)
            self.assertFalse(summary['pacing_proves_root_cause'])
        def test_gap_measured_from_reply_not_previous_send(self):
            result = self.case()
            rows = [r for r in result[4] if r['kind'] == 'round']
            for row in rows:
                for sample in row['samples'] + [row['guard']]:
                    self.assertGreaterEqual(sample['rx_to_next_tx_gap_ms'], 149.999)
                    self.assertLessEqual(sample['rx_to_next_tx_gap_ms'], 150.001)
                    self.assertAlmostEqual(sample['reply_latency_ms'], 50, places=3)
        def test_ff_at_each_channel_quarantined_and_reidentified(self):
            for number in range(2, 7):
                with self.subTest(bare_read=number):
                    result = self.case(Port({number: b'\xff'}))
                    self.assertEqual(result[0], 2)
                    self.assert_restored(result)
                    bad = next(r for r in result[4] if r['kind'] == 'rejected_round')
                    self.assertIsNone(bad['decoded'])
                    self.assertEqual(bad['samples'][-1]['raw'], 255)
                    self.assertGreaterEqual(bad['samples'][-1]['rx_to_next_tx_gap_ms'], 149.999)
                    self.assertEqual(result[4][-1]['reconnections_succeeded'], 1)
        def test_wrong_identity_remains_fatal(self):
            result = self.case(Port({6: b'\x21'}))
            self.assertEqual(result[0], 1)
            self.assert_restored(result)
            self.assertEqual(result[4][-1]['reconnections_attempted'], 0)
        def test_timeout_remains_fatal(self):
            result = self.case(Port({3: None}))
            self.assertEqual(result[0], 1)
            self.assert_restored(result)
            self.assertEqual(result[4][-1]['reconnections_attempted'], 0)
        def test_trailing_byte_remains_fatal(self):
            result = self.case(Port({3: b'\x00\xff'}))
            self.assertEqual(result[0], 1)
            self.assert_restored(result)
        def test_late_queued_byte_during_sleep_blocks_tx(self):
            result = self.case(sleep_hook=lambda p: p.rx.extend(b'\x05'))
            self.assertEqual(result[0], 1)
            self.assertEqual(result[1].bare, 0)
            self.assert_restored(result)
        def test_scheduler_stall_during_sleep_not_hidden(self):
            def stall(p):
                p.t += 0.31
            result = self.case(sleep_hook=stall)
            self.assertEqual(result[0], 1)
            self.assertEqual(result[1].bare, 0)
            self.assert_restored(result)
        def test_interrupt_during_pacing_restores(self):
            def interrupt(p):
                raise KeyboardInterrupt()
            result = self.case(sleep_hook=interrupt)
            self.assertEqual(result[0], 1)
            self.assert_restored(result)
        def test_write_allowlist_unchanged(self):
            result = self.case()
            self.assertTrue(all(data in session.ALLOWED_TX for _, data in result[1].tx))
        def test_unknown_address_rejected_before_sleep(self):
            p = Port()
            w = PacedWire(p, lambda msg: None, p.clock, sleeper=p.sleep)
            with self.assertRaises(ProbeError):
                w.read_session(0x1234, 1)
            self.assertEqual(p.tx, [])
            self.assertEqual(p.t, 0)
        def test_inactive_party_stays_inactive(self):
            result = self.case(party=False)
            self.assertEqual(result[0], 0)
            self.assertFalse(result[2].active[base.PARTY])
            self.assertNotIn(('start', base.PARTY), result[2].calls)
        def test_duration_limits(self):
            for value in ('0', '29', '301', '600', 'nan'):
                with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                    duration_arg(value)
            self.assertEqual(duration_arg('300'), 300)
        def test_clock_budget_during_wait_blocks_new_tx(self):
            p = Port()
            w = PacedWire(p, lambda msg: None, p.clock, sleeper=p.sleep)
            w.active, w.last_reply, w.operation_deadline = True, 0.0, 0.10
            with self.assertRaises(ProbeError):
                w.read_session(0x4050, 0)
            self.assertEqual(p.tx, [])
        def test_early_waking_sleep_still_waits(self):
            p = Port()
            def early_sleep(seconds):
                p.t += max(seconds * 0.5, 0.00001)
            w = PacedWire(p, lambda msg: None, p.clock, sleeper=early_sleep)
            w.active, w.last_reply = True, 0.0
            w.read_session(0x4050, 0)
            self.assertGreaterEqual(p.tx[0][0], 0.15)
            self.assertLess(p.tx[0][0], 0.151)
        def test_console_stall_before_tx_still_checked(self):
            def log_hook(msg, p):
                if msg == 'TX 6b 40 50 01':
                    p.t += 0.31
            result = self.case(log_hook=log_hook)
            self.assertEqual(result[0], 1)
            self.assertEqual(result[1].bare, 0)
            self.assert_restored(result)
    results = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    return 0 if results.wasSuccessful() else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--execute', action='store_true')
    action.add_argument('--self-test', action='store_true')
    parser.add_argument('--seconds', type=duration_arg, default=300)
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if not args.execute:
        print(f'GFA pacing comparison {VERSION}: plan only, no device/service access.\n'
              f'{args.seconds}s; minimum reply-to-next-read gap 150 ms instead of observed ~51 ms.\n'
              'Same five read addresses, 300-ms maximum gap, FF quarantine and max three re-identifications.\n'
              'No parameter writes or burner commands. Normal HA polling/party emulator pause.\n'
              'No root-cause or sample-rate guarantee. --execute required for live action.')
        return 0
    if os.geteuid() != 0:
        print('ERROR: --execute requires root.', file=sys.stderr)
        return 1
    cap, lock_fd, previous, result = None, None, {}, 1
    try:
        import serial
        port = base.read_settings(base.SETTINGS)
        if not stat.S_ISCHR(os.stat(port).st_mode):
            raise ProbeError('Configured port is not a character device.')
        lock_fd = os.open('/run/lock/wb2a-gfa-p80-probe.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        stamp = dt.datetime.now().strftime('%Y%m%d-%H%M%S')
        cap = quality.Capture(Path('/root') / f'wb2a-gfa-paced-{stamp}-{os.getpid()}')
        cap(f'WB2A GFA pacing comparison {VERSION}; LOG={cap.path}; JSONL={cap.json_path}')
        cap('MIN_REPLY_GAP_MS=150; experiment, not a vendor timing specification or a fix claim.')
        cap(f'Configured port: {port}; 4800 8E2; {args.seconds}s plus entry/restoration.')
        cap('Normal HA polling and active party emulator pause; externally maintained requests may change.')
        cap('No burner command/parameter write. No flame, temperature, pump or 55DC measurement.')
        emit = annotated_emit(cap.emit)
        emit({'kind': 'metadata', 'parent_sha256': PARENT_SHA256, 'parent_version': quality.VERSION,
              'seconds': args.seconds, 'parameter_writes': False, 'flame_polled': False,
              'pacing_hardware_validated': False, 'ff_semantics_known': False,
              'max_reconnections': quality.MAX_RECONNECTS, 'maximum_host_gap_ms': 300,
              'cycle_sha256': quality.CYCLE_SHA256, 'session_sha256': quality.SESSION_SHA256,
              'p80_sha256': session.BASE_SHA256})
        cap.ensure_ok()
        def abort(signum, frame):
            raise ProbeError('Interrupted by signal ' + str(signum) + '; entering cleanup.')
        previous = {sig: signal.signal(sig, abort) for sig in base.ABORT_SIGNALS}
        result = quality.run_guarded(base.Services(), lambda: base.open_port(port, serial),
                                     cap, emit, seconds=args.seconds, wire_factory=PacedWire)
    except Exception as exc:
        if cap:
            cap('ERROR: ' + str(exc))
        else:
            print('ERROR: ' + str(exc), file=sys.stderr)
        result = 1
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        if cap:
            cap('LOG=' + str(cap.path))
            cap('JSONL=' + str(cap.json_path))
            try:
                cap.close()
            except Exception as exc:
                print('ERROR: ' + str(exc), file=sys.stderr)
                result = 1
            if cap.error:
                result = 1
        if lock_fd is not None:
            os.close(lock_fd)
    return result


if __name__ == '__main__':
    raise SystemExit(main())
