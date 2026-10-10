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
    P300_RAM_0F20_32 = "p300_ram_0f20_32"
    P300_RAM_1C60_32 = "p300_ram_1c60_32"

    @property
    def mode(self) -> str:
        return "p300" if self.name.startswith("P300_") else "vs1"


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


# ---------------------------------------------------------------------------
# Experimental demand-driven P300 batching (OFFLINE ONLY until dispatcher
# ingress, producer attestation and recovery are integrated). Not an executor.
# Existing production behaviour and BoundedReadQueue remain unchanged.
# ---------------------------------------------------------------------------

P300_DEMAND_KINDS = frozenset({
    ReadKind.P300_ID,
    ReadKind.P300_RAM_0F20_32,
    ReadKind.P300_RAM_1C60_32,
})
_P300_ESTIMATED_READ_MS = {
    ReadKind.P300_ID: 85.0,
    ReadKind.P300_RAM_0F20_32: 140.0,
    ReadKind.P300_RAM_1C60_32: 140.0,
}


@dataclass(eq=False)
class DemandTicket:
    sequence: int
    kind: ReadKind
    enqueued_at: float
    expires_at: float
    state: TicketState = TicketState.QUEUED


@dataclass(frozen=True)
class DemandSelection:
    """A *simulation* only; a separate RuntimeAdmissionGate must allow IO."""
    tickets: tuple[DemandTicket, ...]
    jobs: tuple
    phase_plan: object


