"""Opt-in, in-process dispatch boundary for an existing Optolink serial owner.

The legacy dispatcher remains the ONLY handler for existing MQTT/TCP/poll
messages, including its read, write, writeraw, raw and readback semantics.
No new user command is exposed. This module never constructs a serial device,
starts a service, or imports the original splitter.

Experimental read-only P300 maintenance is disabled by default, requires the
*same* already-open serial object, an externally verified coordinator and a
reviewed VS1-resume callback. Opaque legacy transactions invalidate that proof.
This is an offline integration prototype, not a deployed runtime replacement.
"""
from __future__ import annotations

from contextlib import contextmanager
import threading
from typing import Callable, Any

from .coordinator import HandoverCoordinator, Mode
from .phase_executor import execute_read_phases, ExecutionResult
from .phase_planner import Budget, ReadJob, plan_phase_windows
from .scheduler import GfaFreshnessLedger


class BridgeRejected(RuntimeError):
    """The in-process owner refused an unsafe or unsupported dispatch."""


class InProcessDispatchBridge:
    def __init__(self, serial_handle: object, legacy_dispatch: Callable, *,
                 vs1protocol: bool, vitoconnect_port: str | None,
                 allow_maintenance: bool = False,
                 resume_vs1: Callable[[], None] | None = None):
        if serial_handle is None or not callable(legacy_dispatch):
            raise BridgeRejected('existing serial handle and legacy callback required')
        if type(vs1protocol) is not bool or type(allow_maintenance) is not bool:
            raise BridgeRejected('explicit boolean configuration required')
        if not vs1protocol or vitoconnect_port is not None:
            raise BridgeRejected('requires exclusive original VS1 without Vitoconnect')
        if allow_maintenance and not callable(resume_vs1):
            raise BridgeRejected('explicit VS1 adapter reinitialization callback required')
        self.serial_handle = serial_handle
        self.legacy_dispatch = legacy_dispatch
        self.allow_maintenance = allow_maintenance
        self.resume_vs1 = resume_vs1
        self.owner_thread = threading.get_ident()
        self.coordinator: HandoverCoordinator | None = None
        self._legacy_since_bind = False
        self._failed_closed = False
        self._active_call = False
        self._legacy_group_depth = 0
        self._ledger = GfaFreshnessLedger()
        self.legacy_calls = 0
        self.maintenance_batches = 0

    def _require_owner(self, port=None):
        if threading.get_ident() != self.owner_thread:
            raise BridgeRejected('only the main serial-owner thread may use the bridge')
        if port is not None and port is not self.serial_handle:
            raise BridgeRejected('different serial handle: second owner refused')
        if self._failed_closed:
            raise BridgeRejected('bridge failed closed; independent restore is required')

    def response_to_request(self, request: Any, port: object):
        """Unchanged legacy response tuple and exception behavior."""
        self._require_owner(port)
        if self._active_call:
            raise BridgeRejected('reentrant serial request refused')
        if self.coordinator is not None and self.coordinator.mode is not Mode.VS1_VERIFIED:
            raise BridgeRejected('legacy request forbidden outside verified VS1')
        self._active_call = True
        try:
            return self.legacy_dispatch(request, port)
        finally:
            self._active_call = False
            self.legacy_calls += 1
            # Raw, write or even read may mutate undocumented session globals.
            # Never trust a prior hybrid-mode proof after opaque legacy I/O.
            self._legacy_since_bind = True
            self._ledger.invalidate_all()

    @contextmanager
    def legacy_transaction(self):
        """Explicit write+readback group; maintenance cannot split the group."""
        self._require_owner()
        if self._active_call:
            raise BridgeRejected('cannot start legacy group during another frame')
        self._legacy_group_depth += 1
        try:
            yield self
        finally:
            self._legacy_group_depth -= 1

    def bind_verified_coordinator(self, coordinator: HandoverCoordinator):
        """Bind a separately authenticated owner to the IDENTICAL serial port.

        Only a fresh coordinator not used across opaque legacy calls may be
        bound. After any legacy call, a distinct verified manager is needed;
        simply flipping a boolean cannot attest new identity.
        """
        self._require_owner()
        if not self.allow_maintenance:
            raise BridgeRejected('P300 maintenance feature is disabled')
        if self._active_call or self._legacy_group_depth:
            raise BridgeRejected('cannot bind mid-transaction')
        if (not isinstance(coordinator, HandoverCoordinator) or
                coordinator.mode is not Mode.VS1_VERIFIED or
                coordinator.wire is None or
                coordinator.wire.port is not self.serial_handle):
            raise BridgeRejected('independently verified same-port coordinator required')
        if self.coordinator is coordinator and self._legacy_since_bind:
            raise BridgeRejected('stale coordinator proof after legacy transaction')
        self.coordinator = coordinator
        self._legacy_since_bind = False
        self._ledger.invalidate_all()

    def execute_maintenance(self, jobs: tuple[ReadJob, ...], budget: Budget, *,
                            now_ms: float = 0.0,
                            initial_p06_age_ms: float = 0.0) -> ExecutionResult:
        """One atomic preplanned phase; no MQTT or TCP maintenance entrypoint."""
        self._require_owner()
        if not self.allow_maintenance:
            raise BridgeRejected('P300 maintenance feature is disabled')
        if self._active_call or self._legacy_group_depth:
            raise BridgeRejected('cannot switch inside an active legacy transaction')
        manager = self.coordinator
        if (manager is None or self._legacy_since_bind or
                manager.wire is None or manager.wire.port is not self.serial_handle or
                manager.mode is not Mode.VS1_VERIFIED):
            raise BridgeRejected('fresh verified same-port VS1 session required')
        if not isinstance(budget, Budget) or not isinstance(jobs, tuple):
            raise BridgeRejected('typed, bounded phase plan required')
        # Validate all declared deadlines and GFA freshness BEFORE any EOT.
        # A rejected schedule must not disable the still-working VS1 service.
        plan_phase_windows(jobs, budget, now_ms=now_ms,
                           initial_p06_age_ms=initial_p06_age_ms)
        self._active_call = True
        try:
            result = execute_read_phases(manager, jobs, budget, ledger=self._ledger,
                                         now_ms=now_ms,
                                         initial_p06_age_ms=initial_p06_age_ms)
            if manager.mode is not Mode.VS1_VERIFIED:
                raise BridgeRejected('VS1 not verified at end of batch')
            # Adapter's legacy internal VS1 sync may be stale after an EOT.
            # This callback must be supplied by a reviewed runtime integration.
            self.resume_vs1()  # type: ignore[misc]
            self.maintenance_batches += 1
            self._legacy_since_bind = True
            self._ledger.invalidate_all()
            return result
        except BaseException:
            self._failed_closed = True
            self._ledger.invalidate_all()
            raise
        finally:
            self._active_call = False

    @property
    def failed_closed(self):
        return self._failed_closed
