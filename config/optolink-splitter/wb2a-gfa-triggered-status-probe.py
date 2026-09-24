#!/usr/bin/env python3
"""Triggered WB2A GFA status probe using only A1 normal-room setpoint as stimulus.

The script is deliberately narrow. It requires the unchanged, SHA256-pinned
wb2a-gfa-status-probe.py and its dependency chain beside it.

Live sequence with --execute:
  1. require running splitter; pause active party emulator and splitter;
  2. verify P300 device 20C2;
  3. read A1 normal room setpoint 0x2306 and live modulation/state 0x55DC;
  4. require 0x55DC == 0 and original setpoint in 3..36 C;
  5. confirm the local burner branch twice as P80 == 0x20;
  6. return to P300, re-check the two preconditions, write ONLY 0x2306 = 37,
     and require an exact 37 readback;
  7. switch immediately to VS1 and run a focused startup capture:
     P84, P87, P06 fan speed and P09 modulation setpoint every round, P80 guard;
  8. on every normal/error/signal cleanup path, return to P300 and restore
     the exact previously read 0x2306 value with readback verification;
  9. close serial and restart only services that were previously running.

No coding address, GFA_WRITE, PROCESS_WRITE, actuator output, gas-valve command,
flame-safety parameter or arbitrary write is implemented. The only parameter
write address is 0x2306, with 37 as the temporary value and the exact captured
original value as the cleanup value.

Default: plan only. --self-test: offline tests. --execute: real device action.
The cleanup is best-effort against ordinary exceptions/signals; SIGKILL, power
loss, USB removal or hardware failure can still prevent restoration.
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

VERSION = '1.0.1'
PARENT_NAME = 'wb2a-gfa-status-probe.py'
PARENT_SHA256 = '912de7276ed2a26330abbfb0d7c5778862d171fa5a179ab1b73043fdee9c59bc'
SETPOINT_ADDR = 0x2306
MODULATION_ADDR = 0x55DC
TRIGGER_C = 37
MIN_ORIGINAL_C = 3
MAX_ORIGINAL_C = 36
DEFAULT_SECONDS = 60
MAX_SECONDS = 120
P06 = 0x4006
P09 = 0x4009
P80 = 0x4050
P84 = 0x4054
P87 = 0x4057
FOCUS_ORDER = (P84, P87, P06, P09)
FOCUS_LABELS = {P06: 'P06', P09: 'P09', P80: 'P80', P84: 'P84', P87: 'P87'}
FOCUS_FRAMES = {a: bytes((0x6B, a >> 8, a & 0xFF, 0x01)) for a in (*FOCUS_ORDER, P80)}


def crc(frame_without_crc: bytes) -> int:
    if len(frame_without_crc) < 2 or frame_without_crc[0] != 0x41:
        raise ValueError('P300 frame must begin with 0x41.')
    return sum(frame_without_crc[1:]) & 0xFF


def p300_read_frame(address: int) -> bytes:
    if address not in (SETPOINT_ADDR, MODULATION_ADDR):
        raise ValueError('Only fixed precondition/readback addresses are enabled.')
    body = bytes((0x41, 0x05, 0x00, 0x01, address >> 8, address & 0xFF, 0x01))
    return body + bytes((crc(body),))


def p300_write_setpoint_frame(value: int) -> bytes:
    if isinstance(value, bool) or not isinstance(value, int) or not MIN_ORIGINAL_C <= value <= TRIGGER_C:
        raise ValueError('Setpoint byte outside the bounded 3..37 C range.')
    body = bytes((0x41, 0x06, 0x00, 0x02, 0x23, 0x06, 0x01, value))
    return body + bytes((crc(body),))


def decode_p300_response(frame: bytes, *, function: int, address: int) -> bytes:
    if len(frame) < 8 or frame[0] != 0x41 or len(frame) != frame[1] + 3:
        raise ValueError('P300 response boundary/length mismatch: ' + frame.hex(' '))
    if sum(frame[1:-1]) & 0xFF != frame[-1]:
        raise ValueError('P300 response checksum mismatch: ' + frame.hex(' '))
    if frame[2] != 0x01 or (frame[3] & 0x1F) != function:
        raise ValueError('P300 response is not the requested successful function.')
    if int.from_bytes(frame[4:6], 'big') != address:
        raise ValueError('P300 response address mismatch.')
    count = frame[6]
    data = frame[7:-1]
    if function == 0x01:
        if len(data) != count:
            raise ValueError('P300 READ response data-length mismatch.')
        return data
    if function == 0x02:
        # WB2A Virtual_WRITE success response is:
        #   41 05 01 02 addr_hi addr_lo written_length crc
        # The byte after the address is the acknowledged write length. There is
        # no echoed data byte in this response.
        if data:
            raise ValueError('P300 WRITE response has unexpected trailing data.')
        if count != 1:
            raise ValueError(f'P300 WRITE acknowledged {count} byte(s), expected 1.')
        return b''
    raise ValueError(f'Unsupported P300 response function 0x{function:02x}.')


def duration_arg(text: str) -> int:
    try:
        value = int(text, 10)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError('Seconds must be an integer.') from exc
    if not 30 <= value <= MAX_SECONDS:
        raise argparse.ArgumentTypeError('Triggered status probe is limited to 30..120 seconds.')
    return value


def load_parent():
    path = Path(__file__).resolve().with_name(PARENT_NAME)
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != PARENT_SHA256:
        raise RuntimeError(
            f'Status-helper hash mismatch ({digest}); no service/serial operation.'
        )
    module = types.ModuleType('wb2a_gfa_status_pinned')
    module.__file__ = str(path)
    exec(compile(data, str(path), 'exec'), module.__dict__)
    return module


def make_runtime(parent):
    status = parent
    paced, quality, session, base = status.paced, status.quality, status.session, status.base
    ProbeError = status.ProbeError
    SuspectFF = status.SuspectFF

    READ_SETPOINT = p300_read_frame(SETPOINT_ADDR)
    READ_MODULATION = p300_read_frame(MODULATION_ADDR)
    WRITE_TRIGGER = p300_write_setpoint_frame(TRIGGER_C)

    class TriggerWire(status.StatusWire):
        def __init__(self, port, log, clock=time.monotonic, *, seconds=DEFAULT_SECONDS,
                     emit=None, sleeper=time.sleep):
            super().__init__(port, log, clock, seconds=seconds, emit=emit, sleeper=sleeper)
            self.original_setpoint = None
            self.trigger_mono = None
            self.trigger_wall = None

        def _is_allowed_extra(self, data: bytes) -> bool:
            if data in (READ_SETPOINT, READ_MODULATION, WRITE_TRIGGER):
                return True
            if self.original_setpoint is not None:
                return data == p300_write_setpoint_frame(self.original_setpoint)
            return False

        def send(self, data: bytes):
            if self._is_allowed_extra(data):
                # P300 operations terminate any assumption of an active VS1 session.
                self.active = False
                self.deadline = None
                self.log('TX ' + data.hex(' '))
                self.touched = True
                if self.port.write(data) != len(data):
                    raise ProbeError('Partial P300 parameter write/read request; no retransmission.')
                return
            if data in FOCUS_FRAMES.values():
                self._check_session()
                self.log('TX ' + data.hex(' '))
                self._check_session()
                self.touched = True
                if self.port.write(data) != len(data):
                    raise ProbeError('Partial focused GFA read; no retransmission.')
                return
            return super().send(data)

        def _p300_exchange(self, request: bytes, *, function: int, address: int) -> bytes:
            self.active = False
            self.deadline = None
            self.discard_stale()
            self.send(request)
            if self.exact(1, timeout=2.0) != b'\x06':
                raise ProbeError('P300 request was not acknowledged.')
            header = self.exact(2, timeout=2.0)
            if header[0] != 0x41 or not 5 <= header[1] <= 64:
                raise ProbeError('Invalid P300 response header: ' + header.hex(' '))
            frame = header + self.exact(header[1] + 1, timeout=2.0)
            try:
                data = decode_p300_response(frame, function=function, address=address)
            except ValueError as exc:
                raise ProbeError(str(exc)) from exc
            self.send(b'\x06')
            return data

        def p300_read_byte(self, address: int) -> int:
            request = p300_read_frame(address)
            data = self._p300_exchange(request, function=0x01, address=address)
            if len(data) != 1:
                raise ProbeError(f'P300 0x{address:04x} did not return exactly one byte.')
            value = data[0]
            self.log(f'P300_READ address=0x{address:04x} raw=0x{value:02x} dec={value}')
            return value

        def p300_write_setpoint(self, value: int) -> int:
            if value != TRIGGER_C and value != self.original_setpoint:
                raise ProbeError('Only temporary 37 C and the captured original setpoint are writable.')
            request = p300_write_setpoint_frame(value)
            data = self._p300_exchange(request, function=0x02, address=SETPOINT_ADDR)
            # WB2A confirms one written byte but does not echo the value in the
            # Virtual_WRITE response. Exact value verification is the following readback.
            if data:
                raise ProbeError('Unexpected Virtual_WRITE response payload.')
            readback = self.p300_read_byte(SETPOINT_ADDR)
            if readback != value:
                raise ProbeError(
                    f'Setpoint readback mismatch: wrote {value}, read {readback}.'
                )
            self.log(f'SETPOINT_WRITE_VERIFIED address=0x2306 value={value}')
            return readback

        def encode_sample(self, row):
            record = {
                'parameter': FOCUS_LABELS[row['address']],
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
            if row['address'] == P87:
                record['set_bits'] = status.set_bits(row['raw'])
            return record

        def read_session(self, address: int, round_number: int):
            if address not in FOCUS_FRAMES:
                raise ProbeError('Focused capture enables only P84/P87/P06/P09/P80.')
            self.pending = {
                'address': f'0x{address:04x}',
                'request_hex': FOCUS_FRAMES[address].hex(' '),
                'attempt': round_number,
                'stage': 'pacing_before_tx',
            }
            previous_reply = self.last_reply
            try:
                self._check_session()
                target = previous_reply + status.paced.REPLY_GAP_SECONDS
                while self.clock() < target:
                    self.sleeper(min(target - self.clock(), 0.020))
                    self._check_session()
                self._check_session()
                self.pending['stage'] = 'before_tx'
                start = self.clock()
                self.send(FOCUS_FRAMES[address])
                self.pending['stage'] = 'awaiting_reply'
                value = self.exact(1, timeout=1.0)[0]
                row = {
                    'round': round_number, 'address': address, 'raw': value,
                    'tx_mono': start, 'rx_mono': self.last_reply, 'rx_time': self.last_wall,
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
                extra = ''
                if address == P06:
                    extra = f' fan_actual_rpm={value * 30}'
                elif address == P09:
                    extra = f' modulation_setpoint_pct={value * 0.3922:.4f}'
                elif address == P87:
                    extra = f' set_bits={status.set_bits(value)}'
                self.log(
                    f'SAMPLE attempt={round_number} {FOCUS_LABELS[address]} '
                    f'address=0x{address:04x} raw={value:02x} quality={row["quality"]}{extra} '
                    f'rx_time={row["rx_time"]} reply_latency_ms={row["latency_ms"]:.1f}'
                )
                return row
            except BaseException:
                self.active = False
                raise

        def observe(self):
            self._check_session()
            self.started = self.clock()
            stop_at = self.started + self.seconds
            self.operation_deadline = self.deadline = stop_at + status.quality.ROUND_GRACE_SECONDS
            self.emit({
                'kind': 'observation_start', 'version': VERSION,
                'seconds_requested': self.seconds, 'simultaneous': False,
                'flame_polled': False, 'fixed_sampling_rate': False,
                'max_reconnections': status.quality.MAX_RECONNECTS,
                'ff_semantics_known': False,
                'focus': ['P84', 'P87', 'P06', 'P09'],
            })
            self.log(
                f'OBSERVATION_START seconds={self.seconds}; focus=P84/P87/P06/P09; '
                'no flame semantic assignment.'
            )
            previous = None
            try:
                try:
                    self.read_session(P80, 0)
                except BaseException as exc:
                    self.reject(exc)
                    raise
                self.partial = []
                while self.clock() < stop_at:
                    if self.attempts >= status.quality.MAX_ROUNDS:
                        raise ProbeError('Round safety cap reached before window completed.')
                    self.attempts += 1
                    self.partial, self.pending = [], None
                    try:
                        rows = [self.read_session(a, self.attempts) for a in FOCUS_ORDER]
                        guard = self.read_session(P80, self.attempts)
                    except SuspectFF as exc:
                        self.reject(exc)
                        self.reconnect(stop_at)
                        previous = None
                        continue
                    except BaseException as exc:
                        self.reject(exc)
                        raise

                    values = {row['address']: row['raw'] for row in rows}
                    span_ms = (rows[-1]['rx_mono'] - rows[0]['rx_mono']) * 1000
                    changes = []
                    if previous is not None:
                        for row in rows:
                            old = previous[row['address']]
                            if old['raw'] != row['raw']:
                                change = {
                                    'parameter': FOCUS_LABELS[row['address']],
                                    'old_raw': old['raw'], 'old_raw_hex': f'{old["raw"]:02x}',
                                    'new_raw': row['raw'], 'new_raw_hex': f'{row["raw"]:02x}',
                                    'previous_rx_time': old['rx_time'], 'rx_time': row['rx_time'],
                                }
                                if row['address'] == P87:
                                    change['changed_bits'] = status.changed_bits(old['raw'], row['raw'])
                                    change['new_set_bits'] = status.set_bits(row['raw'])
                                changes.append(change)
                    for row in rows:
                        row['quality'] = 'accepted_by_policy_not_independently_verified'
                    number = self.rounds + 1
                    self.emit({
                        'kind': 'round', 'round': number, 'attempt': self.attempts,
                        'segment': self.segment, 'guard_passed': True,
                        'quality': 'no_ff_and_identity_match', 'physical_validity_proven': False,
                        'sample_span_ms': round(span_ms, 3),
                        'samples': [self.encode_sample(row) for row in rows],
                        'guard': self.encode_sample(guard),
                        'decoded': {
                            'phase_raw': values[P84],
                            'p87_raw': values[P87],
                            'p87_set_bits': status.set_bits(values[P87]),
                            'fan_actual_rpm': values[P06] * 30,
                            'modulation_setpoint_pct': round(values[P09] * 0.3922, 4),
                        },
                        'changes': changes,
                    })
                    self.rounds = number
                    self.last_confirmed_elapsed = self.clock() - self.started
                    self.nonzero_rounds += int(any(values.values()))
                    self.phase_changes += sum(c['parameter'] == 'P84' for c in changes)
                    self.log(
                        f'ROUND {number} attempt={self.attempts} segment={self.segment} '
                        f't={rows[0]["rx_mono"] - self.started:.3f}s '
                        f'P84=0x{values[P84]:02x} P87=0x{values[P87]:02x} '
                        f'rpm={values[P06] * 30} mod={values[P09] * 0.3922:.4f}% '
                        f'span_ms={span_ms:.1f} guard=20 quality=no_ff_and_identity_match'
                    )
                    previous = {row['address']: row for row in rows}
                    self.partial = []

                if not self.rounds or self.clock() - self.started > self.seconds + status.quality.ROUND_GRACE_SECONDS:
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

    def run_triggered(services, opener, log, emit, *, seconds=DEFAULT_SECONDS, wire_factory=None) -> int:
        if not 30 <= seconds <= MAX_SECONDS:
            raise ProbeError('Duration outside 30..120; no service operation performed.')
        state = services.state(base.SPLITTER)
        if (state.get('LoadState'), state.get('ActiveState'), state.get('SubState')) != ('loaded', 'active', 'running'):
            raise ProbeError('Require splitter loaded and running before this test.')
        party = services.state(base.PARTY)
        if party.get('ActiveState') in ('activating', 'deactivating', 'reloading'):
            raise ProbeError('Party emulator is in transition; no service change performed.')
        party_active = party.get('LoadState') == 'loaded' and party.get('ActiveState') == 'active'
        to_stop = ([base.PARTY] if party_active else []) + [base.SPLITTER]

        changed, failures, identities, restarted = [], [], [], set()
        wire = connection = None
        original = None
        setpoint_changed = False
        setpoint_restored = False
        p300_restored = False
        trigger_verified = False
        pre_mod = None
        post_restore_mod = None

        try:
            for unit in to_stop:
                changed.append(unit)
                log('Stopping ' + unit)
                services.stop(unit)
            connection = opener()
            factory = wire_factory or (lambda c, l, **kw: TriggerWire(c, l, **kw))
            wire = factory(connection, log, seconds=seconds, emit=emit)

            if wire.p300_ident() != b'\x20\xc2':
                raise ProbeError('Baseline is not 20C2; no setpoint write sent.')
            original = wire.p300_read_byte(SETPOINT_ADDR)
            if not MIN_ORIGINAL_C <= original <= MAX_ORIGINAL_C:
                raise ProbeError(
                    f'Original A1 normal setpoint is {original}; require 3..36 C so 37 creates an edge.'
                )
            wire.original_setpoint = original
            pre_mod = wire.p300_read_byte(MODULATION_ADDR)
            if pre_mod != 0:
                raise ProbeError(
                    f'Brenner precondition failed: 0x55DC is {pre_mod}, expected 0 before trigger.'
                )

            # Confirm the already hardware-established local variant before changing demand.
            for _ in range(2):
                value = wire.p80()
                identities.append(value)
                if value != 0x20:
                    raise ProbeError('Expected GFA P80=0x20 before trigger.')

            # Return to P300 and re-check both mutable preconditions immediately before the write.
            if wire.p300_ident() != b'\x20\xc2':
                raise ProbeError('P300 re-entry before trigger is not 20C2.')
            original2 = wire.p300_read_byte(SETPOINT_ADDR)
            pre_mod2 = wire.p300_read_byte(MODULATION_ADDR)
            if original2 != original:
                raise ProbeError(
                    f'A1 normal setpoint changed during preflight ({original}->{original2}); no write sent.'
                )
            if pre_mod2 != 0:
                raise ProbeError(
                    f'Brenner became active during preflight: 0x55DC={pre_mod2}; no trigger write sent.'
                )

            # Mark cleanup as required BEFORE transmitting: a write may have reached
            # the controller even if its response/readback subsequently fails.
            setpoint_changed = True
            wire.p300_write_setpoint(TRIGGER_C)
            trigger_verified = True
            wire.trigger_mono = wire.clock()
            wire.trigger_wall = dt.datetime.now().astimezone().isoformat(timespec='milliseconds')
            log(
                f'TRIGGER_VERIFIED original={original} temporary={TRIGGER_C} '
                f'time={wire.trigger_wall}; switching immediately to VS1.'
            )
            emit({
                'kind': 'trigger',
                'address': '0x2306',
                'original_c': original,
                'temporary_c': TRIGGER_C,
                'readback_c': TRIGGER_C,
                'pre_modulation_raw': pre_mod2,
                'trigger_time': wire.trigger_wall,
                'parameter_write': True,
                'write_scope': 'A1 normal room setpoint only',
            })

            # First post-trigger independent P80 both changes interface and timestamps the gap.
            value = wire.p80()
            identities.append(value)
            if value != 0x20:
                raise ProbeError('Post-trigger VS1 entry did not return P80=0x20.')
            log(f'TRIGGER_TO_VS1_SECONDS={wire.clock() - wire.trigger_mono:.3f}')

            wire.observe()

            value = wire.p80()
            identities.append(value)
            if value != 0x20:
                raise ProbeError('Closing P80 differs; capture not confirmed.')
        except BaseException as exc:
            failures.append(str(exc) or type(exc).__name__)
            log('TRIGGERED OBSERVATION FAILED: ' + failures[-1])
        finally:
            previous = {sig: signal.signal(sig, signal.SIG_IGN) for sig in base.ABORT_SIGNALS}
            try:
                if wire is not None and wire.touched:
                    # Restoring the user setpoint has priority over declaring protocol recovery.
                    for attempt in range(1, 4):
                        try:
                            log(f'Cleanup P300/setpoint restoration attempt {attempt}/3.')
                            if wire.p300_ident() != b'\x20\xc2':
                                raise ProbeError('Cleanup P300 identity is not 20C2.')
                            p300_restored = True
                            if setpoint_changed:
                                if original is None:
                                    raise ProbeError('Original setpoint unavailable for cleanup.')
                                wire.original_setpoint = original
                                wire.p300_write_setpoint(original)
                                setpoint_restored = True
                                try:
                                    post_restore_mod = wire.p300_read_byte(MODULATION_ADDR)
                                except Exception as exc:
                                    log('POST_RESTORE_MODULATION_READ_FAILED: ' + str(exc))
                            else:
                                setpoint_restored = True
                            break
                        except Exception as exc:
                            log('Cleanup restoration attempt failed: ' + str(exc))
                    if not p300_restored:
                        failures.append('P300 restoration could not be verified.')
                    if setpoint_changed and not setpoint_restored:
                        failures.append(
                            f'CRITICAL: A1 normal setpoint restoration to {original} C could not be verified.'
                        )
                elif not setpoint_changed:
                    setpoint_restored = True

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

        observation_complete = bool(wire is not None and wire.observation_complete)
        identity_ok = len(identities) == 4 and identities == [0x20] * 4
        splitter_ok = base.SPLITTER in restarted
        passed = (
            trigger_verified and observation_complete and identity_ok and p300_restored
            and setpoint_restored and splitter_ok and not failures
        )

        log('ORIGINAL_DAY_SETPOINT=' + (str(original) if original is not None else 'UNKNOWN'))
        log('TRIGGER_SETPOINT=37')
        log('TRIGGER_VERIFIED=' + ('yes' if trigger_verified else 'no'))
        log('SETPOINT_RESTORED=' + ('yes' if setpoint_restored else 'NOT_VERIFIED'))
        log('P80_CONFIRMED=' + ('0x20 GFA' if identity_ok else 'NOT_CONFIRMED'))
        log('P300_RESTORED=' + ('yes' if p300_restored else 'NOT_VERIFIED'))
        log('SPLITTER_RESTARTED=' + ('yes' if splitter_ok else 'NOT_VERIFIED'))
        if post_restore_mod is not None:
            log(f'POST_RESTORE_MODULATION_RAW={post_restore_mod}')
        log('RESULT=' + ('PASS' if passed else 'FAIL'))
        log('PASS means trigger/readback, bounded status acquisition and exact setpoint restore all verified;')
        log('it does not assign P84/P12/P85-P88 semantics or guarantee immediate burner shutdown.')
        for failure in failures:
            log('ERROR: ' + failure)

        try:
            emit({
                'kind': 'triggered_summary',
                'result': 'PASS' if passed else 'FAIL',
                'original_c': original,
                'temporary_c': TRIGGER_C,
                'trigger_verified': trigger_verified,
                'setpoint_restored': setpoint_restored,
                'pre_modulation_raw': pre_mod,
                'post_restore_modulation_raw': post_restore_mod,
                'p80_values': identities,
                'p300_restored': p300_restored,
                'splitter_restarted': splitter_ok,
                'observation_complete': observation_complete,
                'errors': failures,
            })
        except Exception as exc:
            log('SUMMARY_EMIT_FAILED: ' + str(exc))
            passed = False
        return 0 if passed else 1

    return status, base, TriggerWire, run_triggered


def self_test() -> int:
    import unittest

    class ProtocolTests(unittest.TestCase):
        def test_exact_fixed_read_frames(self):
            self.assertEqual(p300_read_frame(SETPOINT_ADDR).hex(), '4105000123060130')
            self.assertEqual(p300_read_frame(MODULATION_ADDR).hex(), '4105000155dc0138')

        def test_exact_trigger_write(self):
            self.assertEqual(p300_write_setpoint_frame(37).hex(), '410600022306012557')

        def test_restore_write_varies_only_data_crc(self):
            self.assertEqual(p300_write_setpoint_frame(20).hex(), '410600022306011446')

        def test_write_range_bounded(self):
            for value in (2, 38, 255, -1):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    p300_write_setpoint_frame(value)
            self.assertEqual(p300_write_setpoint_frame(3)[7], 3)
            self.assertEqual(p300_write_setpoint_frame(37)[7], 37)

        def test_read_unknown_blocked(self):
            with self.assertRaises(ValueError):
                p300_read_frame(0x1234)

        def response(self, function, address, data=b''):
            body = bytes((0x41, 5 + len(data), 0x01, function,
                          address >> 8, address & 0xff, len(data))) + data
            return body + bytes((crc(body),))

        def test_decode_read_response(self):
            f = self.response(1, SETPOINT_ADDR, b'\x14')
            self.assertEqual(decode_p300_response(f, function=1, address=SETPOINT_ADDR), b'\x14')

        def test_decode_write_count_response_from_live_wb2a(self):
            f = bytes.fromhex('41 05 01 02 23 06 01 32')
            self.assertEqual(decode_p300_response(f, function=2, address=SETPOINT_ADDR), b'')

        def test_zero_written_length_rejected(self):
            body = bytes.fromhex('41 05 01 02 23 06 00')
            f = body + bytes((crc(body),))
            with self.assertRaises(ValueError):
                decode_p300_response(f, function=2, address=SETPOINT_ADDR)

        def test_bad_checksum_rejected(self):
            f = bytearray(self.response(1, SETPOINT_ADDR, b'\x14'))
            f[-1] ^= 1
            with self.assertRaises(ValueError):
                decode_p300_response(bytes(f), function=1, address=SETPOINT_ADDR)

        def test_wrong_address_rejected(self):
            f = self.response(1, SETPOINT_ADDR, b'\x14')
            with self.assertRaises(ValueError):
                decode_p300_response(f, function=1, address=MODULATION_ADDR)

        def test_wrong_function_rejected(self):
            f = self.response(1, SETPOINT_ADDR, b'\x14')
            with self.assertRaises(ValueError):
                decode_p300_response(f, function=2, address=SETPOINT_ADDR)

        def test_wrong_message_type_rejected(self):
            f = bytearray(self.response(1, SETPOINT_ADDR, b'\x14'))
            f[2] = 3
            f[-1] = sum(f[1:-1]) & 0xff
            with self.assertRaises(ValueError):
                decode_p300_response(bytes(f), function=1, address=SETPOINT_ADDR)

        def test_length_mismatch_rejected(self):
            f = self.response(1, SETPOINT_ADDR, b'\x14')[:-1]
            with self.assertRaises(ValueError):
                decode_p300_response(f, function=1, address=SETPOINT_ADDR)

        def test_duration_bounds(self):
            self.assertEqual(duration_arg('60'), 60)
            self.assertEqual(duration_arg('120'), 120)
            for value in ('29', '121', '300', 'nan'):
                with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                    duration_arg(value)

        def test_crc_excludes_leading_stx(self):
            body = bytes.fromhex('41 06 00 02 23 06 01 25')
            self.assertEqual(crc(body), 0x57)

    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(ProtocolTests)
    )
    if not result.wasSuccessful():
        return 1

    # When the pinned chain is present (normal LXC/repo execution), also re-run
    # all inherited status/transport tests. A local standalone download may not
    # have the parent chain; live --execute always requires it before any action.
    try:
        parent = load_parent()
    except Exception as exc:
        print('PARENT_CHAIN_TESTS=SKIPPED: ' + str(exc))
        print('LOCAL_PROTOCOL_TESTS=15/15')
        return 0
    parent_rc = parent.self_test()
    if parent_rc:
        return 1

    status, base, TriggerWire, run_triggered = make_runtime(parent)
    READ_SETPOINT = p300_read_frame(SETPOINT_ADDR)
    READ_MODULATION = p300_read_frame(MODULATION_ADDR)

    def response(function, address, data=b''):
        body = bytes((0x41, 5 + len(data), 0x01, function,
                      address >> 8, address & 0xff, len(data))) + data
        return body + bytes((crc(body),))

    def write_response(address, written_length=1):
        body = bytes((0x41, 0x05, 0x01, 0x02,
                      address >> 8, address & 0xff, written_length))
        return body + bytes((crc(body),))

    class Port:
        def __init__(self, *, setpoints=None, modulations=None,
                     fail_trigger_response=False, interrupt_bare=None,
                     restore_sticks=True):
            self.rx, self.tx = bytearray(), []
            self.t, self.bare = 0.0, 0
            self.enq = self.closed = False
            self.setpoint = 20
            self.setpoint_reads = list(setpoints or [])
            self.modulation_reads = list(modulations or [])
            self.fail_trigger_response = fail_trigger_response
            self.interrupt_bare = interrupt_bare
            self.restore_sticks = restore_sticks
            self.runtime = {
                P84: 0x06, P87: 0x62, P06: 137, P09: 123, P80: 0x20,
            }

        def clock(self):
            return self.t

        def sleep(self, seconds):
            self.t += seconds

        @property
        def in_waiting(self):
            return len(self.rx)

        def _next_setpoint(self):
            if self.setpoint_reads:
                return self.setpoint_reads.pop(0)
            return self.setpoint

        def _next_modulation(self):
            if self.modulation_reads:
                return self.modulation_reads.pop(0)
            return 0

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
                self.rx.extend(b'\x20')
            elif data == READ_SETPOINT:
                v = self._next_setpoint()
                self.rx.extend(b'\x06' + response(1, SETPOINT_ADDR, bytes((v,))))
            elif data == READ_MODULATION:
                v = self._next_modulation()
                self.rx.extend(b'\x06' + response(1, MODULATION_ADDR, bytes((v,))))
            elif (len(data) == 9 and data[:7] == bytes.fromhex('41 06 00 02 23 06 01')):
                value = data[7]
                expected = p300_write_setpoint_frame(value)
                if data != expected:
                    raise AssertionError('Bad setpoint write frame')
                # The trigger may physically take effect even when its response is lost.
                if value == TRIGGER_C or self.restore_sticks:
                    self.setpoint = value
                if value == TRIGGER_C and self.fail_trigger_response:
                    pass
                else:
                    self.rx.extend(b'\x06' + write_response(SETPOINT_ADDR, 1))
            elif data in FOCUS_FRAMES.values():
                self.bare += 1
                if self.interrupt_bare is not None and self.bare == self.interrupt_bare:
                    raise KeyboardInterrupt()
                address = int.from_bytes(data[1:3], 'big')
                self.rx.extend(bytes((self.runtime[address],)))
            elif data == b'\x06':
                pass
            else:
                raise AssertionError('Unexpected TX ' + data.hex())
            return len(data)

        def read(self, count):
            self.t += 0.05
            if not self.rx and self.enq:
                self.rx.extend(b'\x05')
            out = bytes(self.rx[:count])
            del self.rx[:count]
            return out

        def close(self):
            self.closed = True

    class Services:
        def __init__(self, party=True):
            self.active = {base.SPLITTER: True, base.PARTY: party}
            self.calls = []
        def state(self, unit):
            return {'LoadState': 'loaded',
                    'ActiveState': 'active' if self.active[unit] else 'inactive',
                    'SubState': 'running' if self.active[unit] else 'dead'}
        def stop(self, unit):
            self.calls.append(('stop', unit))
            self.active[unit] = False
        def start(self, unit):
            self.calls.append(('start', unit))
            self.active[unit] = True

    class IntegrationTests(unittest.TestCase):
        def case(self, port=None, party=True):
            p = port or Port()
            services = Services(party)
            logs, records = [], []
            def wire_factory(connection, logger, **kwargs):
                return TriggerWire(connection, logger, p.clock, sleeper=p.sleep, **kwargs)
            rc = run_triggered(
                services, lambda: p, logs.append, records.append,
                seconds=30, wire_factory=wire_factory,
            )
            return rc, p, services, logs, records

        def assert_services_restored(self, case):
            self.assertTrue(case[1].closed)
            self.assertTrue(case[2].active[base.SPLITTER])
            self.assertTrue(case[2].active[base.PARTY])

        def write_values(self, p):
            values = []
            for data in p.tx:
                if len(data) == 9 and data[:7] == bytes.fromhex('41 06 00 02 23 06 01'):
                    values.append(data[7])
            return values

        def test_trigger_and_exact_restore_happy_path(self):
            case = self.case()
            self.assertEqual(case[0], 0)
            self.assertEqual(case[1].setpoint, 20)
            self.assertEqual(self.write_values(case[1]), [37, 20])
            self.assertIn('SETPOINT_RESTORED=yes', case[3])
            self.assertIn('RESULT=PASS', case[3])
            self.assert_services_restored(case)

        def test_active_burner_blocks_trigger_write(self):
            case = self.case(Port(modulations=[7]))
            self.assertEqual(case[0], 1)
            self.assertEqual(self.write_values(case[1]), [])
            self.assertEqual(case[1].setpoint, 20)
            self.assert_services_restored(case)

        def test_original_37_blocks_trigger(self):
            p = Port(setpoints=[37])
            p.setpoint = 37
            case = self.case(p)
            self.assertEqual(case[0], 1)
            self.assertEqual(self.write_values(case[1]), [])
            self.assertEqual(case[1].setpoint, 37)
            self.assert_services_restored(case)

        def test_preflight_setpoint_change_blocks_trigger(self):
            case = self.case(Port(setpoints=[20, 21]))
            self.assertEqual(case[0], 1)
            self.assertEqual(self.write_values(case[1]), [])
            self.assert_services_restored(case)

        def test_lost_trigger_response_still_restores_original(self):
            case = self.case(Port(fail_trigger_response=True))
            self.assertEqual(case[0], 1)
            self.assertEqual(case[1].setpoint, 20)
            self.assertEqual(self.write_values(case[1]), [37, 20])
            self.assertIn('SETPOINT_RESTORED=yes', case[3])
            self.assert_services_restored(case)

        def test_interrupt_during_status_capture_restores_original(self):
            case = self.case(Port(interrupt_bare=5))
            self.assertEqual(case[0], 1)
            self.assertEqual(case[1].setpoint, 20)
            self.assertIn(37, self.write_values(case[1]))
            self.assertEqual(self.write_values(case[1])[-1], 20)
            self.assert_services_restored(case)

        def test_restore_failure_is_hard_fail_and_reported(self):
            case = self.case(Port(restore_sticks=False))
            self.assertEqual(case[0], 1)
            self.assertEqual(case[1].setpoint, 37)
            self.assertIn('SETPOINT_RESTORED=NOT_VERIFIED', case[3])
            self.assertTrue(any('CRITICAL:' in x for x in case[3]))
            self.assert_services_restored(case)

        def test_only_2306_is_written(self):
            case = self.case()
            self.assertEqual(case[0], 0)
            for data in case[1].tx:
                if len(data) >= 4 and data[0] == 0x41 and data[3] == 0x02:
                    self.assertEqual(data[4:6], b'\x23\x06')
                    self.assertEqual(data[6], 1)
                    self.assertIn(data[7], (20, 37))

        def test_focus_capture_addresses_only(self):
            case = self.case()
            self.assertEqual(case[0], 0)
            bare = [int.from_bytes(data[1:3], 'big') for data in case[1].tx if data in FOCUS_FRAMES.values()]
            self.assertTrue(bare)
            self.assertEqual(set(bare), {P84, P87, P06, P09, P80})

        def test_inactive_party_remains_inactive(self):
            p = Port()
            services = Services(False)
            logs, records = [], []
            rc = run_triggered(
                services, lambda: p, logs.append, records.append, seconds=30,
                wire_factory=lambda c, l, **kw: TriggerWire(c, l, p.clock, sleeper=p.sleep, **kw),
            )
            self.assertEqual(rc, 0)
            self.assertFalse(services.active[base.PARTY])
            self.assertNotIn(('start', base.PARTY), services.calls)

    integration = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(IntegrationTests)
    )
    if not integration.wasSuccessful():
        return 1
    print('LOCAL_PROTOCOL_TESTS=15/15; PARENT_STATUS_TESTS=PASS; TRIGGER_INTEGRATION_TESTS=10/10')
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
            f'WB2A triggered GFA status probe {VERSION}: plan only; no device/service access.\n'
            'Precondition: P300 20C2, 0x55DC=0, A1 normal setpoint 0x2306 in 3..36 C.\n'
            'Stimulus: write only 0x2306=37 and verify readback; then immediate VS1 status capture.\n'
            'Capture: P84/P87/P06/P09 every round; P80 guard every round.\n'
            'Cleanup: restore exact captured 0x2306 value with readback before service restart.\n'
            'No coding/GFA_WRITE/PROCESS_WRITE/actuator/safety writes. --execute required.'
        )
        return 0
    if os.geteuid() != 0:
        print('ERROR: --execute requires root.', file=sys.stderr)
        return 1

    cap = lock_fd = None
    previous = {}
    result = 1
    try:
        parent = load_parent()  # recursively verifies the complete pinned transport chain
        status, base, TriggerWire, run_triggered = make_runtime(parent)
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
        cap = status.quality.Capture(Path('/root') / f'wb2a-gfa-triggered-status-{stamp}-{os.getpid()}')
        cap(f'WB2A triggered GFA status probe {VERSION}; LOG={cap.path}; JSONL={cap.json_path}')
        cap(f'Configured port: {port}; 4800 8E2; capture={args.seconds}s plus preflight/cleanup.')
        cap('ONLY PARAMETER WRITE: A1 normal setpoint 0x2306 -> 37 C -> exact captured original.')
        cap('Precondition requires 0x55DC=0 immediately before trigger; no actuator/flame-safety write.')
        cap('Focused capture: P84/P87/P06/P09 every round; P84 enum and P87 bit meanings remain unknown.')
        cap('Normal HA polling and active party emulator pause while this helper owns serial.')
        cap.ensure_ok()

        emit = status.annotated_emit(cap.emit)
        emit({
            'kind': 'metadata',
            'version': VERSION,
            'parent_sha256': PARENT_SHA256,
            'seconds': args.seconds,
            'parameter_writes': True,
            'write_addresses': ['0x2306'],
            'temporary_setpoint_c': TRIGGER_C,
            'restore_policy': 'exact captured original with readback before service restart',
            'precondition_modulation_address': '0x55dc',
            'precondition_modulation_required_raw': 0,
            'arbitrary_addresses': False,
            'gfa_write': False,
            'process_write': False,
            'actuator_test': False,
            'focus': ['P84', 'P87', 'P06', 'P09'],
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
