#!/usr/bin/env python3
"""Read-only Viessmann KM-BUS Vitotrol probe.

The tool has three modes:

* sniff:    receive and log only; never transmit.
* register: answer Vitotrol discovery/register reads and PING with identity/PONG.
* read:     same as register, but may use a PING response opportunity to send a
            record 0x15/0x16/0x17 read request for selected internal blocks.

There is intentionally no implementation for record 0x14 commands, room-
temperature injection, setpoints, operating modes, generic raw TX, or any
other write-like request. Every transmitted frame passes a hard allowlist.

Protocol reference:
  config/optolink-splitter/research/vitotrol-kmbus-wire-protocol.md
  config/optolink-splitter/research/kmbus-master-read-service-2026-09-25.md
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import BinaryIO, Deque, Iterator, Optional

MAX_FRAME_LEN = 48
MIN_FRAME_LEN = 8
XOR_DATA = 0xAA


class ProtocolError(ValueError):
    pass


def parse_int(value: str) -> int:
    return int(value, 0)


def crc16_kermit(data: bytes) -> int:
    """KM-BUS CRC: reflected 0x1021, init 0, xorout 0 (Kermit/0x8408)."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0x8408
            else:
                crc >>= 1
            crc &= 0xFFFF
    return crc


def append_crc(data: bytes) -> bytes:
    crc = crc16_kermit(data)
    return data + bytes((crc & 0xFF, (crc >> 8) & 0xFF))


def fmt_hex(data: bytes) -> str:
    return " ".join(f"{byte:02X}" for byte in data)


def build_identity(slot: int, device_id: int, sn1: int, sn2: int) -> bytes:
    return append_crc(
        bytes(
            (
                0x00,
                0x11,
                0xB3,
                0x10,
                slot,
                0x01,
                0xF8,
                0x11,
                0xF9,
                device_id,
                0xFA,
                sn1,
                0xFB,
                sn2,
            )
        )
    )


def build_register0(slot: int, value: int) -> bytes:
    return append_crc(bytes((0x00, 0x11, 0xB1, 0x0A, slot, 0x01, 0x00, value)))


def build_pong(slot: int) -> bytes:
    return append_crc(bytes((0x00, 0x11, 0x80, 0x08, slot, 0x01)))


def read_record_for_slot(slot: int) -> int:
    if slot not in (1, 2, 3):
        raise ProtocolError("Vitotrol slot must be 1, 2, or 3")
    return 0x14 + slot


def response_record_for_slot(slot: int) -> int:
    if slot not in (1, 2, 3):
        raise ProtocolError("Vitotrol slot must be 1, 2, or 3")
    return 0x10 + slot


def build_master_read(slot: int, block: int) -> bytes:
    if not 0 <= block <= 0xFF:
        raise ProtocolError("block must fit in one byte")
    return append_crc(
        bytes(
            (
                0x00,
                0x11,
                0xBF,
                0x0A,
                slot,
                0x01,
                read_record_for_slot(slot),
                block ^ XOR_DATA,
            )
        )
    )


def allowed_tx(frame: bytes, slot: int) -> bool:
    """Hard safety gate for every transmitted frame."""
    if len(frame) < MIN_FRAME_LEN or len(frame) != frame[3]:
        return False
    if crc16_kermit(frame) != 0:
        return False
    if frame[0:2] != bytes((0x00, 0x11)):
        return False
    if frame[4] != slot or frame[5] != 0x01:
        return False

    command = frame[2]
    payload = frame[6:-2]

    if command == 0x80:
        return len(frame) == 8 and not payload

    if command == 0xB1:
        return len(frame) == 10 and len(payload) == 2 and payload[0] == 0x00

    if command == 0xB3:
        return (
            len(frame) == 16
            and len(payload) == 8
            and payload[0] == 0xF8
            and payload[1] == 0x11
            and payload[2] == 0xF9
            and payload[4] == 0xFA
            and payload[6] == 0xFB
        )

    if command == 0xBF:
        return (
            len(frame) == 10
            and len(payload) == 2
            and payload[0] == read_record_for_slot(slot)
        )

    return False


@dataclass(frozen=True)
class Frame:
    raw: bytes

    @property
    def dest(self) -> int:
        return self.raw[0]

    @property
    def src(self) -> int:
        return self.raw[1]

    @property
    def command(self) -> int:
        return self.raw[2]

    @property
    def length(self) -> int:
        return self.raw[3]

    @property
    def slot(self) -> int:
        return self.raw[4]

    @property
    def subclass(self) -> int:
        return self.raw[5]

    @property
    def payload(self) -> bytes:
        return self.raw[6:-2]


