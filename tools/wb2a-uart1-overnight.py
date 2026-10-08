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


def resource_guard(session: Path, trace_stream, sample_stream) -> None:
    """No clock limit. Stop safely if local storage would be exhausted."""
    fs=shutil.disk_usage(session)
    if fs.free < SAFE_FREE_BYTES:
        raise Error('LOW_DISK_SPACE_FAILSAFE_VS1_RESTORE')
    for writer in (trace_stream,sample_stream):
        if writer is not None and writer.tell() >= MAX_LOG_BYTES:
            raise Error('LOG_SIZE_FAILSAFE_VS1_RESTORE')


def summarize_file(path: Path) -> dict:
    """Bounded memory summary; complete sample JSONL is the evidence."""
    from collections import Counter
    counts=Counter()
    statuses=Counter()
    dma_sources=Counter()
    destinations=Counter()
    flame_samples=0
    complete=0
    n=0
    prev=None
    first_utc=last_utc=None
    def lines():
        with path.open(encoding='utf-8') as source:
            yield from source
    for text_line in lines():
        if not text_line.strip():
            continue
        row=json.loads(text_line)
        n+=1
        if row.get('index')!=n:
            raise Error('SAMPLE_INDEX_INTEGRITY_FAILED')
        ram=bytes.fromhex(row['ram_1600']+row['ram_1620'])
        status=bytes.fromhex(row['native_block'])
        dma=bytes.fromhex(row['dma0_0020'])
        if len(ram)!=64 or len(status)!=11 or len(dma)!=16:
            raise Error('SAMPLE_LENGTH_INTEGRITY_FAILED')
        if row['flame_bit'] != bool(status[5] & FLAME_MASK):
            raise Error('SAMPLE_FLAME_INTEGRITY_FAILED')
        if row['dma0_source'] != f"0x{int.from_bytes(dma[:3], 'little')&0xfffff:05x}":
            raise Error('SAMPLE_DMA_POINTER_INTEGRITY_FAILED')
        if row['dma0_target'] != f"0x{int.from_bytes(dma[4:7], 'little')&0xfffff:05x}":
            raise Error('SAMPLE_DMA_TARGET_INTEGRITY_FAILED')
        if prev is not None:
            for j,(x,y) in enumerate(zip(prev,ram)):
                if x!=y:
                    counts[f'0x{0x1600+j:04x}']+=1
        prev=ram
        first_utc=first_utc or row['utc']
        last_utc=row['utc']
        flame_samples+=int(row['flame_bit'])
        complete=max(complete,row['complete_flame_cycles'])
        statuses[row['native_b7']]+=1
        dma_sources[row['dma0_source']]+=1
        destinations[row['dma0_target']]+=1
    return {
        'sample_count':n,
        'first_utc':first_utc,'last_utc':last_utc,
        'flame_bit_samples':flame_samples,
        'completed_natural_flame_cycles':complete,
        'status_byte7_counts':dict(statuses),
        'dma0_source_counts':dict(dma_sources),
        'dma0_destination_counts':dict(destinations),
        'changed_ram_addresses':dict(sorted(counts.items())),
        'changed_ram_byte_count':len(counts),
        'source_pointer_0x161b_byte_changes':counts['0x161b'],
        'outcome':'OPERATOR_STOPPED_READ_ONLY; GFA_RX_AND_P06_RPM_NOT_VERIFIED',
        'no_time_limit':True,
        'uart1_rx_read_performed':False,
        'p06_rpm_alias_verified':False,
        'production_approved':False,
        'ram_write_approved':False}


