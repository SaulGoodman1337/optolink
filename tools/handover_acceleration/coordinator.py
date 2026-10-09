"""Experimental single-owner VS1/P300 coordinator (no port discovery or deployment).

The only serial object is injected by the caller *after* taking the advisory
lease. This is deliberately not a ready-to-run heating-controller client.
No arbitrary address, write, RPC, RAM or GFA-alias interfaces are exposed.
"""
from __future__ import annotations

import enum
import fcntl
import os
import stat
import threading
import time
from pathlib import Path

DEVICE_ID = b"\x20\xc2"
SOFTWARE = b"\x01\x03"
EOT, ENQ, ACK, STX = b"\x04", b"\x05", b"\x06", b"\x01"
VS1_ID = bytes.fromhex("f700f802")
VS1_SOFTWARE = bytes.fromhex("f7778c02")
GFA = {"P80": bytes.fromhex("6b405001"),
       "P06": bytes.fromhex("6b400601"),
       "P09": bytes.fromhex("6b400901"),
       "P87": bytes.fromhex("6b405701")}
P300_ID = bytes.fromhex("4105000100f80200")
P300_SOFTWARE = bytes.fromhex("41050001778c020b")
TX_ALLOW = frozenset([EOT, ACK, b"\x16\x00\x00", STX + VS1_ID,
                      VS1_SOFTWARE, *GFA.values(), P300_ID, P300_SOFTWARE])


class ProtocolError(RuntimeError):
    pass


class BusyError(ProtocolError):
    pass


class RestoreError(ProtocolError):
    pass


class Mode(enum.Enum):
    DETACHED = "detached"
    UNKNOWN = "unknown"
    SWITCHING = "switching"
    VS1_VERIFIED = "vs1_verified"
    P300_VERIFIED = "p300_verified"
    FAILED_CLOSED = "failed_closed"
    RECOVERING = "recovering"


class WirePhase(enum.Enum):
    """An independent low-level TX guard, even if a caller reaches the wire."""
    FAILED_CLOSED = "failed_closed"
    VS1_SYNC = "vs1_sync"
    VS1_HANDSHAKE = "vs1_handshake"
    VS1_VERIFIED = "vs1_verified"
    P300_SYNC = "p300_sync"
    P300_HANDSHAKE = "p300_handshake"
    P300_VERIFIED = "p300_verified"


PHASE_TX_ALLOW = {
    WirePhase.FAILED_CLOSED: frozenset(),
    WirePhase.VS1_SYNC: frozenset((EOT,)),
    WirePhase.VS1_HANDSHAKE: frozenset((STX + VS1_ID, VS1_SOFTWARE,
                                         GFA["P80"], GFA["P06"])),
    WirePhase.VS1_VERIFIED: frozenset(GFA.values()),
    WirePhase.P300_SYNC: frozenset((EOT,)),
    WirePhase.P300_HANDSHAKE: frozenset((b"\x16\x00\x00", ACK,
                                           P300_ID, P300_SOFTWARE)),
    WirePhase.P300_VERIFIED: frozenset((P300_ID, ACK)),
}


class PortLease:
    """Cooperative cross-process lease, not a replacement for TIOCEXCL."""
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.fd: int | None = None

    def acquire(self):
        if self.fd is not None:
            raise BusyError("lease already owned")
        flags = (os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
                 | getattr(os, "O_CLOEXEC", 0))
        try:
            fd = os.open(self.path, flags, 0o600)
        except OSError as exc:
            raise BusyError("port lease unavailable or unsafe path") from exc
        try:
            metadata = os.fstat(fd)
            if (not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_uid != os.getuid()
                    or metadata.st_mode & 0o077):
                raise BusyError("port lease must be owner-only regular file")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError, BusyError) as exc:
            os.close(fd)
            raise BusyError("lease is already owned or unsafe") from exc
        self.fd = fd

    def release(self):
        if self.fd is not None:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)
            self.fd = None


