#!/usr/bin/env python3
"""Triggered mixed-VS1 WB2A flame/status correlation probe.

This helper reuses the already-reviewed and SHA256-pinned
wb2a-gfa-triggered-status-probe.py for:
- burner-off precondition checking;
- bounded 0x2306 -> 37 C demand stimulus;
- exact readback verification;
- cleanup with exact original 0x2306 restoration;
- service/serial ownership and recovery.

Only the observation layer changes. During one persistent VS1 session it
interleaves:
  P84 GFA operating phase (6B / 0x4054)
  0x55D3 normal Virtual_READ (F7, 9 bytes)
  P87 GFA status 3 (6B / 0x4057)
  0x55DD normal Virtual_READ (F7, 1 byte)
  P80 GFA identity guard (6B / 0x4050)

The two normal Virtual_READ channels are independently source-labelled burner
flame/status channels. Hardware-verified decoding used here:
- 0x55D3 byte 5 bit 0x20 = flame
- 0x55D3 byte 5 bit 0x40 = fire-control lockout
- 0x55D3 byte 0 = fine GFA power/control value (diagnostic only)
- 0x55DD bit 0x20 = flame signal

No GFA_WRITE, PROCESS_WRITE, actuator command, gas-valve command, coding write,
or flame-safety parameter write exists in this helper. The only parameter write
remains the inherited temporary A1 room setpoint stimulus at 0x2306, followed by
exact restoration.

Default: plan only. --self-test: offline tests. --execute: live bounded run.
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

VERSION = "1.0.0"
PARENT_NAME = "wb2a-gfa-triggered-status-probe.py"
PARENT_SHA256 = "6d5810e1595ba6e464452dcd927259e9bade8f550a92b492fd40c2a27972604b"

P80 = 0x4050
P84 = 0x4054
P87 = 0x4057
D3 = 0x55D3
DD = 0x55DD
D3_LEN = 9
DD_LEN = 1
MIN_GAP_S = 0.150

VIRTUAL = {
    D3: ("status_55d3", D3_LEN),
    DD: ("flame_55dd", DD_LEN),
}


def load_parent():
    path = Path(__file__).resolve().with_name(PARENT_NAME)
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != PARENT_SHA256:
        raise RuntimeError(
            f"Triggered parent hash mismatch ({digest}); no service/serial operation."
        )
    module = types.ModuleType("wb2a_triggered_status_pinned")
    module.__file__ = str(path)
    exec(compile(data, str(path), "exec"), module.__dict__)
    return module


def virtual_frame(address: int, length: int) -> bytes:
    expected = VIRTUAL.get(address)
    if expected is None or expected[1] != length:
        raise ValueError("Virtual_READ outside fixed correlation allowlist.")
    return bytes((0xF7, address >> 8, address & 0xFF, length))


def flame_decode_55d3(data: bytes) -> dict:
    if len(data) != D3_LEN:
        raise ValueError("0x55D3 must be exactly 9 bytes.")
    return {
        "raw_hex": data.hex(),
        "fine_control_raw": data[0],
        "flame": bool(data[5] & 0x20),
        "lockout": bool(data[5] & 0x40),
        "byte5_raw": data[5],
        "runtime_byte6": data[6],
        "runtime_byte7": data[7],
    }


def flame_decode_55dd(data: bytes) -> dict:
    if len(data) != DD_LEN:
        raise ValueError("0x55DD must be exactly 1 byte.")
    return {
        "raw_hex": data.hex(),
        "flame": bool(data[0] & 0x20),
        "raw": data[0],
    }


def make_runtime(trigger):
    status_parent = trigger.load_parent()
    status, base, ParentWire, run_triggered = trigger.make_runtime(status_parent)
    ProbeError = status.ProbeError

    virtual_frames = {
        virtual_frame(address, length)
        for address, (_name, length) in VIRTUAL.items()
    }

    class MixedFlameWire(ParentWire):
        def send(self, data: bytes):
            if data in virtual_frames:
                self._check_session()
                self.log("TX " + data.hex(" "))
                self._check_session()
                self.touched = True
                if self.port.write(data) != len(data):
                    raise ProbeError("Partial focused VS1 Virtual_READ; no retransmission.")
                return
            return super().send(data)

        def _pace(self):
            self._check_session()
            target = self.last_reply + MIN_GAP_S
            while self.clock() < target:
                self.sleeper(min(target - self.clock(), 0.020))
                self._check_session()
            self._check_session()

        def read_virtual(self, address: int, length: int, round_number: int):
            expected = VIRTUAL.get(address)
            if expected is None or expected[1] != length:
                raise ProbeError("Focused Virtual_READ outside fixed allowlist.")
            self._pace()
            start = self.clock()
            frame = virtual_frame(address, length)
            self.send(frame)
            data = self.exact(length, timeout=1.0)
            received = self.last_reply
            wall = self.last_wall
            tail = self.port.read(1)
            self._check_budget()
            if tail:
                self.log("RX unexpected trailing " + tail.hex(" "))
                raise ProbeError("Unexpected trailing data after focused Virtual_READ.")
            row = {
                "kind": "virtual",
                "round": round_number,
                "address": address,
                "data": data,
                "tx_mono": start,
                "rx_mono": received,
                "rx_time": wall,
                "latency_ms": (received - start) * 1000,
            }
            name = expected[0]
            if address == D3:
                decoded = flame_decode_55d3(data)
                self.log(
                    f"SAMPLE attempt={round_number} {name} address=0x{address:04x} "
                    f"raw={data.hex()} flame={int(decoded['flame'])} "
                    f"lockout={int(decoded['lockout'])} fine={decoded['fine_control_raw']} "
                    f"rx_time={wall} reply_latency_ms={row['latency_ms']:.1f}"
                )
            else:
                decoded = flame_decode_55dd(data)
                self.log(
                    f"SAMPLE attempt={round_number} {name} address=0x{address:04x} "
                    f"raw={data.hex()} flame={int(decoded['flame'])} "
                    f"rx_time={wall} reply_latency_ms={row['latency_ms']:.1f}"
                )
            row["decoded"] = decoded
            return row

        def encode_gfa(self, row):
            record = {
                "kind": "gfa",
                "parameter": trigger.FOCUS_LABELS[row["address"]],
                "address": f"0x{row['address']:04x}",
                "raw": row["raw"],
                "raw_hex": f"{row['raw']:02x}",
                "rx_time": row["rx_time"],
                "tx_elapsed_s": round(row["tx_mono"] - self.started, 6),
                "rx_elapsed_s": round(row["rx_mono"] - self.started, 6),
                "reply_latency_ms": round(row["latency_ms"], 3),
            }
            if row["address"] == P87:
                record["set_bits"] = status.set_bits(row["raw"])
            return record

        def encode_virtual(self, row):
            record = {
                "kind": "virtual",
                "address": f"0x{row['address']:04x}",
                "raw_hex": row["data"].hex(),
                "rx_time": row["rx_time"],
                "tx_elapsed_s": round(row["tx_mono"] - self.started, 6),
                "rx_elapsed_s": round(row["rx_mono"] - self.started, 6),
                "reply_latency_ms": round(row["latency_ms"], 3),
                "decoded": row["decoded"],
            }
            return record

        def observe(self):
            self._check_session()
            self.started = self.clock()
            stop_at = self.started + self.seconds
            self.operation_deadline = self.deadline = stop_at + status.quality.ROUND_GRACE_SECONDS
            self.emit({
                "kind": "observation_start",
                "version": VERSION,
                "seconds_requested": self.seconds,
                "mixed_vs1": True,
                "minimum_reply_gap_ms": int(MIN_GAP_S * 1000),
                "channels": ["P84", "55D3", "P87", "55DD", "P80"],
                "flame_55d3_mask": "byte5 & 0x20",
                "lockout_55d3_mask": "byte5 & 0x40",
                "flame_55dd_mask": "byte0 & 0x20",
            })
            self.log(
                f"OBSERVATION_START seconds={self.seconds}; "
                "focus=P84/55D3/P87/55DD with P80 guard; mixed F7/6B."
            )

            previous = None
            try:
                while self.clock() < stop_at:
                    if self.attempts >= status.quality.MAX_ROUNDS:
                        raise ProbeError("Round safety cap reached before window completed.")
                    self.attempts += 1
                    attempt = self.attempts
                    self.partial, self.pending = [], None

                    p84 = self.read_session(P84, attempt)
                    d3 = self.read_virtual(D3, D3_LEN, attempt)
                    p87 = self.read_session(P87, attempt)
                    dd = self.read_virtual(DD, DD_LEN, attempt)
                    guard = self.read_session(P80, attempt)

                    p84["quality"] = "accepted_by_policy_not_independently_verified"
                    p87["quality"] = "accepted_by_policy_not_independently_verified"

                    span_ms = (guard["rx_mono"] - p84["rx_mono"]) * 1000
                    decoded_d3 = d3["decoded"]
                    decoded_dd = dd["decoded"]
                    flame_agree = decoded_d3["flame"] == decoded_dd["flame"]

                    state = {
                        "p84": p84["raw"],
                        "p87": p87["raw"],
                        "flame_55d3": decoded_d3["flame"],
                        "flame_55dd": decoded_dd["flame"],
                        "lockout_55d3": decoded_d3["lockout"],
                        "fine_control_raw": decoded_d3["fine_control_raw"],
                    }
                    changes = []
                    if previous is not None:
                        for key, value in state.items():
                            if previous[key] != value:
                                changes.append({
                                    "field": key,
                                    "old": previous[key],
                                    "new": value,
                                })

                    self.rounds += 1
                    self.emit({
                        "kind": "round",
                        "round": self.rounds,
                        "attempt": attempt,
                        "guard_passed": True,
                        "p80_raw": guard["raw"],
                        "sample_span_ms": round(span_ms, 3),
                        "flame_indicators_agree": flame_agree,
                        "samples": [
                            self.encode_gfa(p84),
                            self.encode_virtual(d3),
                            self.encode_gfa(p87),
                            self.encode_virtual(dd),
                            self.encode_gfa(guard),
                        ],
                        "state": state,
                        "changes": changes,
                    })

                    self.log(
                        f"ROUND {self.rounds} attempt={attempt} "
                        f"P84=0x{p84['raw']:02x} "
                        f"flame55D3={int(decoded_d3['flame'])} "
                        f"P87=0x{p87['raw']:02x} "
                        f"flame55DD={int(decoded_dd['flame'])} "
                        f"lockout={int(decoded_d3['lockout'])} "
                        f"fine={decoded_d3['fine_control_raw']} "
                        f"agree={'yes' if flame_agree else 'no'} "
                        f"span_ms={span_ms:.1f} guard=20"
                    )
                    for change in changes:
                        self.log(
                            f"CHANGE field={change['field']} "
                            f"old={change['old']} new={change['new']}"
                        )
                    previous = state

                if self.rounds == 0:
                    raise ProbeError("No complete flame-correlation round captured.")
                self.observation_complete = True
                self.log(
                    f"OBSERVATION_COMPLETE=yes ACCEPTED_ROUNDS={self.rounds} "
                    f"REJECTED_ROUNDS={self.rejected_rounds}"
                )
            finally:
                self.elapsed = self.clock() - self.started
                self.operation_deadline = None
                self.deadline = None

    return status, base, MixedFlameWire, run_triggered


def self_test() -> int:
    import unittest

    class Tests(unittest.TestCase):
        def test_virtual_frames(self):
            self.assertEqual(virtual_frame(D3, 9).hex(), "f755d309")
            self.assertEqual(virtual_frame(DD, 1).hex(), "f755dd01")

        def test_unknown_virtual_blocked(self):
            with self.assertRaises(ValueError):
                virtual_frame(0x1234, 1)
            with self.assertRaises(ValueError):
                virtual_frame(D3, 1)

        def test_55d3_flame_decode(self):
            data = bytes.fromhex("2a0000000020000000")
            d = flame_decode_55d3(data)
            self.assertTrue(d["flame"])
            self.assertFalse(d["lockout"])
            self.assertEqual(d["fine_control_raw"], 0x2A)

        def test_55d3_lockout_decode(self):
            data = bytes.fromhex("000000000060000000")
            d = flame_decode_55d3(data)
            self.assertTrue(d["flame"])
            self.assertTrue(d["lockout"])

        def test_55dd_decode(self):
            self.assertTrue(flame_decode_55dd(b"\x20")["flame"])
            self.assertFalse(flame_decode_55dd(b"\x00")["flame"])

        def test_wrong_lengths_rejected(self):
            with self.assertRaises(ValueError):
                flame_decode_55d3(b"\x00")
            with self.assertRaises(ValueError):
                flame_decode_55dd(b"\x00\x00")

    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
    )
    if not result.wasSuccessful():
        return 1

    parent = load_parent()
    if parent.self_test() != 0:
        return 1
    make_runtime(parent)
    print("LOCAL_FLAME_TESTS=6/6; PINNED_TRIGGER_PARENT_TESTS=PASS")
    return 0


def main() -> int:
    trigger = load_parent()

    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--execute", action="store_true")
    action.add_argument("--self-test", action="store_true")
    parser.add_argument(
        "--seconds",
        type=trigger.duration_arg,
        default=trigger.DEFAULT_SECONDS,
    )
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    if not args.execute:
        print(
            f"WB2A mixed flame correlation probe {VERSION}: plan only.\n"
            "Inherited trigger: bounded 0x2306 -> 37 C with exact restore.\n"
            "Observation: P84 -> 55D3 -> P87 -> 55DD -> P80 in one VS1 session.\n"
            "No GFA/safety/actuator write. --execute required."
        )
        return 0

    if os.geteuid() != 0:
        print("ERROR: --execute requires root.", file=sys.stderr)
        return 1

    status, base, MixedFlameWire, run_triggered = make_runtime(trigger)
    cap = None
    lock_fd = None
    previous = {}
    result = 1

    try:
        import serial

        port = base.read_settings(base.SETTINGS)
        if not stat.S_ISCHR(os.stat(port).st_mode):
            raise status.ProbeError("Configured port is not a character device.")

        lock_fd = os.open(
            "/run/lock/wb2a-gfa-p80-probe.lock",
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
            0o600,
        )
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        cap = status.quality.Capture(
            Path("/root") / f"wb2a-gfa-flame-correlation-{stamp}-{os.getpid()}"
        )
        cap(
            f"WB2A mixed flame correlation probe {VERSION}; "
            f"LOG={cap.path}; JSONL={cap.json_path}"
        )
        cap(
            f"Configured port: {port}; capture={args.seconds}s; "
            "mixed persistent VS1 F7/6B."
        )
        cap(
            "Inherited ONLY PARAMETER WRITE: A1 normal setpoint 0x2306 -> 37 C "
            "-> exact captured original."
        )
        cap(
            "Observation only: P84, 55D3, P87, 55DD, P80. "
            "No GFA_WRITE/PROCESS_WRITE/actuator/flame-safety write."
        )
        cap.ensure_ok()

        emit = status.annotated_emit(cap.emit)
        emit({
            "kind": "metadata",
            "version": VERSION,
            "parent_name": PARENT_NAME,
            "parent_sha256": PARENT_SHA256,
            "seconds": args.seconds,
            "mixed_vs1": True,
            "parameter_writes": True,
            "write_addresses": ["0x2306"],
            "temporary_setpoint_c": trigger.TRIGGER_C,
            "restore_policy": "exact captured original with readback",
            "virtual_reads": ["0x55d3/9", "0x55dd/1"],
            "gfa_reads": ["P84/0x4054", "P87/0x4057", "P80/0x4050"],
            "gfa_write": False,
            "process_write": False,
            "actuator_test": False,
        })

        def abort(signum, _frame):
            raise status.ProbeError(
                "Interrupted by signal " + str(signum) + "; entering cleanup."
            )

        previous = {sig: signal.signal(sig, abort) for sig in base.ABORT_SIGNALS}
        result = run_triggered(
            base.Services(),
            lambda: base.open_port(port, serial),
            cap,
            emit,
            seconds=args.seconds,
            wire_factory=lambda c, l, **kw: MixedFlameWire(c, l, **kw),
        )
    except Exception as exc:
        if cap:
            cap("ERROR: " + str(exc))
        else:
            print("ERROR: " + str(exc), file=sys.stderr)
        result = 1
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        if cap:
            cap("LOG=" + str(cap.path))
            cap("JSONL=" + str(cap.json_path))
            try:
                cap.close()
            except Exception as exc:
                print("ERROR: " + str(exc), file=sys.stderr)
                result = 1
            if cap.error:
                result = 1
        if lock_fd is not None:
            os.close(lock_fd)

    return result


if __name__ == "__main__":
    raise SystemExit(main())