def run_worker(session: Path, state: dict) -> int:
    """Long-lived detached worker; samples and trace written incrementally."""
    report=dict(version=VERSION,errors=[],reference_gfa=None,recovery_gfa=None,
                observation_complete=False,operator_stop=False,
                vs1_link_restored=False,
                transport='P300 status + DMA0 SFR + 64B TX RAM only; no writes or GFA reads under P300',
                trace_file='trace.jsonl',samples_file='samples.jsonl',
                telemetry_disabled_for_observation=True)
    serial=wire=trace_stream=sample_stream=None
    current=None
    count=0
    def stop(signum, frame):
        raise Error('OPERATOR_STOP_SIGNAL_'+str(signum))
    for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):
        signal.signal(sig,stop)
    try:
        current=h.read_settings(h.SETTINGS.read_text())
        if current['port_optolink']!=state['port']:
            raise Error('PRODUCTION_SETTINGS_CHANGED')
        if h.unit_state(h.MAIN).get('WorkingDirectory')!='/opt/optolink':
            raise Error('PRODUCTION_PATH_CHANGED')
        for unit,was_active in state['services'].items():
            now=h.unit_state(unit).get('ActiveState')
            if now not in ('active','inactive','failed') or (now=='active')!=was_active:
                raise Error('SERVICE_CHANGED_SINCE_PREFLIGHT_'+unit)
        h.pause_services(session,state)
        isolation(state['port'])
        serial=h.open_serial(state['port'])
        trace_stream=(session/'trace.jsonl').open('x',encoding='utf-8')
        sample_stream=(session/'samples.jsonl').open('x',encoding='utf-8')
        wire=UART1Wire(serial)
        wire.trace_sink=trace_stream
        report['reference_gfa']=wire.reference()
        print('PHASE=P300_OVERNIGHT; VS1 readers paused; NO TIME CAP',flush=True)
        old_flame=None
        def save(row):
            nonlocal count,old_flame
            sample_stream.write(json.dumps(row,separators=(',',':'),sort_keys=True)+'\n')
            count+=1
            if (old_flame!=row['flame_bit'] or count % PROGRESS_EVERY==0):
                print('SAMPLE=%d BURNER_FLAME=%d CYCLES=%d DMA0_TX=%s' % (
                    count,int(row['flame_bit']),row['complete_flame_cycles'],row['dma0_source']),flush=True)
            old_flame=row['flame_bit']
            if count % PROGRESS_EVERY==0:
                sample_stream.flush()
                os.fsync(sample_stream.fileno())
                h.atomic_json(session/'progress.json',{
                    'sample_count':count,'elapsed_s':row['elapsed_s'],
                    'last_sample_utc':row['utc'],
                    'flame_bit':row['flame_bit'],
                    'complete_flame_cycles':row['complete_flame_cycles'],
                    'dma0_source':row['dma0_source'],
                    'worker_status':'RUNNING_OPERATOR_STOPS',
                    'no_time_limit':True})
        wire.observe(save,lambda:isolation(state['port']),
                     lambda:resource_guard(session,trace_stream,sample_stream))
    except BaseException as exc:
        if str(exc)=='OPERATOR_STOP_SIGNAL_15':
            report['operator_stop']=True
            report['observation_complete']=True
        else:
            report['errors'].append(str(exc) or type(exc).__name__)
    finally:
        for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):
            signal.signal(sig,signal.SIG_IGN)
        if wire is not None:
            report['p300_phase_start_monotonic']=wire.phase_start
            report['p300_phase_end_monotonic']=wire.clock()
            try:
                isolation(state['port'])
                report['recovery_gfa']=wire.restore_link()
                report['vs1_link_restored']=True
            except BaseException as exc:
                report['errors'].append('LINK_RECOVERY: '+str(exc))
            try:
                wire.flush_trace()
                report['trace_record_count']=wire.trace_records_written
            except BaseException as exc:
                report['errors'].append('TRACE_FLUSH: '+str(exc))
        if sample_stream is not None:
            try:
                sample_stream.flush()
                os.fsync(sample_stream.fileno())
                sample_stream.close()
            except BaseException as exc:
                report['errors'].append('SAMPLE_CLOSE: '+str(exc))
        if trace_stream is not None:
            try:
                trace_stream.flush()
                os.fsync(trace_stream.fileno())
                trace_stream.close()
            except BaseException as exc:
                report['errors'].append('TRACE_CLOSE: '+str(exc))
        if serial is not None:
            try:serial.close()
            except BaseException as exc:
                report['errors'].append('SERIAL_CLOSE: '+str(exc))
        if (session/'samples.jsonl').is_file():
            try:report['comparison']=summarize_file(session/'samples.jsonl')
            except BaseException as exc:report['errors'].append('OFFLINE_SUMMARY: '+str(exc))
        report['sample_count']=count
        h.atomic_json(session/'measurement.json',report)
    return 0 if report['operator_stop'] and report['vs1_link_restored'] and not report['errors'] else 1


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
    # ExecStopPost always tries to leave ONE upload artifact, even after a
    # worker/protocol failure. Only the original service may be resumed first.
    try:
        health=post_restore_health()
        h.atomic_json(session/'health.json',health)
        archive=upload_bundle(session,health)
        print('UPLOAD_ONE_FILE='+str(archive),flush=True)
    except BaseException as exc:
        errors.append('BUNDLE_OR_POSTCHECK: '+str(exc))
        print('BUNDLE_OR_POSTCHECK_FAILED='+str(exc),flush=True)
    return int(bool(errors))


