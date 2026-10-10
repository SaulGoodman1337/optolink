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
