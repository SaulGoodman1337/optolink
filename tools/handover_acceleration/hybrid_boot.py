"""One-shot read-only in-process FC03 batch on the original split-owner port.

A deliberately finite acceptance program, NOT a thermostat/HA override.
The caller is the already-initialized single-threaded original splitter loop.
No pyserial construction, systemd, arbitrary addresses or writes exist here.
A separate systemd supervisor must stop original services and restore them.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import time
from typing import Callable

from .coordinator import HandoverCoordinator, Mode, PortLease
from .dispatcher_bridge import InProcessDispatchBridge
from .phase_planner import Budget, ReadJob
from .scheduler import ReadKind


class BootRejected(RuntimeError):
    pass


# Fixed previously read addresses (0x0F20/32 and 0x1C60/32); no user input.
PRESET = (
    ("p300_device", ReadKind.P300_ID, 85.0),
    ("ram_0f20_32", ReadKind.P300_RAM_0F20_32, 140.0),
    ("ram_1c60_32", ReadKind.P300_RAM_1C60_32, 140.0),
)


def _private_report_dir(folder: Path) -> Path:
    """Never follow a symlink; report directory must be owned and private."""
    if not isinstance(folder, Path) or not folder.is_absolute() or folder.is_symlink():
        raise BootRejected('private absolute report directory required')
    try:
        meta = folder.stat()
    except OSError as exc:
        raise BootRejected('report directory unavailable') from exc
    if (not stat.S_ISDIR(meta.st_mode) or meta.st_uid != os.geteuid()
            or meta.st_mode & 0o077):
        raise BootRejected('report directory must be owner-only')
    return folder


def _atomic_report(folder: Path, payload: dict) -> None:
    """One JSON result per one-shot worker; no secrets or MQTT configuration."""
    text = json.dumps(payload, sort_keys=True, separators=(',', ':')) + '\n'
    path = folder / 'hybrid-result.json'
    # Exclusive output file: never overwrite a previous result/symlink.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as out:
            out.write(text)
            out.flush()
            os.fsync(out.fileno())
    except BaseException:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def _legacy_gfa(legacy: Callable, port, address: int) -> bytes:
    """Exercise existing HA-patched GFA dispatcher after the hybrid return."""
    command = f'gfaread;0x{address:04x};1;raw;False'
    answer = legacy(command, port)
    if not isinstance(answer, tuple) or len(answer) != 4:
        raise BootRejected('original legacy dispatcher returned malformed tuple')
    rc, data, _val, _text = answer
    if type(rc) is not int or rc != 1 or not isinstance(data, (bytes, bytearray)):
        raise BootRejected(f'original GFA read rejected at 0x{address:04x}')
    raw = bytes(data)
    if len(raw) != 1 or raw == b'\xff':
        raise BootRejected(f'original GFA sample invalid at 0x{address:04x}')
    if address == 0x4050 and raw != b'\x20':
        raise BootRejected('original GFA P80 identity mismatch')
    return raw


def run_one_shot(port, settings, legacy_dispatch: Callable,
                 resume_vs1: Callable, report_dir: Path, *,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> dict:
    """Borrow and verify existing VS1, batch fixed reads, return and recheck.

    This is intentionally called only at the initial startup seam before any
    poll/MQTT/TCP request can be dispatched, never between a write/readback.
    The original application remains the sole serial owner. If an exception
    occurs the coordinator context attempts conservative VS1 restoration;
    the systemd ExecStopPost watchdog must independently restore production.
    """
    if (port is None or settings is None or not callable(legacy_dispatch)
            or not callable(resume_vs1) or getattr(settings, 'vs1protocol', None) is not True
            or getattr(settings, 'port_vitoconnect', 'unknown') is not None):
        raise BootRejected('read-only VS1 single-owner profile not confirmed')
    folder = _private_report_dir(report_dir)
    if ((folder / 'hybrid-result.json').exists() or
            (folder / 'hybrid-result.json').is_symlink()):
        raise BootRejected('result already exists')
    started = clock()
    manager = HandoverCoordinator.borrow_existing_vs1(
        port, PortLease(folder / 'hybrid-port.lease'), clock=clock, sleep=sleep)
    bridge = InProcessDispatchBridge(
        port, legacy_dispatch, vs1protocol=True, vitoconnect_port=None,
        allow_maintenance=True, resume_vs1=resume_vs1)
    results: dict = {}
    try:
        with manager:
            # Verifies full device ID/firmware and REAL GFA P80/P06 first,
            # without an EOT, an ENQ or opening/closing a second port.
            bridge.bind_verified_coordinator(manager)
            after_attach = clock()
            jobs = tuple(ReadJob(name, kind, duration_ms=duration,
                                 deadline_ms=15_000., independent=True)
                         for name, kind, duration in PRESET)
            budget = Budget(max_vs1_unavailable_ms=8_000.,
                            max_p06_age_ms=9_000.,
                            max_queue_wait_ms=8_000.)
            result = bridge.execute_maintenance(jobs, budget)
            after_batch = clock()
            if not 0 <= (after_batch - after_attach) * 1000 <= budget.max_vs1_unavailable_ms:
                raise BootRejected('observed VS1 interruption exceeded verified read-only window')
            if manager.mode is not Mode.VS1_VERIFIED or not result.verified_vs1_at_end:
                raise BootRejected('VS1 not verified after P300 batch')
            if result.p300_entry_count != 1 or len(result.reads) != 3:
                raise BootRejected('unexpected number of P300 windows or reads')
            raw_by_name = {x.name: x.raw for x in result.reads}
            if len(raw_by_name) != 3 or raw_by_name['p300_device'] != b'\x20\xc2':
                raise BootRejected('P300 response identities inconsistent')
            if len(raw_by_name['ram_0f20_32']) != 32 or len(raw_by_name['ram_1c60_32']) != 32:
                raise BootRejected('wrong FC03 data length')
            p80 = _legacy_gfa(bridge.response_to_request, port, 0x4050)
            p06 = _legacy_gfa(bridge.response_to_request, port, 0x4006)
            if p80 != b'\x20' or p06 == b'\xff':
                raise BootRejected('final original GFA verification failed')
            results = {
                'status': 'PASS_VERIFIED_BORROWED_PORT_FIXED_FC03',
                'test_mode': 'read_only_in_process_single_owner',
                'phase_count': 1, 'identity_hex': '20c2',
                'ram_0f20_32_hex': raw_by_name['ram_0f20_32'].hex(),
                'ram_1c60_32_hex': raw_by_name['ram_1c60_32'].hex(),
                'gfa_p80_hex': p80.hex(), 'gfa_p06_hex': p06.hex(),
                'time_ms': {
                    'attach': round((after_attach-started)*1_000,3),
                    'p300_and_vs1': round((after_batch-after_attach)*1_000,3),
                    'total': round((clock()-started)*1_000,3)},
                'verified_vs1_return': True,
                'no_second_serial_open': True,
                'no_device_write': True,
            }
        # The borrowed serial object must still belong to the original main.
        if getattr(port, 'is_open', True) is False:
            raise BootRejected('original serial handle unexpectedly closed')
    except BaseException:
        # A failed result must never be republished as confirmed production.
        raise
    _atomic_report(folder, results)
    return results
