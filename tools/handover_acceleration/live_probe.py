#!/usr/bin/env python3
"""ONE real read-only WB2A acceptance run, backed by independent systemd recovery.

This script is inert without BOTH --execute and --accept-telemetry-pause.
No arbitrary address, GFA write, P300 memory, RPC, RAM, service editing, or
heater control is exposed. It temporarily stops/restores the pre-existing
services only when explicitly invoked by the operator and all guards pass.

Only one verified VS1->P300->VS1 cycle; this validates a NEW coordinator,
not an unverified fast-switch command or a claimed under-4s optimization.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

# Sibling module copies are placed in the session directory before the
# supervisor starts. No file is ever imported from /opt/optolink.
try:
    from .coordinator import HandoverCoordinator, Mode, PortLease
    from . import legacy_probe as base
except ImportError:  # systemd executes the private staged single-file entrypoint
    from coordinator import HandoverCoordinator, Mode, PortLease
    import legacy_probe as base

VERSION = 'handover-acceleration-live-acceptance-v1'
BASE_DIR = Path('/root/p300-trial-work/handover-acceleration-live-results')
UNIT = 'optolink-handover-acceleration-live.service'
SOURCE_NAMES = ('live_probe.py', 'coordinator.py', 'legacy_probe.py')
# This pinned legacy helper is read-only and supplies the already-tested
# service-manifest, exclusive-serial and systemd recovery primitives.
LEGACY_BLOB_SHA = '006c3c75f6e5e0dc3f564156985912bffb1d9bdc'

# Do not touch any running separate research logger or another probe.
CONFLICT_UNITS = (
    'optolink-p300-rpm-trigger.service',
    'optolink-p300-deep-logger.service',
    'optolink-p300-temporal.service',
    'optolink-p300-p06-focus.service',
    'optolink-p300-fullram-logger.service',
    'optolink-uart1-overnight.service',
    'optolink-uart1-p300-focus.service',
    'optolink-uart1-dma0-cycle.service',
    'optolink-p300-trial.service',
    'optolink-handover-probe.service',
)
CONFLICT_SCRIPTS = (
    'wb2a-p300-rpm-trigger.py', 'wb2a-p300-deep-logger.py',
    'wb2a-p300-temporal-logger.py', 'wb2a-p300-p06-focus.py',
    'wb2a-p300-fullram-logger.py', 'wb2a-uart1-overnight.py',
    'wb2a-handover-probe.py', 'wb2a-uart1-p300-focus.py',
    'wb2a-uart1-dma0-cycle.py', 'wb2a-research-batch.py',
    'vs1-p300-handover-latency-probe.py', 'wb2a-p87-p300-check.py',
)

# An independent namespace; reuse legacy lock names used by the research
# helpers, but never take ownership of a port held by a separate process.
base.ROOT = BASE_DIR
base.UNIT = UNIT


def refuse(message: str):
    raise base.ProbeError(message)


def guard_other_research(unit_state=base.unit_state, proc_root=Path('/proc')):
    for unit in CONFLICT_UNITS:
        state = unit_state(unit)
        if state.get('ActiveState') not in ('inactive', 'failed', 'not-found'):
            refuse(f'RUNNING_OR_UNKNOWN_RESEARCH_UNIT: {unit}: {state.get("ActiveState")}')
    for pid in proc_root.iterdir():
        if not pid.name.isdigit() or int(pid.name) == os.getpid():
            continue
        try:
            cmd = (pid / 'cmdline').read_bytes().replace(b'\x00', b' ').decode('utf-8', 'replace')
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError as exc:
            refuse(f'cannot inspect process {pid.name}: {exc}')
        if any(tag in cmd for tag in CONFLICT_SCRIPTS):
            refuse(f'RESEARCH_PROCESS_ACTIVE: pid={pid.name}')


def preflight():
    if not hasattr(os, 'geteuid') or os.geteuid() != 0:
        refuse('root required for ONE supervised real test')
    guard_other_research()
    values, states = base.preflight()  # also checks original VS1 is active
    if base.unit_state(UNIT).get('ActiveState') not in ('inactive', 'failed', 'not-found'):
        refuse('handover acceleration live unit already exists')
    if not Path(values['port_optolink']).exists():
        refuse('configured serial device does not exist')
    return values, states


def git_blob_sha(data: bytes) -> str:
    """Pin the reviewed legacy recovery helper by its exact git blob SHA."""
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def ensure_hashes(session: Path, state: dict):
    for filename, expected in state['source_sha256'].items():
        path = session / filename
        if (not path.is_file() or path.is_symlink() or
                hashlib.sha256(path.read_bytes()).hexdigest() != expected):
            refuse('staged source changed: ' + filename)


def verify_session(session: Path):
    state = base.validate_session(session)
    if state.get('version') != VERSION:
        refuse('wrong acceptance test version')
    if set(state.get('source_sha256', {})) != set(SOURCE_NAMES):
        refuse('unexpected session source manifest')
    ensure_hashes(session, state)
    if git_blob_sha((session / 'legacy_probe.py').read_bytes()) != LEGACY_BLOB_SHA:
        refuse('legacy recovery helper does not match reviewed SHA')
    return state


def snapshot(session: Path, values: dict, services: dict, *, experiment: str = "standard"):
    session.mkdir(mode=0o700)
    here = Path(__file__).resolve().parent
    hashes = {}
    for name in SOURCE_NAMES:
        src, dst = here / name, session / name
        if not src.is_file() or src.is_symlink():
            refuse('missing or symbolic source: ' + name)
        if name == 'legacy_probe.py' and git_blob_sha(src.read_bytes()) != LEGACY_BLOB_SHA:
            refuse('wrong legacy recovery helper source version')
        shutil.copyfile(src, dst)
        os.chmod(dst, 0o600)
        hashes[name] = hashlib.sha256(dst.read_bytes()).hexdigest()
    base.atomic_json(session / 'state.json', dict(
        version=VERSION, services=services, restore=[],
        port=values['port_optolink'], source_sha256=hashes,
        start_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
        expected_device='20c2', expected_software='0103', expected_p80='20',
        accept_telemetry_pause=True, experiment=experiment,
    ))



def enq_trace(events: list[dict]) -> list[dict]:
    """Timestamp *individual* ENQs relative to EOT: host-side, not logic-analyzer."""
    groups = []
    syncing = False
    for item in events:
        if item['direction'] == 'TX':
            if item['hex'] == '04':
                groups.append({'eot_t_monotonic': item['t_monotonic'], 'enq_wait_ms': []})
                syncing = True
            else:
                syncing = False  # any subsequent TX leaves the ENQ handshake
        elif syncing and groups and item['direction'] == 'RX' and item['hex'] == '05':
            last = groups[-1]
            last['enq_wait_ms'].append(round((item['t_monotonic'] -
                                               last['eot_t_monotonic']) * 1000, 3))
    names = ('cold_vs1_setup', 'vs1_to_p300', 'p300_to_vs1')
    for idx, group in enumerate(groups):
        group['name'] = names[idx] if idx < len(names) else 'recovery_or_unexpected'
    return groups


def worker(session: Path) -> int:
    state = verify_session(session)
    experiment = state.get("experiment", "standard")
    if experiment not in ("standard", "early_p300_start"):
        refuse("unknown experiment variant in session before service stop")
    result = dict(version=VERSION, run='ONE_READ_ONLY_REAL_HANDOVER',
                  experiment_pass=False, vs1_link_restored=False,
                  phases_ms={}, gfa={}, errors=[], history=[], events=[], enq_trace=[],
                  source_sha256=state['source_sha256'])
    # Defer graceful stop until a complete telegram/handshake has finished.
    # systemd ExecStopPost remains independent if the worker dies or is killed.
    pending_signals: list[int] = []
    def interrupted(signum, _frame):
        pending_signals.append(signum)
    def check_stop():
        if pending_signals:
            refuse('operator stop signal_' + str(pending_signals[0]))
    old_signals = {s: signal.getsignal(s) for s in
                   (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
    for s in old_signals:
        signal.signal(s, interrupted)
    manager = None
    wire_reference = None
    with base.locks():
        try:
            guard_other_research()
            current = base.read_settings(base.SETTINGS.read_text())
            if current['port_optolink'] != state['port']:
                refuse('serial settings changed since preflight')
            if base.unit_state(base.MAIN).get('WorkingDirectory') != '/opt/optolink':
                refuse('production service is not original VS1')
            for unit, previously_active in state['services'].items():
                if (base.unit_state(unit).get('ActiveState') == 'active') != previously_active:
                    refuse('service snapshot mismatch: ' + unit)
            base.pause_services(session, state)
            guard_other_research()
            base.assert_no_owner(state['port'])
            start_setup = time.monotonic()
            manager = HandoverCoordinator(
                lambda: base.open_serial(state['port']),
                PortLease(session / 'port.lease'))
            with manager:
                wire_reference = manager.wire
                setup_done = time.monotonic()
                result['phases_ms']['cold_setup'] = round((setup_done - start_setup) * 1000, 3)
                if manager.mode is not Mode.VS1_VERIFIED:
                    refuse('cold VS1 not verified')
                check_stop()
                t0 = time.monotonic()
                if experiment == "early_p300_start":
                    manager.to_p300_early_start_experiment()  # known START before ENQ
                else:
                    manager.to_p300()  # verified documented START after ENQ
                t1 = time.monotonic()
                check_stop()
                # No duplicate P300 ID read: already checked inside to_p300().
                manager.to_vs1_fast()  # re-verifies VS1 ID, software, P80, P06
                t2 = time.monotonic()
                check_stop()
                # Values below were physically read *during this VS1 return*,
                # not cached from an earlier session. Reject aged snapshots.
                snap = manager.verified_gfa_snapshot(max_age=.75)
                result['gfa'].update({k: v.hex() for k, v in snap.items()})
                for name in ('P09', 'P87'):
                    result['gfa'][name] = manager.gfa_read(name).hex()
                    check_stop()
                t3 = time.monotonic()
                result['phases_ms'].update({
                    'vs1_to_p300_with_verified_identity': round((t1-t0)*1000,3),
                    'p300_to_vs1_fast_with_verified_gfa': round((t2-t1)*1000,3),
                    'remaining_gfa_block_p09_p87': round((t3-t2)*1000,3),
                    'roundtrip_with_gfa': round((t3-t0)*1000,3),
                })
                if result['gfa']['P80'] != '20' or result['gfa']['P06'] == 'ff':
                    refuse('identity or GFA invalid')
                if manager.mode is not Mode.VS1_VERIFIED:
                    refuse('final VS1 not verified')
            # Count success only after the port has actually closed and the
            # lease has been released without a context-manager exception.
            result['vs1_link_restored'] = manager.mode is Mode.DETACHED
            result['experiment_pass'] = result['vs1_link_restored']
        except BaseException as exc:
            result['errors'].append(type(exc).__name__ + ': ' + str(exc))
        finally:
            # Preserve useful frame timing evidence even if the manager raised.
            if manager is not None:
                result['history'] = manager.history[:]
            if wire_reference is not None:
                result['events'] = [dict(direction=k, hex=v, t_monotonic=t)
                                    for k,v,t in wire_reference.events]
                result['enq_trace'] = enq_trace(result['events'])
            # Do not let another SIGTERM truncate the durable evidence.
            for s in old_signals:
                signal.signal(s, signal.SIG_IGN)
            try:
                base.atomic_json(session / 'measurement.json', result)
            finally:
                for s, previous in old_signals.items():
                    signal.signal(s, previous)
    return 0 if result['experiment_pass'] and result['vs1_link_restored'] and not result['errors'] else 1


def link_restore(session: Path, state: dict) -> dict:
    """An entirely new process runs after the worker exited, including SIGKILL."""
    note = dict(attempted=False, verified=False, error=None)
    if base.MAIN not in state['restore']:
        note['verified'] = True  # no production service stopped by this trial
        return note
    mfile = session / 'measurement.json'
    if mfile.exists():
        try:
            recorded = json.loads(mfile.read_text())
            if recorded.get('experiment_pass') and recorded.get('vs1_link_restored'):
                # Main will independently reinitialize VS1 on start. Avoid
                # additional EOT when worker already ended in verified VS1.
                note['verified'] = True
                return note
        except (ValueError, OSError):
            pass
    note['attempted'] = True
    port = None
    try:
        guard_other_research()
        base.assert_no_owner(state['port'])
        port = base.open_serial(state['port'])
        w = base.Wire(port)
        w.enter_vs1(2)
        w.vs1(base.VS1_SOFTWARE, 2, base.SOFTWARE)
        w.vs1(base.GFA['P80'], 1, b'\x20')
        p06 = w.vs1(base.GFA['P06'], 1)
        if p06 == b'\xff':
            refuse('VS1 P06 FF after independent recovery')
        note['verified'] = True
    except BaseException as exc:
        note['error'] = type(exc).__name__ + ': ' + str(exc)
    finally:
        if port is not None:
            port.close()
    return note


def recover(session: Path) -> int:
    state = verify_session(session)
    link = dict(attempted=False, verified=False, error='not yet checked')
    error = None
    try:
        with base.locks():
            # If another research owner has materialized, do not open this
            # port or revive another owner over it; leave explicit failure.
            guard_other_research()
            link = link_restore(session, state)
            code = base.recover(session)  # main first, writers only if main healthy
            # base.recover() creates recovery.json; retain its original proof.
            record = json.loads((session / 'recovery.json').read_text())
            record['independent_link_restore'] = link
            record['overall_verified'] = bool(code == 0 and link['verified'])
            base.atomic_json(session / 'recovery.json', record)
            return 0 if record['overall_verified'] else 1
    except BaseException as exc:
        error = type(exc).__name__ + ': ' + str(exc)
        base.atomic_json(session / 'recovery.json', {
            'services_restored': False, 'overall_verified': False,
            'independent_link_restore': link, 'errors': [error]})
        return 1


def parse_debug_health(stdout: str, command: str, expected_addr: int,
                       key: str) -> dict:
    """Extract the actual GFA response after optolink-debug's MQTT banner."""
    lines = [line.strip() for line in stdout.splitlines() if ' <- ' in line]
    if len(lines) != 1:
        return {'valid': False, 'response': '', 'reason': 'MISSING_OR_MULTIPLE_REPLY_LINES'}
    echoed, _, detail = lines[0].partition(' <- ')
    if echoed.strip() != command:
        return {'valid': False, 'response': '', 'reason': 'UNEXPECTED_ECHO'}
    topic, separator, response = detail.partition(': ')
    if not separator or not topic.strip():
        return {'valid': False, 'response': '', 'reason': 'NO_MQTT_REPLY_OR_TIMEOUT'}
    response = response.strip()
    fields = response.split(';')
    if len(fields) != 3 or fields[0] != '1':
        return {'valid': False, 'response': response[:100], 'reason': 'INVALID_STATUS_OR_FIELDS'}
    try:
        received_addr = int(fields[1], 0)
    except ValueError:
        return {'valid': False, 'response': response[:100], 'reason': 'INVALID_ADDRESS'}
    if received_addr != expected_addr:
        return {'valid': False, 'response': response[:100], 'reason': 'WRONG_ADDRESS'}
    value = fields[2]
    if len(value) != 2 or any(c not in '0123456789abcdefABCDEF' for c in value):
        return {'valid': False, 'response': response[:100], 'reason': 'INVALID_RAW_BYTE'}
    if value.lower() == 'ff':
        return {'valid': False, 'response': response[:100], 'reason': 'INVALID_FF'}
    if key == 'P80' and value.lower() != '20':
        return {'valid': False, 'response': response[:100], 'reason': 'WRONG_P80'}
    return {'valid': True, 'response': response, 'reason': 'OK'}


