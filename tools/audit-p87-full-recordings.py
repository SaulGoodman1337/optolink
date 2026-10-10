#!/usr/bin/env python3
"""Offline audit of the supplied P300-only recordings. Never opens device/network.

Read regular JSON members in memory; never extract or execute archive content.
Byte semantics are NOT inferred here. Flame/lockout bit masks are the existing
WB2A project mapping; recorded times are host observations, not sensor latency.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import statistics
import tarfile

REQUEST = '4105000155d30b39'
MAX_MEMBER = 16 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024


class AuditError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise AuditError(message)


def pairs_unique(pairs):
    result = {}
    for key, val in pairs:
        require(key not in result, 'duplicate JSON key')
        result[key] = val
    return result


def decode(data):
    return json.loads(data, object_pairs_hook=pairs_unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(AuditError('nonfinite JSON')))


def distribution(values):
    require(bool(values), 'empty distribution')
    return {'min': min(values), 'mean': statistics.mean(values),
            'median': statistics.median(values), 'max': max(values)}


def read_archive(path):
    require(path.stat().st_size <= MAX_TOTAL, 'archive too large')
    files = {}
    with tarfile.open(path, 'r:gz') as archive:
        total = 0
        for member in archive:
            name = member.name
            p = PurePosixPath(name)
            require(not p.is_absolute() and '..' not in p.parts and len(p.parts) == 2,
                    'invalid member path')
            require(re.fullmatch(r'run-\d{8}T\d{6}Z-\d+', p.parts[0]), 'invalid session name')
            require(p.name in ('measurement.json', 'samples.jsonl', 'recovery.json'), 'unexpected member')
            require(member.isfile() and not member.issparse(), 'not a regular file')
            require(name not in files and 0 <= member.size <= MAX_MEMBER, 'duplicate/oversize member')
            total += member.size
            require(total <= MAX_TOTAL, 'expanded archive too large')
            data = archive.extractfile(member).read(MAX_MEMBER + 1)
            require(len(data) == member.size, 'member size mismatch')
            files[name] = data
    sessions = sorted({PurePosixPath(name).parts[0] for name in files})
    require(bool(sessions), 'empty archive')
    require(len(files) == 3 * len(sessions), 'incomplete session')
    return files, sessions


def decode_reply(raw):
    n = 0
    while n < len(raw) and raw[n] == 6:
        n += 1
    require(1 <= n <= 8, 'request ACK missing or excessive')
    frame = raw[n:]
    require(len(frame) == 19 and frame[:2] == b'\x41\x10', 'status frame shape')
    require(sum(frame[1:-1]) & 255 == frame[-1], 'checksum mismatch')
    require(frame[2:7] == bytes.fromhex('010155d30b'), 'reply type/function/address/count')
    return frame[7:-1], n


def audit_trace(measurement):
    start, end = (measurement[k] for k in ('p300_phase_start_monotonic', 'p300_phase_end_monotonic'))
    require(math.isfinite(start) and math.isfinite(end) and end > start, 'invalid phase interval')
    trace = measurement['trace']
    require(all(math.isfinite(e['t_monotonic']) for e in trace), 'invalid timestamp')
    require(all(b['t_monotonic'] >= a['t_monotonic'] for a,b in zip(trace,trace[1:])),
            'nonmonotonic trace')
    phase = [e for e in trace if start <= e['t_monotonic'] <= end]
    chunks, current = [], None
    for e in phase:
        if e['direction'] == 'TX' and e['hex'] == REQUEST:
            if current is not None:
                chunks.append(current)
            current = [e]
        else:
            require(current is not None, 'unexpected phase prefix')
            current.append(e)
    if current is not None:
        chunks.append(current)
    require(len(chunks) == len(measurement['samples']), 'request/sample count')
    latencies, row_lags, extra_acks = [], [], 0
    for chunk,row in zip(chunks,measurement['samples']):
        require(chunk[-1]['direction'] == 'TX' and chunk[-1]['hex'] == '06', 'response ACK missing')
        rx = chunk[1:-1]
        require(rx and all(e['direction'] == 'RX' for e in rx), 'unexpected TX or trace event')
        raw = b''.join(bytes.fromhex(e['hex']) for e in rx)
        payload, acks = decode_reply(raw)
        require(payload.hex() == row['native_block'], 'wire/sample payload mismatch')
        sample_at = start + row['elapsed_s']
        lag = sample_at - chunk[-1]['t_monotonic']
        require(0 <= lag < 1.0, 'sample timestamp inconsistent with own response')
        require(payload[7] != 255, 'native status FF')
        latencies.append((rx[-1]['t_monotonic'] - chunk[0]['t_monotonic']) * 1000)
        row_lags.append(lag * 1000)
        extra_acks += acks - 1
    # These counts concern the *logged observation*, not independent bus hardware.
    return {'status_requests': len(chunks), 'valid_matching_replies': len(chunks),
            'request_ack_repetitions': extra_acks,
            'host_response_duration_ms': distribution(latencies),
            'response_ack_to_sample_ms': distribution(row_lags),
            'observation_tx_counts': dict(Counter(e['hex'] for e in phase if e['direction']=='TX')),
            'observation_contains_only_fixed_status_reads_and_acks': True,
            'physical_read_or_write_during_observation': False,
            'external_gfa_request_in_logged_observation': False}


def flag_windows(rows, byte_index=5, mask=32):
    windows, begin = [], None
    for i,row in enumerate(rows):
        on = bool(bytes.fromhex(row['native_block'])[byte_index] & mask)
        if on and begin is None:
            begin = i
        if not on and begin is not None:
            prev = rows[begin-1] if begin else None
            first, last = rows[begin], rows[i-1]
            windows.append({'first_on_s':first['elapsed_s'], 'last_on_s':last['elapsed_s'],
                            'first_off_s':row['elapsed_s'],
                            'previous_off_s':prev['elapsed_s'] if prev else None,
                            'on_sample_count':i-begin,
                            'first_on_to_first_off_s':row['elapsed_s']-first['elapsed_s'],
                            'sample_bracket_min_s':last['elapsed_s']-first['elapsed_s'],
                            'sample_bracket_max_s':row['elapsed_s']-prev['elapsed_s'] if prev else None,
                            'b9_at_first_on':bytes.fromhex(first['native_block'])[9],
                            'b9_at_last_on':bytes.fromhex(last['native_block'])[9]})
            begin = None
    if begin is not None:
        windows.append({'first_on_s':rows[begin]['elapsed_s'], 'censored_at_end':True})
    return windows


def audit_session(name, files):
    m = decode(files[name+'/measurement.json'])
    rows = m['samples']
    jl = [decode(line) for line in files[name+'/samples.jsonl'].splitlines() if line.strip()]
    require(rows == jl, 'JSON and JSONL samples differ')
    require(rows and len(rows) <= 10000, 'sample count out of range')
    for i,row in enumerate(rows,1):
        require(row['index']==i and re.fullmatch('[0-9a-f]{22}',row['native_block']), 'invalid sample')
        require(row['native_b7']==row['native_block'][14:16], 'status extraction mismatch')
        require(math.isfinite(row['elapsed_s']), 'nonfinite elapsed time')
    intervals = [b['elapsed_s']-a['elapsed_s'] for a,b in zip(rows,rows[1:])]
    require(intervals and min(intervals)>0, 'sample times not monotonic')
    blocks = [bytes.fromhex(row['native_block']) for row in rows]
    recovery = decode(files[name+'/recovery.json'])
    byte_stats = []
    for index in range(11):
        vals=[b[index] for b in blocks]
        counts=Counter(vals)
        byte_stats.append({'index':index,'distinct':len(counts),'min':min(vals),'max':max(vals),
                           'changes':sum(a!=b for a,b in zip(vals,vals[1:])),
                           'histogram_hex':{f'{k:02x}':v for k,v in sorted(counts.items())}})
    flags=[bool(b[5]&32) for b in blocks]
    edges=[]
    for i,(a,b) in enumerate(zip(blocks,blocks[1:]),1):
        if a[7]!=b[7]:
            edges.append({'index':i+1,'elapsed_s':rows[i]['elapsed_s'],
                          'before':f'{a[7]:02x}','after':f'{b[7]:02x}',
                          'b5':f'{b[5]:02x}','native_block':b.hex()})
    return {'session':name, 'sample_count':len(rows), 'jsonl_equals_measurement':True,
            'recorded_window_s':m['p300_phase_end_monotonic']-m['p300_phase_start_monotonic'],
            'reference_gfa':m['reference_gfa'],'recovery_gfa':m['recovery_gfa'],
            'sample_interval_s':distribution(intervals),'wire_audit':audit_trace(m),
            'byte_statistics':byte_stats,'b5_equals_b10_every_sample':all(b[5]==b[10] for b in blocks),
            'flame_bit_on_samples':sum(flags),'lockout_bit_on_samples':sum(bool(b[5]&64) for b in blocks),
            'flame_bit_windows':flag_windows(rows),'status_changes':edges,
            'b0_nonzero_while_flame_off_samples':sum(b[0]!=0 and not f for b,f in zip(blocks,flags)),
            'b9_nonzero_while_flame_off_samples':sum(b[9]!=0 and not f for b,f in zip(blocks,flags)),
            'b0_b9_pairs_decimal':sorted(set((b[0],b[9]) for b in blocks)),
            'observation_complete':m['observation_complete'],'measurement_errors':m['errors'],
            'vs1_link_restored':m['vs1_link_restored'],'service_recovery':recovery,
            'source_members':{filename:{'sha256':hashlib.sha256(files[name+'/'+filename]).hexdigest(),
                                       'bytes':len(files[name+'/'+filename])}
                              for filename in ('measurement.json','samples.jsonl','recovery.json')}}


def audit(path):
    files, sessions = read_archive(path)
    return {'schema_version':1,'offline_only':True,'archive_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'archive_bytes':path.stat().st_size,'sessions':[audit_session(s,files) for s in sessions],
            'interpretation_limits':['Host software trace, not independent logic-analyzer capture.',
              '11 virtual bytes only, not a RAM dump.',
              'P06/P09 references before/after, not simultaneous series.',
              'Flame and lockout masks inherited from project, not independently proven here.',
              'No new units or sensor semantics inferred from correlation.']}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=audit(args.archive)
    with args.output.open('x',encoding='utf-8') as f:
        json.dump(result,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
    print('OFFLINE_AUDIT_OK samples='+str(sum(s['sample_count'] for s in result['sessions'])))
