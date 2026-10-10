#!/usr/bin/env python3
"""Offline audit of saved WB2A P300 UART1 overnight archives. NEVER contacts boiler.

Reads the original tar.gz in memory without extraction, checks manifest digests,
compares four raw response frames per sample, and identifies KM-Bus TX frames
with CRC16/Kermit and observed BCD date/time fields. Does not approve a P06
tachometer alias, any new live RAM read, or production migration.
"""
from __future__ import annotations
import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
from pathlib import Path
import statistics
import tarfile

MEMBER_PREFIX = 'uart1-overnight/'
REQUIRED = {'state.json', 'progress.json', 'samples.jsonl', 'trace.jsonl',
            'measurement.json', 'recovery.json', 'health.json', 'bundle-manifest.json'}
FRAMES = (
    ('4105000155d30b39', 1, 0x55D3, 11, 'native_block'),
    ('4105000300201038', 3, 0x0020, 16, 'dma0_0020'),
    ('410500031600203e', 3, 0x1600, 32, 'ram_1600'),
    ('410500031620205e', 3, 0x1620, 32, 'ram_1620'),
)
MAX_ARCHIVE = 100_000_000
MAX_MEMBER = 35_000_000
KM_START = 0x161A - 0x1600
TZ = dt.timezone(dt.timedelta(hours=2))


def kermit(data: bytes) -> int:
    result = 0
    for x in data:
        result ^= x
        for _ in range(8):
            result = ((result >> 1) ^ 0x8408) if (result & 1) else (result >> 1)
    return result


def bcd(raw: int) -> int:
    if raw >> 4 > 9 or raw & 15 > 9:
        raise ValueError('invalid packed BCD clock field')
    return (raw >> 4) * 10 + (raw & 15)


def read_bundle(path: Path):
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_ARCHIVE:
        raise ValueError('not a regular allowed-size archive')
    with tarfile.open(path, 'r:gz') as tar:
        members = tar.getmembers()
        if len(members) != 8 or any(
                not m.isfile() or not m.name.startswith(MEMBER_PREFIX) or
                m.name[len(MEMBER_PREFIX):] not in REQUIRED or
                m.size < 0 or m.size > MAX_MEMBER for m in members):
            raise ValueError('unexpected archive member or type')
        if len({m.name for m in members}) != 8:
            raise ValueError('duplicate archive entry')
        source = {m.name[len(MEMBER_PREFIX):]:tar.extractfile(m).read() for m in members}
    if set(source) != REQUIRED:
        raise ValueError('missing or extra archive entry')
    manifest = json.loads(source['bundle-manifest.json'])
    if set(manifest['files']) != REQUIRED - {'bundle-manifest.json'}:
        raise ValueError('incorrect manifest')
    for name, row in manifest['files'].items():
        if (len(source[name]) != row['size_bytes'] or
                hashlib.sha256(source[name]).hexdigest() != row['sha256']):
            raise ValueError('source archive manifest digest mismatch: '+name)
    return source


def group_windows(samples, mask):
    starts = []
    active = False
    for index, s in enumerate(samples):
        status = bytes.fromhex(s['native_block'])[5]
        enabled = bool(status & mask)
        if enabled and not active:
            starts.append([index + 1, index + 1])
        if enabled:
            starts[-1][1] = index + 1
        active = enabled
    out = []
    for lo, hi in starts:
        first = dt.datetime.fromisoformat(samples[lo-1]['utc']).astimezone(TZ)
        last = dt.datetime.fromisoformat(samples[hi-1]['utc']).astimezone(TZ)
        out.append({'rounds':[lo, hi], 'samples':hi-lo+1,
                    'start_local':first.isoformat(), 'end_local':last.isoformat(),
                    'span_s':round((last-first).total_seconds(), 3)})
    return out


