#!/usr/bin/env python3
"""Bounded UART1-focus Physical_READ and 55D3 status; inert unless --execute.

Only FC03 RAM at 1600/32 and 1620/32, plus FC01 55D3/11; no writes.
Known external GFA readers are paused; original VS1 returns via ExecStopPost.
The pinned handover helper supplies verified framing and lifecycle primitives.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

VERSION = '1.0.0-uart1'
HELPER = 'wb2a-handover-probe.py'
HELPER_SHA256 = 'e419e0a32206a7398edadff2cb1f5f57ac1884df6532ee26c3b3e75e38cd1269'
ROOT = Path('/root/p300-trial-work/uart1-p300-results')
UNIT = 'optolink-uart1-p300-focus.service'
STATUS = bytes.fromhex('4105000155d30b39')  # FC01 55D3/11, status only.
RAM0 = bytes.fromhex('410500031600203e')  # FC03 physical 1600/32 only.
RAM1 = bytes.fromhex('410500031620205e')  # FC03 physical 1620/32 only.
RAM_READS = ((RAM0, 0x1600), (RAM1, 0x1620))
# 64 bytes total around the previously observed UART1 DMA0 TX source at 0x161B.
INTERVAL = 2.0
RESEARCH_ONLY = True  # Changed bytes do not imply a GFA connection or a tachometer.


def load_helper():
    path = Path(__file__).resolve().with_name(HELPER)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != HELPER_SHA256:
        raise RuntimeError('PINNED_HANDOVER_HELPER_MISMATCH')
    spec = importlib.util.spec_from_file_location('p87_handover_support', path)
    module = importlib.util.module_from_spec(spec)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


h = load_helper()  # No serial/network/service operations on import.
Error = h.ProbeError


def seconds_ok(value: int) -> int:
    if type(value) is not int or not 30 <= value <= 180:
        raise Error('seconds must be an integer in 30..180')
    return value


class UART1Wire(h.Wire):
    """Phase allowlists forbid even VS1 reads during the P300-only interval."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.phase = 'reference'
        self.last_gfa_rx = None
        self.phase_start = None
        self.phase_end = None

    def send(self, data: bytes) -> None:
        vs1 = {b'\x04', b'\x01' + h.VS1_ID, h.VS1_ID, h.VS1_SOFTWARE, *h.GFA.values()}
        entering = {b'\x04', b'\x16\x00\x00', b'\x06', h.P300_ID, h.P300_SOFTWARE}
        allowed = {'reference': vs1, 'entry': entering,
                   'observation': {STATUS, RAM0, RAM1, b'\x06'}, 'recovery': vs1}
        if data not in allowed.get(self.phase, set()):
            raise Error('TX_FORBIDDEN_IN_PHASE_' + self.phase)
        self.record('TX', data)
        if self.port.write(data) != len(data):
            raise Error('short serial write')

    def p300_read(self, request: bytes, address: int, expected: bytes | None) -> bytes:
        approved = ((h.P300_ID, 0x00F8, 1, h.IDENT, 2),
                    (h.P300_SOFTWARE, 0x778C, 1, h.SOFTWARE, 2),
                    (STATUS, 0x55D3, 1, None, 11),
                    (RAM0, 0x1600, 3, None, 32),
                    (RAM1, 0x1620, 3, None, 32))
        matching = [pair for pair in approved
                    if (request, address, expected) == (pair[0], pair[1], pair[3])]
        if len(matching) != 1:
            raise Error('NOT_A_FIXED_P300_READ')
        _, _, function, _, wanted = matching[0]
        self.gap()
        self.send(request)
        end = self.clock() + 3.0
        if self.exact(1, end) != b'\x06':
            raise Error('P300_REQUEST_NOT_ACKNOWLEDGED')
        first = b'\x06'
        for _ in range(8):
            first = self.exact(1, end)
            if first != b'\x06':
                break
        if first != b'\x41':
            raise Error('P300_STX_MISSING')
        size = self.exact(1, end)[0]
        if not 5 <= size <= 37:
            raise Error('P300_RESPONSE_SIZE_INVALID')
        body = self.exact(size + 1, end)
        if (size + sum(body[:-1])) & 255 != body[-1]:
            raise Error('P300_CHECKSUM_INVALID')
        msg, fc, hi, lo, count = body[:5]
        if fc != function or (hi << 8 | lo) != address:
            raise Error('P300_FUNCTION_OR_ADDRESS_MISMATCH')
        if msg == 3:
            raise Error(f'P300_CONTROLLER_ERROR fc={fc:02x} addr={address:04x} payload=' + body[5:-1].hex())
        data = body[5:-1]
        if msg != 1 or count != wanted or len(data) != wanted or size != 5 + wanted:
            raise Error('P300_MESSAGE_OR_LENGTH_INVALID')
        if expected is not None and data != expected:
            raise Error('P300_IDENTITY_MISMATCH')
        if request == STATUS and data[7] == 0xFF:
            raise Error('UNREVIEWED_NATIVE_STATUS_FF')
        self.send(b'\x06')
        self.quiet()
        return data

    def reference(self) -> dict:
        self.enter_vs1(2)
        self.vs1(h.VS1_SOFTWARE, 2, h.SOFTWARE)
        values = self.gfa_block()
        self.last_gfa_rx = self.clock()
        return values

    def observe(self, seconds: int, on_sample, isolation_check) -> None:
        seconds_ok(seconds)
        if self.phase != 'reference' or self.last_gfa_rx is None:
            raise Error('REFERENCE_REQUIRED')
        self.phase = 'entry'
        self.enter_p300()  # Strict identity and firmware gates.
        self.phase = 'observation'
        self.phase_start = self.clock()
        deadline = self.phase_start + seconds
        index = 0
        while self.clock() < deadline:
            if index % 3 == 0:
                isolation_check()
            if self.clock() >= deadline:
                break
            status = self.p300_read(STATUS, 0x55D3, None)
            low = self.p300_read(RAM0, 0x1600, None)
            high = self.p300_read(RAM1, 0x1620, None)
            elapsed = self.clock() - self.phase_start
            row = dict(index=index+1, elapsed_s=elapsed,
                       since_last_external_gfa_s=self.clock()-self.last_gfa_rx,
                       utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                       native_b7=f'{status[7]:02x}', native_block=status.hex(),
                       ram_1600=low.hex(), ram_1620=high.hex(),
                       observed_dma_source_offset=0x161B-0x1600,
                       uart1_gfa_link_verified=False,
                       p06_rpm_alias_verified=False)
            self.samples.append(row)
            on_sample(row)
            index += 1
            self.sleep(max(0.0, min(self.clock()+INTERVAL, deadline)-self.clock()))
        self.phase_end = self.clock()

    def restore_link(self) -> dict:
        self.phase = 'recovery'
        self.enter_vs1(2)
        self.vs1(h.VS1_SOFTWARE, 2, h.SOFTWARE)
        return self.gfa_block()