class ReadOnlyWire:
    """Known fixed messages, exact reads and bounded monotonic deadlines."""
    def __init__(self, port, *, clock=time.monotonic, sleep=time.sleep):
        self.port, self.clock, self.sleep = port, clock, sleep
        self.last_io = self.clock()
        self.phase = WirePhase.FAILED_CLOSED
        self.events: list[tuple[str, str, float]] = []
        # Values obtained as part of the current, verified VS1 handshake only.
        self._handshake_gfa: dict[str, tuple[bytes, float]] = {}

    def _event(self, kind: str, data: bytes):
        self.events.append((kind, data.hex(), self.clock()))

    def tx(self, message: bytes):
        if message not in TX_ALLOW or message not in PHASE_TX_ALLOW[self.phase]:
            raise ProtocolError("TX not permitted in phase " + self.phase.value)
        self._event("TX", message)
        try:
            if self.port.write(message) != len(message):
                raise ProtocolError("short TX")
        except BaseException:
            self.phase = WirePhase.FAILED_CLOSED
            raise

    def exact(self, n: int, timeout: float) -> bytes:
        return self.exact_until(n, self.clock() + timeout)

    def exact_until(self, n: int, deadline: float) -> bytes:
        data = bytearray()
        while len(data) < n:
            if self.clock() >= deadline:
                raise ProtocolError("RX deadline")
            part = self.port.read(n - len(data))
            if part:
                self._event("RX", part)
                data.extend(part)
            else:
                self.sleep(.001)
        return bytes(data)

    def control(self, expected: bytes, timeout=6.0):
        self.control_until(expected, self.clock() + timeout)

    def control_until(self, expected: bytes, deadline: float):
        for _ in range(32):
            x = self.exact_until(1, deadline)
            if x == expected:
                return
            if expected == ENQ and x in (ACK, b"\x15"):
                continue  # only stale control bytes during explicit resync
            raise ProtocolError("unexpected control: " + x.hex())
        raise ProtocolError("too many stale control bytes")

    def gap(self):
        self.sleep(max(0.0, self.last_io + .025 - self.clock()))

    def quiet(self):
        end = self.clock() + .010
        while self.clock() < end:
            x = self.port.read(1)
            if x:
                self._event("UNEXPECTED", x)
                raise ProtocolError("trailing response bytes")
            self.sleep(.001)
        self.last_io = self.clock()

    def reset_before_eot(self):
        # No buffer purge between a request and its complete response.
        self.port.reset_input_buffer()

    def sync(self, count: int):
        if count not in (1, 2):
            raise ProtocolError("invalid ENQ count")
        if self.phase not in (WirePhase.VS1_SYNC, WirePhase.P300_SYNC):
            raise ProtocolError("sync outside transition")
        self.reset_before_eot()
        self.tx(EOT)
        # Each ENQ is a distinct controller phase. Do not turn 2 into a
        # single combined deadline; the baseline has a >2s second ENQ.
        for _ in range(count):
            self.control(ENQ, timeout=6.0)

    def vs1_read(self, request: bytes, expected_length: int) -> bytes:
        if self.phase not in (WirePhase.VS1_HANDSHAKE,
                              WirePhase.VS1_VERIFIED):
            raise ProtocolError("VS1 read outside VS1 phase")
        if request not in (STX + VS1_ID, VS1_SOFTWARE, *GFA.values()):
            raise ProtocolError("unknown VS1 read")
        self.gap()
        self.tx(request)
        result = self.exact(expected_length, 2.0)
        self.quiet()
        return result

    def verify_vs1(self, enqs: int):
        self._handshake_gfa.clear()
        self.phase = WirePhase.VS1_SYNC
        try:
            self.sync(enqs)
            self.phase = WirePhase.VS1_HANDSHAKE
            if self.vs1_read(STX + VS1_ID, 2) != DEVICE_ID:
                raise ProtocolError("VS1 device identity mismatch")
            if self.vs1_read(VS1_SOFTWARE, 2) != SOFTWARE:
                raise ProtocolError("VS1 software identity mismatch")
            p80 = self.vs1_read(GFA["P80"], 1)
            p80_at = self.clock()
            if p80 != b"\x20":
                raise ProtocolError("GFA P80 identity mismatch")
            p06 = self.vs1_read(GFA["P06"], 1)
            p06_at = self.clock()
            if p06 == b"\xff":
                raise ProtocolError("GFA P06 invalid FF")
        except BaseException:
            self._handshake_gfa.clear()
            self.phase = WirePhase.FAILED_CLOSED
            raise
        # Publication is atomic only after all VS1 identity checks succeeded.
        self._handshake_gfa = {'P80': (p80, p80_at), 'P06': (p06, p06_at)}
        self.phase = WirePhase.VS1_VERIFIED

    def verify_vs1_early_identity_experiment(self):
        """Experimental VS1 return: read a KNOWN identity before any ENQ.

        Only a fresh full identity/software/P80/P06 handshake permits VERIFIED.
        A 350-ms negative observation does not prove no later response is
        possible; in particular it is NOT a new controller minimum latency.
        """
        self._handshake_gfa.clear()
        self.phase = WirePhase.VS1_SYNC
        try:
            self.reset_before_eot()
            self.tx(EOT)
            self.sleep(.025)
            self.phase = WirePhase.VS1_HANDSHAKE
            self.tx(STX + VS1_ID)
            try:
                identity = self.exact(2, .35)
            except ProtocolError as exc:
                raise ProtocolError('EARLY_VS1_NO_IDENTITY_WITHIN_350MS') from exc
            self.quiet()
            if identity != DEVICE_ID:
                raise ProtocolError('EARLY_VS1_WRONG_IDENTITY')
            if self.vs1_read(VS1_SOFTWARE, 2) != SOFTWARE:
                raise ProtocolError('EARLY_VS1_WRONG_SOFTWARE')
            p80 = self.vs1_read(GFA['P80'], 1)
            p80_at = self.clock()
            if p80 != b'\x20':
                raise ProtocolError('EARLY_VS1_P80_MISMATCH')
            p06 = self.vs1_read(GFA['P06'], 1)
            p06_at = self.clock()
            if p06 == b'\xff':
                raise ProtocolError('EARLY_VS1_P06_FF')
        except BaseException:
            self._handshake_gfa.clear()
            self.phase = WirePhase.FAILED_CLOSED
            raise
        self._handshake_gfa = {'P80': (p80, p80_at), 'P06': (p06, p06_at)}
        self.phase = WirePhase.VS1_VERIFIED

    def p300_read(self, request: bytes, expected: bytes) -> bytes:
        if self.phase not in (WirePhase.P300_HANDSHAKE,
                              WirePhase.P300_VERIFIED):
            raise ProtocolError("P300 read outside P300 phase")
        if (request, expected) not in ((P300_ID, DEVICE_ID),
                                        (P300_SOFTWARE, SOFTWARE)):
            raise ProtocolError("unknown P300 read")
        self.gap()
        self.tx(request)
        end = self.clock() + 3.0
        self.control_until(ACK, end)
        # Some previously tested peers repeat ACK before STX.
        for _ in range(8):
            first = self.exact_until(1, end)
            if first != ACK:
                break
        if first != b"\x41":
            raise ProtocolError("P300 STX mismatch")
        size = self.exact_until(1, end)[0]
        if size != 7:  # fixed 2-byte identity responses only
            raise ProtocolError("P300 length mismatch")
        body = self.exact_until(size + 1, end)
        if (size + sum(body[:-1])) & 0xff != body[-1]:
            raise ProtocolError("P300 checksum mismatch")
        mid, fc, hi, lo, n = body[:5]
        addr = 0x00f8 if request == P300_ID else 0x778c
        if mid != 1 or fc != 1 or (hi << 8 | lo) != addr or n != 2:
            raise ProtocolError("P300 frame type/function/address mismatch")
        if body[5:-1] != expected:
            raise ProtocolError("P300 identity mismatch")
        self.tx(ACK)
        self.quiet()
        return body[5:-1]

    def verify_p300(self):
        self._handshake_gfa.clear()
        self.phase = WirePhase.P300_SYNC
        try:
            self.sync(1)
            self.phase = WirePhase.P300_HANDSHAKE
            self.tx(b"\x16\x00\x00")
            self.control(ACK)
            self.p300_read(P300_ID, DEVICE_ID)
            self.p300_read(P300_SOFTWARE, SOFTWARE)
        except BaseException:
            self.phase = WirePhase.FAILED_CLOSED
            raise
        self.phase = WirePhase.P300_VERIFIED


