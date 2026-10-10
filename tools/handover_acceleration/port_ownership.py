"""Read-only acceptance guard against the independently installed pump owner.

This module does not start services, open a serial port or touch the boiler.
The *existing* root-owned pump daemon obtains
/run/lock/physical-ram-snapshot.lock before stopping the splitter; the
hybrid test takes the exact same nonblocking advisory lock. The test ALSO
requires the pump unit to be stopped: an idle daemon can receive ON at any
time. This dual check must run again in the worker before stopping services.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import stat
from typing import Callable


PUMP_SERVICE = 'optolink-pump-override.service'
PUMP_LOCK = Path('/run/lock/physical-ram-snapshot.lock')


class OwnershipRejected(RuntimeError):
    """Do not attempt a handover with an unverified competing port owner."""


def require_pump_inactive(unit_state: Callable[[str], dict]) -> None:
    """Fail closed on starting/stopping, active, or unknown systemd states."""
    if not callable(unit_state):
        raise OwnershipRejected('unit state provider required')
    state = unit_state(PUMP_SERVICE)
    if not isinstance(state, dict):
        raise OwnershipRejected('pump service state unreadable')
    if state.get('ActiveState') not in ('inactive', 'failed', 'not-found'):
        raise OwnershipRejected(
            'pump override must be stopped before hybrid acceptance: '
            + str(state.get('ActiveState'))
        )


@contextmanager
def pump_lease(path: Path = PUMP_LOCK):
    """Nonblocking cooperative exclusion with the *original* pump service.

    No blocking retry and no unlink: the root process can retain the kernel
    flock on the same inode for the duration of the critical section.
    """
    path = Path(path)
    if not path.is_absolute() or path.is_symlink():
        raise OwnershipRejected('pump lock path must be absolute, not symlink')
    flags = (os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0)
             | getattr(os, 'O_CLOEXEC', 0))
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise OwnershipRejected('pump coordination lock unavailable') from exc
    try:
        meta = os.fstat(fd)
        if (not stat.S_ISREG(meta.st_mode) or meta.st_uid != os.geteuid()
                or meta.st_mode & 0o077):
            raise OwnershipRejected('pump lock is not owner-only regular file')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise OwnershipRejected('pump coordination lock busy') from exc
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
