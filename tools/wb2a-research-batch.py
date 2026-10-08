#!/usr/bin/env python3
"""One-command WB2A research collection and optional gated read-only trial.

Default = collect existing UART1 evidence; no serial activity and no protocol
switch. --execute-uart1 explicitly delegates to the already-reviewed supervised
probe, and REFUSES an identical rerun after any successful saved session.
No production install, writes, settings edits, E7 writes, or unapproved scans.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path('/root/p300-trial-work/uart1-p300-results')
OUTPUT = Path('/root/p300-trial-work/research-bundles')
PROJECT = Path(__file__).resolve().parents[1]
PYTHON = Path('/opt/optolink/venv/bin/python')
PROBE = PROJECT/'tools/wb2a-uart1-p300-focus.py'
FILES = ('measurement.json', 'samples.jsonl', 'recovery.json', 'state.json')
TESTS = ('test_uart1_p300_focus.py', 'test_uart1_dma0_cycle.py',
         'test_uart1_gfa_ram_audit.py', 'test_p87_p300_check.py',
         'test_handover*.py')
RAM_ADDR = 0x1600
MAX_BYTES = 8_000_000
TX_FRAMES = frozenset((
    '04', '01f700f802', 'f7778c02', '6b405001', '6b400601',
    '6b400901', '6b405701', '160000',
    '4105000100f80200', '41050001778c020b',
    '4105000155d30b39', '410500031600203e', '410500031620205e', '06'
))
P300_OBSERVE = {
    '4105000155d30b39': 'native_status',
    '410500031600203e': 'physical_1600',
    '410500031620205e': 'physical_1620',
}
UNVERIFIED = {
    'uart1_gfa_link_verified': False,
    'p06_rpm_alias_verified': False,
    'production_approved': False,
    'ram_write_approved': False,
}


class BatchError(ValueError):
    pass


def private_dir(path):
    info=path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077:
        raise BatchError('Session/output directory is not private: ' + str(path))


def read_file(path):
    info=path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES or info.st_size < 1:
        raise BatchError('Missing, symlinked or oversized file: '+str(path))
    return path.read_bytes()


def latest():
    if not ROOT.is_dir() or ROOT.is_symlink():
        raise BatchError('No UART1 sessions: '+str(ROOT))
    private_dir(ROOT)
    sessions = sorted(
        (p for p in ROOT.iterdir() if p.name.startswith('run-') and p.is_dir()
         and not p.is_symlink()), key=lambda p:p.name)
    if not sessions:
        raise BatchError('No completed UART1 session to collect')
    private_dir(sessions[-1])
    return sessions[-1]



def verify_p300_response_trace(trace, samples):
    """Independent byte-level check against stored FC01/FC03 samples.

    Stored TX/RX trace is the original acquisition and samples.jsonl is
    derived from the acquisition. Their agreement plus the wire checksum
    is an integrity check, NOT independent proof of register semantics.
    """
    specs = {
        '4105000100f80200': (1, 0x00F8, 2, None, '20c2'),
        '41050001778c020b': (1, 0x778C, 2, None, '0103'),
        '4105000155d30b39': (1, 0x55D3, 11, 'native_block', None),
        '410500031600203e': (3, 0x1600, 32, 'ram_1600', None),
        '410500031620205e': (3, 0x1620, 32, 'ram_1620', None)
    }
    counts = collections.Counter()
    seen_timestamps = []
    for idx, entry in enumerate(trace):
        if entry.get('direction') not in ('RX', 'TX'):
            raise BatchError('Unknown trace direction')
        if 't_monotonic' in entry:
            seen_timestamps.append(entry['t_monotonic'])
        if entry['direction'] != 'TX':
            continue
        command = entry['hex'].lower()
        if command not in specs:
            continue
        function, address, count, field, fixed = specs[command]
        reply_chunks = []
        next_tx = None
        for subsequent in trace[idx+1:]:
            if subsequent['direction'] == 'TX':
                next_tx = subsequent
                break
            reply_chunks.append(bytes.fromhex(subsequent['hex']))
        if next_tx is None or next_tx['hex'].lower() != '06':
            raise BatchError('P300 response not explicitly ACKed')
        reply = b''.join(reply_chunks)
        if len(reply) < 4 or reply[:2] != b'\x06\x41':
            raise BatchError('P300 reply missing ACK/STX')
        size = reply[2]
        if size != 5 + count or len(reply) != size + 4:
            raise BatchError('P300 reply byte length wrong')
        body = reply[3:-1]
        if (size + sum(body)) & 255 != reply[-1]:
            raise BatchError('P300 reply checksum invalid')
        if (body[0] != 1 or body[1] != function
                or int.from_bytes(body[2:4], 'big') != address
                or body[4] != count or len(body[5:]) != count):
            raise BatchError('P300 reply identity/function/length mismatch')
        data = body[5:]
        count_so_far = counts[command]
        if field is not None:
            if count_so_far >= len(samples) or data.hex() != samples[count_so_far][field].lower():
                raise BatchError('P300 response differs from saved sample')
        elif data.hex() != fixed:
            raise BatchError('P300 controller/device identity mismatched')
        counts[command] += 1
    if seen_timestamps and (len(seen_timestamps) != len(trace)
            or any(b < a for a,b in zip(seen_timestamps, seen_timestamps[1:]))):
        raise BatchError('Non-monotonic or incomplete trace timestamps')
    expected = {key: (len(samples) if field is not None else 1)
                for key,(_,_,_,field,_) in specs.items()}
    if dict(counts) != expected:
        raise BatchError('P300 read cycle count incomplete/duplicated')
    return {
        'responses_verified':sum(counts.values()),
        'response_checksum_address_and_payload_verified':True,
        'frames_by_request':dict(counts),
        'source_trace_has_timestamps':bool(seen_timestamps)
    }


def validate(session):
    source={name:read_file(session/name) for name in FILES}
    measurement=json.loads(source['measurement.json'])
    recovery=json.loads(source['recovery.json'])
    state=json.loads(source['state.json'])
    samples=[json.loads(line) for line in source['samples.jsonl'].splitlines()
             if line.strip()]
    if not samples or samples!=measurement.get('samples'):
        raise BatchError('samples.jsonl differs from measurement.json')
    if not measurement.get('observation_complete') or measurement.get('errors'):
        raise BatchError('Observation not complete or includes errors')
    if not measurement.get('vs1_link_restored') or not recovery.get('services_restored') \
            or recovery.get('errors') or recovery.get('systemd_service_result') not in ('success','not-supplied'):
        raise BatchError('VS1/production restoration not proven')
    if measurement.get('recovery_gfa',{}).get('P80')!='20' \
            or measurement.get('reference_gfa',{}).get('P80')!='20':
        raise BatchError('Wrong or unavailable GFA P80')
    if len(state.get('services',{})) != 7 or set(state.get('restore',[])) - set(state['services']):
        raise BatchError('Unexpected recovery manifest')
    by_address=collections.Counter()
    transitions=[]
    unique=set()
    prev=None
    status_states=set()
    for n,row in enumerate(samples,1):
        if row.get('index')!=n:
            raise BatchError('Nonsequential samples')
        raw=bytes.fromhex(row['ram_1600'])+bytes.fromhex(row['ram_1620'])
        status=bytes.fromhex(row['native_block'])
        if len(raw)!=64 or len(status)!=11 or row['native_b7'].lower()!=f'{status[7]:02x}':
            raise BatchError('Malformed native or physical sample')
        if row.get('p06_rpm_alias_verified') is not False \
                or row.get('uart1_gfa_link_verified') is not False:
            raise BatchError('Unjustified sensor alias in samples')
        unique.add(raw)
        status_states.add(row['native_b7'].lower())
        if prev is not None:
            addresses=[f'0x{RAM_ADDR+i:04x}' for i,(a,b) in enumerate(zip(prev,raw)) if a!=b]
            by_address.update(addresses)
            if addresses:
                transitions.append({'sample':n, 'at_s':round(row['elapsed_s'],3),
                                    'changed_addresses':addresses})
        prev=raw
    summary=measurement['comparison']
    if dict(sorted(by_address.items()))!=dict(sorted(summary['changed_address_counts'].items())):
        raise BatchError('Changed-address tally differs from worker')
    if (summary['sample_count']!=len(samples) or summary['changed_byte_count']!=len(by_address)
        or summary['observed_dma_source_changed']!=by_address['0x161b']):
        raise BatchError('Summary counts disagree with raw rounds')
    if any(summary.get(k) is not v for k,v in UNVERIFIED.items()):
        raise BatchError('Evidence improperly approved device modification or alias')
    tx=collections.Counter()
    for entry in measurement.get('trace',[]):
        direction=entry.get('direction')
        if direction=='RX_UNEXPECTED':
            raise BatchError('Unexpected response bytes in trace')
        if direction=='TX':
            frame=entry['hex'].lower()
            if frame not in TX_FRAMES:
                raise BatchError('Unknown outgoing telegram: '+frame)
            tx[frame]+=1
    for frame in P300_OBSERVE:
        if tx[frame]!=len(samples):
            raise BatchError('Trace frame count differs from samples: '+frame)
    if tx['160000']!=1 or tx['4105000100f80200']!=1:
        raise BatchError('Unexpected P300 session boundaries')
    wire_verification=verify_p300_response_trace(measurement['trace'],samples)
    report={
        'schema_version':1,
        'session':session.name,
        'source_sha256':{name:hashlib.sha256(data).hexdigest()
                         for name,data in source.items()},
        'samples_verified':len(samples),
        'p300_phase_s':round(
            measurement['p300_phase_end_monotonic']-
            measurement['p300_phase_start_monotonic'],3),
        'ram_unique_64byte_states':len(unique),
        'ram_changed_addresses':dict(sorted(by_address.items())),
        'ram_change_events':transitions,
        'native_b7_states':sorted(status_states),
        'reference_gfa':measurement['reference_gfa'],
        'recovery_gfa':measurement['recovery_gfa'],
        'service_restore_reported':True,
        'transmit_counts':{P300_OBSERVE[k]:tx[k] for k in P300_OBSERVE},
        'trace_frames_allowlisted':True,
        'p300_wire_responses_verified':wire_verification,
        'sensor_alias_verified':False,
        'uart1_connected_to_gfa_proven':False,
        'hardware_write_performed':False,
        'interpretation':'UART1-source RAM changed; no GFA link/RPM source proven.'
    }
    return report,source


def test_suite():
    output=[]
    for pattern in TESTS:
        command=[sys.executable,'-m','unittest','discover','-s',
                 str(PROJECT/'tests'),'-p',pattern,'-v']
        p=subprocess.run(command,cwd=PROJECT,text=True,stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT,timeout=90,check=False)
        output.append('$ '+ ' '.join(command)+'\n'+p.stdout)
        print('OFFLINE_TEST',pattern,'PASS' if p.returncode==0 else 'FAILED',flush=True)
        if p.returncode:
            raise BatchError('Offline tests failed ('+pattern+'): '+p.stdout[-1400:])
    return '\n\n'.join(output)


def health():
    """Verify current normal service; MQTT GFA reads are optional and read-only."""
    result={'service':'UNVERIFIED', 'mqtt_readbacks':{}, 'ha_freshness_verified':False}
    p=subprocess.run(['systemctl','show','optolink-splitter.service',
                      '-p','ActiveState','-p','SubState','-p','WorkingDirectory'],
                     text=True,capture_output=True,timeout=12,check=False)
    info=dict(line.split('=',1) for line in p.stdout.splitlines() if '=' in line)
    if (p.returncode==0 and info.get('ActiveState')=='active'
            and info.get('SubState')=='running'
            and info.get('WorkingDirectory')=='/opt/optolink'):
        result['service']='PASS'
    else:
        result['service']='NOT_VERIFIED'
    # Do not produce competing serial/MQTT requests unless main is ready.
    if result['service']=='PASS':
        for label,request in [('P80','gfaread;0x4050;1;raw;False'),
                              ('P06','gfaread;0x4006;1;raw;False')]:
            try:
                p=subprocess.run(['optolink-debug','request',request,'--timeout','8'],
                    text=True,capture_output=True,timeout=14,check=False)
                result['mqtt_readbacks'][label]={'returncode':p.returncode,
                    'stdout':p.stdout[-800:],'stderr':p.stderr[-300:]}
            except (OSError,subprocess.TimeoutExpired) as exc:
                result['mqtt_readbacks'][label]={'error':str(exc)[:300]}
    return result


def output_dir():
    if OUTPUT.is_symlink():
        raise BatchError('Bundle output directory symlink')
    OUTPUT.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(OUTPUT,0o700)
    private_dir(OUTPUT)


def archive(session,source,report,tests,check):
    output_dir()
    filename='uart1-'+session.name+'-bundle.tar.gz'
    target=OUTPUT/filename
    if target.is_symlink():
        raise BatchError('Output archive symlink refused: '+str(target))
    if target.exists():
        # Collection is repeatable without redundant archives or changing evidence.
        if not target.is_file():
            raise BatchError('Existing archive is not a regular file')
        with tarfile.open(target, 'r:gz') as previous:
            item=previous.extractfile('uart1/batch-analysis.json')
            if item is None:
                raise BatchError('Existing archive has no evidence manifest')
            old=json.load(item)
            if old.get('source_sha256') != report.get('source_sha256'):
                raise BatchError('Existing archive does not match current source bytes')
        print('BUNDLE_ALREADY_VALID_REUSED='+str(target))
        return target
    import io
    contents=dict(source)
    contents['batch-analysis.json']=(json.dumps(report,indent=2,sort_keys=True)+'\n').encode()
    contents['batch-health.json']=(json.dumps(check,indent=2,sort_keys=True)+'\n').encode()
    contents['offline-tests.txt']=tests.encode()
    with tempfile.NamedTemporaryFile(prefix='bundle-',suffix='.tar.gz',
             dir=OUTPUT,delete=False) as tmp:
        tmp_path=Path(tmp.name)
    try:
        with tarfile.open(tmp_path,mode='w:gz') as tar:
            for name,data in contents.items():
                meta=tarfile.TarInfo('uart1/'+name)
                meta.size=len(data)
                meta.mode=0o600
                meta.mtime=0
                tar.addfile(meta,io.BytesIO(data))
        os.chmod(tmp_path,0o600)
        tmp_path.rename(target)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    return target


def collect(tests=None):
    if tests is None:
        tests=test_suite()
    session=latest()
    report,source=validate(session)
    check=health()
    target=archive(session,source,report,tests,check)
    print('SESSION='+str(session))
    print('RESULT=VALIDATED_EXISTING_DATA, NOT_A_NEW_DEVICE_READ')
    print('RAM_PATTERNS='+str(report['ram_unique_64byte_states']))
    print('RAM_CHANGE_EVENTS='+str(len(report['ram_change_events'])))
    print('MAIN_SERVICE='+check['service'])
    print('HA_FRESHNESS=NOT_VERIFIED_BY_THIS_TOOL')
    print('UPLOAD_ONE_FILE='+str(target))
    return 0 if check['service']=='PASS' else 2


def execute_uart1(tests):
    # This profile has already produced a verified hardware result on WB2A.
    # Only a newly approved profile should be enabled for another hardware run.
    if ROOT.is_dir():
        for path in ROOT.glob('run-*/measurement.json'):
            try:
                m=json.loads(read_file(path))
            except (OSError,ValueError,KeyError):
                continue
            if m.get('observation_complete') and m.get('vs1_link_restored') \
                    and not m.get('errors'):
                raise BatchError('UART1_PROFILE_ALREADY_COMPLETED: refusing duplicate device outage')
    print('RUNNING_ONE_BOUNDED_SUPERVISED_UART1_HARDWARE_TRIAL')
    proc=subprocess.run([sys.executable,'-u',str(PROBE),'--execute',
                         '--seconds','60'],cwd=PROJECT,check=False)
    if proc.returncode:
        raise BatchError('Hardware probe or recovery failed; do not repeat without review')
    return collect(tests)



def execute_dma0_cycle(tests):
    """Single approved hardware session, followed by automatic private archive.

    The dedicated probe owns all serial/service controls, recovery and
    post-restoration VS1 readbacks. Never call production tools directly here.
    """
    script=PROJECT/'tools/wb2a-uart1-dma0-cycle.py'
    if not script.is_file() or script.is_symlink():
        raise BatchError('MISSING_REVIEWED_DMA0_CYCLE_PROBE')
    print('PHASE=GATED_DMA0_CYCLE_ONE_SESSION',flush=True)
    result=subprocess.run([sys.executable,'-u',str(script),'--execute',
                           '--seconds','600'],cwd=PROJECT,check=False)
    if result.returncode:
        raise BatchError('DMA0 CYCLE FAILED OR RESTORE UNVERIFIED. Do not repeat; collect the output bundle and inspect errors.')
    print('DONE=ONE_COMBINED_GATED_P300_SESSION; NO_REPEAT',flush=True)
    return 0


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',nargs='?',choices=('collect','execute-uart1','execute-dma0-cycle','plan'),default='plan')
    args=p.parse_args()
    os.umask(0o077)
    if args.action=='plan':
        print('PLAN ONLY: collect = run offline tests, verify last UART1 session,')
        print('check live VS1 service and GFA readbacks, create ONE private upload bundle.')
        print('execute-uart1 refuses a completed trial; execute-dma0-cycle is a separate explicit 600s opt-in.')
        print('No serial, RAM writes or service stops in plan/collect; no auto retry of live trials.')
        return 0
    if os.geteuid()!=0 or PROJECT!=Path('/root/p300-trial-work/project'):
        raise BatchError('Requires root in the reviewed developer checkout')
    tests=test_suite()
    if args.action=='collect':
        return collect(tests)
    if args.action=='execute-dma0-cycle':
        return execute_dma0_cycle(tests)
    return execute_uart1(tests)


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except (BatchError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print('BATCH_REFUSED_OR_FAILED='+str(exc),file=sys.stderr)
        raise SystemExit(1)
