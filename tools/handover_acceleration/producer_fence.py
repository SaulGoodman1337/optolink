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


LEASE_PATH = Path('/var/lib/optolink-hybrid/producer-epoch.lock')
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


_thread_lease = __import__('threading').local()


def _marker(fd: int, data: bytes) -> None:
    """Persist intent while still holding flock; a crash leaves P300 blocked."""
    if len(data) > 240:
        raise ProducerFenceRejected('lease marker too long')
    os.lseek(fd, 0, os.SEEK_SET)
    os.ftruncate(fd, 0)
    if data:
        if os.write(fd, data) != len(data):
            raise ProducerFenceRejected('producer marker short write')
    os.fsync(fd)


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
    active = getattr(_thread_lease, 'active', None)
    if active is not None:
        if active['path'] != path:
            raise ProducerFenceRejected('nested writers may not change lock path')
        try:
            yield
        except BaseException:
            _latch_failed(active, producer)
            raise
        return  # nested write/readback stays inside the outer kernel flock

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
        prior = os.pread(fd, 241, 0)
        if len(prior) > 240:
            raise ProducerFenceRejected('untrusted oversized lease marker')
        if prior.startswith(b'P300_'):
            raise ProducerFenceRejected('P300 was interrupted; VS1 recovery not proven')
        active = {'path': path, 'fd': fd, 'prior': prior, 'failed': False}
        _marker(fd, ('ACTIVE:' + producer).encode('ascii'))
        _thread_lease.active = active
        try:
            yield
        except BaseException:
            _latch_failed(active, producer)
            raise
        else:
            if not active['failed']:
                _marker(fd, prior)
    finally:
        _thread_lease.active = None
        if acquired:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _latch_failed(active: dict, producer: str) -> None:
    active['failed'] = True
    _marker(active['fd'], ('FAILED:' + producer).encode('ascii'))


def mark_unverified_write(producer: str) -> None:
    """A wrapped producer can latch a swallowed error/False return in-band."""
    active = getattr(_thread_lease, 'active', None)
    if active is None or producer not in COOPERATIVE_SERVICES:
        raise ProducerFenceRejected('cannot latch write without owned transaction')
    _latch_failed(active, producer)


class P300WindowProof:
    """One scoped P300 window; persistent marker until verified return.

    The producer lease stays locked during mark/clear to prevent even a
    millisecond of unverified VS1 transport admission after a crash.
    """
    def __init__(self, fd: int):
        self.fd = fd
        self.started = False
        self.verified = False

    def begin(self) -> None:
        if self.started:
            raise ProducerFenceRejected('P300 window already marked active')
        _marker(self.fd, b'P300_ACTIVE')
        self.started = True

    def confirm_verified_vs1(self) -> None:
        if not self.started:
            raise ProducerFenceRejected('no P300 transfer to confirm')
        self.verified = True


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
        # A killed writer leaves ACTIVE; a failed/ambiguous readback leaves
        # FAILED. Both persist after the process releases its kernel lock.
        if os.fstat(fd).st_size != 0:
            raise ProducerFenceRejected('unverified or interrupted producer transaction')
        proof = P300WindowProof(fd)
        try:
            yield proof
        finally:
            if proof.started:
                # Fatal crash leaves P300_ACTIVE. Python-level failure
                # leaves P300_FAILED. Only complete original GFA verification
                # can clear the marker before allowing another writer.
                _marker(fd, b'' if proof.verified else b'P300_FAILED')
    finally:
        if acquired:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def provision_command() -> str:
    """Describe root-only future provisioning; this function does NOT execute."""
    return ("install -d -o root -g optolink -m 0750 /var/lib/optolink-hybrid; "
            "test -e /var/lib/optolink-hybrid/producer-epoch.lock || "
            "install -o root -g optolink -m 0660 /dev/null "
            "/var/lib/optolink-hybrid/producer-epoch.lock")


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