def verify_wire(records, samples):
    n=len(samples)
    if len(records) != 24 + n*12 + 14:
        raise ValueError('incomplete or extra TX/RX trace records')
    expected={a for a,*_ in FRAMES}
    known_handshakes={'04','06','160000','01f700f802','f7778c02',
                      '6b405001','6b400601','6b400901','6b405701',
                      '4105000100f80200','41050001778c020b'}
    if any(x['hex'] not in expected | known_handshakes for x in records
           if x['direction']=='TX'):
        raise ValueError('unexpected TX command in trace')
    count=Counter()
    for i, sample in enumerate(samples):
        if sample['index'] != i+1:
            raise ValueError('noncontiguous sample numbers')
        raw={key:bytes.fromhex(sample[key]) for _,_,_,_,key in FRAMES}
        for k, (request, function, address, length, key) in enumerate(FRAMES):
            tx, rx, ack=records[24+12*i+3*k:24+12*i+3*k+3]
            if [tx['direction'],rx['direction'],ack['direction']] != ['TX','RX','TX']:
                raise ValueError('wrong TX/RX ordering')
            if tx['hex'] != request or ack['hex'] != '06':
                raise ValueError('unexpected TX or missing acknowledgement')
            data=bytes.fromhex(rx['hex'])
            if (len(data) != length+9 or data[:3] != bytes([6,65,5+length])):
                raise ValueError('bad RX frame header or length')
            body=data[3:]
            if (body[0] != 1 or body[1] != function or
                    int.from_bytes(body[2:4], 'big') != address or
                    body[4] != length or body[5:-1] != raw[key] or
                    (data[2]+sum(body[:-1]))%256 != body[-1]):
                raise ValueError('bad RX frame payload, function or checksum')
            if not (tx['t_monotonic'] < rx['t_monotonic'] < ack['t_monotonic']):
                raise ValueError('nonmonotonic serial timestamps')
            count[request]+=1
    for request in expected:
        if count[request] != n:
            raise ValueError('missing allowed read request')
    return dict(count)


