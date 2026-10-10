#!/usr/bin/env python3
"""Supervised ONE-SHOT acceptance of a copied HA Optolink single-owner runtime.

Default plan/audit mode: never touches systemd or opens a port.
Explicit --execute --accept-telemetry-pause starts an independent systemd
worker which snapshots the existing service state, temporarily pauses exactly
previously-active original services and runs a ONE-SHOT shadow COPY of the
original splitter on the existing configured serial link. ExecStopPost invokes
already vetted conservative VS1 recovery, then starts the old original owner.

NO changes under /opt/optolink, no config writes, no generic FC03, no RAM
writes. The existing service's MQTT/TCP/poll/write paths are never executed by
the test copy: it exits after the pinned read-only batch and GFA crosscheck.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

try:
    from .dispatcher_patch import patch_dispatcher
    from .dispatcher_runtime_audit import audit_directory, _source
    from .port_ownership import pump_lease, require_pump_inactive
except ImportError:
    try:
        from handover_acceleration.dispatcher_patch import patch_dispatcher
        from handover_acceleration.dispatcher_runtime_audit import audit_directory, _source
        from handover_acceleration.port_ownership import pump_lease, require_pump_inactive
    except ImportError:
        from dispatcher_patch import patch_dispatcher
        from dispatcher_runtime_audit import audit_directory, _source
        from port_ownership import pump_lease, require_pump_inactive


VERSION = 'inprocess-fc03-oneshot-v2-owner-gate'
UNIT = 'optolink-inprocess-readonly-acceptance.service'
ROOT = Path('/opt/optolink')
BASE = Path('/root/p300-trial-work/handover-acceleration-live-results')
# Recorded by the operator's actual static audit; refuse changed installed
# source rather than reusing an unreviewed dispatcher unconditionally.
PINNED_INSTALLED_SHA256 = 'e4be265db857d32486fd50aa7eee359e9a054b951e478d5847f17702a0ce7fac'
COMPONENTS = (
    '__init__.py', 'coordinator.py', 'scheduler.py', 'phase_planner.py',
    'port_ownership.py', 'runtime_admission.py',
    'phase_executor.py', 'dispatcher_bridge.py', 'hybrid_boot.py',
    'dispatcher_patch.py', 'dispatcher_runtime_audit.py',
)
STAGE_FILES = tuple('handover_acceleration/' + p for p in COMPONENTS) + (
    'optolinkvs2_switch.py', 'hybrid_acceptance.py',
)


class AcceptanceRejected(RuntimeError):
    pass


def _live():
    try:
        from . import live_probe
    except ImportError:
        import live_probe
    return live_probe


def _verify_original(root: Path) -> dict:
    audit = audit_directory(root)
    mandatory = ('shadow_source_copy_supported', 'legacy_gfa_patch_detected',
                 'legacy_request_parser_present', 'legacy_write_commands_present',
                 'main_direct_vitoconnect_branch', 'main_vs1_keepalive',
                 'adapter_static_protocol_flag')
    if not all(audit.get(k) is True for k in mandatory):
        raise AcceptanceRejected('installed HA source does not have verified dispatcher semantics')
    if audit['main_sha256'] != PINNED_INSTALLED_SHA256:
        raise AcceptanceRejected('installed dispatcher SHA256 no longer matches operator audit')
    return audit


def _digest(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise AcceptanceRejected('missing/symlink staged source: ' + path.name)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_json(folder: Path, name: str, record: dict) -> None:
    path = folder / name
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as out:
        json.dump(record, out, sort_keys=True, indent=2)
        out.write('\n')
        out.flush()
        os.fsync(out.fileno())


def stage(session: Path, root: Path, *, source_dir: Path | None = None) -> dict:
    """Compile and snapshot the real installed dispatcher as a copy only.

    Source identity is checked before staging. Never alter production Python
    files or inherit an unreviewed port setting from an arbitrary test input.
    """
    audit = _verify_original(root)
    if not session.is_dir() or session.is_symlink() or session.stat().st_mode & 0o077:
        raise AcceptanceRejected('private session directory required')
    origin = source_dir or Path(__file__).resolve().parent
    copied = session / 'handover_acceleration'
    copied.mkdir(mode=0o700)
    for name in COMPONENTS:
        source = origin / name
        if source.is_symlink() or not source.is_file():
            raise AcceptanceRejected('missing trusted research source ' + name)
        dest = copied / name
        shutil.copyfile(source, dest)
        dest.chmod(0o600)
    patched = patch_dispatcher(_source(root / 'optolinkvs2_switch.py'))
    compiled = session / 'optolinkvs2_switch.py'
    compiled.write_text(patched, encoding='utf-8')
    compiled.chmod(0o600)
    script = session / 'hybrid_acceptance.py'
    shutil.copyfile(Path(__file__), script)
    script.chmod(0o600)
    digests = {name: _digest(session / name) for name in STAGE_FILES}
    record = {
        'version': VERSION, 'installed_main_sha256': audit['main_sha256'],
        'source_sha256': digests, 'production_changed': False,
        'allowlisted_fc03': ['0x0f20/32', '0x1c60/32'],
        'single_port_owner': True,
        'worker_script': str(script),
    }
    _atomic_json(session, 'hybrid-manifest.json', record)
    return record


def verify_stage(session: Path, root: Path) -> dict:
    if not session.is_dir() or session.is_symlink():
        raise AcceptanceRejected('invalid session')
    meta = json.loads((session / 'hybrid-manifest.json').read_text())
    if meta.get('version') != VERSION or set(meta.get('source_sha256', {})) != set(STAGE_FILES):
        raise AcceptanceRejected('unknown staged source manifest')
    current = _verify_original(root)
    if meta.get('installed_main_sha256') != current['main_sha256']:
        raise AcceptanceRejected('production code changed since snapshot')
    for name, expected in meta['source_sha256'].items():
        if _digest(session / name) != expected:
            raise AcceptanceRejected('staged code changed: ' + name)
    return meta


def _verified_boot_record(result: dict) -> bool:
    if not isinstance(result, dict):
        return False
    if (result.get('status') != 'PASS_VERIFIED_BORROWED_PORT_FIXED_FC03'
            or result.get('identity_hex') != '20c2'
            or result.get('gfa_p80_hex') != '20'
            or not isinstance(result.get('gfa_p06_hex'), str)
            or len(result['gfa_p06_hex']) != 2
            or any(char not in '0123456789abcdef' for char in result['gfa_p06_hex'])
            or result['gfa_p06_hex'] == 'ff'
            or result.get('verified_vs1_return') is not True
            or result.get('no_second_serial_open') is not True
            or result.get('no_device_write') is not True
            or type(result.get('phase_count')) is not int
            or result['phase_count'] != 1):
        return False
    try:
        if any(len(bytes.fromhex(result[k])) != 32 for k in
               ('ram_0f20_32_hex', 'ram_1c60_32_hex')):
            return False
    except (KeyError, ValueError, TypeError):
        return False
    return True


def worker(session: Path) -> int:
    """Fail closed and persist diagnostics even if staged verification fails.

    Earlier builds created ``inprocess-*`` sessions, which the legacy
    recovery validator rejects before the worker could write measurement.json.
    The outer catch now includes all imports, source checks and lock entry.
    """
    outcome = {'version': VERSION, 'experiment_pass': False,
               'vs1_link_restored': False, 'errors': [], 'history': [],
               'source_sha256': {}, 'stage_rc': None,
               'verified_boot_result': False}
    try:
        live = _live()
        state = live.verify_session(session)
        verify_stage(session, ROOT)
        outcome['source_sha256'] = state['source_sha256']
        base = live.base
        with contextlib.ExitStack() as critical:
            critical.enter_context(pump_lease())
            require_pump_inactive(base.unit_state)
            critical.enter_context(base.locks())
            live.guard_other_research()
            if base.read_settings(base.SETTINGS.read_text())['port_optolink'] != state['port']:
                raise AcceptanceRejected('serial port changed since preflight')
            if base.unit_state(base.MAIN).get('WorkingDirectory') != str(ROOT):
                raise AcceptanceRejected('original production service not owned by /opt/optolink')
            for unit, expected in state['services'].items():
                if (base.unit_state(unit).get('ActiveState') == 'active') != expected:
                    raise AcceptanceRejected('original service snapshot differs: ' + unit)
            base.pause_services(session, state)
            live.guard_other_research()
            base.assert_no_owner(state['port'])
            env = os.environ.copy()
            env['PYTHONPATH'] = f'{session}:{ROOT}'
            env['OPTO_RESEARCH_DISPATCH_SHADOW'] = '1'
            env['OPTO_HYBRID_BOOT_ONESHOT'] = 'confirmed-readonly'
            env['OPTO_HYBRID_REPORT_DIR'] = str(session)
            proc = subprocess.run(
                [base.PYTHON, '-u', str(session / 'optolinkvs2_switch.py')],
                cwd=str(ROOT), env=env, check=False, timeout=75)
            outcome['stage_rc'] = proc.returncode
            path = session / 'hybrid-result.json'
            boot = json.loads(path.read_text()) if path.is_file() and not path.is_symlink() else {}
            outcome['verified_boot_result'] = _verified_boot_record(boot)
            if proc.returncode != 0 or not outcome['verified_boot_result']:
                raise AcceptanceRejected('patched original main loop did not verify hybrid boot')
            outcome['experiment_pass'] = True
    except BaseException as exc:
        detail = type(exc).__name__ + ': ' + str(exc)
        outcome['errors'].append(detail)
        print('HYBRID_WORKER_ERROR=' + detail[:400], file=sys.stderr, flush=True)
    finally:
        try:
            _atomic_json(session, 'measurement.json', outcome)
        except BaseException as exc:
            print('HYBRID_MEASUREMENT_WRITE_ERROR=' + type(exc).__name__,
                  file=sys.stderr, flush=True)
            return 1
    return 0 if outcome['experiment_pass'] else 1


def staged_preflight(session: Path, root: Path) -> dict:
    """Read-only boot check using the *staged* imports and legacy validator.

    No systemctl, serial port, MQTT, service start/stop, or worker execution.
    Used as a separate process before systemd-run is even invoked.
    """
    live = _live()
    state = live.verify_session(session)
    manifest = verify_stage(session, root)
    return {'session_version': state['version'],
            'staged_version': manifest['version'],
            'recovery_entry': str(session / 'live_probe.py'),
            'source_files_verified': len(manifest['source_sha256'])}


def run_staged_preflight(session: Path, root: Path, python: str) -> None:
    """Launch an independent exact staged entrypoint without side effects."""
    env = os.environ.copy()
    env['PYTHONPATH'] = f'{session}:{root}'
    cmd = [python, '-u', str(session / 'hybrid_acceptance.py'),
           '--staged-preflight', str(session), '--root', str(root)]
    try:
        completed = subprocess.run(cmd, cwd=str(root), env=env,
                                   capture_output=True, text=True, timeout=15,
                                   check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AcceptanceRejected('staged worker preflight could not start: '
                                 + type(exc).__name__) from exc
    if (completed.returncode != 0 or
            'HYBRID_STAGED_PREFLIGHT=PASS' not in completed.stdout.splitlines()):
        detail = (completed.stderr.strip() or completed.stdout.strip())[-1200:]
        raise AcceptanceRejected('staged worker/recovery preflight failed '
                                 f'(rc={completed.returncode}): {detail}')


def execute() -> int:
    live = _live()
    if os.geteuid() != 0:
        raise AcceptanceRejected('root required for supervised hardware one-shot')
    _verify_original(ROOT)  # all static checks before service activity
    values, services = live.preflight()
    # A prior failed release reported no recovery manifest. Before pausing
    # anything, prove the original production MQTT GFA path is healthy now.
    health_before = live.read_health()
    if (set(health_before) != {'P80', 'P06'} or
            any(entry.get('valid') is not True for entry in health_before.values())):
        raise AcceptanceRejected('original production GFA P80/P06 health not verified; no services stopped')
    base = live.base
    if base.unit_state(UNIT).get('ActiveState') not in ('inactive', 'failed', 'not-found'):
        raise AcceptanceRejected('in-process acceptance unit already running')
    with contextlib.ExitStack() as critical:
        critical.enter_context(pump_lease())
        require_pump_inactive(base.unit_state)
        critical.enter_context(base.locks())
        BASE.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(BASE, 0o700)
        stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        session = BASE / f'run-inprocess-{stamp}-{os.getpid()}'
        live.snapshot(session, values, services, experiment='standard')
        stage(session, ROOT)
    # Run the real staged entrypoint's import graph and legacy validate_session
    # BEFORE starting systemd or pausing any production service.
    run_staged_preflight(session, ROOT, base.PYTHON)
    print('HYBRID_STAGED_PREFLIGHT=PASS', flush=True)
    argv = [
        'systemd-run', '--unit=' + UNIT, '--wait', '--collect',
        '--property=Type=exec', '--property=RuntimeMaxSec=105',
        '--property=TimeoutStopSec=90', '--property=KillMode=control-group',
        '--property=UMask=0077',
        f'--property=ExecStopPost={base.PYTHON} -u {session / "live_probe.py"} --recover {session}',
        base.PYTHON, '-u', str(session / 'hybrid_acceptance.py'), '--worker', str(session),
    ]
    print('HYBRID_SESSION=' + str(session), flush=True)
    try:
        proc = subprocess.run(argv, check=False)
        unit_rc = proc.returncode
    except (OSError, subprocess.SubprocessError) as exc:
        print('HYBRID_SYSTEMD_ERROR=' + type(exc).__name__, flush=True)
        unit_rc = 1
    try:
        outcome = json.loads((session / 'measurement.json').read_text())
    except (OSError, ValueError):
        outcome = {}
    try:
        recovery = json.loads((session / 'recovery.json').read_text())
    except (OSError, ValueError):
        recovery = {}
    try:
        boot_path = session / 'hybrid-result.json'
        boot = (json.loads(boot_path.read_text())
                if boot_path.is_file() and not boot_path.is_symlink() else {})
    except (OSError, ValueError):
        boot = {}
    boot_verified = _verified_boot_record(boot)
    restored = bool(recovery.get('services_restored') and recovery.get('overall_verified'))
    # Independently report the actual production state even when the recovery
    # manifest is missing. Observation is NOT a substitute for recovery proof.
    try:
        production_state = base.unit_state(base.MAIN)
        production_active = (production_state.get('ActiveState') == 'active'
                             and production_state.get('SubState') == 'running'
                             and production_state.get('WorkingDirectory') == str(ROOT))
    except (OSError, RuntimeError, subprocess.SubprocessError):
        production_active = False
    health = live.read_health() if production_active else {}
    healthy = set(health) == {'P80','P06'} and all(v.get('valid') for v in health.values())
    passed = bool(unit_rc == 0 and restored and healthy and outcome.get('experiment_pass')
                  and outcome.get('verified_boot_result') and boot_verified)
    label = 'PASS_VERIFIED_INPROCESS_FIXED_FC03' if passed else 'FAIL_OR_NOT_VERIFIED'
    report = {'result': label, 'unit_rc': unit_rc, 'session': str(session),
              'worker_verified': bool(outcome.get('verified_boot_result')),
              'boot_record_verified': boot_verified,
              'phase_ms': boot.get('time_ms', {}) if boot_verified else {},
              'gfa': ({'P80': boot['gfa_p80_hex'], 'P06': boot['gfa_p06_hex']}
                      if boot_verified else {}),
              'services_restored': restored,
              'production_splitter_running': production_active,
              'production_health': health,
              'worker_errors': outcome.get('errors',[]),
              'independent_recovery': recovery.get('independent_link_restore',{}),
              'production_changes_performed': False}
    live.base.atomic_json(session / 'hybrid-summary.json', report)
    print('HYBRID_SUMMARY=' + json.dumps(report, sort_keys=True), flush=True)
    print('RESULT=' + label, flush=True)
    return 0 if passed else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    group=p.add_mutually_exclusive_group()
    group.add_argument('--execute',action='store_true')
    group.add_argument('--worker',type=Path,help=argparse.SUPPRESS)
    group.add_argument('--staged-preflight',type=Path,help=argparse.SUPPRESS)
    p.add_argument('--accept-telemetry-pause',action='store_true')
    p.add_argument('--root',type=Path,default=ROOT,
                   help='source audit target for PLAN ONLY; hardware always uses original /opt/optolink')
    args=p.parse_args(argv)
    os.umask(0o077)
    if args.staged_preflight is not None:
        if args.accept_telemetry_pause:
            raise AcceptanceRejected('staged preflight never accepts a service pause')
        details = staged_preflight(args.staged_preflight, args.root)
        print('HYBRID_STAGED_PREFLIGHT=PASS')
        print('HYBRID_STAGED_PREFLIGHT_DETAILS=' + json.dumps(details, sort_keys=True))
        return 0
    if args.worker is not None:
        if args.accept_telemetry_pause or os.geteuid() != 0 or 'INVOCATION_ID' not in os.environ:
            raise AcceptanceRejected('worker only permitted in supervised systemd unit')
        return worker(args.worker)
    if args.execute:
        if not args.accept_telemetry_pause or args.root != ROOT:
            raise AcceptanceRejected('explicit opt-in and exactly original install required')
        return execute()
    if args.accept_telemetry_pause:
        raise AcceptanceRejected('no telemetry pause without --execute')
    report = _verify_original(args.root)
    print('HYBRID_PLAN=READY_FOR_STAGED_SUPERVISED_ONE_SHOT')
    print('HYBRID_COMPAT=' + json.dumps(report, sort_keys=True))
    print('NO_SERVICES_OR_SERIAL_TOUCHED')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (AcceptanceRejected, OSError, ValueError, RuntimeError) as exc:
        print('HYBRID_REFUSED_OR_FAILED=' + type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
        raise SystemExit(1)