def supervisor_command(session: Path) -> list[str]:
    """Detached transient unit. Deliberately NO RuntimeMaxSec."""
    script=session/'probe.py'
    return ['systemd-run','--unit='+UNIT,'--no-block','--collect',
            '--property=Type=exec','--property=Restart=no',
            '--property=TimeoutStopSec=240','--property=KillMode=control-group',
            '--property=UMask=0077',
            f'--property=ExecStopPost={h.PYTHON} -u {script} --recover {session}',
            h.PYTHON,'-u',str(script),'--worker',str(session)]



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


def upload_bundle(session: Path,health: dict) -> Path:
    """Atomic single private archive. Stream large logs rather than loading them."""
    import stat
    if ROOT.is_symlink() or session.parent!=ROOT or session.is_symlink():
        raise Error('INVALID_BUNDLE_SESSION')
    if BUNDLES.is_symlink():
        raise Error('OUTPUT_ROOT_SYMLINK')
    BUNDLES.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(BUNDLES,0o700)
    target=BUNDLES/('uart1-overnight-'+session.name+'-bundle.tar.gz')
    if target.exists() or target.is_symlink():
        if not target.is_file() or target.is_symlink():
            raise Error('INVALID_EXISTING_BUNDLE')
        return target
    names=('state.json','progress.json','samples.jsonl','trace.jsonl',
           'measurement.json','recovery.json','health.json')
    included={}
    for name in names:
        path=session/name
        if not path.exists():
            continue
        info=path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or info.st_mode&0o077:
            raise Error('UNSAFE_SESSION_FILE_'+name)
        digest=hashlib.sha256()
        with path.open('rb') as fd:
            for chunk in iter(lambda:fd.read(1024*1024),b''):
                digest.update(chunk)
        included[name]={'sha256':digest.hexdigest(),'size_bytes':info.st_size}
    manifest={'schema_version':1,'session':session.name,'files':included,
              'operational_health':health,
              'uart1_gfa_link_proven':False,
              'p06_measured_rpm_alias_proven':False,
              'production_approved':False,'ram_write_approved':False,
              'no_time_limit':True,
              'read_allowlist':['FC01 0x55D3/11','FC03 0x0020/16',
                                'FC03 0x1600/32','FC03 0x1620/32']}
    temp=None
    import tempfile
    try:
        with tempfile.NamedTemporaryFile(prefix='bundle-',suffix='.tar.gz',
                  dir=BUNDLES,delete=False) as f:
            temp=Path(f.name)
        os.chmod(temp,0o600)
        with tarfile.open(temp,'w:gz') as tar:
            for name in included:
                tar.add(session/name,arcname='uart1-overnight/'+name,
                        recursive=False)
            data=(json.dumps(manifest,sort_keys=True,indent=2)+'\n').encode()
            item=tarfile.TarInfo('uart1-overnight/bundle-manifest.json')
            item.size=len(data);item.mode=0o600;item.mtime=0
            tar.addfile(item,io.BytesIO(data))
        temp.rename(target)
    except BaseException:
        if temp is not None:temp.unlink(missing_ok=True)
        raise
    return target



def latest_session() -> Path:
    if ROOT.is_symlink() or not ROOT.is_dir():
        raise Error('NO_OVERNIGHT_SESSION')
    dirs=sorted(p for p in ROOT.glob('run-*') if p.is_dir() and not p.is_symlink())
    if not dirs:
        raise Error('NO_OVERNIGHT_SESSION')
    return dirs[-1]


def launch() -> int:
    with locks():
        values,states=h.preflight()
        if h.unit_state(UNIT).get('ActiveState') not in ('inactive','failed'):
            raise Error('OVERNIGHT_UNIT_ALREADY_ACTIVE')
        for competing in ('optolink-uart1-dma0-cycle.service',
                          'optolink-p87-p300-check.service',
                          'optolink-handover-probe.service',
                          'optolink-uart1-p300-focus.service'):
            if h.unit_state(competing).get('ActiveState') not in ('inactive','failed'):
                raise Error('COMPETING_PROBE_ACTIVE_'+competing)
        if ROOT.is_symlink():
            raise Error('SESSION_ROOT_SYMLINK')
        ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
        os.chmod(ROOT,0o700)
        for old in ROOT.glob('run-*/state.json'):
            if old.is_symlink():raise Error('PREVIOUS_STATE_SYMLINK')
            previous=json.loads(old.read_text())
            rec=old.with_name('recovery.json')
            if previous.get('restore') and (not rec.exists() or
                    not json.loads(rec.read_text()).get('services_restored')):
                raise Error('UNRESOLVED_VS1_RECOVERY_'+old.parent.name)
        stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        session=ROOT/f'run-{stamp}-{os.getpid()}'
        session.mkdir(mode=0o700)
        for src,name in ((Path(__file__),'probe.py'),
                         (Path(__file__).with_name(HELPER),HELPER)):
            shutil.copyfile(src,session/name)
            (session/name).chmod(0o600)
        h.atomic_json(session/'state.json',{
            'version':VERSION,'no_time_limit':True,'services':states,
            'restore':[],'port':values['port_optolink'],
            'script_sha256':hashlib.sha256((session/'probe.py').read_bytes()).hexdigest(),
            'helper_sha256':HELPER_SHA256})
    print('SESSION='+str(session),flush=True)
    result=subprocess.run(supervisor_command(session),capture_output=True,
                          text=True,check=False,timeout=30)
    if result.returncode:
        raise Error('SYSTEMD_START_REJECTED: '+result.stderr[-500:])
    print('OVERNIGHT_START_ACCEPTED='+UNIT,flush=True)
    print('DURATION=UNTIL_OPERATOR_STOPS; NO_RUNTIMEMAXSEC',flush=True)
    print('STATUS_CMD=systemctl status '+UNIT+' --no-pager',flush=True)
    print('STOP_CMD=use reviewed batch action stop-overnight',flush=True)
    return 0


