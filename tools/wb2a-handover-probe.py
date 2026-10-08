#!/usr/bin/env python3
"""Fixed, read-only WB2A handover measurement; default is an inert plan.

No C9, RAM, parameter writes, unreviewed opcodes or protocol shortcuts.
--execute launches a short supervised systemd worker; ExecStopPost restores
only services recorded BEFORE stopping them. Production files are never edited.
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import termios
import time

VERSION = '1.0.0'
ROOT = Path('/root/p300-trial-work/handover-results')
SETTINGS = Path('/opt/optolink/settings_ini.py')
PYTHON = '/opt/optolink/venv/bin/python'
UNIT = 'optolink-handover-probe.service'
MAIN = 'optolink-splitter.service'
# Stop timers first and the serial owner last. Restore in reverse order.
SERVICES = (
    'optolink-clock-sync.timer', 'optolink-clock-sync.service',
    'optolink-service-programs.service', 'optolink-maintenance-api.service',
    'optolink-schedule-manager.service', 'optolink-party-emulator.service', MAIN,
)
LOCKS = ('/run/lock/optolink-handover-probe.lock',
         '/run/lock/optolink-p300-trial.lock')
IDENT = b'\x20\xc2'
SOFTWARE = b'\x01\x03'
VS1_ID = bytes.fromhex('f700f802')
VS1_SOFTWARE = bytes.fromhex('f7778c02')
GFA = {'P80': bytes.fromhex('6b405001'), 'P06': bytes.fromhex('6b400601'),
       'P09': bytes.fromhex('6b400901'), 'P87': bytes.fromhex('6b405701')}
P300_ID = bytes.fromhex('4105000100f80200')
P300_SOFTWARE = bytes.fromhex('41050001778c020b')
TX_ALLOWLIST = frozenset((b'\x04', b'\x16\x00\x00', b'\x06',
                         b'\x01' + VS1_ID, VS1_ID, VS1_SOFTWARE,
                         P300_ID, P300_SOFTWARE, *GFA.values()))


class ProbeError(RuntimeError):
    pass


def atomic_json(path: Path, value: dict) -> None:
    tmp = path.with_name(path.name + '.tmp')
    with tmp.open('w', encoding='utf-8') as out:
        os.chmod(tmp, 0o600)
        json.dump(value, out, indent=2, sort_keys=True)
        out.write('\n')
        out.flush()
        os.fsync(out.fileno())
    tmp.replace(path)


def read_settings(text: str) -> dict:
    """Never import settings; refuse conditional/dynamic assignments to key fields."""
    keys = {'port_optolink', 'port_vitoconnect', 'vs1protocol'}
    tree = ast.parse(text)
    top = {id(n) for n in tree.body}
    values = {}
    for n in ast.walk(tree):
        if isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            names = {x.id for t in targets for x in ast.walk(t) if isinstance(x, ast.Name)} & keys
            if names:
                if id(n) not in top or not isinstance(n, ast.Assign):
                    raise ProbeError('ambiguous production settings')
                try:
                    value = ast.literal_eval(n.value)
                except (ValueError, TypeError) as exc:
                    raise ProbeError('non-literal production settings') from exc
                for name in names:
                    values[name] = value
    if values.get('vs1protocol') is not True or values.get('port_vitoconnect', 'missing') is not None:
        raise ProbeError('requires the reviewed single-port VS1 production setup')
    port = values.get('port_optolink')
    if not isinstance(port, str) or not port.startswith('/dev/') or '\x00' in port:
        raise ProbeError('configured serial device missing or invalid')
    return values


class Wire:
    """Injected I/O and clock: no port creation, service control or generic requests."""
    def __init__(self, port, clock=time.monotonic, sleep=time.sleep):
        self.port, self.clock, self.sleep = port, clock, sleep
        self.trace = []
        self.samples = []
        self.last_io = self.clock()

    def record(self, direction: str, data: bytes) -> None:
        self.trace.append({'t_monotonic': self.clock(), 'direction': direction, 'hex': data.hex()})

    def send(self, data: bytes) -> None:
        if data not in TX_ALLOWLIST:
            raise ProbeError('TX outside fixed read-only allowlist')
        self.record('TX', data)
        if self.port.write(data) != len(data):
            raise ProbeError('short serial write')

    def exact(self, count: int, deadline: float) -> bytes:
        out = bytearray()
        while len(out) < count:
            if self.clock() >= deadline:
                raise ProbeError('receive deadline exceeded')
            part = self.port.read(count - len(out))
            if part:
                self.record('RX', part)
                out.extend(part)
            else:
                self.sleep(0.001)
        return bytes(out)

    def control(self, wanted: int) -> None:
        deadline = self.clock() + 6.0
        for _ in range(32):
            value = self.exact(1, deadline)[0]
            if value == wanted:
                return
            # Only stale protocol controls during detection are tolerated.
            if wanted == 5 and value in (6, 0x15):
                continue
            raise ProbeError(f'unexpected control {value:02x}, expected {wanted:02x}')
        raise ProbeError('too many control bytes')

    def gap(self) -> None:
        self.sleep(max(0.0, self.last_io + .025 - self.clock()))

    def quiet(self) -> None:
        """Detect trailing data; short fixed guard remains inside read timings."""
        until = self.clock() + .010
        while self.clock() < until:
            tail = self.port.read(1)
            if tail:
                self.record('RX_UNEXPECTED', tail)
                raise ProbeError('unexpected trailing response bytes')
            self.sleep(.001)
        self.last_io = self.clock()

    def discard_before_sync(self) -> None:
        # Only before a new, explicit EOT. Never purge a partial data response.
        data = self.port.read(256)
        if data:
            self.record('DISCARD_BEFORE_EOT', data)
        self.port.reset_input_buffer()

    def vs1(self, request: bytes, count: int, expected: bytes | None = None) -> bytes:
        if request not in (VS1_ID, VS1_SOFTWARE, b'\x01' + VS1_ID, *GFA.values()):
            raise ProbeError('not an allowed VS1 read')
        self.gap()
        self.send(request)
        data = self.exact(count, self.clock() + 2.0)
        self.quiet()
        if expected is not None and data != expected:
            raise ProbeError(f'VS1 identity mismatch: {data.hex()}')
        return data

    def enter_vs1(self) -> dict:
        self.discard_before_sync()
        t0 = self.clock()
        self.send(b'\x04')
        self.control(5)
        t1 = self.clock()
        self.control(5)  # Deliberately retain the proven conservative baseline.
        t2 = self.clock()
        self.vs1(b'\x01' + VS1_ID, 2, IDENT)
        t3 = self.clock()
        return {'first_enq_ms': (t1-t0)*1000, 'additional_enq_ms': (t2-t1)*1000,
                'identity_ms': (t3-t2)*1000, 'total_ms': (t3-t0)*1000}

    def p300_read(self, request: bytes, address: int, expected: bytes) -> bytes:
        if (request, address, expected) not in ((P300_ID, 0xF8, IDENT),
                                               (P300_SOFTWARE, 0x778C, SOFTWARE)):
            raise ProbeError('not an allowed P300 read')
        self.gap()
        self.send(request)
        end = self.clock() + 3.0
        if self.exact(1, end) != b'\x06':
            raise ProbeError('P300 request not acknowledged')
        for _ in range(8):
            first = self.exact(1, end)
            if first != b'\x06':
                break
        if first != b'\x41':
            raise ProbeError('P300 STX missing')
        size = self.exact(1, end)[0]
        if not 5 <= size <= 16:
            raise ProbeError('P300 response length invalid')
        body = self.exact(size + 1, end)
        if (size + sum(body[:-1])) & 255 != body[-1]:
            raise ProbeError('P300 response checksum invalid')
        self.send(b'\x06')
        msg, fc, hi, lo, length = body[:5]
        if fc != 1 or (hi << 8 | lo) != address:
            raise ProbeError('P300 response function/address mismatch')
        if msg == 3:
            raise ProbeError('P300 controller error: ' + body[5:-1].hex())
        if msg != 1 or length != 2 or body[5:-1] != expected:
            raise ProbeError('P300 identity/message/length mismatch')
        self.quiet()
        return body[5:-1]

    def enter_p300(self) -> dict:
        self.discard_before_sync()
        t0 = self.clock()
        self.send(b'\x04')
        self.control(5)
        t1 = self.clock()
        self.send(b'\x16\x00\x00')
        self.control(6)
        t2 = self.clock()
        self.p300_read(P300_ID, 0xF8, IDENT)
        t3 = self.clock()
        self.p300_read(P300_SOFTWARE, 0x778C, SOFTWARE)
        t4 = self.clock()
        return {'enq_ms': (t1-t0)*1000, 'start_ack_ms': (t2-t1)*1000,
                'device_id_ms': (t3-t2)*1000, 'software_ms': (t4-t3)*1000,
                'total_ms': (t4-t0)*1000}

    def gfa_block(self) -> dict:
        result = {}
        for name, req in GFA.items():
            data = self.vs1(req, 1)
            if data == b'\xff':
                self.sleep(.150)
                data = self.vs1(req, 1)
            if data == b'\xff' or (name == 'P80' and data != b'\x20'):
                raise ProbeError(f'{name} invalid or FF after retry')
            result[name] = data.hex()
        return result

    def experiment(self) -> list[dict]:
        self.enter_vs1()
        self.vs1(VS1_SOFTWARE, 2, SOFTWARE)
        self.gfa_block()
        samples = self.samples
        for index in range(3):
            # A real valid VS1 transaction immediately before each measured switch.
            self.vs1(VS1_ID, 2, IDENT)
            start = self.clock()
            p300 = self.enter_p300()
            vs1 = self.enter_vs1()
            ident_end = self.clock()
            gfa = self.gfa_block()
            end = self.clock()
            samples.append({'index': index + 1, 'p300': p300, 'vs1': vs1, 'gfa': gfa,
                            'roundtrip_to_vs1_id_ms': (ident_end-start)*1000,
                            'gfa_block_ms': (end-ident_end)*1000,
                            'roundtrip_with_gfa_ms': (end-start)*1000})
        return samples


def command(args: list[str], timeout=15) -> str:
    proc = subprocess.run(args, check=False, capture_output=True, text=True, timeout=timeout)
    if proc.returncode:
        raise ProbeError('command failed: ' + ' '.join(args[:3]) + ': ' + proc.stderr.strip()[:200])
    return proc.stdout


def unit_state(unit: str) -> dict:
    args = ['systemctl', 'show', unit, '-p', 'LoadState', '-p', 'ActiveState',
            '-p', 'SubState', '-p', 'WorkingDirectory', '-p', 'InvocationID']
    proc = subprocess.run(args, capture_output=True, text=True, timeout=15)
    result = dict(line.split('=', 1) for line in proc.stdout.splitlines() if '=' in line)
    if proc.returncode and result.get('LoadState') != 'not-found':
        raise ProbeError('cannot inspect service: ' + unit)
    return result


def assert_no_owner(port: str) -> None:
    dev = os.stat(port)
    if not stat.S_ISCHR(dev.st_mode):
        raise ProbeError('serial path is not a character device')
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            for fd in (proc / 'fd').iterdir():
                try:
                    info = fd.stat()
                except FileNotFoundError:
                    continue
                if stat.S_ISCHR(info.st_mode) and info.st_rdev == dev.st_rdev:
                    raise ProbeError('serial port still owned by PID ' + proc.name)
        except FileNotFoundError:
            continue
        except PermissionError as exc:
            raise ProbeError('cannot inspect serial owners in visible process namespace') from exc


def open_serial(port: str):
    import serial  # Lazy import; plan and offline wire tests never import pyserial.
    assert_no_owner(port)
    s = serial.Serial(port, baudrate=4800, bytesize=8, parity='E', stopbits=2,
                      timeout=0, write_timeout=1, exclusive=True,
                      xonxoff=False, rtscts=False, dsrdtr=False)
    try:
        fcntl.ioctl(s.fileno(), termios.TIOCEXCL)
        assert_no_owner(port)
        return s
    except BaseException:
        s.close()
        raise


@contextlib.contextmanager
def locks():
    with contextlib.ExitStack() as stack:
        for path in LOCKS:
            fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            stack.callback(os.close, fd)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def validate_session(session: Path) -> dict:
    if session.parent != ROOT or session.is_symlink() or not session.name.startswith('run-'):
        raise ProbeError('invalid session path')
    info = session.stat()
    if info.st_uid != 0 or info.st_mode & 0o077:
        raise ProbeError('session must be private and root-owned')
    state = json.loads((session / 'state.json').read_text())
    if set(state['services']) != set(SERVICES):
        raise ProbeError('unexpected service manifest')
    return state


def pause_services(session: Path, state: dict, action=command, inspect=unit_state) -> None:
    for unit in SERVICES:
        if not state['services'][unit]:
            continue
        # Persist intent before stop: an accepted job may outlive a timeout.
        state['restore'].append(unit)
        atomic_json(session / 'state.json', state)
        action(['systemctl', 'stop', unit])
        if inspect(unit).get('ActiveState') != 'inactive':
            raise ProbeError('service did not become inactive: ' + unit)


def worker(session: Path) -> int:
    state = validate_session(session)
    report = {'version': VERSION, 'variant': 'two-enq-baseline', 'samples': [],
              'experiment_pass': False, 'vs1_link_restored': False, 'errors': []}
    wire = None
    s = None
    def interrupted(signum, frame):
        raise ProbeError('interrupted by signal ' + str(signum))
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, interrupted)
    with locks():
        try:
            live = read_settings(SETTINGS.read_text())
            if live['port_optolink'] != state['port']:
                raise ProbeError('serial settings changed since preparation')
            if unit_state(MAIN).get('WorkingDirectory') != '/opt/optolink':
                raise ProbeError('production runtime changed since preparation')
            for unit, was_active in state['services'].items():
                current = unit_state(unit).get('ActiveState')
                if current not in ('active', 'inactive', 'failed') or (current == 'active') != was_active:
                    raise ProbeError('service state changed since preparation: ' + unit)
            pause_services(session, state)
            s = open_serial(state['port'])
            wire = Wire(s)
            report['samples'] = wire.experiment()
            report['experiment_pass'] = True
        except BaseException as exc:
            report['errors'].append(str(exc) or type(exc).__name__)
        finally:
            # A second signal must not interrupt the bounded recovery attempt.
            for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
                signal.signal(sig, signal.SIG_IGN)
            if wire is not None:
                try:
                    wire.enter_vs1()
                    wire.vs1(VS1_SOFTWARE, 2, SOFTWARE)
                    wire.vs1(GFA['P80'], 1, b'\x20')
                    report['vs1_link_restored'] = True
                except BaseException as exc:
                    report['errors'].append('VS1 link recovery: ' + str(exc))
                report['trace'] = wire.trace
                report['samples'] = wire.samples
            if s is not None:
                try:
                    s.close()
                except BaseException as exc:
                    report['errors'].append('serial close: ' + str(exc))
            atomic_json(session / 'measurement.json', report)
    return 0 if report['experiment_pass'] and report['vs1_link_restored'] and not report['errors'] else 1


def wait_main_ready() -> None:
    """Readiness from this invocation, not merely an active restart loop."""
    initial = unit_state(MAIN)
    invocation = initial.get('InvocationID')
    if not invocation or initial.get('WorkingDirectory') != '/opt/optolink':
        raise ProbeError('original splitter invocation unavailable')
    until = time.monotonic() + 15
    while time.monotonic() < until:
        now = unit_state(MAIN)
        if now.get('ActiveState') != 'active' or now.get('InvocationID') != invocation:
            raise ProbeError('original splitter restarted/stopped during recovery')
        journal = command(['journalctl', '-q', '_SYSTEMD_INVOCATION_ID=' + invocation,
                           '-n', '150', '-o', 'cat', '--no-pager'], timeout=5)
        if 'enter main loop' in journal and 're-start #' not in journal:
            return
        if 'init_protocol' in journal and 'failed' in journal:
            raise ProbeError('original splitter protocol init failed')
        time.sleep(.25)
    raise ProbeError('no original splitter main-loop readiness in 15 seconds')


def recover(session: Path, action=command, inspect=unit_state, ready=wait_main_ready) -> int:
    """Systemd ExecStopPost: runs after the worker is dead, including SIGKILL."""
    state = validate_session(session)
    restored, errors = [], []
    for unit in reversed(state['restore']):
        if unit not in SERVICES or not state['services'][unit]:
            raise ProbeError('unexpected restore intent')
        try:
            action(['systemctl', 'start', unit])
            now = inspect(unit)
            if unit != 'optolink-clock-sync.service' and now.get('ActiveState') != 'active':
                raise ProbeError('service is not active after start')
            if unit == MAIN:
                ready()
            restored.append(unit)
        except BaseException as exc:
            errors.append(unit + ': ' + str(exc))
            if unit == MAIN:
                errors.append('writer services deferred until original splitter is healthy')
                break
    # Keep recovery intentions on disk even on failure; never silently discard.
    result = {'restored': restored, 'errors': errors, 'services_restored': not errors,
              'mqtt_freshness_verified': False,
              'systemd_service_result': os.getenv('SERVICE_RESULT', 'not-supplied')}
    atomic_json(session / 'recovery.json', result)
    print(json.dumps(result, sort_keys=True), flush=True)
    return int(bool(errors))


def preflight() -> tuple[dict, dict]:
    if os.geteuid() != 0:
        raise ProbeError('execute requires root in the Optolink LXC')
    if Path('/run/optolink-p300-trial').exists() or Path(
            '/run/systemd/system/optolink-splitter.service.d/95-p300-canary.conf').exists():
        raise ProbeError('restore the old P300 canary first')
    if not Path(PYTHON).is_file():
        raise ProbeError('production virtualenv missing')
    values = read_settings(SETTINGS.read_text())
    main = unit_state(MAIN)
    if main.get('ActiveState') != 'active' or main.get('SubState') != 'running' or main.get('WorkingDirectory') != '/opt/optolink':
        raise ProbeError('original VS1 production service must be running')
    if unit_state(UNIT).get('ActiveState') not in ('inactive', 'failed'):
        raise ProbeError('another supervised handover probe is present')
    states = {}
    for unit in SERVICES:
        s = unit_state(unit)
        if s.get('ActiveState') not in ('active', 'inactive', 'failed'):
            raise ProbeError('service transition in progress: ' + unit)
        states[unit] = s.get('ActiveState') == 'active'
    return values, states


def supervisor_command(session: Path) -> list[str]:
    script = session / 'probe.py'
    return ['systemd-run', '--unit=' + UNIT, '--wait', '--collect',
            '--property=Type=exec', '--property=RuntimeMaxSec=90',
            '--property=TimeoutStopSec=90', '--property=KillMode=control-group',
            '--property=UMask=0077',
            f'--property=ExecStopPost={PYTHON} -u {script} --recover {session}',
            PYTHON, '-u', str(script), '--worker', str(session)]


def launch() -> int:
    values, states = preflight()
    with locks():
        ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(ROOT, 0o700)
        stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        session = ROOT / f'run-{stamp}-{os.getpid()}'
        session.mkdir(mode=0o700)
        script = session / 'probe.py'
        shutil.copyfile(Path(__file__), script)
        script.chmod(0o600)
        atomic_json(session / 'state.json', {'version': VERSION, 'services': states,
                    'restore': [], 'port': values['port_optolink'],
                    'script_sha256': hashlib.sha256(script.read_bytes()).hexdigest()})
    # Neither the launcher nor its SSH session owns the serial descriptor.
    # ExecStopPost is registered BEFORE any production unit is stopped.
    args = supervisor_command(session)
    print('SESSION=' + str(session), flush=True)
    result = subprocess.run(args, check=False)
    print('SESSION=' + str(session), flush=True)
    m = json.loads((session / 'measurement.json').read_text()) if (session / 'measurement.json').exists() else {}
    r = json.loads((session / 'recovery.json').read_text()) if (session / 'recovery.json').exists() else {}
    ok = result.returncode == 0 and m.get('experiment_pass') and m.get('vs1_link_restored') and r.get('services_restored')
    print('RESULT=' + ('PASS_READ_ONLY_BASELINE' if ok else 'FAIL_OR_NOT_VERIFIED'))
    for sample in m.get('samples', []):
        print(json.dumps(sample, sort_keys=True))
    for error in m.get('errors', []) + r.get('errors', []):
        print('ERROR=' + error)
    print('Verify fresh VS1 MQTT P80/P06 separately. Do not repeat a failed probe unchanged.')
    return 0 if ok else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    modes = p.add_mutually_exclusive_group()
    modes.add_argument('--execute', action='store_true')
    modes.add_argument('--worker', type=Path, help=argparse.SUPPRESS)
    modes.add_argument('--recover', type=Path, help=argparse.SUPPRESS)
    args = p.parse_args()
    os.umask(0o077)
    if args.worker or args.recover:
        if os.geteuid() != 0 or os.getenv('INVOCATION_ID') is None:
            raise ProbeError('internal modes require a supervised systemd invocation')
        return worker(args.worker) if args.worker else recover(args.recover)
    if args.execute:
        return launch()
    print('PLAN ONLY: 3 warm VS1 -> P300 -> two-ENQ VS1 rounds; fixed identity/GFA reads.')
    print('No C9, RAM, writes, service operations or serial access without --execute.')
    print('Temporary telemetry pause; supervised recovery, no persistent unit/settings changes.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ProbeError, OSError, subprocess.SubprocessError, ValueError) as exc:
        print('REFUSED_OR_FAILED: ' + str(exc), file=sys.stderr)
        raise SystemExit(1)