class StreamParser:
    def __init__(self) -> None:
        self.buffer = bytearray()
        self.discarded = 0

    def feed(self, data: bytes) -> Iterator[Frame]:
        self.buffer.extend(data)
        while True:
            if len(self.buffer) < 4:
                return

            frame_len = self.buffer[3]
            if frame_len < MIN_FRAME_LEN or frame_len > MAX_FRAME_LEN:
                del self.buffer[0]
                self.discarded += 1
                continue

            if len(self.buffer) < frame_len:
                return

            candidate = bytes(self.buffer[:frame_len])
            if crc16_kermit(candidate) == 0:
                del self.buffer[:frame_len]
                yield Frame(candidate)
                continue

            del self.buffer[0]
            self.discarded += 1


def classify_frame(frame: Frame, local_slot: int) -> dict:
    info: dict = {
        "dest": f"0x{frame.dest:02X}",
        "src": f"0x{frame.src:02X}",
        "command": f"0x{frame.command:02X}",
        "slot": frame.slot,
        "subclass": frame.subclass,
        "length": frame.length,
    }

    if (
        frame.dest == 0x11
        and frame.src == 0x00
        and frame.command == 0x33
        and frame.slot == local_slot
        and frame.subclass == 0x01
        and frame.payload[:2] == bytes((0xF8, 0x04))
    ):
        info["type"] = "vitotrol_discovery"
        return info

    if (
        frame.dest == 0x11
        and frame.src == 0x00
        and frame.command == 0x31
        and frame.slot == local_slot
        and frame.subclass == 0x01
        and frame.payload[:1] == bytes((0x00,))
    ):
        info["type"] = "vitotrol_register0_read"
        return info

    if (
        frame.dest == 0x11
        and frame.src == 0x00
        and frame.command == 0x00
        and frame.slot == local_slot
        and frame.subclass == 0x01
    ):
        info["type"] = "vitotrol_ping"
        return info

    if frame.src == 0x00 and frame.command == 0xBF and frame.payload:
        record = frame.payload[0]
        info["record"] = f"0x{record:02X}"
        if (
            frame.dest == 0x11
            and frame.slot == local_slot
            and record == response_record_for_slot(local_slot)
            and len(frame.payload) >= 2
        ):
            decoded = bytes(byte ^ XOR_DATA for byte in frame.payload[1:])
            info["type"] = "master_read_response"
            info["block"] = f"0x{decoded[0]:02X}"
            info["data"] = fmt_hex(decoded[1:])
            info["decoded_payload"] = fmt_hex(decoded)
            return info
        if 0x18 <= record <= 0x1F:
            info["type"] = "master_status_record"
            info["data_xor_aa"] = fmt_hex(
                bytes(byte ^ XOR_DATA for byte in frame.payload[1:])
            )
            return info

    info["type"] = "other"
    if frame.payload:
        info["payload"] = fmt_hex(frame.payload)
    return info


def parse_blocks(spec: str) -> list[int]:
    result: list[int] = []
    seen = set()
    for token in spec.replace(";", ",").split(","):
        token = token.strip()
        if not token:
            continue
        value = parse_int(token)
        if not 0 <= value <= 0xFF:
            raise argparse.ArgumentTypeError(f"invalid block {token}: must be 0..255")
        if value not in seen:
            result.append(value)
            seen.add(value)
    if not result:
        raise argparse.ArgumentTypeError("at least one block is required")
    return result


def event_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class EventLogger:
    def __init__(self, jsonl_path: Optional[str]) -> None:
        self.fp: Optional[BinaryIO] = None
        if jsonl_path:
            parent = os.path.dirname(os.path.abspath(jsonl_path))
            os.makedirs(parent, exist_ok=True)
            self.fp = open(jsonl_path, "ab", buffering=0)

    def emit(self, event: dict) -> None:
        row = {"ts": event_now(), **event}
        line = json.dumps(row, sort_keys=True, separators=(",", ":"))
        print(line, flush=True)
        if self.fp is not None:
            self.fp.write(line.encode("utf-8") + b"\n")

    def close(self) -> None:
        if self.fp is not None:
            self.fp.close()


def send_allowed(ser, frame: bytes, slot: int, logger: EventLogger, reason: str) -> None:
    if not allowed_tx(frame, slot):
        raise ProtocolError(f"TX safety gate rejected frame: {fmt_hex(frame)}")
    ser.write(frame)
    ser.flush()
    logger.emit({"direction": "tx", "reason": reason, "raw": fmt_hex(frame)})


def should_ignore_echo(
    frame: bytes, last_tx: Optional[bytes], last_tx_at: float, window_s: float
) -> bool:
    return (
        last_tx is not None
        and frame == last_tx
        and (time.monotonic() - last_tx_at) <= window_s
    )


