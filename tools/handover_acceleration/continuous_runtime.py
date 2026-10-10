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

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
import json
import os
import re
import secrets
import socket
import stat
import struct
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


# The only optional external demand ingress. It is a local root-authenticated
# control plane, never a second serial owner and never an MQTT/TCP raw bridge.
DEMAND_SOCKET_PATH = Path("/run/optolink-hybrid/p300-demand.sock")
_DEMAND_ID = re.compile(r"[0-9a-f]{32}\Z")
_DEMAND_KINDS = {
    "p300_identity": "P300_ID",
    "p300_ram_0f20_32": "P300_RAM_0F20_32",
    "p300_ram_1c60_32": "P300_RAM_1C60_32",
    "p300_ram_1640_32": "P300_RAM_1640_32",
}


class DemandControlRejected(RuntimeError):
    pass


class LocalDemandControl:
    """Bounded SOCK_SEQPACKET RPC, driven ONLY by the VS1 serial main loop.

    The process remains optolink. SO_PEERCRED must prove root for each
    connection. This is an operator-only boundary, NOT HA/MQTT authorization.
    Both processing and result publication happen on the serial-owner thread;
    no socket callback or other thread can emit a physical protocol frame.
    """

    MAX_RECORDS = 128
    MAX_SESSION_IDS = 1024  # prevent reexecution of retired idempotency keys
    MAX_CLIENTS = 8
    MAX_PACKET = 512
    KEEP_RESULT_S = 180.0

    def __init__(self, runtime: OnDemandReadonlyRuntime, *,
                 path: Path = DEMAND_SOCKET_PATH,
                 clock: Callable[[], float] = time.monotonic):
        if (type(runtime) is not OnDemandReadonlyRuntime or
                not isinstance(path, Path) or not path.is_absolute() or
                not callable(clock)):
            raise DemandControlRejected("typed owner and absolute local socket required")
        runtime._assert_owner()
        self.runtime = runtime
        self.owner = threading.get_ident()
        self.path = path
        self.clock = clock
        self.epoch = secrets.token_hex(16)
        self.records: OrderedDict[str, dict] = OrderedDict()
        self.seen_ids: set[str] = set()
        self.server: socket.socket | None = None
        self.clients: dict[socket.socket, float] = {}
        self._bound_inode: int | None = None

    def _owner_only(self):
        if threading.get_ident() != self.owner:
            raise DemandControlRejected("only serial-owner may operate demand gateway")

    @staticmethod
    def _peer_uid(client: socket.socket) -> int:
        # Linux kernel credentials, not client-provided JSON or environment.
        data = client.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED,
                                 struct.calcsize("3i"))
        pid, uid, _gid = struct.unpack("3i", data)
        if pid <= 0:
            raise DemandControlRejected("unidentified local client")
        return uid

    def start(self):
        self._owner_only()
        if self.server is not None:
            raise DemandControlRejected("socket already bound")
        parent = self.path.parent
        try:
            pstat = parent.lstat()
        except OSError as exc:
            raise DemandControlRejected("explicit private runtime directory absent") from exc
        if (not stat.S_ISDIR(pstat.st_mode) or pstat.st_uid != os.geteuid()
                or pstat.st_mode & 0o077 or parent.resolve() != parent):
            raise DemandControlRejected("runtime socket directory not owner-private")
        if self.path.exists() or self.path.is_symlink():
            raise DemandControlRejected("refusing existing socket or symlink")
        server = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        bound_here = False
        try:
            server.setblocking(False)
            server.bind(str(self.path))
            bound_here = True
            os.chmod(self.path, 0o600)
            server.listen(self.MAX_CLIENTS)
            bound = self.path.lstat()
            if not stat.S_ISSOCK(bound.st_mode) or bound.st_uid != os.geteuid():
                raise DemandControlRejected("created socket ownership invalid")
            self._bound_inode = bound.st_ino
            self.server = server
        except BaseException:
            server.close()
            if bound_here:
                try:
                    bound = self.path.lstat()
                    if bound.st_uid == os.geteuid() and stat.S_ISSOCK(bound.st_mode):
                        self.path.unlink()
                except FileNotFoundError:
                    pass
            raise

    def _unlink_own_socket(self):
        if self._bound_inode is None:
            return
        try:
            current = self.path.lstat()
            if (current.st_ino == self._bound_inode
                    and current.st_uid == os.geteuid()
                    and stat.S_ISSOCK(current.st_mode)):
                self.path.unlink()
        except FileNotFoundError:
            pass
        self._bound_inode = None

    def close(self):
        self._owner_only()
        for conn in tuple(self.clients):
            conn.close()
        self.clients.clear()
        if self.server is not None:
            self.server.close()
            self.server = None
        self._unlink_own_socket()

    @staticmethod
    def _pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise DemandControlRejected("duplicate JSON member")
            result[key] = value
        return result

    @staticmethod
    def _error(code: str) -> dict:
        return {"v": 1, "ok": False, "error": code}

    @staticmethod
    def _send(conn: socket.socket, payload: dict):
        try:
            wire = json.dumps(payload, sort_keys=True,
                              separators=(",", ":")).encode("utf-8")
            conn.send(wire)
        except (BrokenPipeError, ConnectionError, BlockingIOError, OSError):
            pass


    def _prune(self):
        self.runtime.demands.pending_count()  # advances QUEUED -> EXPIRED
        now = self.clock()
        for request_id, record in tuple(self.records.items()):
            if (record["ticket"].state.value not in ("queued", "running")
                    and now - record["submitted_at"] > self.KEEP_RESULT_S):
                del self.records[request_id]
        for conn, until in tuple(self.clients.items()):
            if now > until:
                self._send(conn, self._error("CLIENT_TIMEOUT"))
                self._drop(conn)

    def _drop(self, conn: socket.socket):
        self.clients.pop(conn, None)
        conn.close()

    def _status(self, request_id: str, *, epoch: str) -> dict:
        if epoch != self.epoch:
            return self._error("STALE_SESSION")
        record = self.records.get(request_id)
        if record is None:
            return self._error("UNKNOWN_REQUEST")
        state = record["ticket"].state.value
        # Never claim completion until fully verified result was attached.
        if state == "completed" and record["result"] is None:
            return self._error("UNVERIFIED_RESULT")
        row = {
            "v": 1, "ok": True, "session": self.epoch,
            "request_id": request_id, "state": state,
            "kind": record["kind"], "expires_at_monotonic": record["ticket"].expires_at,
        }
        if state == "completed":
            row["result"] = record["result"]
        if state == "queued" and record.get("last_refusal"):
            row["last_refusal"] = record["last_refusal"]
        return row

    def _dispatch(self, raw: bytes) -> dict:
        if not raw or len(raw) > self.MAX_PACKET:
            return self._error("INVALID_PACKET_SIZE")
        try:
            msg = json.loads(raw.decode("utf-8"), object_pairs_hook=self._pairs,
                             parse_constant=lambda _v: (_ for _ in ()).throw(
                                 DemandControlRejected("invalid JSON constant")))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError,
                DemandControlRejected):
            return self._error("INVALID_JSON")
        if type(msg) is not dict or type(msg.get("v")) is not int or msg["v"] != 1:
            return self._error("INVALID_VERSION")
        op = msg.get("op")
        request_id = msg.get("request_id")
        if (type(request_id) is not str or not _DEMAND_ID.fullmatch(request_id)):
            return self._error("INVALID_REQUEST_ID")
        if op == "submit":
            if set(msg) != {"v", "op", "request_id", "kind", "ttl_s"}:
                return self._error("INVALID_FIELDS")
            kind, ttl_s = msg["kind"], msg["ttl_s"]
            if type(kind) is not str or kind not in _DEMAND_KINDS:
                return self._error("READ_KIND_FORBIDDEN")
            if type(ttl_s) is not int or not 5 <= ttl_s <= 120:
                return self._error("TTL_OUT_OF_RANGE")
            found = self.records.get(request_id)
            if found is not None:
                if found["kind"] != kind or found["ttl_s"] != ttl_s:
                    return self._error("IDEMPOTENCY_CONFLICT")
                return self._status(request_id, epoch=self.epoch)
            # A pruned/expired session ID must not be reused for a second
            # physical P300 roundtrip during the same process generation.
            if request_id in self.seen_ids:
                return self._error("REQUEST_ID_RETIRED")
            self._prune()
            if len(self.records) >= self.MAX_RECORDS:
                return self._error("RECORDS_FULL")
            if len(self.seen_ids) >= self.MAX_SESSION_IDS:
                return self._error("SESSION_REQUEST_LIMIT")
            from .scheduler import ReadKind, QueueBusy, SchedulingError
            if self.runtime.gate.failed_closed or self.runtime.demands.failed_closed:
                return self._error("HYBRID_FAILED_CLOSED")
            try:
                ticket = self.runtime.submit_internal(
                    ReadKind[_DEMAND_KINDS[kind]], ttl_s=ttl_s)
            except (QueueBusy, SchedulingError):
                return self._error("DEMAND_QUEUE_FULL_OR_CLOSED")
            self.records[request_id] = {
                "kind": kind, "ttl_s": ttl_s, "ticket": ticket,
                "submitted_at": self.clock(), "result": None, "last_refusal": None,
            }
            self.seen_ids.add(request_id)
            return self._status(request_id, epoch=self.epoch)
        if op in ("status", "cancel"):
            if set(msg) != {"v", "op", "request_id", "session"}:
                return self._error("INVALID_FIELDS")
            session = msg["session"]
            if type(session) is not str or not _DEMAND_ID.fullmatch(session):
                return self._error("INVALID_SESSION")
            if op == "cancel":
                if session != self.epoch:
                    return self._error("STALE_SESSION")
                record = self.records.get(request_id)
                if record is None:
                    return self._error("UNKNOWN_REQUEST")
                if not self.runtime.demands.cancel(record["ticket"]):
                    return self._error("NOT_CANCELLABLE")
            return self._status(request_id, epoch=session)
        return self._error("OPERATION_FORBIDDEN")

    def poll(self):
        """No blocking, no background threads; max four RPCs per VS1 loop."""
        self._owner_only()
        if self.server is None:
            raise DemandControlRejected("control plane not started")
        self._prune()
        for _ in range(4):
            if len(self.clients) >= self.MAX_CLIENTS:
                break
            try:
                conn, _addr = self.server.accept()
            except BlockingIOError:
                break
            conn.setblocking(False)
            try:
                authorized = self._peer_uid(conn) == 0
            except (OSError, DemandControlRejected):
                authorized = False
            if not authorized:
                # Drain one bounded packet: Linux SEQPACKET may reset the
                # connection on close when unread frames are queued.
                try:
                    conn.recv(self.MAX_PACKET + 1)
                except (OSError, BlockingIOError):
                    pass
                self._send(conn, self._error("ROOT_PEER_REQUIRED"))
                conn.close()
                continue
            self.clients[conn] = self.clock() + 1.0
        for conn in tuple(self.clients)[:4]:
            try:
                raw = conn.recv(self.MAX_PACKET + 1)
            except BlockingIOError:
                continue
            except OSError:
                self._drop(conn)
                continue
            if not raw:
                self._drop(conn)
                continue
            try:
                response = self._dispatch(raw)
            except Exception:
                # Internal control-plane errors must never produce phantom
                # admission or successes. Existing serial control is retained.
                response = self._error("INTERNAL_ERROR")
            self._send(conn, response)
            self._drop(conn)

    def note_outcome(self, outcome: DemandTickOutcome):
        """Release diagnostic bytes only AFTER the genuine verified VS1 return."""
        self._owner_only()
        if outcome.status == "NOT_ADMITTED":
            for record in self.records.values():
                if record["ticket"].state.value == "queued":
                    record["last_refusal"] = outcome.reason[:80]
            return
        if outcome.status != "VERIFIED_SWITCH":
            return
        result = outcome.result
        if result is None or result.verified_vs1 is not True:
            raise DemandControlRejected("unverified runtime outcome")
        allowed = set()
        for reply in outcome.replies:
            if reply.origin != "P300_RAW_DIAGNOSTIC_NOT_ACTUAL_RPM":
                raise DemandControlRejected("unknown P300 result provenance")
            for record in self.records.values():
                ticket = record["ticket"]
                if ticket.sequence != reply.sequence:
                    continue
                if (record["kind"] != reply.kind or
                        ticket.state.value != "completed" or
                        (reply.sequence, reply.kind) in allowed):
                    raise DemandControlRejected("result ticket mismatch")
                allowed.add((reply.sequence, reply.kind))
                record["result"] = {
                    "raw_hex": reply.raw_hex,
                    "origin": reply.origin,
                    "verified_vs1": True,
                    "vs1_p80": result.p80_hex,
                    "vs1_p06": result.p06_hex,
                    "elapsed_ms": result.elapsed_ms,
                }
                break
