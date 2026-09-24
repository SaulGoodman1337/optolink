#!/usr/bin/env python3
"""High-resolution WB2A GFA P87/P09 correlation probe.

This helper is a narrow follow-up to the successful triggered-status capture.
It reuses the exact pinned 37 C A1 normal-room setpoint trigger and exact-value
restore implementation from wb2a-gfa-triggered-status-probe.py v1.0.1.

Only two GFA runtime channels are sampled in the observation loop:
  P87 / 0x4057 - GFA Status 3, raw byte; bit semantics unknown
  P09 / 0x4009 - local-GFA modulation setpoint, raw x 0.3922 percent

Two P87/P09 sample pairs are acquired between P80=0x20 identity guards. The
sample order reverses on alternating blocks so one channel is not always read
first. The existing experimental minimum reply-to-next-request gap remains
150 ms; this test changes channel count/order, not transport pacing.

The purpose is only to narrow the timing bracket around P87 0x60->0x62 and
release of the P09 startup plateau. It does not assign a manufacturer meaning
to P87 bit 1 and does not poll an independent flame signal.

No new write path is implemented. The parent permits only temporary 0x2306=37
and exact restoration of the pre-read 0x2306 value. No coding/GFA_WRITE/
PROCESS_WRITE/actuator/flame-safety write exists here.
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
PARENT_NAME = 'wb2a-gfa-triggered-status-probe.py'
PARENT_SHA256 = '6d5810e1595ba6e464452dcd927259e9bade8f550a92b492fd40c2a27972604b'
DEFAULT_SECONDS = 35
MAX_SECONDS = 60
P09 = 0x4009
P80 = 0x4050
P87 = 0x4057
MIN_REPLY_GAP_MS = 150
PAIRS_PER_BLOCK = 2


def duration_arg(text: str) -> int:
    try:
        value = int(text, 10)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError('Seconds must be an integer.') from exc
    if not 30 <= value <= MAX_SECONDS:
        raise argparse.ArgumentTypeError('Hi-res probe is limited to 30..60 seconds.')
    return value


def block_order(block_number: int) -> tuple[int, ...]:
    if isinstance(block_number, bool) or not isinstance(block_number, int) or block_number < 1:
        raise ValueError('Block number must be a positive integer.')
    if block_number & 1:
        return (P87, P09, P87, P09)
    return (P09, P87, P09, P87)


def pair_rows(rows: list[dict], block_number: int) -> list[tuple[dict, dict]]:
    if len(rows) != 4:
        raise ValueError('A hi-res block must contain exactly four runtime samples.')
    expected = block_order(block_number)
    actual = tuple(r.get('address') for r in rows)
    if actual != expected:
        raise ValueError(f'Unexpected block order {actual!r}; expected {expected!r}.')
    pairs = []
    for offset in (0, 2):
        a, b = rows[offset], rows[offset + 1]
        by_address = {a['address']: a, b['address']: b}
        if set(by_address) != {P87, P09}:
            raise ValueError('Each pair must contain exactly one P87 and one P09 sample.')
        pairs.append((by_address[P87], by_address[P09]))
    return pairs


def p87_bit1(value: int) -> bool:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 255:
        raise ValueError('P87 raw value must be one byte.')
    return bool(value & 0x02)


def annotated_emit(emit):
    def wrapped(row):
        record = dict(row)
        record['experiment'] = 'p87_p09_hires_150ms'
        record['experiment_version'] = VERSION
        record['minimum_reply_gap_ms'] = MIN_REPLY_GAP_MS
        record['p87_bit_semantics_known'] = False
        record['flame_polled'] = False
        emit(record)
    return wrapped


def load_parent():
    path = Path(__file__).resolve().with_name(PARENT_NAME)
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != PARENT_SHA256:
        raise RuntimeError(
            f'Triggered-status helper hash mismatch ({digest}); no service/serial operation.'
        )
    module = types.ModuleType('wb2a_gfa_triggered_status_pinned')
    module.__file__ = str(path)
    exec(compile(data, str(path), 'exec'), module.__dict__)
    return module


def make_runtime(triggered):
    status_parent = triggered.load_parent()
    status, base, ParentWire, run_triggered = triggered.make_runtime(status_parent)
    ProbeError = status.ProbeError
    SuspectFF = status.SuspectFF

    class HiResWire(ParentWire):
        def observe(self):
            self._check_session()
            self.started = self.clock()
            stop_at = self.started + self.seconds
            self.operation_deadline = self.deadline = stop_at + status.quality.ROUND_GRACE_SECONDS
            pair_number = 0
            first_b1_sample = None
            first_p09_change_after_b1 = None
            previous_p87 = None
            previous_p09 = None
            self.emit({
                'kind': 'hires_observation_start',
                'version': VERSION,
                'seconds_requested': self.seconds,
                'channels': ['P87', 'P09'],
                'pairs_per_guard_block': PAIRS_PER_BLOCK,
                'order_policy': 'odd blocks P87->P09 twice; even blocks P09->P87 twice',
                'simultaneous': False,
                'fixed_sampling_rate': False,
                'p87_bit_semantics_known': False,
                'flame_polled': False,
            })
            self.log(
                f'HIRES_OBSERVATION_START seconds={self.seconds}; '
                'two P87/P09 pairs per P80 guard; order reverses by block; '
                'P87 bit semantics unknown.'
            )
            try:
                try:
                    self.read_session(P80, 0)
                except BaseException as exc:
                    self.reject(exc)
                    raise
                self.partial = []

                while self.clock() < stop_at:
                    if self.attempts >= status.quality.MAX_ROUNDS:
                        raise ProbeError('Block safety cap reached before window completed.')
                    self.attempts += 1
                    block = self.attempts
                    self.partial, self.pending = [], None
                    order = block_order(block)
                    try:
                        rows = [self.read_session(address, block) for address in order]
                        guard = self.read_session(P80, block)
                    except SuspectFF as exc:
                        self.reject(exc)
                        self.reconnect(stop_at)
                        previous_p87 = previous_p09 = None
                        continue
                    except BaseException as exc:
                        self.reject(exc)
                        raise

                    for row in rows:
                        row['quality'] = 'accepted_by_policy_not_independently_verified'
                    pairs = pair_rows(rows, block)
                    block_pair_records = []
                    for p87, p09 in pairs:
                        pair_number += 1
                        changes = []
                        if previous_p87 is not None and previous_p87['raw'] != p87['raw']:
                            changes.append({
                                'parameter': 'P87',
                                'old_raw': previous_p87['raw'],
                                'old_raw_hex': f'{previous_p87["raw"]:02x}',
                                'new_raw': p87['raw'],
                                'new_raw_hex': f'{p87["raw"]:02x}',
                                'previous_rx_time': previous_p87['rx_time'],
                                'rx_time': p87['rx_time'],
                                'changed_bits': status.changed_bits(previous_p87['raw'], p87['raw']),
                                'new_set_bits': status.set_bits(p87['raw']),
                            })
                        if previous_p09 is not None and previous_p09['raw'] != p09['raw']:
                            changes.append({
                                'parameter': 'P09',
                                'old_raw': previous_p09['raw'],
                                'old_raw_hex': f'{previous_p09["raw"]:02x}',
                                'new_raw': p09['raw'],
                                'new_raw_hex': f'{p09["raw"]:02x}',
                                'previous_rx_time': previous_p09['rx_time'],
                                'rx_time': p09['rx_time'],
                            })

                        b1 = p87_bit1(p87['raw'])
                        if b1 and first_b1_sample is None:
                            first_b1_sample = {
                                'pair': pair_number,
                                'raw': p87['raw'],
                                'raw_hex': f'{p87["raw"]:02x}',
                                'rx_time': p87['rx_time'],
                                'rx_elapsed_s': round(p87['rx_mono'] - self.started, 6),
                            }
                        if (
                            first_b1_sample is not None
                            and first_p09_change_after_b1 is None
                            and previous_p09 is not None
                            and previous_p09['raw'] != p09['raw']
                        ):
                            first_p09_change_after_b1 = {
                                'pair': pair_number,
                                'old_raw': previous_p09['raw'],
                                'new_raw': p09['raw'],
                                'previous_rx_time': previous_p09['rx_time'],
                                'rx_time': p09['rx_time'],
                                'rx_elapsed_s': round(p09['rx_mono'] - self.started, 6),
                            }

                        span_ms = abs(p09['rx_mono'] - p87['rx_mono']) * 1000
                        order_name = 'P87->P09' if p87['rx_mono'] < p09['rx_mono'] else 'P09->P87'
                        record = {
                            'kind': 'hires_pair',
                            'pair': pair_number,
                            'block': block,
                            'segment': self.segment,
                            'guard_pending': True,
                            'sample_order': order_name,
                            'pair_span_ms': round(span_ms, 3),
                            'P87': self.encode_sample(p87),
                            'P09': self.encode_sample(p09),
                            'decoded': {
                                'p87_raw': p87['raw'],
                                'p87_set_bits': status.set_bits(p87['raw']),
                                'p87_bit1': b1,
                                'p09_raw': p09['raw'],
                                'modulation_setpoint_pct': round(p09['raw'] * 0.3922, 4),
                            },
                            'changes': changes,
                        }
                        block_pair_records.append(record)
                        previous_p87, previous_p09 = p87, p09

                    # The following P80=20 validates the complete two-pair block by policy.
                    for record in block_pair_records:
                        record['guard_pending'] = False
                        record['guard_passed'] = True
                        record['guard'] = self.encode_sample(guard)
                        self.emit(record)
                        self.log(
                            f'PAIR {record["pair"]} block={block} segment={self.segment} '
                            f'order={record["sample_order"]} '
                            f'P87=0x{record["decoded"]["p87_raw"]:02x} '
                            f'b1={int(record["decoded"]["p87_bit1"])} '
                            f'P09=0x{record["decoded"]["p09_raw"]:02x} '
                            f'mod={record["decoded"]["modulation_setpoint_pct"]:.4f}% '
                            f'pair_span_ms={record["pair_span_ms"]:.1f} guard=20'
                        )

                    self.rounds += 1  # quality/reconnect policy counts accepted guarded blocks
                    self.last_confirmed_elapsed = self.clock() - self.started
                    self.nonzero_rounds += int(any(r['raw'] for r in rows))
                    self.partial = []

                if not self.rounds or self.clock() - self.started > self.seconds + status.quality.ROUND_GRACE_SECONDS:
                    raise ProbeError('Window incomplete or final-block budget exceeded.')
                self.observation_complete = True
                self.emit({
                    'kind': 'hires_observation_summary',
                    'accepted_guard_blocks': self.rounds,
                    'accepted_pairs': pair_number,
                    'rejected_blocks': self.rejected_rounds,
                    'reconnections': self.reconnects_succeeded,
                    'first_p87_bit1_sample': first_b1_sample,
                    'first_p09_change_after_bit1_sample': first_p09_change_after_b1,
                    'semantic_conclusion': None,
                })
                self.log(
                    f'HIRES_OBSERVATION_COMPLETE=yes BLOCKS={self.rounds} PAIRS={pair_number} '
                    f'REJECTED_BLOCKS={self.rejected_rounds} RECONNECTIONS={self.reconnects_succeeded}'
                )
            except BaseException:
                self.failure_elapsed = self.clock() - self.started
                raise
            finally:
                self.elapsed = self.clock() - self.started
                self.operation_deadline = None
                self.deadline = None

    return status, base, HiResWire, run_triggered


def self_test() -> int:
    import unittest

    class LocalTests(unittest.TestCase):
        def test_duration_bounds(self):
            self.assertEqual(duration_arg('30'), 30)
            self.assertEqual(duration_arg('35'), 35)
            self.assertEqual(duration_arg('60'), 60)
            for value in ('29', '61', '120', 'nan'):
                with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                    duration_arg(value)

        def test_block_order_reverses(self):
            self.assertEqual(block_order(1), (P87, P09, P87, P09))
            self.assertEqual(block_order(2), (P09, P87, P09, P87))
            self.assertEqual(block_order(3), (P87, P09, P87, P09))

        def test_bad_block_numbers(self):
            for value in (0, -1, True, 1.5):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    block_order(value)

        def test_pair_rows_odd(self):
            rows = [
                {'address': P87, 'raw': 0x60}, {'address': P09, 'raw': 0x93},
                {'address': P87, 'raw': 0x62}, {'address': P09, 'raw': 0x91},
            ]
            pairs = pair_rows(rows, 1)
            self.assertEqual([(a['raw'], b['raw']) for a, b in pairs], [(0x60, 0x93), (0x62, 0x91)])

        def test_pair_rows_even(self):
            rows = [
                {'address': P09, 'raw': 0x93}, {'address': P87, 'raw': 0x60},
                {'address': P09, 'raw': 0x91}, {'address': P87, 'raw': 0x62},
            ]
            pairs = pair_rows(rows, 2)
            self.assertEqual([(a['raw'], b['raw']) for a, b in pairs], [(0x60, 0x93), (0x62, 0x91)])

        def test_pair_rows_rejects_wrong_order(self):
            rows = [{'address': P87}, {'address': P09}, {'address': P09}, {'address': P87}]
            with self.assertRaises(ValueError):
                pair_rows(rows, 1)

        def test_p87_bit1(self):
            self.assertFalse(p87_bit1(0x60))
            self.assertTrue(p87_bit1(0x62))
            self.assertTrue(p87_bit1(0x02))
            self.assertFalse(p87_bit1(0x00))

        def test_p87_bit1_range(self):
            for value in (-1, 256, True, 1.5):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    p87_bit1(value)

        def test_constants_are_read_only_gfa_targets(self):
            self.assertEqual(P87, 0x4057)
            self.assertEqual(P09, 0x4009)
            self.assertEqual(P80, 0x4050)
            self.assertEqual(MIN_REPLY_GAP_MS, 150)
            self.assertEqual(PAIRS_PER_BLOCK, 2)

    local = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(LocalTests)
    )
    if not local.wasSuccessful():
        return 1

    try:
        triggered = load_parent()
    except Exception as exc:
        print('PARENT_CHAIN_TESTS=SKIPPED: ' + str(exc))
        print('LOCAL_HIRES_TESTS=9/9')
        return 0

    parent_rc = triggered.self_test()
    if parent_rc:
        return 1
    # Construction itself verifies that the exact parent exposes the expected
    # pinned status/transport runtime. Live behavior is still hardware evidence.
    make_runtime(triggered)
    print('LOCAL_HIRES_TESTS=9/9; PARENT_TRIGGERED_CHAIN_TESTS=PASS')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--execute', action='store_true')
    action.add_argument('--self-test', action='store_true')
    parser.add_argument('--seconds', type=duration_arg, default=DEFAULT_SECONDS)
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if not args.execute:
        print(
            f'WB2A P87/P09 hi-res probe {VERSION}: plan only; no device/service access.\n'
            'Uses the pinned v1.0.1 37 C trigger and exact original-value restore.\n'
            'Observation: two P87/P09 pairs per P80 guard; order reverses by block.\n'
            'Pacing stays at the previously tested 150 ms minimum reply gap.\n'
            'No new write path and no P87 bit meaning is assigned. --execute required.'
        )
        return 0
    if os.geteuid() != 0:
        print('ERROR: --execute requires root.', file=sys.stderr)
        return 1

    cap = lock_fd = None
    previous = {}
    result = 1
    try:
        triggered = load_parent()
        status, base, HiResWire, run_triggered = make_runtime(triggered)
        import serial

        port = base.read_settings(base.SETTINGS)
        if not stat.S_ISCHR(os.stat(port).st_mode):
            raise status.ProbeError('Configured port is not a character device.')
        lock_fd = os.open(
            '/run/lock/wb2a-gfa-p80-probe.lock',
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
            0o600,
        )
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        stamp = dt.datetime.now().strftime('%Y%m%d-%H%M%S')
        cap = status.quality.Capture(Path('/root') / f'wb2a-gfa-p87-p09-hires-{stamp}-{os.getpid()}')
        cap(f'WB2A P87/P09 hi-res probe {VERSION}; LOG={cap.path}; JSONL={cap.json_path}')
        cap(f'Configured port: {port}; 4800 8E2; capture={args.seconds}s plus trigger/cleanup.')
        cap('PARENT TRIGGER: only A1 normal setpoint 0x2306 -> 37 C -> exact captured original.')
        cap('HIRES READS: only P87/P09 runtime pairs plus P80 guards; 150-ms experimental pacing.')
        cap('P87 bit semantics remain unknown; no independent flame signal is polled.')
        cap('Normal HA polling and active party emulator pause while this helper owns serial.')
        cap.ensure_ok()

        emit = annotated_emit(cap.emit)
        emit({
            'kind': 'metadata',
            'version': VERSION,
            'parent_sha256': PARENT_SHA256,
            'seconds': args.seconds,
            'parameter_write_policy': 'inherited exact pinned 0x2306 37C trigger and original restore only',
            'runtime_read_addresses': ['0x4057', '0x4009', '0x4050'],
            'pairs_per_guard_block': PAIRS_PER_BLOCK,
            'minimum_reply_gap_ms': MIN_REPLY_GAP_MS,
            'order_reverses_by_block': True,
            'p87_bit_semantics_known': False,
            'flame_polled': False,
            'arbitrary_addresses': False,
            'gfa_write': False,
            'process_write': False,
            'actuator_test': False,
        })

        def abort(signum, _frame):
            raise status.ProbeError('Interrupted by signal ' + str(signum) + '; entering cleanup.')

        previous = {sig: signal.signal(sig, abort) for sig in base.ABORT_SIGNALS}
        result = run_triggered(
            base.Services(),
            lambda: base.open_port(port, serial),
            cap,
            emit,
            seconds=args.seconds,
            wire_factory=lambda connection, logger, **kwargs: HiResWire(connection, logger, **kwargs),
        )
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
