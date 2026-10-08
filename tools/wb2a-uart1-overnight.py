#!/usr/bin/env python3
"""Operator-stopped, read-only UART1 DMA0/RAM/55D3 overnight acquisition.

Only historical FC03 DMA0 SFR 0020/16, RAM 1600/32 and 1620/32,
and native FC01 55D3/11. Never reads UART1 U1RB (receive-data register),
changes UART configuration, writes RAM/parameters or forces the burner.
Uses single supervised P300 ownership and conservative original VS1 restore.
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
import re
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import tarfile
import io

VERSION = '2.0.0-uart1-dma0-overnight'
HELPER = 'wb2a-handover-probe.py'
HELPER_SHA256 = 'e419e0a32206a7398edadff2cb1f5f57ac1884df6532ee26c3b3e75e38cd1269'
ROOT = Path('/root/p300-trial-work/uart1-overnight-results')
BUNDLES = Path('/root/p300-trial-work/research-bundles')
UNIT = 'optolink-uart1-overnight.service'
STATUS = bytes.fromhex('4105000155d30b39')  # FC01 55D3/11, status only.
RAM0 = bytes.fromhex('410500031600203e')  # FC03 physical 1600/32 only.
RAM1 = bytes.fromhex('410500031620205e')  # FC03 physical 1620/32 only.
DMA0 = bytes.fromhex('4105000300201038')  # Historical read-only SFR DMA0 0020/16.
RAM_READS = ((RAM0, 0x1600), (RAM1, 0x1620))
# 64 bytes total around the previously observed UART1 DMA0 TX source at 0x161B.
INTERVAL = 2.0
RESEARCH_ONLY = True  # DMA0 is a UART1-TX path, NOT a verified GFA-RX/P06 path.
FLAME_MASK = 0x20
SAFE_FREE_BYTES = 128 * 1024 * 1024
MAX_LOG_BYTES = 384 * 1024 * 1024
PROGRESS_EVERY = 30
# NO measurement duration cap and NO natural-cycle auto-stop.



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


class UART1Wire(h.Wire):
    """Phase allowlists forbid even VS1 reads during the P300-only interval."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.phase = 'reference'
        self.last_gfa_rx = None
        self.phase_start = None
        self.phase_end = None
        self.trace_sink = None
        self._pending_rx = bytearray()
        self._pending_rx_at = None
        self.trace_records_written = 0

    def _emit_trace(self, item: dict) -> None:
        if self.trace_sink is None:
            return
        self.trace_sink.write(json.dumps(item, separators=(',', ':'), sort_keys=True) + '\n')
        self.trace_records_written += 1
        if self.trace_records_written % 200 == 0:
            self.trace_sink.flush()
        if self.trace_records_written % 4000 == 0:
            os.fsync(self.trace_sink.fileno())

    def flush_trace(self) -> None:
        if self._pending_rx:
            self._emit_trace({'t_monotonic': self._pending_rx_at,
                              'direction':'RX', 'hex':self._pending_rx.hex()})
            self._pending_rx.clear()
            self._pending_rx_at = None
        if self.trace_sink is not None:
            self.trace_sink.flush()

    def record(self, direction: str, data: bytes) -> None:
        # Keep just a tiny in-memory tail for the pinned handover helper.
        # All bytes are streamed to trace.jsonl, batching RX before each TX.
        now = self.clock()
        self.trace.append({'t_monotonic':now,'direction':direction,'hex':data.hex()})
        if len(self.trace) > 24:
            del self.trace[:-12]
        if direction == 'RX':
            if self._pending_rx_at is None:
                self._pending_rx_at = now
            self._pending_rx.extend(data)
            if len(self._pending_rx) >= 1024:
                self.flush_trace()
        else:
            self.flush_trace()
            self._emit_trace({'t_monotonic':now,'direction':direction,'hex':data.hex()})

    def send(self, data: bytes) -> None:
        vs1 = {b'\x04', b'\x01' + h.VS1_ID, h.VS1_ID, h.VS1_SOFTWARE, *h.GFA.values()}
        entering = {b'\x04', b'\x16\x00\x00', b'\x06', h.P300_ID, h.P300_SOFTWARE}
        allowed = {'reference': vs1, 'entry': entering,
                   'observation': {STATUS, RAM0, RAM1, DMA0, b'\x06'}, 'recovery': vs1}
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
                    (RAM1, 0x1620, 3, None, 32),
                    (DMA0, 0x0020, 3, None, 16))
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

    def observe(self, on_sample, isolation_check, resource_check) -> None:
        if self.phase != 'reference' or self.last_gfa_rx is None:
            raise Error('REFERENCE_REQUIRED')
        self.phase = 'entry'
        self.enter_p300()
        self.phase = 'observation'
        self.phase_start = self.clock()
        index = 0
        confirmed_flame, flame_streak, off_streak, completed = False, 0, 0, 0
        while True:
            if index % PROGRESS_EVERY == 0:
                isolation_check()
                resource_check()
            status=self.p300_read(STATUS,0x55D3,None)
            dma=self.p300_read(DMA0,0x0020,None)
            low=self.p300_read(RAM0,0x1600,None)
            high=self.p300_read(RAM1,0x1620,None)
            elapsed=self.clock()-self.phase_start
            source=int.from_bytes(dma[:3],'little') & 0xFFFFF
            target=int.from_bytes(dma[4:7],'little') & 0xFFFFF
            flame=bool(status[5] & FLAME_MASK)
            if flame:
                flame_streak+=1
                off_streak=0
                if flame_streak>=3:
                    confirmed_flame=True
            else:
                flame_streak=0
                if confirmed_flame:
                    off_streak+=1
                    if off_streak>=3:
                        completed+=1
                        confirmed_flame=False
                        off_streak=0
            row=dict(index=index+1,elapsed_s=elapsed,
                     utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                     native_b7=f'{status[7]:02x}', native_block=status.hex(),
                     flame_bit=flame,ram_1600=low.hex(),ram_1620=high.hex(),
                     dma0_0020=dma.hex(),dma0_source=f'0x{source:05x}',
                     dma0_target=f'0x{target:05x}',
                     dma0_tcr=int.from_bytes(dma[8:10],'little'),
                     dma0_control=dma[12],
                     complete_flame_cycles=completed,
                     since_last_external_gfa_s=self.clock()-self.last_gfa_rx,
                     uart1_gfa_link_verified=False,p06_rpm_alias_verified=False)
            on_sample(row)
            index+=1
            self.sleep(INTERVAL)

    def restore_link(self) -> dict:
        self.phase = 'recovery'
        self.enter_vs1(2)
        self.vs1(h.VS1_SOFTWARE, 2, h.SOFTWARE)
        return self.gfa_block()


