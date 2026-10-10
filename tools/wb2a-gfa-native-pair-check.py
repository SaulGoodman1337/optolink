#!/usr/bin/env python3
"""Fixed read-only P06/P09/native-block comparison via existing VS1 MQTT.

Default is inert. No serial access, service stop, settings change or P300/RAM.
Goal: distinguish measured fan reference from demand; no automatic replacement.
"""
from __future__ import annotations
import argparse
from collections import Counter
import contextlib
import datetime as dt
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import time

VERSION = '1.0.0'
HELPER = 'wb2a-p87-mirror-check.py'
HELPER_SHA256 = '2d50024f9418f4ba72170c28e3aa08a23e7a4929654e8e9b7196296cef6ea914'
ROOT = Path('/root/p300-trial-work/gfa-native-pairs')
INTERVAL = 5.0
MAX_BRACKET_SECONDS = 2.0


def load_helper():
    path = Path(__file__).resolve().with_name(HELPER)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != HELPER_SHA256:
        raise RuntimeError('PINNED_MQTT_HELPER_MISMATCH')
    spec = importlib.util.spec_from_file_location('gfa_native_mqtt_support', path)
    module = importlib.util.module_from_spec(spec)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


h = load_helper()
Error = h.CheckError
# Replace the private imported module's allowlist, never files or production state.
h.READS = {
    'device': ('r;0x00F8;2;raw;False', 0xF8, 2),
    'software': ('r;0x778C;2;raw;False', 0x778C, 2),
    'p80': ('gfaread;0x4050;1;raw;False', 0x4050, 1),
    'p06': ('gfaread;0x4006;1;raw;False', 0x4006, 1),
    'p09': ('gfaread;0x4009;1;raw;False', 0x4009, 1),
    'native_status': ('r;0x55D3;11;raw;False', 0x55D3, 11),
}
h.ADDRESSES = frozenset(v[1] for v in h.READS.values())


def valid_read(row, name):
    try:
        expected_len = h.READS[name][2]
        value = bytes.fromhex(row['raw'])
        if row['name'] != name or len(value) != expected_len:
            raise ValueError
        if row['sent'] > row['received']:
            raise ValueError
    except (KeyError, ValueError, TypeError):
        raise Error('INVALID_PAIR_INPUT') from None
    if name in ('p80','p06','p09') and value == b'\xff':
        raise Error('GFA_FF_IS_NOT_VALID_DATA')
    return value


def classify(before, middle, after):
    span = after['received'] - before['received']
    if before['raw'] != after['raw']:
        verdict = 'REFERENCE_CHANGED'
    elif span > MAX_BRACKET_SECONDS:
        verdict = 'BRACKET_TOO_WIDE'
    else:
        verdict = 'STABLE_REFERENCE'
    return {'before':before['raw'], 'after':after['raw'], 'verdict':verdict,
            'bracket_ms':span*1000}


def pair(p06a, p09a, native, p09b, p06b):
    rows = [p06a,p09a,native,p09b,p06b]
    names = ['p06','p09','native_status','p09','p06']
    vals = [valid_read(r,n) for r,n in zip(rows,names)]
    if any(a['received'] > b['sent'] for a,b in zip(rows,rows[1:])):
        raise Error('NON_MONOTONIC_PAIR')
    block = vals[2]
    p06, p09 = classify(p06a,native,p06b), classify(p09a,native,p09b)
    both = p06['verdict']==p09['verdict']=='STABLE_REFERENCE'
    return {'p06':p06, 'p09':p09, 'native_block':block.hex(),
            'native_b0':block[0], 'native_b9':block[9], 'native_b7':f'{block[7]:02x}',
            'flame_bit':bool(block[5]&32), 'lockout_bit':bool(block[5]&64),
            'stable_raw_p06_p09_differ':bool(both and p06['before']!=p09['before']),
            'reads':rows, 'simultaneous_acquisition':False,
            'flame_bit_mapping_source':'existing WB2A project profile'}


def summarize(rows):
    result = {}
    for key in ('p06','p09'):
        good=[r for r in rows if r[key]['verdict']=='STABLE_REFERENCE']
        states=sorted({r[key]['before'] for r in good})
        result[key]={'counts':dict(Counter(r[key]['verdict'] for r in rows)),
                     'stable_reference_states':states,
                     'stable_nonzero_reference_states':[v for v in states if v!='00'],
                     'nonzero_stable_pairs':sum(r[key]['before']!='00' for r in good)}
    useful = all(result[k]['nonzero_stable_pairs'] for k in result)
    result.update(outcome='PAIRS_RECORDED_NEEDS_ANALYSIS' if useful else 'INCONCLUSIVE_REFERENCE_COVERAGE',
                  sample_count=len(rows),stable_p06_p09_separation_count=sum(r['stable_raw_p06_p09_differ'] for r in rows),
                  production_alias_verified=False, p300_freshness_verified=False,
                  measured_vs_commanded_source_identified=False,
                  new_conversion_fitted=False)
    return result


