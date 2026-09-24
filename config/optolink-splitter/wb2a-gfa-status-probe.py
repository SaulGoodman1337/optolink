#!/usr/bin/env python3
"""Read-only WB2A GFA startup-status probe with alternating status banks.

Requires the unchanged SHA256-pinned paced helper and its dependency chain in
the same directory. Live reads are restricted to P84/P12/P85/P86/P87/P88
plus P80 identity. P84 and P12 are read every measurement round; P85/P86 and
P87/P88 alternate so each round remains four runtime reads plus the P80 guard,
matching the read count of the previously validated paced startup capture.

P84 has no recovered phase enum. P12 is source-labelled a bit-coded digital
input. P85-P88 are source-labelled GFA Status 1..4. Their bit meanings are not
known. This helper records raw bytes, set-bit positions, and bit changes only;
it does not label any bit as flame, ignition, gas valve, or safety state.

Default: plan only. --self-test: simulated serial/systemd only. --execute:
explicit 30..120-second service pause plus entry/restoration. Minimum
reply-to-next-read gap remains the experimental 150 ms. FF quarantines the
whole current round; the inherited bounded re-identification policy remains.
No writes, burner command, actuator test, arbitrary address, or process write.
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
PARENT_NAME = 'wb2a-gfa-paced-probe.py'
PARENT_SHA256 = '053c7806d863c7fe551903a24498f4841c0d2235b661e674f80f07696065e974'
MAX_SECONDS = 120
REPLY_GAP_SECONDS = 0.150

P12 = 0x400C
P80 = 0x4050
P84 = 0x4054
P85 = 0x4055
P86 = 0x4056
P87 = 0x4057
P88 = 0x4058

BANK_A = (P84, P12, P85, P86)
BANK_B = (P84, P12, P87, P88)
LABELS = {
    P12: 'P12', P80: 'P80', P84: 'P84', P85: 'P85',
    P86: 'P86', P87: 'P87', P88: 'P88',
}
FRAMES = {
    address: bytes((0x6B, address >> 8, address & 0xFF, 0x01))
    for address in (P12, P80, P84, P85, P86, P87, P88)
}


def load_parent():
    path = Path(__file__).resolve().with_name(PARENT_NAME)
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != PARENT_SHA256:
        raise RuntimeError('Paced helper hash mismatch; no service/serial operation.')
    module = types.ModuleType('wb2a_gfa_paced_pinned')
    module.__file__ = str(path)
    exec(compile(data, str(path), 'exec'), module.__dict__)
    return module


try:
    paced = load_parent()
except Exception as exc:
    print('ERROR: cannot load pinned helpers: ' + str(exc), file=sys.stderr)
    raise SystemExit(2)

quality, session, base = paced.quality, paced.session, paced.base
ProbeError = quality.ProbeError
SuspectFF = quality.SuspectFF
ALLOWED_TX = base.ALLOWED_TX | frozenset(FRAMES.values())


def set_bits(value: int) -> list[int]:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 255:
        raise ProbeError('Invalid one-byte value for bit view.')
    return [bit for bit in range(8) if value & (1 << bit)]


def changed_bits(old: int, new: int) -> list[int]:
    return set_bits(old ^ new)


def duration_arg(text: str) -> int:
    try:
        value = int(text, 10)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError('Seconds must be an integer.') from exc
    if not 30 <= value <= MAX_SECONDS:
        raise argparse.ArgumentTypeError('This status probe is limited to 30..120 seconds.')
    return value


def annotated_emit(emit):
    def wrapped(row):
        record = dict(row)
        record['experiment'] = 'gfa_status_banks_150ms'
        record['experiment_version'] = VERSION
        record['minimum_reply_gap_ms'] = 150
        record['p84_enum_known'] = False
        record['p12_bit_semantics_known'] = False
        record['status_bit_semantics_known'] = False
        if record.get('kind') == 'summary':
            record['flame_polled'] = False
            record['status_probe_proves_flame_timing'] = False
        emit(record)
    return wrapped


class StatusWire(paced.PacedWire):
    """Paced same-session reads for the fixed P84/P12/P85-P88 target set."""

    def __init__(self, port, log, clock=time.monotonic, *, seconds=60,
                 emit=None, sleeper=time.sleep):
        super().__init__(port, log, clock, seconds=seconds, emit=emit, sleeper=sleeper)

    def send(self, data: bytes):
        self._check_budget()
        if data not in ALLOWED_TX:
            raise ProbeError('TX blocked by fixed read-only status-probe allowlist.')
        bare = data in FRAMES.values()
        if bare:
            self._check_session()
        else:
            self.active = False
            self.deadline = None
        self.log('TX ' + data.hex(' '))
        if bare:
            self._check_session()
        self.touched = True
        if self.port.write(data) != len(data):
            raise ProbeError('Partial serial write; no automatic retransmission.')

    def read_session(self, address: int, round_number: int):
        if address not in FRAMES:
            raise ProbeError('Only P80/P84/P12/P85/P86/P87/P88 are enabled.')
        self.pending = {
            'address': f'0x{address:04x}',
            'request_hex': FRAMES[address].hex(' '),
            'attempt': round_number,
            'stage': 'pacing_before_tx',
        }
        previous_reply = self.last_reply
        try:
            self._check_session()
            target = previous_reply + REPLY_GAP_SECONDS
            while self.clock() < target:
                self.sleeper(min(target - self.clock(), 0.020))
                self._check_session()
            self._check_session()
            self.pending['stage'] = 'before_tx'
            start = self.clock()
            self.send(FRAMES[address])
            self.pending['stage'] = 'awaiting_reply'
            value = self.exact(1, timeout=1.0)[0]
            row = {
                'round': round_number,
                'address': address,
                'raw': value,
                'tx_mono': start,
                'rx_mono': self.last_reply,
                'rx_time': self.last_wall,
                'latency_ms': (self.last_reply - start) * 1000,
                'quality': 'received_pending_guard',
                'rx_to_next_tx_gap_ms': (start - previous_reply) * 1000,
            }
            self.partial.append(row)
            self.pending['stage'] = 'received_checking_tail'
            tail = self.port.read(1)
            self._check_budget()
            if tail:
                row['quality'] = 'rejected_trailing_data'
                self.log('RX unexpected trailing ' + tail.hex(' '))
                raise ProbeError('Unexpected trailing data; no automatic reconnection.')
            if value == 0xFF:
                row['quality'] = 'suspect_ff_unresolved'
                self.log(
                    f'SUSPECT_FF attempt={round_number} address=0x{address:04x} '
                    f'raw=ff decoded=unavailable rx_time={row["rx_time"]} '
                    f'reply_latency_ms={row["latency_ms"]:.1f}'
                )
                raise SuspectFF(f'FF at 0x{address:04x}; current round quarantined.')
            if address == P80 and value != 0x20:
                row['quality'] = 'rejected_identity'
                raise ProbeError(
                    f'P80 changed to 0x{value:02x}; expected 20. No automatic reconnection.'
                )
            row['quality'] = 'identity_match' if address == P80 else 'received_pending_guard'
            self.pending['stage'] = 'received'
            bits = '' if address == P84 or address == P80 else f' set_bits={set_bits(value)}'
            self.log(
                f'SAMPLE attempt={round_number} {LABELS[address]} '
                f'address=0x{address:04x} raw={value:02x} quality={row["quality"]}{bits} '
                f'rx_time={row["rx_time"]} reply_latency_ms={row["latency_ms"]:.1f}'
            )
            return row
        except BaseException:
            self.active = False
            raise

    def encode_sample(self, row):
        record = {
            'parameter': LABELS[row['address']],
            'address': f'0x{row["address"]:04x}',
            'raw': row['raw'],
            'raw_hex': f'{row["raw"]:02x}',
            'rx_time': row['rx_time'],
            'tx_elapsed_s': round(row['tx_mono'] - self.started, 6),
            'rx_elapsed_s': round(row['rx_mono'] - self.started, 6),
            'reply_latency_ms': round(row['latency_ms'], 3),
            'quality': row['quality'],
        }
        if 'rx_to_next_tx_gap_ms' in row:
            record['rx_to_next_tx_gap_ms'] = round(row['rx_to_next_tx_gap_ms'], 3)
        if row['address'] in (P12, P85, P86, P87, P88):
            record['set_bits'] = set_bits(row['raw'])
        return record

    def observe(self):
        self._check_session()
        self.started = self.clock()
        stop_at = self.started + self.seconds
        self.operation_deadline = self.deadline = stop_at + quality.ROUND_GRACE_SECONDS
        self.emit({
            'kind': 'observation_start',
            'version': VERSION,
            'seconds_requested': self.seconds,
            'simultaneous': False,
            'flame_polled': False,
            'fixed_sampling_rate': False,
            'max_reconnections': quality.MAX_RECONNECTS,
            'ff_semantics_known': False,
            'bank_A': [LABELS[a] for a in BANK_A],
            'bank_B': [LABELS[a] for a in BANK_B],
        })
        self.log(
            f'OBSERVATION_START seconds={self.seconds}; alternating banks; '
            'raw status bits only; no flame semantic assignment; no burner command.'
        )
        previous_by_address = {}
        try:
            try:
                self.read_session(P80, 0)
            except BaseException as exc:
                self.reject(exc)
                raise
            self.partial = []
            while self.clock() < stop_at:
                if self.attempts >= quality.MAX_ROUNDS:
                    raise ProbeError('Round safety cap reached before window completed.')
                self.attempts += 1
                bank_name = 'A' if self.attempts % 2 else 'B'
                bank = BANK_A if bank_name == 'A' else BANK_B
                self.partial, self.pending = [], None
                try:
                    rows = [self.read_session(address, self.attempts) for address in bank]
                    guard = self.read_session(P80, self.attempts)
                except SuspectFF as exc:
                    self.reject(exc)
                    self.reconnect(stop_at)
                    previous_by_address = {}
                    continue
                except BaseException as exc:
                    self.reject(exc)
                    raise

                span_ms = (rows[-1]['rx_mono'] - rows[0]['rx_mono']) * 1000
                changes = []
                for row in rows:
                    old = previous_by_address.get(row['address'])
                    if old is not None and old['raw'] != row['raw']:
                        change = {
                            'parameter': LABELS[row['address']],
                            'old_raw': old['raw'],
                            'old_raw_hex': f'{old["raw"]:02x}',
                            'new_raw': row['raw'],
                            'new_raw_hex': f'{row["raw"]:02x}',
                            'previous_rx_time': old['rx_time'],
                            'rx_time': row['rx_time'],
                        }
                        if row['address'] in (P12, P85, P86, P87, P88):
                            change['changed_bits'] = changed_bits(old['raw'], row['raw'])
                            change['new_set_bits'] = set_bits(row['raw'])
                        changes.append(change)
                for row in rows:
                    row['quality'] = 'accepted_by_policy_not_independently_verified'

                number = self.rounds + 1
                raw_by_parameter = {LABELS[row['address']]: row['raw'] for row in rows}
                self.emit({
                    'kind': 'round',
                    'round': number,
                    'attempt': self.attempts,
                    'segment': self.segment,
                    'bank': bank_name,
                    'guard_passed': True,
                    'quality': 'no_ff_and_identity_match',
                    'physical_validity_proven': False,
                    'sample_span_ms': round(span_ms, 3),
                    'samples': [self.encode_sample(row) for row in rows],
                    'guard': self.encode_sample(guard),
                    'raw_by_parameter': raw_by_parameter,
                    'changes': changes,
                })
                self.rounds = number
                self.last_confirmed_elapsed = self.clock() - self.started
                self.nonzero_rounds += int(any(row['raw'] for row in rows))
                self.phase_changes += sum(c['parameter'] == 'P84' for c in changes)

                display = {name: '--' for name in ('P85', 'P86', 'P87', 'P88')}
                for row in rows:
                    if LABELS[row['address']] in display:
                        display[LABELS[row['address']]] = f'{row["raw"]:02x}'
                values = {row['address']: row['raw'] for row in rows}
                self.log(
                    f'ROUND {number} attempt={self.attempts} segment={self.segment} bank={bank_name} '
                    f't={rows[0]["rx_mono"] - self.started:.3f}s '
                    f'P84=0x{values[P84]:02x} P12=0x{values[P12]:02x} '
                    f'P85={display["P85"]} P86={display["P86"]} '
                    f'P87={display["P87"]} P88={display["P88"]} '
                    f'span_ms={span_ms:.1f} guard=20 quality=no_ff_and_identity_match'
                )
                for row in rows:
                    previous_by_address[row['address']] = row
                self.partial = []

            if not self.rounds or self.clock() - self.started > self.seconds + quality.ROUND_GRACE_SECONDS:
                raise ProbeError('Window incomplete or final-round budget exceeded.')
            self.observation_complete = True
            self.log(
                f'OBSERVATION_COMPLETE=yes ACCEPTED_ROUNDS={self.rounds} '
                f'REJECTED_ROUNDS={self.rejected_rounds} RECONNECTIONS={self.reconnects_succeeded}'
            )
        except BaseException:
            self.failure_elapsed = self.clock() - self.started
            raise
        finally:
            self.elapsed = self.clock() - self.started
            self.operation_deadline = None
            self.deadline = None


def self_test():
    import unittest

    if paced.self_test() != 0:
        return 1

    class Port:
        def __init__(self, overrides=None, value_hook=None):
            self.rx, self.tx = bytearray(), []
            self.t, self.bare = 0.0, 0
            self.enq = self.closed = False
            self.overrides = overrides or {}
            self.value_hook = value_hook
            self.values = {
                P84: 0x06, P12: 0x12, P85: 0x01, P86: 0x02,
                P87: 0x04, P88: 0x08, P80: 0x20,
            }

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
            elif data in FRAMES.values():
                self.bare += 1
                address = int.from_bytes(data[1:3], 'big')
                answer = self.overrides.get(self.bare)
                if answer is None and self.bare not in self.overrides:
                    value = self.value_hook(address, self.bare) if self.value_hook else self.values[address]
                    answer = bytes((value,))
                if isinstance(answer, BaseException):
                    raise answer
                if answer is not None:
                    self.rx.extend(answer)
            elif data == b'\x06':
                pass
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
            return {
                'LoadState': 'loaded',
                'ActiveState': 'active' if self.active[unit] else 'inactive',
                'SubState': 'running' if self.active[unit] else 'dead',
            }

        def stop(self, unit):
            self.calls.append(('stop', unit))
            self.active[unit] = False

        def start(self, unit):
            self.calls.append(('start', unit))
            self.active[unit] = True

    class Tests(unittest.TestCase):
        def case(self, port=None, seconds=30, party=True, sleep_hook=None, log_hook=None):
            p = port or Port()
            services = Services(party)
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
                return StatusWire(connection, logger, p.clock, sleeper=sleep, **kwargs)

            rc = quality.run_guarded(
                services, lambda: p, log, annotated_emit(records.append),
                seconds=seconds, wire_factory=factory,
            )
            return rc, p, services, logs, records

        def assert_restored(self, result):
            self.assertTrue(result[1].closed)
            self.assertTrue(result[2].active[base.SPLITTER])
            self.assertTrue(result[4][-1]['P300_restored'])

        def test_bit_helpers(self):
            self.assertEqual(set_bits(0), [])
            self.assertEqual(set_bits(0xA5), [0, 2, 5, 7])
            self.assertEqual(changed_bits(0x01, 0x05), [2])
            with self.assertRaises(ProbeError):
                set_bits(256)

        def test_banks_are_fixed_and_alternating(self):
            result = self.case()
            self.assertEqual(result[0], 0)
            rows = [r for r in result[4] if r.get('kind') == 'round']
            self.assertGreaterEqual(len(rows), 2)
            self.assertEqual(rows[0]['bank'], 'A')
            self.assertEqual([s['parameter'] for s in rows[0]['samples']], ['P84', 'P12', 'P85', 'P86'])
            self.assertEqual(rows[1]['bank'], 'B')
            self.assertEqual([s['parameter'] for s in rows[1]['samples']], ['P84', 'P12', 'P87', 'P88'])
            self.assertTrue(all(r['guard']['parameter'] == 'P80' for r in rows))
            self.assert_restored(result)

        def test_five_reads_per_round_preserves_request_count(self):
            result = self.case()
            rows = [r for r in result[4] if r.get('kind') == 'round']
            self.assertGreater(len(rows), 0)
            self.assertEqual(result[1].bare, 1 + len(rows) * 5)

        def test_raw_bits_recorded_without_semantic_names(self):
            result = self.case()
            row = next(r for r in result[4] if r.get('kind') == 'round')
            samples = {s['parameter']: s for s in row['samples']}
            self.assertEqual(samples['P12']['set_bits'], [1, 4])
            self.assertEqual(samples['P85']['set_bits'], [0])
            self.assertNotIn('flame', samples['P12'])
            self.assertFalse(row['p12_bit_semantics_known'])
            self.assertFalse(row['status_bit_semantics_known'])

        def test_bit_changes_use_xor_and_keep_raw(self):
            counts = {P12: 0}
            def hook(address, bare):
                if address == P12:
                    counts[P12] += 1
                    return 0x01 if counts[P12] == 1 else 0x05
                return Port().values[address]
            result = self.case(Port(value_hook=hook))
            rows = [r for r in result[4] if r.get('kind') == 'round']
            change = next(c for r in rows for c in r['changes'] if c['parameter'] == 'P12')
            self.assertEqual(change['old_raw_hex'], '01')
            self.assertEqual(change['new_raw_hex'], '05')
            self.assertEqual(change['changed_bits'], [2])
            self.assertEqual(change['new_set_bits'], [0, 2])

        def test_p84_change_count_only_counts_p84(self):
            seen = {P84: 0, P12: 0}
            def hook(address, bare):
                if address == P84:
                    seen[P84] += 1
                    return 2 if seen[P84] == 1 else 6
                if address == P12:
                    seen[P12] += 1
                    return seen[P12] & 1
                return Port().values[address]
            result = self.case(Port(value_hook=hook))
            summary = result[4][-1]
            self.assertGreater(summary['phase_changes'], 0)
            p84_changes = sum(
                c['parameter'] == 'P84'
                for r in result[4] if r.get('kind') == 'round'
                for c in r['changes']
            )
            self.assertEqual(summary['phase_changes'], p84_changes)

        def test_gap_at_least_150ms(self):
            result = self.case()
            rows = [r for r in result[4] if r.get('kind') == 'round']
            for row in rows:
                for sample in row['samples'] + [row['guard']]:
                    self.assertGreaterEqual(sample['rx_to_next_tx_gap_ms'], 149.999)
                    self.assertLess(sample['rx_to_next_tx_gap_ms'], 150.001)

        def test_allowlist_has_reads_and_no_write_function(self):
            for address, frame in FRAMES.items():
                self.assertEqual(frame[0], 0x6B)
                self.assertEqual(frame[-1], 1)
                self.assertEqual(int.from_bytes(frame[1:3], 'big'), address)
            result = self.case()
            self.assertTrue(all(data in ALLOWED_TX for _, data in result[1].tx))
            self.assertFalse(any(data and data[0] in (0x6C, 0xC8, 0xCA) for _, data in result[1].tx))

        def test_unknown_address_blocked_before_tx(self):
            p = Port()
            w = StatusWire(p, lambda msg: None, p.clock, seconds=30, sleeper=p.sleep)
            w.active, w.last_reply = True, 0.0
            with self.assertRaises(ProbeError):
                w.read_session(0x1234, 1)
            self.assertEqual(p.tx, [])

        def test_ff_each_runtime_position_is_quarantined(self):
            for bare in (2, 3, 4, 5):
                with self.subTest(bare=bare):
                    result = self.case(Port({bare: b'\xff'}))
                    self.assertEqual(result[0], 2)
                    bad = next(r for r in result[4] if r.get('kind') == 'rejected_round')
                    self.assertIsNone(bad['decoded'])
                    self.assertEqual(bad['samples'][-1]['raw'], 255)
                    self.assertEqual(result[4][-1]['reconnections_succeeded'], 1)
                    self.assert_restored(result)

        def test_wrong_p80_fatal_no_reconnect(self):
            result = self.case(Port({6: b'\x21'}))
            self.assertEqual(result[0], 1)
            self.assertEqual(result[4][-1]['reconnections_attempted'], 0)
            self.assert_restored(result)

        def test_timeout_fatal(self):
            result = self.case(Port({3: None}))
            self.assertEqual(result[0], 1)
            self.assert_restored(result)

        def test_trailing_byte_fatal(self):
            result = self.case(Port({3: b'\x00\xff'}))
            self.assertEqual(result[0], 1)
            self.assert_restored(result)

        def test_second_ff_too_soon_stops_loop(self):
            # FF P12 in round 1, then after reconnect FF P87 in the next attempted bank.
            result = self.case(Port({3: b'\xff', 7: b'\xff'}))
            self.assertEqual(result[0], 1)
            self.assertEqual(result[4][-1]['reconnections_succeeded'], 1)
            self.assertEqual(result[4][-1]['reconnections_attempted'], 1)
            self.assert_restored(result)

        def test_inactive_party_stays_inactive(self):
            result = self.case(party=False)
            self.assertEqual(result[0], 0)
            self.assertFalse(result[2].active[base.PARTY])
            self.assertNotIn(('start', base.PARTY), result[2].calls)

        def test_duration_limits(self):
            for value in ('0', '29', '121', '300', 'nan'):
                with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                    duration_arg(value)
            self.assertEqual(duration_arg('60'), 60)
            self.assertEqual(duration_arg('120'), 120)

        def test_scheduler_stall_during_pacing_remains_fatal(self):
            def stall(p):
                p.t += 0.31
            result = self.case(sleep_hook=stall)
            self.assertEqual(result[0], 1)
            self.assertEqual(result[1].bare, 0)
            self.assert_restored(result)

        def test_60_seconds_simulated(self):
            result = self.case(seconds=60)
            self.assertEqual(result[0], 0)
            summary = result[4][-1]
            self.assertTrue(summary['observation_complete'])
            self.assertGreater(summary['rounds_confirmed'], 20)
            self.assertEqual(summary['rejected_rounds'], 0)
            self.assertFalse(summary['flame_polled'])
            self.assertFalse(summary['status_probe_proves_flame_timing'])
            self.assert_restored(result)

    results = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
    )
    return 0 if results.wasSuccessful() else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--execute', action='store_true')
    action.add_argument('--self-test', action='store_true')
    parser.add_argument('--seconds', type=duration_arg, default=60)
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if not args.execute:
        print(
            f'GFA status probe {VERSION}: plan only, no device/service access.\n'
            f'{args.seconds}s; P84/P12 every round; P85/P86 and P87/P88 alternate.\n'
            'Each round: four read-only runtime requests plus P80 guard; minimum gap 150 ms.\n'
            'Raw bytes and bit positions only; no phase or status-bit semantic assignment.\n'
            'No parameter writes, burner commands, actuator tests, or arbitrary addresses.\n'
            'Normal HA polling and active party emulator pause. --execute required for live action.'
        )
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
        lock_fd = os.open(
            '/run/lock/wb2a-gfa-p80-probe.lock',
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
            0o600,
        )
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        stamp = dt.datetime.now().strftime('%Y%m%d-%H%M%S')
        cap = quality.Capture(Path('/root') / f'wb2a-gfa-status-{stamp}-{os.getpid()}')
        cap(f'WB2A GFA status probe {VERSION}; LOG={cap.path}; JSONL={cap.json_path}')
        cap('MIN_REPLY_GAP_MS=150; experimental pacing, not a vendor specification.')
        cap(f'Configured port: {port}; 4800 8E2; {args.seconds}s plus entry/restoration.')
        cap('Banks: A=P84/P12/P85/P86; B=P84/P12/P87/P88; P80 guards every round.')
        cap('P84 enum unknown; P12/P85-P88 bit meanings unknown; raw/bit changes only.')
        cap('No burner command/parameter write. No independent flame, temperature, pump or 55DC measurement.')
        cap('Normal HA polling and active party emulator pause; externally maintained requests may change.')
        emit = annotated_emit(cap.emit)
        emit({
            'kind': 'metadata',
            'parent_sha256': PARENT_SHA256,
            'parent_version': paced.VERSION,
            'seconds': args.seconds,
            'parameter_writes': False,
            'flame_polled': False,
            'arbitrary_addresses': False,
            'max_reconnections': quality.MAX_RECONNECTS,
            'maximum_host_gap_ms': 300,
            'ff_semantics_known': False,
            'targets': {
                'P12': '0x400c bit-coded digital input; bit meanings unknown',
                'P84': '0x4054 GFA operating phase; enum unknown',
                'P85': '0x4055 GFA status 1; bit meanings unknown',
                'P86': '0x4056 GFA status 2; bit meanings unknown',
                'P87': '0x4057 GFA status 3; bit meanings unknown',
                'P88': '0x4058 GFA status 4; bit meanings unknown',
                'P80': '0x4050 GFA variant guard; expected 0x20',
            },
            'bank_A': ['P84', 'P12', 'P85', 'P86'],
            'bank_B': ['P84', 'P12', 'P87', 'P88'],
            'pacing_sha256': PARENT_SHA256,
            'quality_sha256': paced.PARENT_SHA256,
            'cycle_sha256': quality.CYCLE_SHA256,
            'session_sha256': quality.SESSION_SHA256,
            'p80_sha256': session.BASE_SHA256,
        })
        cap.ensure_ok()

        def abort(signum, frame):
            raise ProbeError('Interrupted by signal ' + str(signum) + '; entering cleanup.')

        previous = {sig: signal.signal(sig, abort) for sig in base.ABORT_SIGNALS}
        result = quality.run_guarded(
            base.Services(),
            lambda: base.open_port(port, serial),
            cap,
            emit,
            seconds=args.seconds,
            wire_factory=StatusWire,
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