def summarize(rows: list[dict]) -> dict:
    """Separate UART1 DMA0 TX transfer evidence from unverified GFA RX."""
    changes = {f'0x{x:04x}': 0 for x in range(0x1600,0x1640)}
    status_changes, dma_changes, flame_windows = [], [], []
    prev_ram = prev_status = prev_dma = None
    flame_first = None
    streak = 0
    for row in rows:
        block = bytes.fromhex(row['ram_1600']+row['ram_1620'])
        dma = bytes.fromhex(row['dma0_0020'])
        status = bytes.fromhex(row['native_block'])
        if len(block) != 64 or len(dma) != 16 or len(status) != 11:
            raise Error('SAMPLE_LENGTH_INVALID')
        if row['flame_bit'] != bool(status[5] & FLAME_MASK):
            raise Error('INCONSISTENT_FLAME_BIT')
        if (row['dma0_source'] != f"0x{int.from_bytes(dma[:3], 'little') & 0xfffff:05x}"
                or row['dma0_target'] != f"0x{int.from_bytes(dma[4:7], 'little') & 0xfffff:05x}"
                or row['dma0_tcr'] != int.from_bytes(dma[8:10], 'little')
                or row['dma0_control'] != dma[12]):
            raise Error('INCONSISTENT_DMA0_FIELDS')
        if prev_ram is not None:
            for j, (x,y) in enumerate(zip(prev_ram,block)):
                if x != y:
                    changes[f'0x{0x1600+j:04x}'] += 1
            if prev_status != row['native_b7']:
                status_changes.append({'at_s':row['elapsed_s'],
                                       'before':prev_status,'after':row['native_b7']})
            if prev_dma != row['dma0_source']:
                dma_changes.append({'at_s':row['elapsed_s'],
                                    'before':prev_dma,'after':row['dma0_source']})
        if row['flame_bit']:
            if flame_first is None:
                flame_first=row['elapsed_s']
            streak += 1
        elif flame_first is not None:
            flame_windows.append({'first_flame_sample_s':flame_first,
                                  'first_off_sample_s':row['elapsed_s'],
                                  'flame_samples':streak})
            flame_first = None
            streak = 0
        prev_ram,prev_status,prev_dma=block,row['native_b7'],row['dma0_source']
    changed={addr:n for addr,n in changes.items() if n}
    natural=any(w['flame_samples']>=3 for w in flame_windows)
    return {
        'outcome':('NATURAL_FLAME_CYCLE_RECORDED_TX_PATH_ONLY' if natural else
                   'INCONCLUSIVE_FLAME_STILL_ON' if flame_first is not None else
                   'INCONCLUSIVE_NO_COMPLETE_NATURAL_FLAME_CYCLE'),
        'sample_count':len(rows),
        'flame_windows':flame_windows,
        'native_p87_changes':status_changes,
        'dma0_source_transitions':dma_changes,
        'dma0_source_states':sorted({r['dma0_source'] for r in rows}),
        'dma0_destination_states':sorted({r['dma0_target'] for r in rows}),
        'dma0_uart1_expected_destination':'0x003aa',
        'dma0_source_within_previous_0x161b_1622':
            all(0x161b <= int(r['dma0_source'],16) <= 0x1622 for r in rows),
        'ram_changed_byte_count':len(changed),
        'ram_changed_address_counts':changed,
        'ram_source_byte_0x161b_changes':changes['0x161b'],
        'p300_reads_fixed':['FC01/55D3/11', 'FC03/0020/16',
                            'FC03/1600/32', 'FC03/1620/32'],
        'possible_non_atomic_sampling':True,
        'external_gfa_reads_during_p300':False,
        'uart1_rx_data_register_read':False,
        'uart1_connected_to_gfa_proven':False,
        'p06_rpm_alias_verified':False,
        'production_approved':False,
        'ram_write_approved':False}