def sample(client):
    h.require(client.read('p80'), '20')
    names=('p06','p09','native_status','p09','p06')
    rows=[]
    for name in names:
        row=client.read(name)
        valid_read(row,name)  # Stop immediately on invalid data; no follow-on read.
        rows.append(row)
    return pair(*rows)


@contextlib.contextmanager
def locks():
    with contextlib.ExitStack() as stack:
        for name in ('optolink-handover-probe.lock','optolink-p300-trial.lock',
                     'optolink-p87-mirror.lock','optolink-p87-p300-check.lock',
                     'optolink-gfa-native-pair.lock'):
            fd=os.open('/run/lock/'+name,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
            stack.callback(os.close,fd)
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield


def execute(seconds):
    values=h.preflight()  # Read-only systemctl check; never stops the splitter.
    if ROOT.is_symlink():
        raise Error('RESULT_ROOT_MUST_NOT_BE_SYMLINK')
    ROOT.mkdir(parents=True,exist_ok=True,mode=0o700);ROOT.chmod(0o700)
    session=ROOT/('run-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+str(os.getpid()))
    session.mkdir(mode=0o700)
    report={'version':VERSION,'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'helper_sha256':HELPER_SHA256,'transport':'existing VS1 via MQTT',
            'protocol_switched':False,'services_stopped':False,'device_writes':False,
            'rounds':[],'errors':[]}
    print('SESSION='+str(session),flush=True)
    client=None
    def stop(signum,frame):
        raise KeyboardInterrupt
    old={sig:signal.signal(sig,stop) for sig in (signal.SIGTERM,signal.SIGHUP)}
    try:
        client=h.MQTT(values)
        report['opening']={}
        for name,value in (('device','20c2'),('software','0103'),('p80','20')):
            row=client.read(name);h.require(row,value);report['opening'][name]=row
        deadline=time.monotonic()+seconds
        with (session/'pairs.jsonl').open('x',encoding='utf-8') as out:
            for index in range((seconds+4)//5):
                if time.monotonic()>=deadline:
                    break
                start=time.monotonic()
                row=sample(client);row.update(index=index+1,utc=dt.datetime.now(dt.timezone.utc).isoformat())
                report['rounds'].append(row)
                out.write(json.dumps(row,sort_keys=True)+'\n');out.flush()
                print(json.dumps({k:row[k] for k in ('index','p06','p09','native_b0','native_b9','native_b7','flame_bit')},sort_keys=True),flush=True)
                client.pump(max(0.0,min(start+INTERVAL,deadline)-time.monotonic()))
        report['closing_p80']=client.read('p80');h.require(report['closing_p80'],'20')
    except KeyboardInterrupt:
        report['errors'].append('STOPPED_BY_USER_NO_RESTORE_NEEDED')
    except (Error,OSError,ValueError) as exc:
        report['errors'].append(str(exc) if isinstance(exc,Error) else type(exc).__name__)
    finally:
        if client is not None:
            try:
                report['retained_responses_ignored']=client.receiver.retained_ignored
                client.close()
            except Exception:
                report['errors'].append('MQTT_CLOSE_FAILED')
        for sig,handler in old.items():
            signal.signal(sig,handler)
        report['comparison']=summarize(report['rounds'])
        if report['errors']:
            report['comparison']['outcome']='INCOMPLETE_OR_FAILED'
        report['limits']=['No request IDs; exclude parallel debug clients on tracked addresses.',
                          'Sequential host reads; identical endpoints do not exclude hidden changes.',
                          'B0 is an existing control diagnostic, not a validated tachometer.',
                          'P06/P09 raw values are not native percentages; no replacement conversion assumed.']
        with (session/'summary.json').open('x',encoding='utf-8') as out:
            json.dump(report,out,indent=2,sort_keys=True);out.write('\n')
    print('RESULT='+report['comparison']['outcome'],flush=True)
    print(json.dumps(report['comparison'],sort_keys=True),flush=True)
    for error in report['errors']:
        print('ERROR='+error,flush=True)
    print('No service, protocol or settings change. No rollback needed.')
    return int(bool(report['errors']))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute',action='store_true')
    p.add_argument('--seconds',type=int,default=600)
    args=p.parse_args()
    if not 30<=args.seconds<=900:
        p.error('--seconds must be in 30..900')
    if not args.execute:
        print('PLAN ONLY: P80 -> P06 -> P09 -> 55D3/11 -> P09 -> P06.')
        print('Six fixed reads per round, >=5s between starts; running VS1, no service stop/P300/RAM/write.')
        print('Record raw paired references. No automatic RPM, percent conversion or production alias.')
        return 0
    os.umask(0o077)
    with locks():
        return execute(args.seconds)


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except (Error,OSError,ValueError,subprocess.SubprocessError) as exc:
        print('REFUSED_OR_FAILED='+(str(exc) if isinstance(exc,Error) else type(exc).__name__))
        raise SystemExit(1)