def status() -> int:
    session=latest_session()
    unit=h.unit_state(UNIT)
    progress=session/'progress.json'
    obj=json.loads(progress.read_text()) if progress.exists() else {}
    print('SESSION='+str(session))
    print('UNIT_ACTIVE='+unit.get('ActiveState','unknown'))
    print('PROGRESS='+json.dumps(obj,sort_keys=True))
    return 0


def stop() -> int:
    session=latest_session()
    unit=h.unit_state(UNIT)
    if unit.get('ActiveState') in ('active','activating','deactivating'):
        proc=subprocess.run(['systemctl','stop',UNIT],capture_output=True,text=True,
                            check=False,timeout=300)
        if proc.returncode:
            print('SYSTEMD_STOP_ERROR='+proc.stderr[-500:],flush=True)
    elif unit.get('ActiveState') not in ('inactive','failed'):
        raise Error('UNEXPECTED_UNIT_STATE_'+str(unit))
    # systemctl stop waits for ExecStopPost, including service recovery and archive.
    for _ in range(45):
        if (session/'recovery.json').is_file():
            break
        time.sleep(1)
    health=json.loads((session/'health.json').read_text()) if (session/'health.json').is_file() else post_restore_health()
    if not (session/'health.json').exists():
        h.atomic_json(session/'health.json',health)
    archive=upload_bundle(session,health)
    rec=json.loads((session/'recovery.json').read_text()) if (session/'recovery.json').is_file() else {}
    measurement=json.loads((session/'measurement.json').read_text()) if (session/'measurement.json').is_file() else {}
    print('SESSION='+str(session),flush=True)
    print('LINK_AND_SERVICE_RESTORE='+('PASS' if measurement.get('vs1_link_restored') and rec.get('services_restored') else 'NOT_VERIFIED'),flush=True)
    print('CAPTURE='+json.dumps(measurement.get('comparison',{}),sort_keys=True),flush=True)
    print('UPLOAD_ONE_FILE='+str(archive),flush=True)
    healthy=health.get('production_main_verified') and all(
        health.get('gfa_reads',{}).get(key,{}).get('format_and_identity_verified')
        for key in ('P80','P06'))
    print('VS1_P80_P06_HEALTH='+('PASS' if healthy else 'NOT_VERIFIED'),flush=True)
    return 0 if rec.get('services_restored') and healthy else 1



def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    mode=p.add_mutually_exclusive_group()
    mode.add_argument('--start',action='store_true')
    mode.add_argument('--stop',action='store_true')
    mode.add_argument('--status',action='store_true')
    mode.add_argument('--worker',type=Path,help=argparse.SUPPRESS)
    mode.add_argument('--recover',type=Path,help=argparse.SUPPRESS)
    args=p.parse_args()
    os.umask(0o077)
    if args.worker or args.recover:
        if os.geteuid()!=0 or not os.getenv('INVOCATION_ID'):
            p.error('worker/recover require controlled systemd context')
        return worker(args.worker) if args.worker else recover(args.recover)
    if args.start:return launch()
    if args.stop:return stop()
    if args.status:return status()
    print('PLAN ONLY: operator-stopped P300 capture; no duration cap, no auto-stop on flame changes.')
    print('Fixed reads FC01 55D3/11, FC03 0020/16, 1600/32, 1620/32.')
    print('No U1RB, RAM writes, pump override, burner trigger or serial access in plan mode.')
    print('Starts detached by systemd; operator uses stop-overnight to restore VS1 and export.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (Error, OSError, ValueError, subprocess.SubprocessError) as exc:
        print('REFUSED_OR_FAILED=' + str(exc), file=sys.stderr)
        raise SystemExit(1)