def run(args: argparse.Namespace) -> int:
    try:
        import serial  # type: ignore
    except ImportError:
        print(
            "pyserial is required for live operation. Install Debian package "
            "python3-serial. --self-test does not require it.",
            file=sys.stderr,
        )
        return 2

    blocks: Deque[int] = deque(args.blocks)
    completed: list[int] = []
    inflight: Optional[int] = None
    inflight_at = 0.0
    ping_count = 0
    last_tx: Optional[bytes] = None
    last_tx_at = 0.0
    parser = StreamParser()
    logger = EventLogger(args.jsonl)

    logger.emit(
        {
            "event": "start",
            "mode": args.mode,
            "port": args.port,
            "slot": args.slot,
            "device_id": f"0x{args.device_id:02X}",
            "register0": f"0x{args.register0:02X}",
            "blocks": [f"0x{x:02X}" for x in args.blocks],
            "note": "no 0x14/room-temp/generic-write TX path exists in this tool",
        }
    )

    try:
        ser = serial.Serial(
            port=args.port,
            baudrate=1200,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_EVEN,
            stopbits=serial.STOPBITS_ONE,
            timeout=args.serial_timeout,
            write_timeout=args.write_timeout,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
            exclusive=True,
        )
    except Exception as exc:
        logger.emit({"event": "serial_open_failed", "error": repr(exc)})
        logger.close()
        return 2

    deadline = None if args.duration <= 0 else time.monotonic() + args.duration

    try:
        while deadline is None or time.monotonic() < deadline:
            chunk = ser.read(args.read_chunk)
            if not chunk:
                if (
                    inflight is not None
                    and (time.monotonic() - inflight_at) > args.query_timeout
                ):
                    logger.emit(
                        {
                            "event": "read_timeout",
                            "block": f"0x{inflight:02X}",
                            "timeout_s": args.query_timeout,
                        }
                    )
                    inflight = None
                continue

            for frame in parser.feed(chunk):
                if should_ignore_echo(
                    frame.raw,
                    last_tx,
                    last_tx_at,
                    args.echo_window_ms / 1000.0,
                ):
                    logger.emit(
                        {
                            "direction": "rx",
                            "type": "tx_echo",
                            "raw": fmt_hex(frame.raw),
                        }
                    )
                    continue

                info = classify_frame(frame, args.slot)
                logger.emit(
                    {"direction": "rx", "raw": fmt_hex(frame.raw), **info}
                )

                if info.get("type") == "master_read_response":
                    block = int(info["block"], 0)
                    if inflight is not None:
                        if (block & 0xF8) == (inflight & 0xF8):
                            completed.append(inflight)
                            inflight = None
                        else:
                            logger.emit(
                                {
                                    "event": "response_block_mismatch",
                                    "expected": f"0x{inflight:02X}",
                                    "received": f"0x{block:02X}",
                                }
                            )
                    continue

                if args.mode == "sniff":
                    continue

                response: Optional[bytes] = None
                reason = ""

                if info.get("type") == "vitotrol_discovery":
                    response = build_identity(
                        args.slot, args.device_id, args.sn1, args.sn2
                    )
                    reason = "identity"
                elif info.get("type") == "vitotrol_register0_read":
                    response = build_register0(args.slot, args.register0)
                    reason = "register0"
                elif info.get("type") == "vitotrol_ping":
                    ping_count += 1
                    if (
                        args.mode == "read"
                        and inflight is None
                        and blocks
                        and ping_count % args.query_every_pings == 0
                    ):
                        inflight = blocks.popleft()
                        inflight_at = time.monotonic()
                        response = build_master_read(args.slot, inflight)
                        reason = f"read_block_0x{inflight:02X}"
                    else:
                        response = build_pong(args.slot)
                        reason = "pong"

                if response is not None:
                    send_allowed(ser, response, args.slot, logger, reason)
                    last_tx = response
                    last_tx_at = time.monotonic()

                if (
                    args.exit_after_reads
                    and args.mode == "read"
                    and not blocks
                    and inflight is None
                ):
                    logger.emit(
                        {
                            "event": "read_plan_complete",
                            "completed": [f"0x{x:02X}" for x in completed],
                        }
                    )
                    return 0

    except KeyboardInterrupt:
        logger.emit({"event": "interrupted"})
    except Exception as exc:
        logger.emit({"event": "runtime_error", "error": repr(exc)})
        return 1
    finally:
        try:
            ser.close()
        finally:
            logger.close()

    return 0