def read_health() -> dict:
    """MQTT via original splitter only; do not open a second serial handle."""
    results = {}
    for key, address in (('P80', 0x4050), ('P06', 0x4006)):
        command = f'gfaread;0x{address:04x};1;raw;False'
        args = ['optolink-debug', 'request', command, '--timeout', '8']
        try:
            output = subprocess.run(args, capture_output=True, text=True,
                                    timeout=13, check=False)
            result = parse_debug_health(output.stdout, command, address, key)
            result['rc'] = output.returncode
            if output.returncode != 0:
                result['valid'] = False
                result['reason'] = 'DEBUG_CLIENT_EXIT_NONZERO'
            results[key] = result
        except (OSError, subprocess.TimeoutExpired) as exc:
            results[key] = {'valid': False, 'response': '',
                            'reason': type(exc).__name__ + ': ' + str(exc)}
    return results


def health_only() -> int:
    """No stop/start or serial access; the existing MQTT owner handles reads."""
    guard_other_research()
    main = base.unit_state(base.MAIN)
    if (main.get('ActiveState') != 'active' or
            main.get('SubState') != 'running' or
            main.get('WorkingDirectory') != '/opt/optolink'):
        refuse('production VS1 splitter not confirmed active; health-only refused')
    health = read_health()
    passed = set(health) == {'P80','P06'} and all(v.get('valid') for v in health.values())
    print('PRODUCTION_HEALTH=' + ('PASS' if passed else 'FAIL_NOT_VERIFIED'),flush=True)
    print('PRODUCTION_HEALTH_JSON=' + json.dumps(health,sort_keys=True),flush=True)
    return 0 if passed else 1


