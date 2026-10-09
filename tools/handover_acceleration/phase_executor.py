"""Offline injectable owner: execute a *validated* read-only phase plan.

Use ONLY after a caller has obtained an injected verified coordinator by
`with HandoverCoordinator(fake_open_port, fake_lease) as coordinator`.
This module never imports pySerial, opens a port or controls services.

The limited P300 operation is identity (00F8), not a RAM/FC03 read.
Production dispatcher and write/readback integration are NOT implemented.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .coordinator import DEVICE_ID, HandoverCoordinator, Mode, ProtocolError
from .phase_planner import Budget, PhasePlan, ReadJob, PlanRejected, plan_phase_windows
from .scheduler import GfaFreshnessLedger, ReadKind


class ExecutionRejected(RuntimeError):
    pass


@dataclass(frozen=True)
class ReadResult:
    name: str
    kind: ReadKind
    raw: bytes
    generation: int


@dataclass(frozen=True)
class ExecutionResult:
    plan: PhasePlan
    reads: tuple[ReadResult, ...]
    generation: int
    p300_entry_count: int
    verified_vs1_at_end: bool


VS1_NAME = {
    ReadKind.VS1_P80: 'P80',
    ReadKind.VS1_P06: 'P06',
    ReadKind.VS1_P09: 'P09',
    ReadKind.VS1_P87: 'P87',
}


def execute_read_phases(coordinator: HandoverCoordinator,
                        jobs: Iterable[ReadJob], budget: Budget, *,
                        ledger: GfaFreshnessLedger | None = None,
                        now_ms: float = 0.0,
                        initial_p06_age_ms: float = 0.0) -> ExecutionResult:
    """Execute a typed, dependency-safe plan with a single injected serial owner.

    The schedule is determined BEFORE any IO. An invalid age/deadline fails
    without an extra handshake. The return VS1 handshake refreshes real
    P80 and P06 from the current session, never P09/P10/RAM substitutes.
    If any frame fails, publish no successful batch and invalidate the
    sample ledger. The outer coordinator context owns recovery/close.
    """
    if not isinstance(coordinator, HandoverCoordinator):
        raise ExecutionRejected('verified coordinator instance required')
    if coordinator.mode is not Mode.VS1_VERIFIED or coordinator.wire is None:
        raise ExecutionRejected('current verified VS1 ownership is required')
    if ledger is not None and not isinstance(ledger, GfaFreshnessLedger):
        raise ExecutionRejected('invalid freshness ledger')
    jobs=tuple(jobs)
    plan=plan_phase_windows(jobs,budget,now_ms=now_ms,
                            initial_p06_age_ms=initial_p06_age_ms)
    assert coordinator.mode is Mode.VS1_VERIFIED
    if ledger is None:
        ledger=GfaFreshnessLedger(clock=coordinator.clock)
    # Forbid retained samples from a different prior serial session.
    ledger.invalidate_all()
    generation=1
    p300_windows=0
    results=[]
    by_name={x.name:x for x in jobs}

    def record_current_handshake_p80_p06():
        snap=coordinator.verified_gfa_snapshot(max_age=0.75)
        ledger.record(ReadKind.VS1_P80,snap['P80'],
                      session_generation=generation,vs1_verified=True)
        ledger.record(ReadKind.VS1_P06,snap['P06'],
                      session_generation=generation,vs1_verified=True)

    try:
        record_current_handshake_p80_p06()
        for step in plan.steps:
            if step.kind=='verified_p300_entry':
                if coordinator.mode is not Mode.VS1_VERIFIED:
                    raise ExecutionRejected('attempt to enter P300 outside verified VS1')
                ledger.invalidate_all()
                coordinator.to_p300()   # 1 ENQ + exact 20C2,0103
                generation+=1
                p300_windows+=1
            elif step.kind=='verified_vs1_return':
                if coordinator.mode is not Mode.P300_VERIFIED:
                    raise ExecutionRejected('unexpected VS1 return step')
                ledger.invalidate_all()
                coordinator.to_vs1_fast()  # one ENQ; requires exact ID/SW/GFA
                generation+=1
                record_current_handshake_p80_p06()
            elif step.kind=='read':
                job=by_name.get(step.request)
                if job is None or job.kind.mode!=step.mode:
                    raise ExecutionRejected('plan does not map to typed request')
                if job.kind is ReadKind.P300_ID:
                    if coordinator.mode is not Mode.P300_VERIFIED:
                        raise ExecutionRejected('P300 read in wrong protocol')
                    raw=coordinator.p300_identity()
                    if raw != DEVICE_ID:
                        raise ProtocolError('P300 identity unexpectedly changed')
                else:
                    if coordinator.mode is not Mode.VS1_VERIFIED:
                        raise ExecutionRejected('VS1 GFA read in wrong protocol')
                    raw=coordinator.gfa_read(VS1_NAME[job.kind])
                    ledger.record(job.kind,raw,session_generation=generation,
                                  vs1_verified=True)
                results.append(ReadResult(job.name,job.kind,raw,generation))
            else:
                raise ExecutionRejected('unknown read phase step')
        if coordinator.mode is not Mode.VS1_VERIFIED:
            raise ExecutionRejected('unfinished P300 session')
        if tuple(r.name for r in results)!=plan.request_order:
            raise ExecutionRejected('request count or ordering mismatch')
        return ExecutionResult(plan,tuple(results),generation,p300_windows,True)
    except BaseException:
        ledger.invalidate_all()
        # Propagate: HandoverCoordinator.__exit__ then attempts 2-ENQ
        # conservative recovery if no verified VS1 state exists.
        raise
