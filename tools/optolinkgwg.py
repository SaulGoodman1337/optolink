"""Bounded, read-only GWG-C7 protocol using an ALREADY OWNED serial handle.

The historical GWG request has one address byte. It does not address CPU ROM.
Only C7 virtual reads are enabled; no raw command or write entrypoint exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import time
from typing import Callable

SUCCESS = 0x01
TRANSPORT_LOST = 0xAA
UNSUPPORTED = 0xAF
INVALID_FRAME = 0xFD
TIMEOUT = 0xFF
GWG_VIRTUAL_READ = 0xC7
MAX_READ_LENGTH = 8  # Longest GWG C7 tested successfully on WB2A 20C2.
MAX_RETRIES = 1


@dataclass(frozen=True)
class GWGResult:
    code: int
    address: int
    data: bytes
    wire: bytes = b""
    received: bytes = b""
    sync_seen: bool = False
    attempts: int = 0
    reason: str = ""

    def as_adapter_tuple(self) -> tuple[int, int, bytearray]:
        return self.code, self.address, bytearray(self.data)

    def trace(self) -> dict:
        return {
            "protocol": "GWG", "function": "VIRTUAL_READ_C7",
            "at_utc": datetime.now(timezone.utc).isoformat(),
            "status": f"{self.code:02X}", "address": self.address,
            "requested_frame": self.wire.hex(), "response": self.received.hex(),
            "accepted_bytes": self.data.hex(), "sync_seen": self.sync_seen,
            "attempts": self.attempts, "reason": self.reason,
        }


class GWGProtocol:
    """Sequential request helper. Caller alone owns and serializes ser."""

    def __init__(self, ser, *, retries: int = 0,
                 sync_timeout: float = 3.0, reply_timeout: float = 0.75,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep,
                 trace_hook: Callable[[dict], None] | None = None):
        if type(retries) is not int or not 0 <= retries <= MAX_RETRIES:
            raise ValueError("GWG retry count must be 0 or 1")
        if not 0 < sync_timeout <= 3.0 or not 0 < reply_timeout <= 0.75:
            raise ValueError("GWG timeout exceeds established safety envelope")
        self.ser, self.retries = ser, retries
        self.sync_timeout, self.reply_timeout = sync_timeout, reply_timeout
        self.clock, self.sleep, self.trace_hook = clock, sleep, trace_hook

    @staticmethod
    def frame(address: int, length: int) -> bytes:
        if type(address) is not int or not 0 <= address <= 0xFF:
            raise ValueError("GWG address is exactly 8 bits")
        if type(length) is not int or not 1 <= length <= MAX_READ_LENGTH:
            raise ValueError("GWG length restricted to 1..8 until independently tested")
        if address + length > 0x100:
            raise ValueError("GWG request crosses 8-bit address boundary")
        return bytes((0x01, GWG_VIRTUAL_READ, address, length, 0x04))

    def _once(self, address: int, length: int, frame: bytes) -> GWGResult:
        raw = bytearray()
        synced = False
        try:
            self.ser.reset_input_buffer()
            if self.ser.write(b"\x04") != 1:
                return GWGResult(TRANSPORT_LOST, address, b"", frame,
                                 reason="short_sync_write")
            self.ser.flush()
            deadline = self.clock() + self.sync_timeout
            while self.clock() < deadline:
                incoming = self.ser.read(1)
                if incoming == b"\x05":
                    synced = True
                    break
                self.sleep(0.005)
            if not synced:
                return GWGResult(TIMEOUT, address, b"", frame,
                                 reason="enq_timeout")
            self.ser.reset_input_buffer()
            if self.ser.write(frame) != len(frame):
                return GWGResult(TRANSPORT_LOST, address, b"", frame,
                                 sync_seen=True, reason="short_frame_write")
            self.ser.flush()
            deadline = self.clock() + self.reply_timeout
            while self.clock() < deadline:
                rx = self.ser.read_all()
                if rx:
                    raw.extend(rx)
                    if len(raw) > length:
                        return GWGResult(INVALID_FRAME, address, b"", frame,
                                         bytes(raw), True,
                                         reason="unexpected_extra_reply_bytes")
                    if len(raw) == length:
                        return GWGResult(SUCCESS, address, bytes(raw), frame,
                                         bytes(raw), True, reason="ok")
                else:
                    self.sleep(0.005)
            return GWGResult(TIMEOUT, address, b"", frame, bytes(raw), True,
                             reason="partial_reply" if raw else "no_reply")
        except Exception as exc:
            # Never deliver partial or stale data as a successful measurement.
            return GWGResult(TRANSPORT_LOST, address, b"", frame,
                             bytes(raw), synced, reason=type(exc).__name__)

    def read_virtual(self, address: int, length: int) -> GWGResult:
        try:
            frame = self.frame(address, length)
        except ValueError as exc:
            result = GWGResult(INVALID_FRAME, address, b"", reason=str(exc))
            if self.trace_hook:
                self.trace_hook(result.trace())
            return result
        last = None
        for i in range(self.retries + 1):
            result = self._once(address, length, frame)
            last = GWGResult(result.code, address, result.data, result.wire,
                             result.received, result.sync_seen, i + 1,
                             result.reason)
            if self.trace_hook:
                self.trace_hook(last.trace())
            if last.code in (SUCCESS, INVALID_FRAME, TRANSPORT_LOST):
                break
        assert last is not None
        return last


def read_datapoint_ext(address: int, length: int, ser, *, retries: int = 0,
                       trace_hook: Callable[[dict], None] | None = None
                       ) -> tuple[int, int, bytearray]:
    return GWGProtocol(ser, retries=retries,
                       trace_hook=trace_hook).read_virtual(
                           address, length).as_adapter_tuple()