def audit(archive: Path):
    source = read_bundle(archive)
    samples=[json.loads(x) for x in source['samples.jsonl'].splitlines() if x.strip()]
    records=[json.loads(x) for x in source['trace.jsonl'].splitlines() if x.strip()]
    meta=json.loads(source['measurement.json'])
    recovery=json.loads(source['recovery.json'])
    health=json.loads(source['health.json'])
    if (not samples or len(samples)!=meta['sample_count'] or
            meta['comparison']['sample_count']!=len(samples) or
            meta['trace_record_count']!=len(records)):
        raise ValueError('sample/measurement count mismatch')
    if (meta['errors'] or not meta['observation_complete'] or
            not meta['operator_stop'] or not meta['vs1_link_restored'] or
            not recovery['services_restored'] or
            not health['production_main_verified']):
        raise ValueError('observation/restore gates not passed')
    for name in ('P80','P06'):
        if not health['gfa_reads'][name]['format_and_identity_verified']:
            raise ValueError('fresh GFA identity/readback not verified')
    checked_tx=verify_wire(records,samples)
    ram_prev=None
    changed=Counter()
    headers=Counter()
    crc_ok=Counter()
    crc_mismatch=Counter()
    time_changes=[]
    source_counts=Counter()
    endpoints=Counter()
    last_time=None
    for sample in samples:
        stamp=dt.datetime.fromisoformat(sample['utc'])
        if last_time is not None and stamp <= last_time:
            raise ValueError('out-of-order samples')
        last_time=stamp
        raw=bytes.fromhex(sample['native_block'])
        dma=bytes.fromhex(sample['dma0_0020'])
        ram=bytes.fromhex(sample['ram_1600'])+bytes.fromhex(sample['ram_1620'])
        if len(raw)!=11 or len(dma)!=16 or len(ram)!=64:
            raise ValueError('unreviewed field length')
        if sample['flame_bit']!=bool(raw[5]&0x20) or sample['native_b7']!=f'{raw[7]:02x}':
            raise ValueError('invalid native status decode')
        sourceptr=int.from_bytes(dma[:3],'little')&0xfffff
        dest=int.from_bytes(dma[4:7],'little')&0xfffff
        tcr=int.from_bytes(dma[8:10],'little')
        if (f'0x{sourceptr:05x}' != sample['dma0_source'] or
                f'0x{dest:05x}' != sample['dma0_target'] or
                sample['dma0_tcr'] != tcr or
                sample['dma0_control'] != dma[12] or dest != 0x03aa):
            raise ValueError('invalid DMA0 decode')
        source_counts[f'0x{sourceptr:05x}']+=1
        endpoints[f'0x{sourceptr+tcr:05x}']+=1
        body=ram[KM_START:]
        length=body[3]
        if not 8 <= length <= len(body):
            raise ValueError('invalid KM-Bus TX length')
        frame=body[:length]
        code=frame[:4].hex()
        headers[code]+=1
        (crc_ok if kermit(frame)==0 else crc_mismatch)[code]+=1
        if ram_prev is not None:
            for i,(a,b) in enumerate(zip(ram_prev,ram)):
                if a!=b:
                    changed[f'0x{0x1600+i:04x}']+=1
            indices=(0x1627,0x1629,0x162b,0x162d)
            if any(ram[x-0x1600]!=ram_prev[x-0x1600] for x in indices):
                d,h,m,s=(bcd(ram[x-0x1600]) for x in indices)
                now=stamp.astimezone(TZ)
                decoded=dt.datetime(now.year,now.month,d,h,m,s,tzinfo=TZ)
                time_changes.append({'round':sample['index'],
                                     'host_local':now.isoformat(),
                                     'decoded_local':decoded.isoformat(),
                                     'lag_s':round((now-decoded).total_seconds(),3)})
        ram_prev=ram
    if changed != meta['comparison']['changed_ram_addresses']:
        raise ValueError('RAM transitions differ from measurement summary')
    if dict(source_counts)!=meta['comparison']['dma0_source_counts']:
        raise ValueError('DMA source counts differ from measurement summary')
    if len(time_changes) < 2:
        raise ValueError('no source-backed changing clock for this archive')
    lags=[x['lag_s'] for x in time_changes]
    if not all(0 <= lag < 10 for lag in lags):
        raise ValueError('KM-Bus timestamp relation not supported')
    return {
        'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
        'samples':len(samples), 'trace_records':len(records),
        'checked_p300_requests':checked_tx,
        'frames_crc_valid':sum(crc_ok.values()),
        'frames_crc_mismatch':sum(crc_mismatch.values()),
        'kmbus_header_counts':dict(headers),
        'crc_valid_by_header':dict(crc_ok),
        'dma0_sources':dict(source_counts),
        'dma0_endpoints':dict(endpoints),
        'changed_ram_bytes':len(changed),
        'flame_windows':group_windows(samples,0x20),
        'lockout_windows':group_windows(samples,0x40),
        'kmbus_clock_updates':len(time_changes),
        'kmbus_clock_lag_min_s':min(lags),
        'kmbus_clock_lag_median_s':round(statistics.median(lags),3),
        'kmbus_clock_lag_max_s':max(lags),
        'lockout_cause_identified':False,
        'uart1_rx_measured':False,
        'p06_rpm_alias_verified':False,
        'production_migration_approved':False,
        'device_writes_approved':False,
        'new_hardware_access_performed':False
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('bundle',nargs='?',type=Path)
    p.add_argument('--output',type=Path)
    args=p.parse_args()
    if args.bundle is None:
        print('PLAN ONLY: provide saved overnight bundle; offline archive analysis only.')
        return
    result=audit(args.bundle)
    print('OVERNIGHT_AUDIT_PASS samples=%s p300_reads=%s km_crc_valid=%s clock_updates=%s' %
          (result['samples'],sum(result['checked_p300_requests'].values()),
           result['frames_crc_valid'],result['kmbus_clock_updates']))
    if args.output:
        if args.output.is_symlink():
            raise ValueError('output path is a symlink')
        with args.output.open('x') as out:
            json.dump(result,out,indent=2,sort_keys=True)
            out.write('\n')


if __name__ == '__main__':
    main()