def summarize(rows: list[dict]) -> dict:
    """Report changes only, never a GFA bus or actual blower RPM alias."""
    changes = {f'0x{x:04x}': 0 for x in range(0x1600,0x1640)}
    status_changes = []
    prev = None
    for row in rows:
        block = bytes.fromhex(row['ram_1600']+row['ram_1620'])
        if len(block) != 64:
            raise Error('SAMPLE_RAM_LENGTH_INVALID')
        if prev is not None:
            for j, (a, b) in enumerate(zip(prev[0], block)):
                if a != b:
                    changes[f'0x{0x1600+j:04x}'] += 1
            if row['native_b7'] != prev[1]:
                status_changes.append(dict(at_s=row['elapsed_s'], before=prev[1],
                                           after=row['native_b7']))
        prev = (block, row['native_b7'])
    changed = {addr: n for addr, n in changes.items() if n}
    return dict(
        outcome='CHANGES_SEEN_SOURCE_UNKNOWN' if changed else 'NO_CHANGES_IN_UART1_FOCUS',
        sample_count=len(rows), bytes_per_sample=64,
        physical_addresses=['0x1600/32', '0x1620/32'],
        dma0_source_reference='0x161b (historical UART1-TX SAR0 snapshot; not proven GFA)',
        observed_dma_source_changed=changes['0x161b'],
        changed_byte_count=len(changed),
        changed_address_counts=changed,
        native_p87_changes=status_changes,
        gfa_rx_during_p300=False,
        uart1_gfa_link_verified=False,
        p06_rpm_alias_verified=False,
        production_approved=False,
        ram_write_approved=False)