def execute(*, experiment: str = "standard") -> int:
    if experiment not in ("standard", "early_p300_start"):
        refuse("unknown experiment requested")
    values, services = preflight()
    with base.locks():
        base.ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(base.ROOT, 0o700)
        stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        session = base.ROOT / f'run-{stamp}-{os.getpid()}'
        snapshot(session, values, services, experiment=experiment)
    prog = session / 'live_probe.py'
    argv = [
        'systemd-run', '--unit=' + UNIT, '--wait', '--collect',
        '--property=Type=exec', '--property=RuntimeMaxSec=120',
        '--property=TimeoutStopSec=90', '--property=KillMode=control-group',
        '--property=UMask=0077',
        f'--property=ExecStopPost={base.PYTHON} -u {prog} --recover {session}',
        base.PYTHON, '-u', str(prog), '--worker', str(session),
    ]
    print('SESSION=' + str(session), flush=True)
    try:
        completed = subprocess.run(argv, check=False)
        service_rc = completed.returncode
    except BaseException as exc:
        print('SUPERVISOR_ERROR=' + str(exc), flush=True)
        service_rc = 1
    measurement = json.loads((session / 'measurement.json').read_text()) if (session / 'measurement.json').exists() else {}
    recovery = json.loads((session / 'recovery.json').read_text()) if (session / 'recovery.json').exists() else {}
    safe = bool(recovery.get('services_restored') and recovery.get('overall_verified'))
    # Separate fresh production GFA check is optional data, not a replacement
    # for true recovery status; still perform it to minimize operator roundtrips.
    health = read_health() if safe and measurement.get('experiment_pass') else {}
    ok = bool(service_rc == 0 and safe and measurement.get('experiment_pass') and
              measurement.get('vs1_link_restored'))
    ok = ok and set(health) == {'P80', 'P06'} and all(h.get('valid') for h in health.values())
    label = ('PASS_VERIFIED_READ_ONLY_EARLY_START_EXPERIMENT'
             if experiment == 'early_p300_start' else 'PASS_VERIFIED_READ_ONLY_REAL_HANDOVER')
    report = {'result': label if ok else 'FAIL_OR_NOT_VERIFIED',
              'experiment': experiment,
              'session': str(session), 'unit_rc': service_rc,
              'phase_ms': measurement.get('phases_ms'),
              'enq_trace': measurement.get('enq_trace'), 'gfa': measurement.get('gfa'),
              'measurement_errors': measurement.get('errors'),
              'independent_recovery': recovery.get('independent_link_restore'),
              'services_restored': recovery.get('services_restored'),
              'recovery_errors': recovery.get('errors'),
              'production_health': health}
    base.atomic_json(session / 'summary.json', report)
    print('SUMMARY=' + json.dumps(report, sort_keys=True), flush=True)
    print('RESULT=' + report['result'], flush=True)
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--execute', action='store_true')
    actions.add_argument('--health-only', action='store_true')
    actions.add_argument('--worker', type=Path, help=argparse.SUPPRESS)
    actions.add_argument('--recover', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--accept-telemetry-pause', action='store_true')
    parser.add_argument('--experiment-early-p300-start', action='store_true',
                        help='experimental, known START immediately after EOT before ENQ')
    args = parser.parse_args()
    os.umask(0o077)
    if args.worker or args.recover:
        if args.accept_telemetry_pause or os.geteuid() != 0 or 'INVOCATION_ID' not in os.environ:
            refuse('internal worker/recovery must be invoked by systemd only')
        return worker(args.worker) if args.worker else recover(args.recover)
    if args.health_only:
        if args.experiment_early_p300_start or args.accept_telemetry_pause:
            refuse('health-only never accepts any experiment or telemetry pause')
        return health_only()
    if args.experiment_early_p300_start and not args.execute:
        refuse('early-start trial requires --execute and explicit telemetry pause')
    if args.execute:
        if not args.accept_telemetry_pause:
            refuse('must explicitly accept temporary telemetry/service pause')
        return execute(experiment='early_p300_start' if args.experiment_early_p300_start else 'standard')
    print('PLAN ONLY. One real read-only VS1->P300->VS1 cycle (new manager).')
    print('No serial or systemd activity without --execute --accept-telemetry-pause.')
    print('Temporary interruption of previously-active original services; selective restore.')
    print('Refuses if P300/RPM logger or other serial research process is active.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (base.ProbeError, OSError, subprocess.SubprocessError, ValueError) as exc:
        print('REFUSED_OR_FAILED=' + str(exc), file=sys.stderr)
        raise SystemExit(1)
