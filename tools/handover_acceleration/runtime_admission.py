"""Opt-in read-only VS1/P300 scheduling boundary for an existing serial owner.

No serial device discovery, systemd calls, configuration files or write frames.
An admission *proof* must be provided by the original main loop and all
external write producers. The installed splitter does not yet provide that
proof; therefore recurring hardware maintenance stays disabled.

The gate covers logical multi-message transactions, not merely one complete
serial frame. Even an apparently idle MQTT queue cannot prove that a separate
Party/schedule/maintenance writer has finished its next readback.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import threading
import time
from typing import Callable

from .coordinator import HandoverCoordinator, Mode, PortLease
from .dispatcher_bridge import InProcessDispatchBridge
from .phase_planner import Budget, ReadJob
from .scheduler import ReadKind


class AdmissionRejected(RuntimeError):
    pass


@dataclass(frozen=True)
class DispatcherSnapshot:
    """Owner-created consistent snapshot; no individual flag means 'safe'."""

    mqtt_pending: int
    tcp_pending: int
    forced_polls_pending: int
    pending_readbacks: int
    frame_idle: bool
    external_writers_quiesced: bool
    queue_admission_paused: bool
    legacy_vs1_verified: bool
    nearest_writer_deadline_ms: float

    def __post_init__(self):
        for name in ('mqtt_pending', 'tcp_pending', 'forced_polls_pending',
                     'pending_readbacks'):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise AdmissionRejected('invalid pending queue count: ' + name)
        for name in ('frame_idle', 'external_writers_quiesced',
                     'queue_admission_paused', 'legacy_vs1_verified'):
            if type(getattr(self, name)) is not bool:
                raise AdmissionRejected('explicit boolean evidence required: ' + name)
        deadline = self.nearest_writer_deadline_ms
        if (type(deadline) not in (int, float)
                or not math.isfinite(deadline) or deadline < 0):
            raise AdmissionRejected('writer deadline must be finite and >=0')


@dataclass(frozen=True)
class AdmissionDecision:
    admitted: bool
    reason: str


@dataclass(frozen=True)
class ReadOnlyBatchResult:
    reads: tuple[tuple[str, str], ...]
    p80_hex: str
    p06_hex: str
    elapsed_ms: float
    p300_windows: int
    verified_vs1: bool


# Only fixed, previously hardware-exercised addresses may be read in P300.
READONLY_PRESET = (
    ('p300_device', ReadKind.P300_ID, 85.0),
    ('ram_0f20_32', ReadKind.P300_RAM_0F20_32, 140.0),
    ('ram_1c60_32', ReadKind.P300_RAM_1C60_32, 140.0),
)


def _write_intent(request) -> tuple[int, bytes] | None:
    """Only exact, known VS1 virtual writes can be proven by raw readback.

    A transport ACK is never proof that the controller has applied the value.
    Arbitrary P300 commands, raw serial frames and malformed writes remain
    permanently opaque until an explicit trusted completion.
    """
    if not isinstance(request,str):
        return None
    fields=request.split(";")
    if len(fields)<3 or fields[0].lower() not in (
            "w","write","writeraw","wraw"):
        return None
    try:
        addr=int(fields[1],0)
        if not 0 <= addr <= 0xffff:
            return None
        if fields[0].lower() in ("w","write"):
            if len(fields)!=4:
                return None
            n=int(fields[2],0)
            value=int(fields[3],0)
            if not 1<=n<=32:
                return None
            raw=value.to_bytes(n,"little",signed=value<0)
        else:
            if len(fields)!=3:
                return None
            raw=bytes.fromhex(fields[2].removeprefix("0x"))
            if not 1<=len(raw)<=32:
                return None
        return addr,raw
    except (ValueError, OverflowError):
        return None


def _read_evidence(request, result) -> tuple[int,bytes] | None:
    """Exact successful original VS1 response, not formatted/scaled MQTT."""
    if isinstance(request,str):
        fields=request.split(";")
        if len(fields)<3 or fields[0].lower() not in ("read","r"):
            return None
    elif isinstance(request,(list,tuple)) and len(request)>=3:
        # Already-stripped original poll item (Name, Addr, Len, ...).
        # The MQTT /set forced-refresh machinery uses these very tuples.
        fields=request
    else:
        return None
    try:
        addr = int(fields[1],0) if isinstance(fields[1],str) else fields[1]
        size = int(fields[2],0) if isinstance(fields[2],str) else fields[2]
    except (ValueError,TypeError):
        return None
    if (not 0<=addr<=0xffff or not 1<=size<=32 or
            not isinstance(result,tuple) or len(result)!=4 or
            type(result[0]) is not int or result[0]!=1 or
            not isinstance(result[1],(bytes,bytearray)) or
            len(result[1])!=size):
        return None
    return addr,bytes(result[1])


def _requires_write_fence(request) -> bool:
    """Never interpret arbitrary raw/request traffic as a harmless read."""
    if not isinstance(request, str):
        # Legacy poll tuples are read-only datapoint declarations.
        return not isinstance(request, (list, tuple))
    fields = request.split(';')
    if len(fields) == 1:
        return True
    return fields[0].lower() not in ('read', 'r', 'gfaread', 'gr')


class RuntimeAdmissionGate:
    """Single-threaded main-loop admission. Fail closed after any ambiguity.

    Only a trusted producer integration can release a write fence after its
    complete write + readback/rollback transaction. Elapsed time alone never
    releases a fence. External writers must also acknowledge a quiescent epoch
    that lasts until the batch ends, *including* asynchronous MQTT arrivals.
    """

    def __init__(self, *, clock: Callable[[], float] = time.monotonic,
                 min_write_settle_s: float = 5.25,
                 min_batch_interval_s: float = 120.0):
        if (not callable(clock) or type(min_write_settle_s) not in (float, int)
                or not math.isfinite(min_write_settle_s)
                or min_write_settle_s < 5.0):
            raise AdmissionRejected('write settle window must be >=5 seconds')
        if (type(min_batch_interval_s) not in (int, float)
                or not math.isfinite(min_batch_interval_s)
                or min_batch_interval_s < 30.0):
            raise AdmissionRejected('P300 batch spacing must be >=30 seconds')
        self.clock = clock
        self.owner = threading.get_ident()
        self.min_write_settle_s = float(min_write_settle_s)
        self.min_batch_interval_s = float(min_batch_interval_s)
        self.last_completed_at: float | None = None
        self.last_write_at: float | None = None
        self.unacknowledged_write = False
        self._readback_pending: list[tuple[int,bytes]] = []
        self._opaque_write_pending = False
        self.in_window = False
        self.failed_closed = False
        self.completed_windows = 0

    def _require_owner(self):
        if threading.get_ident() != self.owner:
            raise AdmissionRejected('only the serial-owner main thread may decide')

    def observe_legacy(self, request) -> None:
        self._require_owner()
        if self.in_window:
            self.failed_closed = True
            raise AdmissionRejected('legacy request during P300 batch')
        if _requires_write_fence(request):
            self.last_write_at = self.clock()
            self.unacknowledged_write = True
            intent = _write_intent(request)
            if intent is None:
                self._opaque_write_pending = True
            else:
                self._readback_pending.append(intent)

    def observe_legacy_result(self, request, result) -> None:
        """Recognize ONLY a real, matching post-write read of original bytes.

        A write acknowledgement by itself never clears a fence. An unknown
        frame remains opaque. Multiple writes require multiple matching
        response reads, preventing an unrelated read from ending a group.
        """
        self._require_owner()
        if self.in_window or self.failed_closed:
            raise AdmissionRejected('no result acknowledgements during P300')
        evidence = _read_evidence(request,result)
        if evidence is not None:
            for i,pending in enumerate(self._readback_pending):
                if pending == evidence:
                    self._readback_pending.pop(i)
                    break
        self.unacknowledged_write = bool(
            self._opaque_write_pending or self._readback_pending)

    def acknowledge_external_transaction(self, *, producer_confirmed: bool) -> None:
        self._require_owner()
        if producer_confirmed is not True or self.in_window or self.failed_closed:
            raise AdmissionRejected('explicit trusted write/readback completion required')
        self.unacknowledged_write = False
        self._readback_pending.clear()
        self._opaque_write_pending = False

    def decide(self, snapshot: DispatcherSnapshot, budget: Budget) -> AdmissionDecision:
        self._require_owner()
        if not isinstance(snapshot, DispatcherSnapshot) or not isinstance(budget, Budget):
            raise AdmissionRejected('typed snapshot and budget required')
        if self.failed_closed:
            return AdmissionDecision(False, 'FAILED_CLOSED')
        if self.in_window:
            return AdmissionDecision(False, 'WINDOW_ALREADY_ACTIVE')
        if self.unacknowledged_write:
            return AdmissionDecision(False, 'WRITE_READBACK_NOT_ACKNOWLEDGED')
        if (self.last_completed_at is not None
                and self.clock() - self.last_completed_at < self.min_batch_interval_s):
            return AdmissionDecision(False, 'BATCH_COOLDOWN')
        if (self.last_write_at is not None
                and self.clock() - self.last_write_at < self.min_write_settle_s):
            return AdmissionDecision(False, 'DELAYED_HA_READBACK_SETTLE')
        if not snapshot.external_writers_quiesced:
            return AdmissionDecision(False, 'EXTERNAL_WRITERS_NOT_QUIESCED')
        if not snapshot.queue_admission_paused:
            return AdmissionDecision(False, 'NEW_MQTT_TCP_WRITES_NOT_FENCED')
        if not snapshot.legacy_vs1_verified:
            return AdmissionDecision(False, 'LEGACY_VS1_NOT_VERIFIED')
        if not snapshot.frame_idle:
            return AdmissionDecision(False, 'LEGACY_FRAME_IN_FLIGHT')
        if (snapshot.mqtt_pending or snapshot.tcp_pending
                or snapshot.forced_polls_pending or snapshot.pending_readbacks):
            return AdmissionDecision(False, 'PENDING_LEGACY_WORK')
        if snapshot.nearest_writer_deadline_ms < budget.max_vs1_unavailable_ms:
            return AdmissionDecision(False, 'WRITER_DEADLINE_TOO_CLOSE')
        return AdmissionDecision(True, 'ALL_PRODUCERS_FENCED')

    def run_readonly_batch(self, snapshot: DispatcherSnapshot, budget: Budget, *,
                           port, legacy_dispatch: Callable, resume_vs1: Callable,
                           lease: PortLease,
                           jobs: tuple[ReadJob, ...] | None = None,
                           clock: Callable[[], float] = time.monotonic,
                           sleep: Callable[[float], None] = time.sleep,
                           plan_clock_deadlines: bool = False,
                           initial_p06_age_ms: float = 0.0,
                           ) -> ReadOnlyBatchResult | None:
        """Borrow the SAME existing VS1 handle; no other serial open.

        A refusal performs *zero* serial I/O. Failed dispatch is latched closed.
        Never call from a thread whose queue-producer barrier is not installed.
        """
        decision = self.decide(snapshot, budget)
        if not decision.admitted:
            return None
        if port is None or not callable(legacy_dispatch) or not callable(resume_vs1):
            raise AdmissionRejected('existing port and verified callbacks required')
        if not isinstance(lease, PortLease):
            raise AdmissionRejected('reviewed port lease required')
        if jobs is None:
            jobs = tuple(ReadJob(name, kind, duration_ms=duration,
                                 deadline_ms=15_000.0, independent=True)
                         for name, kind, duration in READONLY_PRESET)
        if not isinstance(jobs, tuple) or not jobs:
            raise AdmissionRejected('only typed finite read-only batches are supported')
        if type(plan_clock_deadlines) is not bool:
            raise AdmissionRejected('absolute deadline mode must be explicit')
        if (type(initial_p06_age_ms) not in (int,float)
                or not math.isfinite(initial_p06_age_ms)
                or initial_p06_age_ms < 0):
            raise AdmissionRejected('invalid P06 age for runtime planner')
        started = clock()
        self.in_window = True
        try:
            manager = HandoverCoordinator.borrow_existing_vs1(
                port, lease, clock=clock, sleep=sleep)
            bridge = InProcessDispatchBridge(
                port, legacy_dispatch, vs1protocol=True, vitoconnect_port=None,
                allow_maintenance=True, resume_vs1=resume_vs1)
            with manager:
                bridge.bind_verified_coordinator(manager)
                # Demand jobs carry absolute monotonic deadlines. Existing
                # preset jobs remain relative to 0 for backwards compatibility.
                _now_ms = clock()*1000 if plan_clock_deadlines else 0.0
                _age_ms = (initial_p06_age_ms+(clock()-started)*1000
                           if plan_clock_deadlines else 0.0)
                result = bridge.execute_maintenance(
                    jobs, budget, now_ms=_now_ms, initial_p06_age_ms=_age_ms)
                if manager.mode is not Mode.VS1_VERIFIED:
                    raise AdmissionRejected('no verified VS1 after batch')
                # Recheck through the actual legacy adapter, never a P300 proxy.
                p80 = _legacy_gfa(bridge, port, 0x4050)
                p06 = _legacy_gfa(bridge, port, 0x4006)
                elapsed_ms = (clock() - started) * 1000
                if elapsed_ms > budget.max_vs1_unavailable_ms:
                    raise AdmissionRejected('observed read-only handover over budget')
                record = ReadOnlyBatchResult(
                    tuple((r.name, r.raw.hex()) for r in result.reads),
                    p80.hex(), p06.hex(), round(elapsed_ms, 3),
                    result.p300_entry_count, True)
            if getattr(port, 'is_open', True) is False:
                raise AdmissionRejected('borrowed legacy port unexpectedly closed')
            self.completed_windows += 1
            self.last_completed_at = self.clock()
            return record
        except BaseException:
            self.failed_closed = True
            raise
        finally:
            self.in_window = False


def _legacy_gfa(bridge: InProcessDispatchBridge, port, address: int) -> bytes:
    ret = bridge.response_to_request(f'gfaread;0x{address:04x};1;raw;False', port)
    if not isinstance(ret, tuple) or len(ret) != 4 or ret[0] != 1:
        raise AdmissionRejected('legacy GFA status not confirmed')
    data = ret[1]
    if not isinstance(data, (bytes, bytearray)) or len(data) != 1 or data == b'\xff':
        raise AdmissionRejected('legacy GFA byte absent or invalid')
    if address == 0x4050 and data != b'\x20':
        raise AdmissionRejected('legacy P80 identity mismatch')
    return bytes(data)