class BoundedDemandBatcher:
    """Finite read-only P300 demand queue owned by the original serial loop.

    Producers may submit known diagnostic reads from other threads. Only the
    creating serial-loop thread may select and reserve a batch. No port,
    MQTT client, command dispatcher or transition operation is imported.
    A reserved batch MUST be completed after the verified VS1 return.
    Rejected admission must NOT reserve or discard waiting tickets.
    """

    def __init__(self, *, capacity: int = 16, max_distinct_reads: int = 3,
                 min_spacing_s: float = 60.0, clock=time.monotonic):
        if (type(capacity) is not int or not 1 <= capacity <= 128
                or type(max_distinct_reads) is not int
                or not 1 <= max_distinct_reads <= 3
                or type(min_spacing_s) not in (int, float)
                or not math.isfinite(min_spacing_s) or min_spacing_s < 30
                or not callable(clock)):
            raise ValueError("bounded capacity, batch and cooldown required")
        self.capacity = capacity
        self.max_distinct_reads = max_distinct_reads
        self.min_spacing_s = float(min_spacing_s)
        self.clock = clock
        self._owner = threading.get_ident()
        self._pending: deque[DemandTicket] = deque()
        self._reserved: DemandSelection | None = None
        self._offered: DemandSelection | None = None
        self._offered_at: float | None = None
        self._next = 1
        self._last_completed: float | None = None
        self._failed_closed = False
        self._lock = threading.RLock()

    def _require_owner(self):
        if threading.get_ident() != self._owner:
            raise QueueBusy("batch selection belongs only to serial-owner thread")

    def _expire(self):
        now = self.clock()
        keep = deque()
        for t in self._pending:
            if now >= t.expires_at:
                t.state = TicketState.EXPIRED
            else:
                keep.append(t)
        self._pending = keep

    def submit(self, kind: ReadKind, *, ttl_s: float = 30.0) -> DemandTicket:
        if type(kind) is not ReadKind or kind not in P300_DEMAND_KINDS:
            raise SchedulingError("only three exact P300 diagnostic read kinds")
        if (type(ttl_s) not in (int,float) or not math.isfinite(ttl_s)
                or ttl_s <= 0 or ttl_s > 300):
            raise SchedulingError("finite 0<ttl<=300s required")
        with self._lock:
            if self._failed_closed:
                raise SchedulingError("demand queue latched FAILED_CLOSED")
            self._expire()
            if len(self._pending) >= self.capacity:
                raise QueueBusy("bounded P300 demand queue full")
            now = self.clock()
            ticket = DemandTicket(self._next,kind,now,now+float(ttl_s))
            self._next += 1
            self._pending.append(ticket)
            return ticket

    def pending_count(self) -> int:
        with self._lock:
            self._expire()
            return len(self._pending)

    def cancel(self, ticket: DemandTicket) -> bool:
        with self._lock:
            if type(ticket) is not DemandTicket or ticket not in self._pending:
                return False
            self._pending.remove(ticket)
            ticket.state = TicketState.CANCELLED
            return True

    def select(self, budget, *, initial_p06_age_ms: float) -> DemandSelection | None:
        """Dry-run against caller-supplied deadlines and phase/freshness budget.

        Deliberately does not clear the queue or claim a serial/producer lock.
        The caller must first prove external writer quiescence and perform the
        existing RuntimeAdmissionGate checks before calling reserve().
        """
        self._require_owner()
        from .phase_planner import Budget, ReadJob, plan_phase_windows, PlanRejected
        if type(budget) is not Budget:
            raise SchedulingError("reviewed Budget required")
        if (type(initial_p06_age_ms) not in (int,float)
                or not math.isfinite(initial_p06_age_ms)
                or initial_p06_age_ms < 0):
            raise SchedulingError("explicit valid P06 age required")
        with self._lock:
            self._offered = None
            self._offered_at = None
            self._expire()
            if self._failed_closed or self._reserved is not None:
                return None
            if (self._last_completed is not None
                    and self.clock()-self._last_completed < self.min_spacing_s):
                return None
            if not self._pending:
                return None
            selected = []
            kinds = []
            for ticket in self._pending:
                if ticket.kind not in kinds and len(kinds) >= self.max_distinct_reads:
                    break  # do not starve earlier work by skipping a barrier
                selected.append(ticket)
                if ticket.kind not in kinds:
                    kinds.append(ticket.kind)
            now_ms = self.clock() * 1000
            jobs = tuple(
                ReadJob(kind.value,kind,_P300_ESTIMATED_READ_MS[kind],
                        min(t.expires_at for t in selected if t.kind is kind)*1000,
                        min(t.enqueued_at for t in selected if t.kind is kind)*1000,
                        True) for kind in kinds
            )
            try:
                plan = plan_phase_windows(jobs,budget,now_ms=now_ms,
                       initial_p06_age_ms=initial_p06_age_ms)
            except PlanRejected:
                return None  # no serial IO; deadlines will expire naturally
            if plan.p300_windows != 1 or plan.handovers != 2:
                raise SchedulingError("only one bounded P300 roundtrip allowed")
            selection = DemandSelection(tuple(selected),jobs,plan)
            self._offered = selection
            self._offered_at = self.clock()
            return selection

    def reserve(self, selection: DemandSelection) -> None:
        """Call only AFTER a verified producer fence and runtime admission."""
        self._require_owner()
        if type(selection) is not DemandSelection:
            raise SchedulingError("validated selection required")
        with self._lock:
            if self._reserved is not None or self._failed_closed:
                raise QueueBusy("active or failed demand batch")
            if (selection is not self._offered or self._offered_at is None
                    or not 0 <= self.clock()-self._offered_at <= 1.0):
                raise SchedulingError("untrusted or expired batch selection")
            self._expire()
            if not selection.tickets or any(
                    t not in self._pending or t.state is not TicketState.QUEUED
                    for t in selection.tickets):
                raise SchedulingError("selection expired or no longer pending")
            for t in selection.tickets:
                self._pending.remove(t)
                t.state = TicketState.RUNNING
            self._reserved = selection
            self._offered = None
            self._offered_at = None

    def complete(self, *, success: bool, verified_vs1: bool) -> None:
        """No ticket may be marked successful without an original VS1 proof."""
        self._require_owner()
        if type(success) is not bool or type(verified_vs1) is not bool:
            raise SchedulingError("explicit boolean result required")
        with self._lock:
            if self._reserved is None:
                raise SchedulingError("no reserved demand batch")
            if success and not verified_vs1:
                success = False
            now = self.clock()
            for t in self._reserved.tickets:
                t.state = (TicketState.COMPLETED if now <= t.expires_at
                           else TicketState.EXPIRED) if success else TicketState.FAILED
            if success:
                self._last_completed = now
            else:
                self._failed_closed = True
            self._reserved = None

    @property
    def failed_closed(self) -> bool:
        with self._lock:
            return self._failed_closed


