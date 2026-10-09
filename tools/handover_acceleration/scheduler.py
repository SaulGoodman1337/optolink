"""Offline request queue and GFA freshness model; never opens a serial port.

No executor, MQTT client, physical/virtual address or write operation exists.
The owner must explicitly take a ticket and finish it after a complete frame.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
import math
import threading
import time


class SchedulingError(RuntimeError):
    pass


class QueueBusy(SchedulingError):
    pass


class StaleReading(SchedulingError):
    pass


class ReadKind(Enum):
    VS1_P80 = "vs1_p80"
    VS1_P06 = "vs1_p06"
    VS1_P09 = "vs1_p09"
    VS1_P87 = "vs1_p87"
    P300_ID = "p300_identity"

    @property
    def mode(self) -> str:
        return "p300" if self is ReadKind.P300_ID else "vs1"


class TicketState(Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


@dataclass(eq=False)
class Ticket:
    sequence: int
    kind: ReadKind
    enqueued_at: float
    deadline: float
    state: TicketState = TicketState.QUEUED


class BoundedReadQueue:
    """Capacity- and deadline-bounded read-only admission.

    One consumer thread, one in-flight transaction. Prefer the currently
    verified protocol for batching, but force the other pending protocol
    after `max_same_mode` successive selections. This is only a scheduler:
    it does NOT perform handshakes, I/O or independent recovery.
    """
    def __init__(self, capacity: int = 32, max_same_mode: int = 4,
                 *, clock=time.monotonic):
        if (type(capacity) is not int or capacity < 1 or
                type(max_same_mode) is not int or max_same_mode < 1):
            raise ValueError("capacity and max_same_mode must be positive integers")
        self.capacity = capacity
        self.max_same_mode = max_same_mode
        self.clock = clock
        self._pending: deque[Ticket] = deque()
        self._inflight: Ticket | None = None
        self._consumer_tid: int | None = None
        self._last_mode: str | None = None
        self._same_mode_count = 0
        self._next_sequence = 1
        self._closed = False
        self._lock = threading.RLock()

    def _expire(self):
        now = self.clock()
        kept = deque()
        for ticket in self._pending:
            if ticket.deadline <= now:
                ticket.state = TicketState.EXPIRED
            else:
                kept.append(ticket)
        self._pending = kept

    def submit(self, kind: ReadKind, *, ttl_s: float = 10.0) -> Ticket:
        if not isinstance(kind, ReadKind):
            raise SchedulingError("unknown read kind; writes/raw requests forbidden")
        if (isinstance(ttl_s, bool) or not isinstance(ttl_s, (int, float))
                or not math.isfinite(ttl_s) or ttl_s <= 0):
            raise SchedulingError("read deadline must be finite and positive")
        with self._lock:
            if self._closed:
                raise SchedulingError("queue closed")
            self._expire()
            if len(self._pending) >= self.capacity:
                raise QueueBusy("read queue is full")
            now = self.clock()
            ticket = Ticket(self._next_sequence, kind, now, now + ttl_s)
            self._next_sequence += 1
            self._pending.append(ticket)
            return ticket

    def cancel(self, ticket: Ticket) -> bool:
        with self._lock:
            if ticket.state is not TicketState.QUEUED or ticket not in self._pending:
                return False  # already in flight: never break an on-wire frame
            self._pending.remove(ticket)
            ticket.state = TicketState.CANCELLED
            return True

    def take(self, *, preferred_mode: str | None = None) -> Ticket | None:
        if preferred_mode not in (None, "vs1", "p300"):
            raise SchedulingError("invalid preferred mode")
        with self._lock:
            if self._closed:
                raise SchedulingError("queue closed")
            caller = threading.get_ident()
            if self._consumer_tid is None:
                self._consumer_tid = caller
            if self._consumer_tid != caller:
                raise QueueBusy("only one consumer thread may own the queue")
            if self._inflight is not None:
                raise QueueBusy("one atomic request already in flight")
            self._expire()
            if not self._pending:
                return None
            modes = {t.kind.mode for t in self._pending}
            forced_other = (self._last_mode is not None
                            and self._same_mode_count >= self.max_same_mode
                            and (modes - {self._last_mode}))
            if forced_other:
                desired = next(iter(modes - {self._last_mode}))
            elif preferred_mode in modes:
                desired = preferred_mode
            else:
                desired = self._pending[0].kind.mode
            chosen = next(t for t in self._pending if t.kind.mode == desired)
            self._pending.remove(chosen)
            chosen.state = TicketState.RUNNING
            self._inflight = chosen
            if desired == self._last_mode:
                self._same_mode_count += 1
            else:
                self._last_mode = desired
                self._same_mode_count = 1
            return chosen

    def finish(self, ticket: Ticket, *, success: bool):
        with self._lock:
            if threading.get_ident() != self._consumer_tid:
                raise QueueBusy("only queue owner may finish a frame")
            if ticket is not self._inflight or ticket.state is not TicketState.RUNNING:
                raise SchedulingError("ticket not in flight")
            if type(success) is not bool:
                raise SchedulingError("completion must be explicitly boolean")
            ticket.state = TicketState.COMPLETED if success else TicketState.FAILED
            self._inflight = None

    def close(self):
        with self._lock:
            if self._inflight is not None:
                raise QueueBusy("cannot close during an atomic frame")
            self._closed = True
            for ticket in self._pending:
                ticket.state = TicketState.CANCELLED
            self._pending.clear()

    def pending_count(self) -> int:
        with self._lock:
            self._expire()
            return len(self._pending)


@dataclass(frozen=True)
class GfaSample:
    kind: ReadKind
    raw: bytes
    acquired_at: float
    session_generation: int
    source: str = "verified_vs1_gfa"


class GfaFreshnessLedger:
    """Exact GFA provenance: no P09/P10/RAM substitution for P06."""
    def __init__(self, *, clock=time.monotonic):
        self.clock = clock
        self._samples: dict[ReadKind, GfaSample] = {}
        self._lock = threading.RLock()

    def record(self, kind: ReadKind, raw: bytes, *, session_generation: int,
               vs1_verified: bool):
        if not isinstance(kind, ReadKind) or kind.mode != "vs1":
            raise SchedulingError("only real VS1 GFA sample types are accepted")
        if type(session_generation) is not int or session_generation < 1:
            raise SchedulingError("invalid session generation")
        with self._lock:
            if (vs1_verified is not True or not isinstance(raw, bytes)
                    or len(raw) != 1 or raw == b"\xff"
                    or (kind is ReadKind.VS1_P80 and raw != b"\x20")):
                self._samples.pop(kind, None)  # a failed read invalidates old data
                raise SchedulingError("unverified or invalid GFA sample")
            sample = GfaSample(kind, raw, self.clock(), session_generation)
            self._samples[kind] = sample
            return sample

    def fresh(self, kind: ReadKind, *, current_generation: int,
              max_age_s: float) -> GfaSample:
        if (isinstance(max_age_s, bool) or not isinstance(max_age_s, (int,float))
                or not math.isfinite(max_age_s) or max_age_s < 0):
            raise SchedulingError("invalid freshness age bound")
        with self._lock:
            sample = self._samples.get(kind)
            if sample is None:
                raise StaleReading("no verified GFA sample")
            age = self.clock() - sample.acquired_at
            if (age < 0 or age > max_age_s
                    or sample.session_generation != current_generation):
                raise StaleReading("GFA data is stale or from a past session")
            return sample

    def invalidate_all(self):
        with self._lock:
            self._samples.clear()