@contextlib.contextmanager
def locks():
    # Share all known diagnostic locks, including the still-running MQTT observer.
    with h.locks(), contextlib.ExitStack() as stack:
        for name in ('optolink-p87-mirror.lock', 'optolink-p87-p300-check.lock', 'optolink-uart1-p300-focus.lock'):
            fd = os.open('/run/lock/' + name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            stack.callback(os.close, fd)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def private_file(path: Path) -> None:
    info = path.lstat()
    if path.is_symlink() or not path.is_file() or info.st_uid != 0 or info.st_mode & 0o077:
        raise Error('SESSION_FILE_NOT_PRIVATE')


def session_state(session: Path) -> dict:
    if session.parent != ROOT or session.is_symlink() or not session.name.startswith('run-'):
        raise Error('INVALID_SESSION')
    info = session.stat()
    if info.st_uid != 0 or info.st_mode & 0o077:
        raise Error('SESSION_NOT_PRIVATE')
    private_file(session / 'state.json')
    state = json.loads((session / 'state.json').read_text())
    seconds_ok(state['seconds'])
    if (set(state['services']) != set(h.SERVICES)
            or any(type(v) is not bool for v in state['services'].values())
            or len(state['restore']) != len(set(state['restore']))
            or any(u not in h.SERVICES or not state['services'][u] for u in state['restore'])):
        raise Error('INVALID_RESTORE_MANIFEST')
    return state


def isolation(port: str) -> None:
    for unit in h.SERVICES:
        if h.unit_state(unit).get('ActiveState') not in ('inactive', 'failed'):
            raise Error('PRODUCTION_READER_RESTARTED_' + unit)
    h.assert_no_owner(port)


def run_worker(session: Path, state: dict) -> int:
    """Caller holds shared locks. All stop intentions are durable before action."""
    report = dict(version=VERSION, samples=[], errors=[], reference_gfa=None,
                  recovery_gfa=None, observation_complete=False, vs1_link_restored=False,
                  transport='P300 FC01 55D3/11 and FC03 RAM 1600/32, 1620/32; no external GFA during observation')
    wire = serial = None
    def stop(signum, frame):
        raise Error('INTERRUPTED_' + str(signum))
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, stop)
    try:
        current = h.read_settings(h.SETTINGS.read_text())
        if current['port_optolink'] != state['port']:
            raise Error('SETTINGS_CHANGED')
        if h.unit_state(h.MAIN).get('WorkingDirectory') != '/opt/optolink':
            raise Error('PRODUCTION_RUNTIME_CHANGED')
        for unit, was_active in state['services'].items():
            now = h.unit_state(unit).get('ActiveState')
            if now not in ('active', 'inactive', 'failed') or (now == 'active') != was_active:
                raise Error('SERVICE_CHANGED_SINCE_PREFLIGHT_' + unit)
        h.pause_services(session, state)
        isolation(state['port'])
        serial = h.open_serial(state['port'])
        wire = UART1Wire(serial)
        report['reference_gfa'] = wire.reference()
        print('PHASE=ENTERING_P300; external GFA polling paused', flush=True)
        with (session / 'samples.jsonl').open('x', encoding='utf-8') as out:
            previous = None
            def save(row):
                nonlocal previous
                if row['index'] == 1:
                    print('PHASE=P300_ONLY; first status + both bounded RAM frames validated', flush=True)
                out.write(json.dumps(row, sort_keys=True) + '\n')
                out.flush()
                if previous != row['native_b7'] or row['index'] % 10 == 0:
                    print(json.dumps({k:row[k] for k in (
                        'index', 'elapsed_s', 'native_b7',
                        'since_last_external_gfa_s')}, sort_keys=True), flush=True)
                previous = row['native_b7']
            wire.observe(state['seconds'], save, lambda: isolation(state['port']))
        report['observation_complete'] = True
    except BaseException as exc:
        report['errors'].append(str(exc) or type(exc).__name__)
    finally:
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(sig, signal.SIG_IGN)
        if wire is not None:
            report['samples'] = wire.samples
            report['comparison'] = summarize(wire.samples)
            report['p300_phase_start_monotonic'] = wire.phase_start
            report['p300_phase_end_monotonic'] = wire.phase_end
            try:
                isolation(state['port'])
                report['recovery_gfa'] = wire.restore_link()
                report['vs1_link_restored'] = True
            except BaseException as exc:
                report['errors'].append('LINK_RECOVERY: ' + (str(exc) or type(exc).__name__))
            report['trace'] = wire.trace
        if serial is not None:
            try:
                serial.close()
            except BaseException as exc:
                report['errors'].append('SERIAL_CLOSE: ' + str(exc))
        h.atomic_json(session / 'measurement.json', report)
    return int(bool(report['errors']) or not report['observation_complete'] or not report['vs1_link_restored'])