# VS1 P06 provenance is deliberately independent of the P300 scheduler.
# Only raw results from the original synchronous GFA dispatch are accepted.
class OwnerGfaProvenance:
    """Single-owner, generation-scoped P80/P06 proof for a hybrid request.

    Passing a formatted MQTT value, virtual read, FC01 status or P300 memory
    cannot renew either reference. observe_original must be called solely
    after the original legacy GFA dispatcher has actually returned.
    """

    def __init__(self, *, clock=time.monotonic):
        if not callable(clock):
            raise ValueError("clock required")
        self.clock = clock
        self.owner = threading.get_ident()
        self.generation = 1
        self.in_transfer = False
        self.ledger = GfaFreshnessLedger(clock=clock)

    def _require_owner(self):
        if threading.get_ident() != self.owner:
            raise QueueBusy("only the original serial owner may attest GFA")

    @staticmethod
    def _gfa_kind(request) -> ReadKind | None:
        if isinstance(request, str):
            fields = request.split(";")
            if not 3 <= len(fields) <= 5 or fields[0].lower() not in ("gr", "gfaread"):
                return None
            if len(fields) > 3 and fields[3].lower() != "raw":
                return None
            if len(fields) > 4 and fields[4].lower() not in ("false", "0"):
                return None
            addr, size = fields[1:3]
        elif isinstance(request, (list, tuple)) and len(request) == 5:
            # Original normalized poll item: Name, Addr, Len, Scale, Signed.
            name, addr, size, fmt, signed = request
            if (not isinstance(name, str)
                    or not isinstance(fmt, str) or not fmt.lower().startswith("gfa:")
                    or signed is not False):
                return None
        else:
            return None
        try:
            address = int(addr,0) if isinstance(addr,str) else addr
            length = int(size,0) if isinstance(size,str) else size
        except (ValueError, TypeError):
            return None
        if type(address) is not int or type(length) is not int or length != 1:
            return None
        return ({0x4050: ReadKind.VS1_P80,
                 0x4006: ReadKind.VS1_P06}).get(address)

    def observe_original(self, request, response) -> bool:
        """Record a REAL raw original GFA response, or invalidate on failure."""
        self._require_owner()
        kind = self._gfa_kind(request)
        if kind is None:
            return False
        if self.in_transfer:
            self.ledger.invalidate_all()
            raise SchedulingError("legacy GFA response during protocol transfer")
        if (not isinstance(response, tuple) or len(response) != 4
                or type(response[0]) is not int or response[0] != 1
                or not isinstance(response[1], (bytes, bytearray))
                or len(response[1]) != 1):
            self.ledger.invalidate_all()
            return False
        raw = bytes(response[1])
        if raw == b"\xff" or (kind is ReadKind.VS1_P80 and raw != b"\x20"):
            self.ledger.invalidate_all()
            return False
        self.ledger.record(kind, raw, session_generation=self.generation,
                           vs1_verified=True)
        return True

    def require_age_ms(self, *, max_age_ms: float) -> float:
        """Fresh P80 plus fresh P06 required; zero RPM is valid, FF is not."""
        self._require_owner()
        if self.in_transfer:
            raise StaleReading("P300 transfer active")
        if (type(max_age_ms) not in (int,float) or not math.isfinite(max_age_ms)
                or max_age_ms <= 0):
            raise SchedulingError("finite positive age required")
        p80 = self.ledger.fresh(ReadKind.VS1_P80,
                               current_generation=self.generation,
                               max_age_s=max_age_ms/1000)
        if p80.raw != b"\x20":
            raise StaleReading("unverified P80 identity")
        p06 = self.ledger.fresh(ReadKind.VS1_P06,
                               current_generation=self.generation,
                               max_age_s=max_age_ms/1000)
        age_ms = (self.clock() - p06.acquired_at)*1000
        if age_ms < 0 or age_ms > max_age_ms:
            raise StaleReading("invalid P06 acquisition age")
        return age_ms

    def before_transfer(self):
        self._require_owner()
        if self.in_transfer:
            raise SchedulingError("nested protocol transfer forbidden")
        self.ledger.invalidate_all()
        self.in_transfer = True
        self.generation += 1

    def after_verified_return(self, *, p80_hex: str, p06_hex: str):
        """Accept bytes only from the existing verified VS1 runtime result."""
        self._require_owner()
        if not self.in_transfer or not isinstance(p80_hex,str) or not isinstance(p06_hex,str):
            raise SchedulingError("original VS1 verified-return proof required")
        if (p80_hex.lower() != "20" or len(p06_hex) != 2):
            raise SchedulingError("VS1 P80/P06 return identity invalid")
        try:
            p06 = bytes.fromhex(p06_hex)
        except ValueError as exc:
            raise SchedulingError("invalid VS1 P06 return byte") from exc
        if len(p06) != 1 or p06 == b"\xff":
            raise SchedulingError("VS1 P06 return invalid")
        self.ledger.record(ReadKind.VS1_P80,b"\x20",
                           session_generation=self.generation,vs1_verified=True)
        self.ledger.record(ReadKind.VS1_P06,p06,
                           session_generation=self.generation,vs1_verified=True)
        self.in_transfer = False

    def fail_closed(self):
        self._require_owner()
        self.ledger.invalidate_all()
        self.in_transfer = True