class HandoverCoordinator:
    """Single owner, never trusts an old session after an EOT or failure.

    Use `with ...` to acquire lease before opening the injected port.
    Setup and recovery use conservative two-ENQ. Only a verified normal
    P300->VS1 handover may use the measured one-ENQ shortcut.
    """
    def __init__(self, open_port, lease: PortLease, *, clock=time.monotonic,
                 sleep=time.sleep):
        self.open_port, self.lease = open_port, lease
        self.clock, self.sleep = clock, sleep
        self.mode = Mode.DETACHED
        self.wire: ReadOnlyWire | None = None
        self._lock = threading.RLock()
        self.history: list[tuple[str, str]] = []
        self._recovery_attempted = False

    def __enter__(self):
        with self._lock:
            if self.mode != Mode.DETACHED:
                raise ProtocolError("already open")
            self.lease.acquire()  # before opening the serial resource
            try:
                self.wire = ReadOnlyWire(self.open_port(), clock=self.clock,
                                         sleep=self.sleep)
                self.mode = Mode.UNKNOWN
                self._verify_vs1(2, recovery=False)
            except BaseException:
                self.mode = Mode.FAILED_CLOSED
                self._close_resources()
                raise
            return self

    def _close_resources(self):
        try:
            if self.wire is not None:
                self.wire.port.close()
        finally:
            self.wire = None
            self.lease.release()

    def __exit__(self, exc_type, exc_value, traceback):
        with self._lock:
            restore_error = None
            try:
                if self.mode != Mode.VS1_VERIFIED:
                    if self._recovery_attempted:
                        restore_error = RestoreError("previous recovery already failed")
                    else:
                        try:
                            self.restore_vs1()
                        except BaseException as exc:
                            restore_error = exc
            finally:
                self._close_resources()
                self.mode = Mode.DETACHED if restore_error is None else Mode.FAILED_CLOSED
            if restore_error is not None:
                raise RestoreError("VS1 restore not confirmed") from restore_error
        return False

    def _verify_vs1(self, count: int, *, recovery: bool):
        assert self.wire is not None
        self.mode = Mode.RECOVERING if recovery else Mode.SWITCHING
        try:
            self.wire.verify_vs1(count)
        except BaseException:
            self.mode = Mode.FAILED_CLOSED
            self.history.append(("vs1", "failed"))
            raise
        self.mode = Mode.VS1_VERIFIED
        self.history.append(("vs1", f"verified:{count}"))

    def _fail_closed(self):
        self.mode = Mode.FAILED_CLOSED
        if self.wire is not None:
            self.wire.phase = WirePhase.FAILED_CLOSED
            self.wire._handshake_gfa.clear()

    def to_p300(self):
        with self._lock:
            if self.mode != Mode.VS1_VERIFIED:
                raise ProtocolError("P300 transition requires verified VS1")
            self.mode = Mode.SWITCHING
            try:
                assert self.wire is not None
                self.wire.verify_p300()
            except BaseException:
                self._fail_closed()
                self.history.append(("p300", "failed"))
                raise
            self.mode = Mode.P300_VERIFIED
            self._recovery_attempted = False
            self.history.append(("p300", "verified"))

    def to_p300_early_start_experiment(self):
        """RESEARCH ONLY: test known START immediately after EOT, before ENQ.

        Not the documented protocol: OpenV specifies ENQ before 16 00 00.
        This one alternate *timing* uses known control/identity READ frames,
        not an unknown operation/address. A fresh ACK AND valid identities
        are mandatory. Failure is never silently retried as a success.
        A separate two-ENQ VS1 restore is required after an unsuccessful run.
        """
        with self._lock:
            if self.mode != Mode.VS1_VERIFIED or self.wire is None:
                raise ProtocolError("early-start trial requires verified VS1")
            self.mode = Mode.SWITCHING
            w = self.wire
            w._handshake_gfa.clear()
            try:
                w.phase = WirePhase.P300_SYNC
                w.reset_before_eot()
                w.tx(EOT)
                # Line idle after known EOT: avoid contiguous bytes. We do
                # NOT wait for ENQ. No GFA, RAM, RPC or parameter write.
                w.sleep(.025)
                w.phase = WirePhase.P300_HANDSHAKE
                w.tx(b"\x16\x00\x00")
                w.control(ACK, timeout=.35)
                w.p300_read(P300_ID, DEVICE_ID)
                w.p300_read(P300_SOFTWARE, SOFTWARE)
            except BaseException:
                self._fail_closed()
                self.history.append(("p300_early_start", "failed"))
                raise
            w.phase = WirePhase.P300_VERIFIED
            self.mode = Mode.P300_VERIFIED
            self._recovery_attempted = False
            self.history.append(("p300_early_start", "verified"))

    def to_vs1_fast(self):
        with self._lock:
            if self.mode != Mode.P300_VERIFIED:
                raise ProtocolError("fast return requires verified P300")
            self._verify_vs1(1, recovery=False)  # no silent second ENQ

    def to_vs1_early_identity_experiment(self):
        """Research only: known VS1 STX/identity immediately after EOT.

        One opt-in attempt; failure is recorded before conservative VS1
        recovery. No unknown addresses, writes, RAM, or free-form frames.
        """
        with self._lock:
            if self.mode != Mode.P300_VERIFIED or self.wire is None:
                raise ProtocolError('early VS1 requires a freshly verified P300')
            self.mode = Mode.SWITCHING
            try:
                self.wire.verify_vs1_early_identity_experiment()
            except BaseException:
                self._fail_closed()
                self.history.append(('vs1_early_identity', 'failed'))
                raise
            self.mode = Mode.VS1_VERIFIED
            self.history.append(('vs1_early_identity', 'verified'))

    def restore_vs1(self):
        with self._lock:
            if self.mode == Mode.VS1_VERIFIED:
                return  # reuse only a still-owned, presently verified session
            if self.wire is None:
                raise RestoreError("no port for recovery")
            if self._recovery_attempted:
                raise RestoreError("recovery already attempted; operator required")
            self._recovery_attempted = True
            self._verify_vs1(2, recovery=True)

    def verified_gfa_snapshot(self, *, max_age: float = 0.75) -> dict[str, bytes]:
        """Use *only* recent P80/P06 from the current verified VS1 handshake.

        An older value must never be represented as a newly queried reading.
        This does not replace a new GFA operation after expiry or EOT.
        """
        with self._lock:
            if self.mode is not Mode.VS1_VERIFIED or self.wire is None:
                raise ProtocolError("no verified VS1 GFA snapshot")
            values = self.wire._handshake_gfa
            if set(values) != {'P80', 'P06'} or not 0 < max_age <= 1.0:
                raise ProtocolError("missing or unbounded GFA snapshot")
            now = self.clock()
            if any(not 0 <= now - t <= max_age for _value, t in values.values()):
                raise ProtocolError("VS1 GFA snapshot is stale")
            return {key: value for key, (value, _at) in values.items()}

    def gfa_read(self, name: str) -> bytes:
        with self._lock:
            if self.mode != Mode.VS1_VERIFIED:
                raise ProtocolError("GFA only in verified VS1")
            if name not in GFA:
                raise ProtocolError("unknown GFA parameter")
            assert self.wire is not None
            try:
                value = self.wire.vs1_read(GFA[name], 1)
                if value == b"\xff" or (name == "P80" and value != b"\x20"):
                    raise ProtocolError("invalid GFA response")
                return value
            except BaseException:
                self._fail_closed()
                raise

    def p300_identity(self) -> bytes:
        with self._lock:
            if self.mode != Mode.P300_VERIFIED:
                raise ProtocolError("P300 request requires verified P300")
            assert self.wire is not None
            try:
                return self.wire.p300_read(P300_ID, DEVICE_ID)
            except BaseException:
                self._fail_closed()
                raise

    def p300_window(self, fn):
        """Serialize a read-only P300 callback and restore VS1 in all outcomes.

        No data frame may be interrupted: each individual read is synchronous.
        A failing fast return triggers separately logged conservative recovery.
        """
        with self._lock:
            if self.mode != Mode.VS1_VERIFIED:
                raise ProtocolError("window requires verified VS1")
            try:
                self.to_p300()
                return fn(self)
            finally:
                if self.mode == Mode.P300_VERIFIED:
                    try:
                        self.to_vs1_fast()
                    except BaseException:
                        self.restore_vs1()  # separate recovery, never count as fast success
                        raise
                elif self.mode != Mode.VS1_VERIFIED:
                    self.restore_vs1()
