"""Cooperative cross-process transaction boundary (offline integration module).

Both a multi-MQTT-message producer transaction and a P300 maintenance window
take the same EXCLUSIVE kernel flock. This is intentionally stronger than a
single-frame mutex: Party restore, 8-byte schedule readback and maintenance
rollback must retain the lock until the logical operation is done.

DO NOT deploy as a safety mechanism until EVERY producer of writes/raw frames
is instrumented and acknowledged. The current production scripts do NOT use
this lease. A separate trusted DispatcherSnapshot must still account for
unowned MQTT/TCP requests, timer-delayed HA refreshes, and VS1 freshness.

No daemon, pyserial, MQTT, systemd, controller write or file provisioning here.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import stat
import time
from typing import Callable


LEASE_PATH = Path('/run/lock/optolink-hybrid-producer-epoch.lock')
COOPERATIVE_SERVICES = frozenset({
    'party', 'schedule', 'maintenance', 'service-programs', 'clock-sync',
    'mqtt-direct', 'tcp-direct',
})


class ProducerFenceRejected(RuntimeError):
    pass


def _open_reviewed_lock(path: Path) -> int:
    if not isinstance(path, Path) or not path.is_absolute() or path.is_symlink():
        raise ProducerFenceRejected('absolute nonsymlink lease path required')
    flags = (os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0)
             | getattr(os, 'O_CLOEXEC', 0))
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        # Missing provisioning must not silently turn fencing OFF.
        raise ProducerFenceRejected('producer lease missing or inaccessible') from exc
    try:
        info = os.fstat(fd)
        path_info = os.stat(path, follow_symlinks=False)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_ino != path_info.st_ino
                or info.st_dev != path_info.st_dev
                or info.st_mode & 0o007):
            raise ProducerFenceRejected('producer lease has unsafe inode or permissions')
        if info.st_uid not in (0, os.geteuid()):
            raise ProducerFenceRejected('producer lease has untrusted file owner')
        if info.st_gid not in os.getgroups() + [os.getegid()]:
            # Root can access an owner-only file; non-root users need trusted group.
            if info.st_uid != os.geteuid():
                raise ProducerFenceRejected('producer lease group not assigned to caller')
        return fd
    except BaseException:
        os.close(fd)
        raise


@contextmanager
def writer_transaction(producer: str, *, path: Path = LEASE_PATH,
                       max_wait_s: float = 10.0,
                       clock: Callable[[], float] = time.monotonic,
                       sleep: Callable[[float], None] = time.sleep):
    """Logical read-before-write/write/readback/restore, not one MQTT frame.

    New producer transactions wait at most max_wait_s for an active batch.
    Acquire BEFORE publishing the first MQTT request, and release only after
    all readback and rollback attempts. Nonparticipants remain UNSAFE.
    """
    if producer not in COOPERATIVE_SERVICES:
        raise ProducerFenceRejected('unreviewed writer cannot take a cooperative lease')
    if (type(max_wait_s) not in (int, float)
            or not 0 < max_wait_s <= 60):
        raise ProducerFenceRejected('bounded wait required')
    fd = _open_reviewed_lock(path)
    acquired = False
    try:
        deadline = clock() + max_wait_s
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except BlockingIOError as exc:
                if clock() >= deadline:
                    raise ProducerFenceRejected('writer timeout waiting for P300 barrier') from exc
                sleep(min(0.025, max(0, deadline - clock())))
        yield
    finally:
        if acquired:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


@contextmanager
def p300_window(*, path: Path = LEASE_PATH):
    """No wait: if ANY complete writer transaction owns the line, do not switch.

    A real dispatcher must also prohibit new direct MQTT/TCP requests and
    verify all producer services have opted in to the same lease.
    """
    fd = _open_reviewed_lock(path)
    acquired = False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except BlockingIOError as exc:
            raise ProducerFenceRejected('an external writer transaction is active') from exc
        yield
    finally:
        if acquired:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def provision_command() -> str:
    """Describe root-only future provisioning; this function does NOT execute."""
    return ('install -o root -g optolink -m 0660 /dev/null '
            + str(LEASE_PATH))


def fenced_readonly_batch(gate, snapshot_provider, budget, *, lock_path: Path,
                          port, legacy_dispatch, resume_vs1, serial_lease,
                          jobs=None, clock=time.monotonic, sleep=time.sleep):
    """One atomic admission and read-only P300 window under an OS writer lease.

    snapshot_provider must be a TRUSTED in-loop callback, called only AFTER
    the producer-exclusive lease is acquired. It must freeze direct MQTT/TCP
    admission and confirm every external producer is enrolled and quiescent.
    Merely returning all-True flags without installing these producer hooks
    is not a production safety guarantee.
    """
    from .runtime_admission import RuntimeAdmissionGate
    from .phase_planner import Budget
    if (not isinstance(gate, RuntimeAdmissionGate) or
            not callable(snapshot_provider) or not isinstance(budget, Budget)):
        raise ProducerFenceRejected('typed gate, budget and snapshot callback required')
    with p300_window(path=lock_path):
        snapshot = snapshot_provider()
        return gate.run_readonly_batch(
            snapshot, budget, port=port, legacy_dispatch=legacy_dispatch,
            resume_vs1=resume_vs1, lease=serial_lease, jobs=jobs,
            clock=clock, sleep=sleep)