def worker(session: Path) -> int:
    state = session_state(session)
    with locks():
        return run_worker(session, state)


def recover(session: Path) -> int:
    """ExecStopPost runs after worker exit, including a killed worker."""
    state = session_state(session)
    restored, errors = [], []
    with locks():
        # Even partial stop failures require the main service to be healthy first.
        if state['restore']:
            try:
                if h.MAIN in state['restore']:
                    h.command(['systemctl', 'start', h.MAIN])
                h.wait_main_ready()
                if h.MAIN in state['restore']:
                    restored.append(h.MAIN)
            except BaseException as exc:
                errors.append('VS1_NOT_READY_WRITERS_DEFERRED: ' + str(exc))
        if not errors:
            for unit in reversed(state['restore']):
                if unit == h.MAIN:
                    continue
                try:
                    h.command(['systemctl', 'start', unit])
                    if unit != 'optolink-clock-sync.service' and h.unit_state(unit).get('ActiveState') != 'active':
                        raise Error('not active after start')
                    restored.append(unit)
                except BaseException as exc:
                    errors.append(unit + ': ' + str(exc))
        result = dict(restored=restored, errors=errors, services_restored=not errors,
                      mqtt_freshness_verified=False,
                      systemd_service_result=os.getenv('SERVICE_RESULT', 'not-supplied'))
        h.atomic_json(session / 'recovery.json', result)
    print(json.dumps(result, sort_keys=True), flush=True)
    return int(bool(errors))


def supervisor_command(session: Path, seconds: int) -> list[str]:
    seconds_ok(seconds)
    script = session / 'probe.py'
    return ['systemd-run', '--unit=' + UNIT, '--wait', '--collect',
            '--property=Type=exec', '--property=RuntimeMaxSec=' + str(seconds + 120),
            '--property=TimeoutStopSec=180', '--property=KillMode=control-group',
            '--property=UMask=0077',
            f'--property=ExecStopPost={h.PYTHON} -u {script} --recover {session}',
            h.PYTHON, '-u', str(script), '--worker', str(session)]