@contextlib.contextmanager
def locks():
    # Share all known diagnostic locks, including the still-running MQTT observer.
    with h.locks(), contextlib.ExitStack() as stack:
        for name in ('optolink-p87-mirror.lock', 'optolink-p87-p300-check.lock', 'optolink-uart1-p300-focus.lock', 'optolink-uart1-dma0-cycle.lock'):
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
                  transport='P300 FC01 55D3/11 and FC03 SFR_DMA0 0020/16 and RAM 1600/32,1620/32; no external GFA')
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
                    print('PHASE=P300_ONLY; first status, DMA0 SFR and both bounded RAM frames validated', flush=True)
                out.write(json.dumps(row, sort_keys=True) + '\n')
                out.flush()
                if previous != (row['native_b7'], row['flame_bit']) or row['index'] % 20 == 0:
                    print(json.dumps({k:row[k] for k in (
                        'index', 'elapsed_s', 'native_b7', 'flame_bit', 'dma0_source',
                        'since_last_external_gfa_s')}, sort_keys=True), flush=True)
                previous = (row['native_b7'], row['flame_bit'])
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



def post_restore_health() -> dict:
    """Read-only P80/P06 checks after restored production service only."""
    result = {'production_main_verified':False,'gfa_reads':{},
              'ha_entity_freshness_verified':False}
    try:
        live=h.unit_state(h.MAIN)
        result['production_main_verified']=(
            live.get('ActiveState')=='active' and
            live.get('SubState')=='running' and
            live.get('WorkingDirectory')=='/opt/optolink')
        if not result['production_main_verified']:
            return result
        for name,request in (('P80','gfaread;0x4050;1;raw;False'),
                             ('P06','gfaread;0x4006;1;raw;False')):
            proc=subprocess.run(['optolink-debug','request',request,'--timeout','8'],
                    capture_output=True,text=True,timeout=14,check=False)
            expected=(r'1;0x4050;20\b' if name=='P80'
                      else r'1;0x4006;[0-9a-fA-F]{2}\b')
            verified=(proc.returncode==0 and
                      bool(re.search(expected,proc.stdout,re.IGNORECASE)))
            result['gfa_reads'][name]={'returncode':proc.returncode,
                    'stdout':proc.stdout[-600:], 'stderr':proc.stderr[-300:],
                    'format_and_identity_verified':verified}
    except (OSError,subprocess.TimeoutExpired) as exc:
        result['health_error']=str(exc)
    return result


