"""Experimental WB2A P300 backend. No port opening and no implicit VS1 fallback.

The running splitter supplies its single, nonblocking serial handle. Normal
Virtual_WRITE is preserved; physical writes are NOT exposed through request().
Source: sarnau/InsideViessmannVitosoft/VitosoftCommunication.md (GFA_READ=201).
Offline tests do not establish hardware support for C9 on the local 20C2.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable

OK, ERROR, DENIED, LENGTH, CHECKSUM, TIMEOUT = 1, 3, 0xAF, 0xFD, 0xFE, 0xFF
GFA_TARGETS = frozenset((0x4050, 0x4006, 0x4009, 0x4057))
RAM_START, RAM_END = 0x0400, 0x5400


class TransportError(Exception):
    def __init__(self, code: int, message: str, data: bytes = b""):
        super().__init__(message)
        self.code, self.data = code, data


@dataclass(frozen=True)
class RamWriteRule:
    """Exact data-field allowlist, supplied explicitly by a reviewed experiment.

    No production rules are shipped. A RAM range alone is NOT a write policy.
    Read/compare/write is serialized on the host, not atomic inside the MCU.
    """
    address: int
    allowed_values: frozenset[bytes]


def request_frame(function: int, address: int, length: int, data: bytes = b"") -> bytes:
    if not (0 <= function <= 255 and 0 <= address <= 0xFFFF and 1 <= length <= 55):
        raise ValueError("invalid P300 request geometry")
    if len(data) > 55 or (data and len(data) != length):
        raise ValueError("payload length mismatch")
    body = bytes((5 + len(data), 0, function, address >> 8, address & 255, length)) + data
    return b"\x41" + body + bytes((sum(body) & 255,))


class P300:
    def __init__(self, serial, *, timeout: float = 3.0, gap: float = 0.025,
                 ram_read: bool = False, virtual_write: bool = False, write_rules: tuple[RamWriteRule, ...] = (),
                 audit: Callable[[str], None] = lambda message: None):
        if getattr(serial, "timeout", None) != 0:
            raise ValueError("splitter serial handle must be nonblocking (timeout=0)")
        if not (0 < timeout <= 10 and 0 <= gap <= 1):
            raise ValueError("invalid timing configuration")
        self.serial, self.timeout, self.gap = serial, timeout, gap
        self.ram_read, self.write_rules, self.audit = ram_read, tuple(write_rules), audit
        self.virtual_write = virtual_write
        self.ready = False
        self.last_io = 0.0
        self.lock = threading.RLock()

    def _send(self, data: bytes) -> None:
        if self.serial.write(data) != len(data):
            raise TransportError(TIMEOUT, "short serial write; outcome may be unknown")

    def _exact(self, count: int, deadline: float) -> bytes:
        result = bytearray()
        while len(result) < count:
            if time.monotonic() >= deadline:
                raise TransportError(TIMEOUT, "P300 receive deadline exceeded")
            part = self.serial.read(count - len(result))
            if part:
                result.extend(part)
            else:
                time.sleep(0.001)
        return bytes(result)

    def _exchange(self, function: int, address: int, length: int,
                  data: bytes = b"") -> bytes:
        frame = request_frame(function, address, length, data)
        remaining = self.last_io + self.gap - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)
        self.serial.reset_input_buffer()
        self._send(frame)  # Never automatically replay a write.
        deadline = time.monotonic() + self.timeout
        first = self._exact(1, deadline)
        if first == b"\x15":
            raise TransportError(0x15, "P300 NACK")
        if first != b"\x06":
            raise TransportError(0x20, "missing initial P300 ACK")
        # Some peers send repeated ACKs before STX. Bound this explicitly.
        for _ in range(8):
            first = self._exact(1, deadline)
            if first != b"\x06":
                break
        if first != b"\x41":
            raise TransportError(0x41, "missing P300 STX")
        size = self._exact(1, deadline)[0]
        if not 5 <= size <= 60:
            raise TransportError(LENGTH, "invalid response length")
        tail = self._exact(size + 1, deadline)
        if (size + sum(tail[:-1])) & 255 != tail[-1]:
            raise TransportError(CHECKSUM, "P300 checksum mismatch")
        self._send(b"\x06")  # Acknowledge the checked frame, not just its prefix.
        self.last_io = time.monotonic()
        msg, reply_function, hi, lo, declared = tail[:5]
        payload = tail[5:-1]
        if msg not in (1, 3) or reply_function != function or (hi << 8 | lo) != address:
            raise TransportError(LENGTH, "response message/function/address mismatch")
        if msg == ERROR:
            if declared != len(payload):
                raise TransportError(LENGTH, "malformed controller error")
            raise TransportError(ERROR, "controller rejected request", payload)
        if function in (2, 4):
            # WB2A write replies may carry an empty payload with a count echo.
            if declared not in (0, length) or payload not in (b"", data):
                raise TransportError(LENGTH, "unexpected write reply")
        elif declared != length or len(payload) != length:
            raise TransportError(LENGTH, "short/oversized data is not a valid reading")
        return payload

    def _gfa(self, address: int) -> bytes:
        result = self._exchange(0xC9, address, 1)
        if result == b"\xff":
            time.sleep(0.15)
            result = self._exchange(0xC9, address, 1)
        if result == b"\xff":
            raise TransportError(TIMEOUT, "GFA FF quarantined after one retry")
        if address == 0x4050 and result != b"\x20":
            self.ready = False
            raise TransportError(DENIED, "GFA P80 identity mismatch")
        return result

    def _init_expect(self, stage: str, function: int, address: int, expected: bytes) -> None:
        """Identify the exact P300 initialization command rejected by the MCU.

        Error payload is limited to eight bytes; no credentials, configuration
        writes, RAM reads or extra probes are introduced by this diagnostic.
        """
        try:
            if function == 0xC9:
                actual = self._gfa(address)
            else:
                actual = self._exchange(function, address, len(expected))
            if actual != expected:
                raise TransportError(DENIED, "unexpected identity response", actual)
        except TransportError as exc:
            detail = exc.data[:8].hex() if exc.data else "-"
            self.audit(
                f"P300_INIT_STAGE_FAILED stage={stage} "
                f"fc={function:02X} addr={address:04X} "
                f"code={exc.code:02X} payload={detail}"
            )
            raise

    def _initialize(self) -> None:
        self.ready = False
        self.serial.reset_input_buffer()
        self._send(b"\x04")
        deadline = time.monotonic() + self.timeout
        while self._exact(1, deadline) != b"\x05":
            pass
        self.serial.reset_input_buffer()
        self._send(b"\x16\x00\x00")
        deadline = time.monotonic() + self.timeout
        if self._exact(1, deadline) != b"\x06":
            raise TransportError(DENIED, "P300 initialization handshake failed")
        self._init_expect("virtual_device_id", 1, 0x00F8, b"\x20\xc2")
        self._init_expect("virtual_software", 1, 0x778C, b"\x01\x03")
        self._init_expect("gfa_p80", 0xC9, 0x4050, b"\x20")
        self.ready = True

    def initialize(self) -> bool:
        with self.lock:
            try:
                self._initialize()
                return True
            except (TransportError, OSError) as exc:
                self.ready = False
                self.audit(f"P300_INIT_FAILED: {exc}")
                return False

    def _ensure(self) -> None:
        if not self.ready or time.monotonic() - self.last_io > 4.0:
            self._initialize()

    @staticmethod
    def _ram_geometry(address: int, length: int) -> bool:
        return 1 <= length <= 32 and RAM_START <= address < address + length <= RAM_END

    def request(self, function: int, address: int, length: int, data: bytes = b"",
                protid: int = 0) -> tuple[int, int, bytearray]:
        data = bytes(data)
        allowed = (protid == 0 and 0 <= address <= 0xFFFF and 1 <= length <= 55)
        allowed &= ((function == 1 and not data)
                    or (function == 2 and self.virtual_write and len(data) == length)
                    or (function == 3 and self.ram_read and not data
                        and self._ram_geometry(address, length))
                    or (function == 0xC9 and address in GFA_TARGETS and length == 1 and not data))
        if not allowed:
            return DENIED, address, bytearray()
        with self.lock:
            try:
                self._ensure()
                result = self._gfa(address) if function == 0xC9 else self._exchange(
                    function, address, length, data)
                return OK, address, bytearray(result)
            except TransportError as exc:
                if exc.code != ERROR:
                    self.ready = False
                self.audit(f"P300_REQUEST_FAILED fc={function:02X} addr={address:04X}: {exc}")
                return exc.code, address, bytearray(exc.data)
            except OSError as exc:
                self.ready = False
                self.audit(f"P300_SERIAL_FAILED: {exc}")
                return 0xAA, address, bytearray()

    def compare_write_ram(self, address: int, expected: bytes, replacement: bytes) -> bytes:
        """Library-only primitive; never exposed by MQTT/raw request dispatch.

        Requires an exact explicit rule and pre/post reads. No automatic retry,
        rollback, pump policy, timer repair, pointer patch or EEPROM write.
        On failure, state may have changed; obtain a fresh read before recovery.
        """
        expected, replacement = bytes(expected), bytes(replacement)
        length = len(expected)
        rule = next((r for r in self.write_rules if r.address == address), None)
        if (rule is None or not self._ram_geometry(address, length)
                or len(replacement) != length
                or expected not in rule.allowed_values or replacement not in rule.allowed_values):
            raise PermissionError("RAM write is not explicitly allowlisted")
        with self.lock:
            self._ensure()
            before = self._exchange(3, address, length)
            if before != expected:
                raise TransportError(DENIED, "RAM compare failed; nothing written")
            self.audit(f"RAM_WRITE_ATTEMPT {address:04X} {before.hex()} -> {replacement.hex()}")
            try:
                if replacement != before:
                    self._exchange(4, address, length, replacement)
                after = self._exchange(3, address, length)
                if after != replacement:
                    raise TransportError(DENIED, "RAM readback mismatch; no automatic rollback")
            except (TransportError, OSError):
                self.ready = False
                self.audit("RAM_WRITE_UNVERIFIED: do not replay; inspect current state")
                raise
            self.audit(f"RAM_WRITE_VERIFIED {address:04X} {after.hex()}")
            return after
