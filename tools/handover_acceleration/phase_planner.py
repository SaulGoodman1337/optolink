"""Offline cost-aware, dependency-constrained VS1/P300 phase planner.

This is NOT a serial executor. It never opens ports or changes a boiler.
The only available P300 operations are verified identity and explicitly
reviewed, fixed-size FC03 diagnostic reads. Arbitrary RAM and writes are blocked.

All timings are caller-supplied engineering budgets, NOT guaranteed upper
bounds, since the WB2A firmware response has no proven maximum latency.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

from .scheduler import ReadKind


class PlanRejected(ValueError):
    """No phase ordering satisfies the declared dependency/freshness limits."""


def _finite_number(value: float, key: str, *, min_value: float = 0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PlanRejected(f'{key} must be numeric')
    if not math.isfinite(value) or value < min_value:
        raise PlanRejected(f'{key} must be finite and >= {min_value}')
    return float(value)


@dataclass(frozen=True)
class Budget:
    """Engineering budgets for verified mode transitions, in milliseconds.

    enter_p300_ms and return_vs1_ms include original identity verification.
    Data reads and the final GFA payload are accounted separately by jobs.
    """
    enter_p300_ms: float = 2175.657
    return_vs1_ms: float = 2295.102
    max_vs1_unavailable_ms: float = 10000.0
    max_p06_age_ms: float = 10000.0
    max_queue_wait_ms: float = 10000.0

    def __post_init__(self):
        for key in ('enter_p300_ms', 'return_vs1_ms'):
            _finite_number(getattr(self, key), key, min_value=0.001)
        for key in ('max_vs1_unavailable_ms', 'max_p06_age_ms',
                    'max_queue_wait_ms'):
            _finite_number(getattr(self, key), key, min_value=0.001)


@dataclass(frozen=True)
class ReadJob:
    """A read with explicitly reviewed independence and external deadlines.

    independent=True is a caller *claim* that the operation may move within
    its contiguous independent region. False is an ordering barrier. It is
    never permitted to reorder across a barrier, or to include writes.
    """
    name: str
    kind: ReadKind
    duration_ms: float
    deadline_ms: float
    queued_ms: float = 0.0
    independent: bool = False

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name or len(self.name) > 120:
            raise PlanRejected('invalid job name')
        if not isinstance(self.kind, ReadKind):
            raise PlanRejected('only enumerated read-only jobs are supported')
        if not isinstance(self.independent, bool):
            raise PlanRejected('independence requires a boolean')
        _finite_number(self.duration_ms, 'duration_ms', min_value=0.001)
        _finite_number(self.deadline_ms, 'deadline_ms')
        _finite_number(self.queued_ms, 'queued_ms')
        if self.deadline_ms < self.queued_ms:
            raise PlanRejected('deadline precedes enqueue time')


@dataclass(frozen=True)
class PlanStep:
    name: str
    kind: str
    mode: str
    started_ms: float
    finished_ms: float
    request: str | None = None


@dataclass(frozen=True)
class PhasePlan:
    steps: tuple[PlanStep, ...]
    request_order: tuple[str, ...]
    handovers: int
    p300_windows: int
    duration_ms: float
    max_p06_gap_ms: float
    max_vs1_unavailable_ms: float
    status: str = 'SIMULATED_ONLY_NO_HARDWARE_TIMING_GUARANTEE'


def _dependency_safe_order(jobs: tuple[ReadJob, ...], initial: str) -> list[ReadJob]:
    result: list[ReadJob] = []
    i = 0
    mode = initial
    while i < len(jobs):
        if not jobs[i].independent:
            result.append(jobs[i]); mode = jobs[i].kind.mode; i += 1
            continue
        j = i
        while j < len(jobs) and jobs[j].independent:
            j += 1
        epoch = jobs[i:j]
        # Reordering *within* an explicitly independent epoch; stable among
        # jobs of the same protocol, and never crosses an ordered barrier.
        same = [r for r in epoch if r.kind.mode == mode]
        other = [r for r in epoch if r.kind.mode != mode]
        result.extend(same + other)
        if other:
            mode = other[-1].kind.mode
        i = j
    return result


def plan_phase_windows(jobs: Iterable[ReadJob], budget: Budget, *,
                       now_ms: float = 0.0, initial_p06_age_ms: float = 0.0,
                       initial_mode: str = 'vs1') -> PhasePlan:
    """Construct a deterministic plan, or refuse unsafe deadlines/freshness.

    All jobs must be already queued. The model begins with a *currently*
    verified VS1 session and ends with a verified VS1 session. No ancient
    protocol state or P06 byte may be reused after a transition.
    """
    if not isinstance(budget, Budget):
        raise PlanRejected('Budget required')
    if initial_mode != 'vs1':
        raise PlanRejected('initial state must be verified VS1')
    now = _finite_number(now_ms, 'now_ms')
    initial_age = _finite_number(initial_p06_age_ms, 'initial_p06_age_ms')
    if initial_age > budget.max_p06_age_ms:
        raise PlanRejected('initial P06 freshness already expired')
    jobs = tuple(jobs)
    if len(jobs) > 1000:
        raise PlanRejected('bounded planning only')
    for r in jobs:
        if not isinstance(r, ReadJob):
            raise PlanRejected('all jobs must be reviewed ReadJob instances')
        if r.queued_ms > now:
            raise PlanRejected('not-yet-arrived jobs cannot be planned')
    if len({r.name for r in jobs}) != len(jobs):
        raise PlanRejected('ambiguous duplicate job identity')
    planned = _dependency_safe_order(jobs, initial_mode)
    steps: list[PlanStep] = []
    mode = initial_mode
    t = now
    last_p06 = now - initial_age
    absence_started: float | None = None
    windows, handovers = 0, 0
    max_gap, max_absence = initial_age, 0.0

    def stage(kind: str, mode_label: str, duration: float, request: str | None = None):
        nonlocal t
        start = t; t += duration
        steps.append(PlanStep(request or kind, kind, mode_label, start, t, request))

    def return_vs1():
        nonlocal mode, absence_started, handovers, last_p06, max_gap, max_absence
        if mode != 'p300':
            return
        stage('verified_vs1_return', 'vs1', budget.return_vs1_ms)
        handovers += 1
        absence = t - absence_started
        gap = t - last_p06
        max_absence = max(max_absence, absence)
        max_gap = max(max_gap, gap)
        if absence > budget.max_vs1_unavailable_ms:
            raise PlanRejected('P300 window exceeds maximum VS1 unavailability')
        if gap > budget.max_p06_age_ms:
            raise PlanRejected('fresh real VS1 P06 cannot be maintained through P300')
        mode = 'vs1'
        absence_started = None
        # The return verification includes an actual fresh GFA P06 read.
        last_p06 = t

    for job in planned:
        if job.kind.mode == 'vs1':
            return_vs1()
        else:
            if mode == 'vs1':
                absence_started = t
                stage('verified_p300_entry', 'p300', budget.enter_p300_ms)
                mode = 'p300'
                windows += 1
                handovers += 1
        if t - job.queued_ms > budget.max_queue_wait_ms:
            raise PlanRejected('maximum queued request wait exceeded: ' + job.name)
        if t + job.duration_ms > job.deadline_ms:
            raise PlanRejected('request would finish after deadline: ' + job.name)
        stage('read', job.kind.mode, job.duration_ms, job.name)
        if job.kind is ReadKind.VS1_P06:
            last_p06 = t
        # If a VS1 task runs after freshness expired, it must not be
        # represented as a timely previous sample. A fresh VS1 P06 may
        # legitimately be the operation which renews it.
        if job.kind.mode == 'vs1' and t - last_p06 > budget.max_p06_age_ms:
            raise PlanRejected('P06 freshness exceeded in VS1 scheduling')
    return_vs1()
    return PhasePlan(tuple(steps), tuple(r.name for r in planned), handovers,
                     windows, t-now, max_gap, max_absence)