def launch(seconds: int) -> int:
    seconds_ok(seconds)
    with locks():
        values, states = h.preflight()
        if h.unit_state(UNIT).get('ActiveState') not in ('inactive', 'failed'):
            raise Error('P300_UART1_TEST_ALREADY_RUNNING')
        for competing in ('optolink-p87-p300-check.service', 'optolink-handover-probe.service'):
            if h.unit_state(competing).get('ActiveState') not in ('inactive', 'failed'):
                raise Error('COMPETING_PROBE_ACTIVE_' + competing)
        if ROOT.is_symlink():
            raise Error('RESULT_ROOT_IS_SYMLINK')
        ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(ROOT, 0o700)
        # Refuse to hide a failed/unfinished previous recovery with a new trial.
        for old in ROOT.glob('run-*/state.json'):
            prior = json.loads(old.read_text())
            recovery = old.with_name('recovery.json')
            if prior.get('restore') and (not recovery.exists() or
                    not json.loads(recovery.read_text()).get('services_restored')):
                raise Error('PREVIOUS_RECOVERY_UNRESOLVED_' + old.parent.name)
        stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        session = ROOT / f'run-{stamp}-{os.getpid()}'
        session.mkdir(mode=0o700)
        for source, name in ((Path(__file__), 'probe.py'), (Path(__file__).with_name(HELPER), HELPER)):
            shutil.copyfile(source, session / name)
            (session / name).chmod(0o600)
        h.atomic_json(session / 'state.json', dict(version=VERSION, seconds=seconds,
                      services=states, restore=[], port=values['port_optolink'],
                      script_sha256=hashlib.sha256((session/'probe.py').read_bytes()).hexdigest(),
                      helper_sha256=HELPER_SHA256))
    print('SESSION=' + str(session), flush=True)
    result = subprocess.run(supervisor_command(session, seconds), check=False)
    mpath, rpath = session / 'measurement.json', session / 'recovery.json'
    m = json.loads(mpath.read_text()) if mpath.exists() else {}
    r = json.loads(rpath.read_text()) if rpath.exists() else {}
    ok = (result.returncode == 0 and m.get('observation_complete')
          and m.get('vs1_link_restored') and not m.get('errors') and r.get('services_restored'))
    print('SESSION=' + str(session), flush=True)
    print('RESULT=' + (m.get('comparison', {}).get('outcome', 'FAILED_OR_INCOMPLETE')
                      if ok else 'FAILED_OR_INCOMPLETE'), flush=True)
    print(json.dumps(m.get('comparison', {}), sort_keys=True), flush=True)
    print('LINK_AND_SERVICE_RESTORE=' + ('PASS' if m.get('vs1_link_restored') and r.get('services_restored') else 'NOT_VERIFIED'), flush=True)
    print('GFA_AFTER=' + json.dumps(m.get('recovery_gfa'), sort_keys=True), flush=True)
    for error in m.get('errors', []) + r.get('errors', []):
        print('ERROR=' + error, flush=True)
    print('Verify fresh original VS1 MQTT P80/P06. No UART1/GFA identity or P06 alias approval.', flush=True)
    return 0 if ok else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    modes = p.add_mutually_exclusive_group()
    modes.add_argument('--execute', action='store_true')
    modes.add_argument('--worker', type=Path, help=argparse.SUPPRESS)
    modes.add_argument('--recover', type=Path, help=argparse.SUPPRESS)
    p.add_argument('--seconds', type=int, default=None)
    args = p.parse_args()
    os.umask(0o077)
    if args.worker or args.recover:
        if args.seconds is not None or os.geteuid() != 0 or not os.getenv('INVOCATION_ID'):
            p.error('internal mode requires systemd; duration comes from session')
        return worker(args.worker) if args.worker else recover(args.recover)
    seconds = seconds_ok(60 if args.seconds is None else args.seconds)
    if args.execute:
        return launch(seconds)
    print(f'PLAN ONLY: {seconds}s P300-only FC01 55D3/11 and two FC03 Physical_READs: 1600/32, 1620/32; 2s spacing.')
    print('VS1 references only before/after; known external GFA readers paused; supervised restore.')
    print('No C9, RAM writes, parameters or heater triggers. UART1/GFA linkage and P06 remain UNVERIFIED.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (Error, OSError, ValueError, subprocess.SubprocessError) as exc:
        print('REFUSED_OR_FAILED=' + str(exc), file=sys.stderr)
        raise SystemExit(1)
