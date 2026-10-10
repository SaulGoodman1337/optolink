"""Freeze request admission while a read-only P300 hardware window is active.

The serial owner acquires this barrier *before* the producer OS flock and
holds it through post-return legacy GFA verification. The original MQTT
callbacks and TCP receive thread acquire the same gate BEFORE queuing any
new data/request/scheduled refresh. This is NOT a replacement for the OS
producer fence or complete write/readback acknowledgement.

No network, serial, filesystem, service or worker thread is started here.
"""
from __future__ import annotations

from collections import deque
from contextlib import contextmanager
from functools import wraps
import threading
from typing import Callable


class IngressRejected(RuntimeError):
    pass


class IngressEpoch:
    def __init__(self, *, max_tcp_queue: int = 32):
        if type(max_tcp_queue) is not int or not 1 <= max_tcp_queue <= 1024:
            raise ValueError("bounded TCP admission queue required")
        self.mutex = threading.RLock()
        self.owner = threading.get_ident()
        self.freeze_depth = 0
        self.max_tcp_queue = max_tcp_queue
        self.tcp_overflow = False

    @contextmanager
    def freeze(self):
        if threading.get_ident() != self.owner:
            raise IngressRejected("only the original serial thread may freeze")
        with self.mutex:
            if self.freeze_depth != 0:
                raise IngressRejected("nested P300 admission freeze")
            self.freeze_depth = 1
            try:
                yield self
            finally:
                self.freeze_depth = 0

    def wrap_mqtt_callback(self, handler: Callable) -> Callable:
        if not callable(handler):
            raise IngressRejected("original MQTT callback required")
        @wraps(handler)
        def protected(*args, **kwargs):
            with self.mutex:
                return handler(*args, **kwargs)
        return protected

    def tcp_class(self, original):
        """The original TCP .received_data single slot loses burst traffic.

        Shadow subclass retains the original socket I/O and special commands,
        but queues EVERY accepted nonempty request in a bounded FIFO. Network
        writes of this attribute are blocked during the P300 freeze. A queue
        overflow FAILS CLOSED and terminates the offending client read loop
        instead of silently replacing a pending command.
        """
        epoch = self
        if not isinstance(original, type):
            raise IngressRejected("original TCP class required")
        for method in ("__init__", "_listen", "get_request", "send", "stop"):
            if not callable(getattr(original, method, None)):
                raise IngressRejected("unknown TCP listener contract: " + method)

        class GuardedTcpServer(original):
            def __init__(self, *args, **kwargs):
                object.__setattr__(self, "_hybrid_tcp_queue", deque())
                object.__setattr__(self, "_hybrid_epoch", epoch)
                super().__init__(*args, **kwargs)

            def __setattr__(self, name, value):
                if name == "received_data" and "_hybrid_epoch" in self.__dict__:
                    with epoch.mutex:
                        if value not in ("", None):
                            if not isinstance(value, str):
                                epoch.tcp_overflow = True
                                raise IngressRejected("unexpected TCP request payload")
                            if len(self._hybrid_tcp_queue) >= epoch.max_tcp_queue:
                                epoch.tcp_overflow = True
                                raise IngressRejected("TCP admission queue overflow")
                            self._hybrid_tcp_queue.append(value)
                    return
                return super().__setattr__(name, value)

            def get_request(self) -> str:
                with epoch.mutex:
                    return (self._hybrid_tcp_queue.popleft()
                            if self._hybrid_tcp_queue else "")

            def pending_count(self) -> int:
                with epoch.mutex:
                    return len(self._hybrid_tcp_queue)

        GuardedTcpServer.__name__ = "HybridGuardedTcpServer"
        return GuardedTcpServer

    def wrap_tcp_command(self, handler: Callable) -> Callable:
        # Existing TCP special commands (including reloadini) run on the
        # TCP listener thread; they must not change application state mid-EOT.
        return self.wrap_mqtt_callback(handler)
