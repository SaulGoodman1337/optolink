"""Lossless ledger for delayed HA /set readbacks (SHADOW integration only).

Installed BEFORE mqtt_util.connect_mqtt: every scheduled delayed readback
adds one opaque queue marker. Main-thread is_forced marks the readback as
in flight; ONLY a successful completed datapoint read retires that ticket. A stale marker from a discarded or delayed timer NEVER
silently disappears from the ledger. Arbitrary polls with the same index
cannot be mistaken for a completed write readback.

Fail-closed invariants:
* install only once, before MQTT is connected
* never infer idle from an empty queue while timers are sleeping
* no TTL-based forgiveness: canceled/lost readbacks require a reviewed reset
* never open a port or change a controller setting
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable


class RefreshLedgerRejected(RuntimeError):
    pass


class PendingReadbackLedger:
    def __init__(self):
        self._lock = threading.RLock()
        self._next_ticket = 1
        self._pending: dict[int, int] = {}
        self._marker = object()
        self._seen = 0
        self._inflight: int | None = None
        self._failed_closed = False

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

    def register(self, index: int) -> tuple[object, int, int]:
        if type(index) is not int or index < 0:
            raise RefreshLedgerRejected("readback index must be nonnegative int")
        with self._lock:
            ticket = self._next_ticket
            self._next_ticket += 1
            self._pending[ticket] = index
            self._seen += 1
            return self._marker, ticket, index

    def consume(self, item: Any) -> int | None:
        if not (isinstance(item, tuple) and len(item) == 3
                and item[0] is self._marker):
            # A legacy force-poll index is NOT a completion of delayed /set.
            return item
        _, ticket, index = item
        with self._lock:
            if self._pending.get(ticket) != index:
                raise RefreshLedgerRejected("duplicate or forged readback ticket")
            if self._inflight is not None:
                self._failed_closed = True
                raise RefreshLedgerRejected("two readbacks in flight")
            self._inflight = ticket
            return index

    def complete_forced(self, retcode: int) -> None:
        """Called by original main loop AFTER the forced datapoint read returns.

        In particular, popping a queue item must NOT masquerade as a readback
        completion; a timeout/invalid return permanently disables switching.
        """
        with self._lock:
            ticket = self._inflight
            if ticket is None:
                return
            self._inflight = None
            if type(retcode) is int and retcode == 1:
                del self._pending[ticket]
            else:
                self._failed_closed = True

    @property
    def failed_closed(self) -> bool:
        with self._lock:
            return self._failed_closed

    def cancel_not_scheduled(self, item: tuple) -> None:
        # Only when Thread.start() itself failed; NOT when an already
        # started worker fails or an entry gets lost from the HA queue.
        with self._lock:
            self._pending.pop(item[1], None)

    def require_idle_for_p300(self) -> None:
        with self._lock:
            if self._failed_closed or self._inflight is not None or self._pending:
                raise RefreshLedgerRejected('delayed HA readback not verified')

    @property
    def total_registered(self) -> int:
        return self._seen


def install_before_mqtt_connect(mqtt_module, *,
                                sleep: Callable[[float], None] = time.sleep,
                                thread_type=threading.Thread) -> PendingReadbackLedger:
    """Swap two tiny callback functions without touching the serial owner.

    The old force_delayed worker enqueued just a naked integer. The new worker
    enqueues a ticket that the main's existing is_forced() adapter unwraps.
    All other MQTT handling and polling behavior stays the same.
    """
    if getattr(mqtt_module, "_hybrid_readback_ledger", None) is not None:
        raise RefreshLedgerRejected("readback ledger already installed")
    if getattr(mqtt_module, "mqtt_client", None) is not None:
        raise RefreshLedgerRejected("must install before MQTT client connection")
    if not isinstance(getattr(mqtt_module, "lst_force_refresh", None), list):
        raise RefreshLedgerRejected("expected original list-based forced queue")
    prior_is_forced = getattr(mqtt_module, "is_forced", None)
    prior_force_delayed = getattr(mqtt_module, "force_delayed", None)
    if not callable(prior_is_forced) or not callable(prior_force_delayed):
        raise RefreshLedgerRejected("unknown original MQTT refresh topology")

    ledger = PendingReadbackLedger()

    def tracked_force_delayed(listidx, delay=1):
        if type(delay) not in (int, float) or not 0 <= delay <= 60:
            raise RefreshLedgerRejected("unbounded refresh scheduling")
        item = ledger.register(listidx)

        def worker():
            sleep(delay)
            mqtt_module.lst_force_refresh.append(item)

        thread = thread_type(target=worker, daemon=True)
        try:
            thread.start()
        except BaseException:
            ledger.cancel_not_scheduled(item)
            raise
        return thread

    def tracked_is_forced():
        return ledger.consume(prior_is_forced())

    # These callbacks are swapped while the MQTT client is not yet running.
    # An exception before this point leaves the original intact.
    mqtt_module.force_delayed = tracked_force_delayed
    mqtt_module.is_forced = tracked_is_forced
    mqtt_module._hybrid_readback_ledger = ledger
    mqtt_module._hybrid_complete_forced = ledger.complete_forced
    return ledger
