"""Opt-in continuous *read-only* P300 windows in the original VS1 serial owner.

The caller is the **original** single serial main loop. Nothing here opens a
serial port, starts a service or sends writes. A window requires, atomically:

* an operator-reviewed attestation of all external writer programs;
* a frozen MQTT callback/TCP ingress epoch;
* exclusive kernel producer lock with EMPTY persistent failure marker;
* NO pending MQTT/TCP command or delayed HA write readback;
* very recent successful original VS1 keepalive;
* original gate's write-settle, cooldown and frame/identity checks.

On any actual protocol error the gate fails closed and the caller MUST
terminate its hybrid worker and invoke independent serial recovery. A producer
lock refusal by itself is harmless and sends NO controller frame.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading
import time
from typing import Callable, Any

from .coordinator import PortLease
from .ingress_epoch import IngressEpoch, IngressRejected
from .phase_planner import Budget
from .producer_fence import (
    LEASE_PATH, ProducerFenceRejected, p300_window,
)
from .runtime_admission import (
    RuntimeAdmissionGate, DispatcherSnapshot, ReadOnlyBatchResult,
)


class ContinuousRuntimeRejected(RuntimeError):
    pass


@dataclass(frozen=True)
class TickOutcome:
    status: str
    result: ReadOnlyBatchResult | None = None
    reason: str = ""


class ContinuousReadonlyRuntime:
    """Never construct without an explicit verified producer attestor."""

    def __init__(self, *, port, legacy_dispatch: Callable,
                 resume_vs1: Callable, mqtt, tcp_state: Callable,
                 ingress: IngressEpoch, all_writers_attested: Callable[[], bool],
                 lease_path: Path = LEASE_PATH,
                 serial_lease_path: Path = Path('/var/lib/optolink-hybrid/serial.lease'),
                 budget: Budget | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep,
                 min_interval_s: float = 120.0):
        if (port is None or not callable(legacy_dispatch)
                or not callable(resume_vs1)
                or not isinstance(ingress, IngressEpoch)
                or not callable(all_writers_attested)
                or not callable(tcp_state)
                or getattr(mqtt, '_hybrid_readback_ledger', None) is None):
            raise ContinuousRuntimeRejected('missing original owner, callback or HA ledger')
        if type(min_interval_s) not in (int,float) or min_interval_s < 60:
            raise ContinuousRuntimeRejected('minimum recurring interval 60 seconds')
        if not isinstance(lease_path, Path) or not isinstance(serial_lease_path,Path):
            raise ContinuousRuntimeRejected('reviewed physical lease paths required')
        self.owner = threading.get_ident()
        self.port = port
        self.legacy_dispatch = legacy_dispatch
        self.resume_vs1 = resume_vs1
        self.mqtt = mqtt
        self.tcp_state = tcp_state
        self.ingress = ingress
        self.all_writers_attested = all_writers_attested
        self.lease_path = lease_path
        self.serial_lease_path = serial_lease_path
        self.budget = budget if budget is not None else Budget()
        self.clock,self.sleep = clock,sleep
        self.min_interval_s=float(min_interval_s)
        self.gate = RuntimeAdmissionGate(clock=clock,min_batch_interval_s=min_interval_s)
        self.next_due = clock() + min_interval_s
        self.last_keepalive_at:float|None=None
        self.last_refusal = 'STARTUP_WARMUP'
        self.last_result:ReadOnlyBatchResult|None=None

    def _assert_owner(self):
        if threading.get_ident()!=self.owner:
            raise ContinuousRuntimeRejected('only original serial owner may drive P300')

    def note_keepalive(self, retcode: int) -> None:
        self._assert_owner()
        if type(retcode) is int and retcode == 1:
            self.last_keepalive_at=self.clock()
        else:
            # No stale success may be reused as a valid handover precondition.
            self.last_keepalive_at=None

    def observe_legacy(self, request) -> None:
        self._assert_owner()
        self.gate.observe_legacy(request)

    def _snapshot(self) -> DispatcherSnapshot:
        ledger=self.mqtt._hybrid_readback_ledger
        mqtt_pending=getattr(self.mqtt, 'cmnd_queue', None)
        forced=getattr(self.mqtt, 'lst_force_refresh', None)
        tcp_pending=self.tcp_state()
        if (not isinstance(mqtt_pending,list)
                or not isinstance(forced,list)
                or type(tcp_pending) is not int or tcp_pending<0
                or self.ingress.tcp_overflow):
            raise ContinuousRuntimeRejected('inconsistent MQTT/TCP queue topology')
        fresh=(self.last_keepalive_at is not None
               and 0 <= self.clock()-self.last_keepalive_at <= 2.0)
        if not getattr(self.port,'is_open', True):
            fresh=False
        # Only the in-loop owner can supply frame_idle. Here every preceding
        # synchronous legacy serial request is already complete.
        return DispatcherSnapshot(
            mqtt_pending=len(mqtt_pending),
            tcp_pending=tcp_pending,
            forced_polls_pending=len(forced),
            pending_readbacks=ledger.pending_count,
            frame_idle=True,
            external_writers_quiesced=True,
            queue_admission_paused=(self.ingress.freeze_depth==1),
            legacy_vs1_verified=fresh,
            # Every enrolled cooperative writer waits at least 15 seconds.
            nearest_writer_deadline_ms=15_000.0,
        )

    def tick(self) -> TickOutcome:
        self._assert_owner()
        if self.gate.failed_closed:
            return TickOutcome('FAIL_CLOSED',reason='previous protocol failure')
        now=self.clock()
        if now < self.next_due:
            return TickOutcome('NOT_DUE',reason='bounded background cadence')
        # Failed admission must not busy-loop. Try again after a shorter
        # interval, but never run two successful batches within cooldown.
        self.next_due = now + min(15.0,self.min_interval_s)
        if not self.all_writers_attested():
            self.last_refusal='WRITER_ENROLMENT_NOT_ATTESTED'
            return TickOutcome('NOT_ADMITTED',reason=self.last_refusal)
        if self.last_keepalive_at is None or now-self.last_keepalive_at >2.0:
            self.last_refusal='LEGACY_KEEPALIVE_NOT_FRESH'
            return TickOutcome('NOT_ADMITTED',reason=self.last_refusal)

        with self.ingress.freeze():
            try:
                with p300_window(path=self.lease_path) as proof:
                    ledger=self.mqtt._hybrid_readback_ledger
                    if ledger.failed_closed:
                        self.gate.failed_closed=True
                        return TickOutcome('FAIL_CLOSED',reason='HA_READBACK_FAILED')
                    if ledger.pending_count:
                        self.last_refusal='HA_READBACK_PENDING'
                        return TickOutcome('NOT_ADMITTED',reason=self.last_refusal)
                    snapshot=self._snapshot()
                    decision=self.gate.decide(snapshot,self.budget)
                    if not decision.admitted:
                        self.last_refusal=decision.reason
                        return TickOutcome('NOT_ADMITTED',reason=decision.reason)
                    # Persist the in-flight P300 state BEFORE the first
                    # potentially protocol-changing EOT. SIGKILL cannot
                    # clear the marker and accidentally release a writer.
                    proof.begin()
                    result=self.gate.run_readonly_batch(
                        snapshot,self.budget,
                        port=self.port,legacy_dispatch=self.legacy_dispatch,
                        resume_vs1=self.resume_vs1,
                        lease=PortLease(self.serial_lease_path),
                        clock=self.clock,sleep=self.sleep)
                    if result is None or not result.verified_vs1:
                        raise ContinuousRuntimeRejected(
                            'no original VS1 readback after P300 window')
                    proof.confirm_verified_vs1()
            except ProducerFenceRejected as exc:
                self.last_refusal='WRITER_LEASE_BUSY_OR_UNVERIFIED'
                return TickOutcome('NOT_ADMITTED',reason=self.last_refusal)
            except BaseException:
                self.gate.failed_closed=True
                raise
        self.last_result=result
        self.next_due=self.clock()+self.min_interval_s
        self.last_keepalive_at=self.clock()  # verified final legacy P80/P06
        self.last_refusal=''
        return TickOutcome('VERIFIED_SWITCH',result=result)



@dataclass(frozen=True)
class DemandReply:
    """Raw diagnostic from one fully recovered, nonexpired P300 ticket."""
    sequence: int
    kind: str
    raw_hex: str
    origin: str = "P300_RAW_DIAGNOSTIC_NOT_ACTUAL_RPM"


@dataclass(frozen=True)
class DemandTickOutcome:
    status: str
    reason: str = ""
    replies: tuple[DemandReply, ...] = ()
    result: ReadOnlyBatchResult | None = None


class OnDemandReadonlyRuntime(ContinuousReadonlyRuntime):
    """Opt-in, single-serial-owner demand path; never schedules itself.

    Only an explicitly bound original main-loop integration can call tick().
    Ingress admission and the complete external producer epoch are checked
    again under the same exclusive freeze/producer lock as the existing
    continuous read-only canary, not via a second serial connection.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        from .scheduler import BoundedDemandBatcher, OwnerGfaProvenance
        self.demands = BoundedDemandBatcher(
            clock=self.clock, min_spacing_s=self.min_interval_s)
        self.provenance = OwnerGfaProvenance(clock=self.clock)
        self.next_due = self.clock()
        self._last_replies: tuple[DemandReply, ...] = ()

    def submit_internal(self, kind, *, ttl_s: float = 30.0):
        """Typed internal API, NEVER a generic MQTT/TCP raw-frame parser."""
        return self.demands.submit(kind, ttl_s=ttl_s)

    def observe_original_result(self, request, response) -> bool:
        """Only post original synchronous VS1 GFA_READ, never a P300 proxy."""
        self._assert_owner()
        return self.provenance.observe_original(request, response)

    def due(self) -> bool:
        self._assert_owner()
        return (not self.gate.failed_closed
                and not self.demands.failed_closed
                and self.demands.pending_count() > 0
                and self.clock() >= self.next_due)

    @staticmethod
    def _validate_raw(result, selection) -> dict[str, str]:
        from .scheduler import ReadKind
        expected = {job.name: job.kind for job in selection.jobs}
        received = dict(result.reads)
        if len(received) != len(result.reads) or set(received) != set(expected):
            raise ContinuousRuntimeRejected("P300 diagnostic count/address mismatch")
        for name, kind in expected.items():
            value = received[name]
            if (not isinstance(value,str)
                    or len(value) != (4 if kind is ReadKind.P300_ID else 64)):
                raise ContinuousRuntimeRejected("P300 raw length not verified")
            try:
                raw = bytes.fromhex(value)
            except ValueError as exc:
                raise ContinuousRuntimeRejected("P300 raw hex invalid") from exc
            if kind is ReadKind.P300_ID and raw != bytes.fromhex("20c2"):
                raise ContinuousRuntimeRejected("P300 identity mismatch")
        return received

    def tick(self) -> DemandTickOutcome:
        from .scheduler import StaleReading
        self._assert_owner()
        if self.gate.failed_closed or self.demands.failed_closed:
            return DemandTickOutcome("FAIL_CLOSED", reason="previous protocol failure")
        if self.demands.pending_count() == 0:
            return DemandTickOutcome("NO_DEMAND",reason="read-only queue empty")
        now=self.clock()
        if now < self.next_due:
            return DemandTickOutcome("NOT_DUE",reason="bounded admission backoff")
        self.next_due = now + 3.0
        if not self.all_writers_attested():
            return DemandTickOutcome("NOT_ADMITTED",
                                     reason="WRITER_ENROLMENT_NOT_ATTESTED")
        if self.last_keepalive_at is None or not 0 <= now-self.last_keepalive_at <= 2.0:
            return DemandTickOutcome("NOT_ADMITTED",reason="LEGACY_KEEPALIVE_NOT_FRESH")
        try:
            age_ms=self.provenance.require_age_ms(
                max_age_ms=self.budget.max_p06_age_ms)
        except StaleReading:
            return DemandTickOutcome("NOT_ADMITTED",reason="REAL_GFA_P06_NOT_FRESH")
        selected=self.demands.select(self.budget,initial_p06_age_ms=age_ms)
        if selected is None:
            return DemandTickOutcome("NOT_ADMITTED",
                                     reason="DEADLINE_OR_P06_BUDGET_REJECTED")

        with self.ingress.freeze():
            try:
                with p300_window(path=self.lease_path) as proof:
                    ha_ledger=self.mqtt._hybrid_readback_ledger
                    if ha_ledger.failed_closed:
                        self.gate.failed_closed=True
                        return DemandTickOutcome("FAIL_CLOSED",
                                                 reason="HA_READBACK_FAILED")
                    if ha_ledger.pending_count:
                        return DemandTickOutcome("NOT_ADMITTED",
                                                 reason="HA_READBACK_PENDING")
                    snapshot=self._snapshot()
                    decision=self.gate.decide(snapshot,self.budget)
                    if not decision.admitted:
                        return DemandTickOutcome("NOT_ADMITTED",
                                                 reason=decision.reason)
                    # Recheck under the frozen ingress and producer lock.
                    try:
                        fresh_age=self.provenance.require_age_ms(
                            max_age_ms=self.budget.max_p06_age_ms)
                    except StaleReading:
                        return DemandTickOutcome("NOT_ADMITTED",
                                                 reason="REAL_GFA_P06_NOT_FRESH")
                    selection=self.demands.select(
                        self.budget,initial_p06_age_ms=fresh_age)
                    if selection is None:
                        return DemandTickOutcome("NOT_ADMITTED",
                                                 reason="DEADLINE_OR_P06_BUDGET_REJECTED")
                    self.demands.reserve(selection)
                    try:
                        self.provenance.before_transfer()
                        # Persist the crash-proof P300 marker before any EOT.
                        proof.begin()
                        result=self.gate.run_readonly_batch(
                            snapshot,self.budget,
                            port=self.port,legacy_dispatch=self.legacy_dispatch,
                            resume_vs1=self.resume_vs1,
                            lease=PortLease(self.serial_lease_path),
                            jobs=selection.jobs,
                            clock=self.clock,sleep=self.sleep,
                            plan_clock_deadlines=True,
                            initial_p06_age_ms=fresh_age)
                        if result is None or result.verified_vs1 is not True:
                            raise ContinuousRuntimeRejected(
                                "P300 return identity/P80/P06 not verified")
                        received=self._validate_raw(result,selection)
                        self.provenance.after_verified_return(
                            p80_hex=result.p80_hex,p06_hex=result.p06_hex)
                        proof.confirm_verified_vs1()
                        self.demands.complete(success=True,verified_vs1=True)
                        replies=tuple(
                            DemandReply(ticket.sequence,ticket.kind.value,
                                        received[ticket.kind.value])
                            for ticket in selection.tickets
                            if ticket.state.value == "completed")
                    except BaseException:
                        self.provenance.fail_closed()
                        self.gate.failed_closed=True
                        if any(t.state.value == "running" for t in selection.tickets):
                            self.demands.complete(success=False,verified_vs1=False)
                        raise
            except ProducerFenceRejected:
                return DemandTickOutcome("NOT_ADMITTED",
                                         reason="WRITER_LEASE_BUSY_OR_UNVERIFIED")
            except BaseException:
                self.gate.failed_closed=True
                self.provenance.fail_closed()
                raise
        self.last_result=result
        self._last_replies=replies
        self.next_due=self.clock()+self.min_interval_s
        self.last_keepalive_at=self.clock()
        return DemandTickOutcome("VERIFIED_SWITCH",replies=replies,result=result)