def upload_bundle(session: Path, health: dict) -> Path:
    """Package ONE private artifact even for an incomplete hardware run.

    Only files from this one validated fresh experiment are included.
    Never touches production settings and refuses symlinks/overwrites.
    """
    if ROOT.is_symlink() or session.parent!=ROOT or session.is_symlink():
        raise Error('INVALID_BUNDLE_SESSION')
    if BUNDLES.is_symlink():
        raise Error('BUNDLE_ROOT_SYMLINK')
    BUNDLES.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(BUNDLES,0o700)
    archive=BUNDLES/('uart1-dma0-'+session.name+'-bundle.tar.gz')
    if archive.exists() or archive.is_symlink():
        raise Error('REFUSE_OVERWRITE_EXISTING_BUNDLE')
    paths=('state.json','samples.jsonl','measurement.json','recovery.json')
    included={}
    for name in paths:
        path=session/name
        if path.is_symlink():
            raise Error('SESSION_FILE_SYMLINK')
        if path.is_file():
            raw=path.read_bytes()
            if len(raw)>20_000_000:
                raise Error('SESSION_FILE_TOO_BIG')
            included[name]=raw
    manifest={'schema_version':1,'session':session.name,
              'source_sha256':{name:hashlib.sha256(raw).hexdigest()
                               for name,raw in included.items()},
              'operational_health':health,
              'source_capture':'P300 DMA0-SFR + 64 RAM + native status; no UART1 U1RB',
              'uart1_rx_or_gfa_identity_verified':False,
              'p06_rpm_alias_verified':False,
              'production_approved':False,
              'ram_write_approved':False}
    included['bundle-manifest.json']=(json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode()
    with tarfile.open(archive,'x:gz') as tar:
        for name,raw in included.items():
            member=tarfile.TarInfo('uart1-dma0/'+name)
            member.mode=0o600
            member.mtime=0
            member.size=len(raw)
            tar.addfile(member,io.BytesIO(raw))
    os.chmod(archive,0o600)
    return archive


def launch(seconds: int) -> int:
    seconds_ok(seconds)
    with locks():
        values, states = h.preflight()
        if h.unit_state(UNIT).get('ActiveState') not in ('inactive', 'failed'):
            raise Error('P300_UART1_DMA0_CYCLE_ALREADY_RUNNING')
        for competing in ('optolink-p87-p300-check.service', 'optolink-handover-probe.service',
                          'optolink-uart1-p300-focus.service'):
            if h.unit_state(competing).get('ActiveState') not in ('inactive', 'failed'):
                raise Error('COMPETING_PROBE_ACTIVE_' + competing)
        if ROOT.is_symlink():
            raise Error('RESULT_ROOT_IS_SYMLINK')
        ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(ROOT, 0o700)
        # One complete capture is enough: refuse repeated hardware outage.
        for previous in ROOT.glob('run-*/measurement.json'):
            if previous.is_file() and not previous.is_symlink():
                old_report=json.loads(previous.read_text())
                if old_report.get('observation_complete') and old_report.get('vs1_link_restored'):
                    raise Error('DMA0_CYCLE_PROFILE_ALREADY_COMPLETED')
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
    health=post_restore_health()
    print('POST_RESTORE_PRODUCTION=' + ('PASS' if health['production_main_verified'] else 'NOT_VERIFIED'), flush=True)
    for name,item in health['gfa_reads'].items():
        print('POST_RESTORE_'+name+'='+json.dumps(item,sort_keys=True),flush=True)
    artifact=upload_bundle(session,health)
    print('UPLOAD_ONE_FILE='+str(artifact),flush=True)
    print('UART1_GFA_RX_AND_P06_RPM=NOT_VERIFIED',flush=True)
    health_ok=(health['production_main_verified'] and
               all(health['gfa_reads'].get(k,{}).get('format_and_identity_verified')
                   for k in ('P80','P06')))
    return 0 if ok and health_ok else 1


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
    seconds = seconds_ok(600 if args.seconds is None else args.seconds)
    if args.execute:
        return launch(seconds)
    print(f'PLAN ONLY: max {seconds}s, auto-stop after natural flame+off+15s; FC01 55D3/11, FC03 0020/16, 1600/32, 1620/32.')
    print('VS1 references only before/after; known external GFA readers paused; supervised restore.')
    print('No U1RB/03AE read, no C9 or writes, no forced burner. UART1/GFA and P06 remain UNVERIFIED.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (Error, OSError, ValueError, subprocess.SubprocessError) as exc:
        print('REFUSED_OR_FAILED=' + str(exc), file=sys.stderr)
        raise SystemExit(1)