def self_test() -> int:
    assert fmt_hex(build_pong(1)) == "00 11 80 08 01 01 F9 5C"
    assert (
        fmt_hex(build_identity(1, 0x34, 0x00, 0x05))
        == "00 11 B3 10 01 01 F8 11 F9 34 FA 00 FB 05 06 64"
    )
    assert (
        fmt_hex(build_master_read(1, 0x00))
        == "00 11 BF 0A 01 01 15 AA 51 3E"
    )
    assert (
        fmt_hex(build_master_read(1, 0x08))
        == "00 11 BF 0A 01 01 15 A2 19 B2"
    )
    assert allowed_tx(build_pong(1), 1)
    assert allowed_tx(build_identity(1, 0x34, 0, 5), 1)
    assert allowed_tx(build_register0(1, 0x12), 1)
    assert allowed_tx(build_master_read(1, 0x00), 1)

    write_like = append_crc(
        bytes((0x00, 0x11, 0xBF, 0x0A, 0x01, 0x01, 0x14, 0xAA))
    )
    room_temp = append_crc(
        bytes(
            (
                0x00,
                0x11,
                0xBF,
                0x0C,
                0x01,
                0x01,
                0x20,
                0x62,
                0xAA,
                0xAA,
            )
        )
    )
    assert not allowed_tx(write_like, 1)
    assert not allowed_tx(room_temp, 1)

    discovery = append_crc(
        bytes((0x11, 0x00, 0x33, 0x0A, 0x01, 0x01, 0xF8, 0x04))
    )
    parser = StreamParser()
    got = list(parser.feed(b"\x99" + discovery[:5]))
    assert not got
    got = list(parser.feed(discovery[5:]))
    assert len(got) == 1 and got[0].raw == discovery
    assert classify_frame(got[0], 1)["type"] == "vitotrol_discovery"

    response = append_crc(
        bytes(
            (
                0x11,
                0x00,
                0xBF,
                0x0C,
                0x01,
                0x01,
                0x11,
                0x08 ^ 0xAA,
                0x12 ^ 0xAA,
                0x34 ^ 0xAA,
            )
        )
    )
    info = classify_frame(Frame(response), 1)
    assert info["type"] == "master_read_response"
    assert info["block"] == "0x08"
    assert info["data"] == "12 34"

    print("self-test: PASS")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only Viessmann physical KM-BUS Vitotrol probe"
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run offline protocol/safety tests",
    )
    parser.add_argument(
        "--port",
        help="serial device connected through an M-Bus/KM-BUS slave transceiver",
    )
    parser.add_argument(
        "--mode",
        choices=("sniff", "register", "read"),
        default="sniff",
        help=(
            "sniff=0 TX; register=identity/PONG only; "
            "read=register plus 0x15-family reads"
        ),
    )
    parser.add_argument(
        "--slot",
        type=parse_int,
        choices=(1, 2, 3),
        default=1,
    )
    parser.add_argument(
        "--device-id",
        type=parse_int,
        default=0x34,
        help="0x34=Vitotrol 200A family",
    )
    parser.add_argument("--sn1", type=parse_int, default=0x00)
    parser.add_argument("--sn2", type=parse_int, default=0x05)
    parser.add_argument(
        "--register0",
        type=parse_int,
        default=0x12,
        help=(
            "reply to register 0x00 read; "
            "0x12 is current WiFiVitotrol default"
        ),
    )
    parser.add_argument(
        "--blocks",
        type=parse_blocks,
        default=parse_blocks("0x00,0x08,0x10"),
        help=(
            "comma-separated internal block IDs; "
            "conservative default: 0x00,0x08,0x10"
        ),
    )
    parser.add_argument(
        "--query-every-pings",
        type=int,
        default=1,
        help="send at most one queued read on every Nth matching PING",
    )
    parser.add_argument("--query-timeout", type=float, default=3.0)
    parser.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="seconds; 0 means run until interrupted",
    )
    parser.add_argument("--exit-after-reads", action="store_true")
    parser.add_argument("--jsonl", help="optional JSONL evidence log path")
    parser.add_argument("--serial-timeout", type=float, default=0.05)
    parser.add_argument("--write-timeout", type=float, default=0.25)
    parser.add_argument("--read-chunk", type=int, default=64)
    parser.add_argument("--echo-window-ms", type=float, default=100.0)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    if not args.port:
        parser.error("--port is required unless --self-test is used")
    if args.query_every_pings < 1:
        parser.error("--query-every-pings must be >= 1")
    if (
        not 0 <= args.device_id <= 0xFF
        or not 0 <= args.sn1 <= 0xFF
        or not 0 <= args.sn2 <= 0xFF
    ):
        parser.error("device-id/sn1/sn2 must fit in one byte")
    if not 0 <= args.register0 <= 0xFF:
        parser.error("--register0 must fit in one byte")

    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
