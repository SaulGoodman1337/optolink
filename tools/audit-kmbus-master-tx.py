#!/usr/bin/env python3
"""Classify KM-Bus master TX frames from an EXISTING WB2A P300 overnight bundle.

Offline only. Uses the vetted local archive validator, not a serial client.
A CRC-valid RAM snapshot is *not* necessarily a distinct bus transmission.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OFFLINE_AUDITOR = HERE / 'audit-uart1-overnight-bundle.py'
BASE = 0x1600
KM_START = 0x161A - BASE
CAVEAT = ('These are non-atomic, approximately 2.5s-spaced RAM snapshots, '
          'not a UART1 RX trace and not a count of on-wire telegrams.')


def load_legacy_auditor():
    spec = importlib.util.spec_from_file_location('wb2a_overnight_bundle', OFFLINE_AUDITOR)
    if spec is None or spec.loader is None:
        raise RuntimeError('required offline bundle auditor missing')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_tx_bytes(ram: bytes, kermit_fn):
    """Return the visible candidate frame and a CRC gate; never repair torn RAM."""
    if len(ram) != 64:
        raise ValueError('expected exactly 64 physical RAM bytes')
    buffer = ram[KM_START:]
    length = buffer[3]
    if length < 8 or length > len(buffer):
        return None
    frame = buffer[:length]
    return dict(frame=frame, dest=frame[0], source=frame[1], command=frame[2],
                length=frame[3], slot=frame[4], subclass=frame[5],
                payload=frame[6:-2], crc_valid=(kermit_fn(frame) == 0))


def label_for_fields(dest, source, command, slot, payload, crc_valid):
    """Only model-family-supported *purpose*, not physical counterparty presence."""
    if not crc_valid:
        return 'UNVERIFIED_CRC_RAM_VIEW'
    if (source == 0x00 and command == 0x33 and dest == 0x11 and
            slot in (1, 2) and payload == bytes.fromhex('f804')):
        return 'VITOTROL_IDENTITY_QUERY'
    if (dest == 0x20 and source == 0x00 and slot == 0xEE and command == 0xB3):
        return 'OLDER_KW2_CLASS20_SLOT_EE_MATCH_NO_LOCAL_DEVICE_ID'
    if dest == 0xFF and source == 0x00 and command == 0xB3 and slot == 0x00:
        return 'MASTER_BROADCAST_DATA'
    if dest == 0x01 and source == 0x00:
        return 'MASTER_CLASS01_TARGET_UNKNOWN'
    if dest == 0x04 and source == 0x00 and command == 0x33:
        return 'CLASS04_IDENTITY_QUERY_HISTORICAL_EXTENSION'
    return 'UNCLASSIFIED_SOURCE_FORMATTED_TX'


def classify_samples(samples, kermit_fn):
    groups = {}
    total_valid = 0
    malformed = 0
    last_utc = None
    for expected_index, sample in enumerate(samples, start=1):
        if sample.get('index') != expected_index:
            raise ValueError('sample indices must be contiguous from one')
        stamp = datetime.fromisoformat(sample['utc'])
        if last_utc is not None and stamp <= last_utc:
            raise ValueError('non-monotonic timestamps')
        last_utc = stamp
        data = bytes.fromhex(sample['ram_1600'] + sample['ram_1620'])
        item = parse_tx_bytes(data, kermit_fn)
        if item is None:
            malformed += 1
            continue
        key = tuple(item[k] for k in ('dest','source','command','length','slot','subclass'))
        if key not in groups:
            groups[key] = dict(
                snapshot_count=0, crc_valid_samples=0,
                crc_invalid_samples=0, valid_snapshot_episodes=0,
                last_crc_valid_index=None, flame_valid_samples=0,
                lockout_valid_samples=0, distinct_valid_frames=Counter(),
                first_valid_sample=None, last_valid_sample=None,
                labels=Counter(), register_pairs=Counter())
        g = groups[key]
        g['snapshot_count'] += 1
        if item['crc_valid']:
            total_valid += 1
            g['crc_valid_samples'] += 1
            if g['last_crc_valid_index'] != expected_index - 1:
                g['valid_snapshot_episodes'] += 1
            g['last_crc_valid_index'] = expected_index
            g['distinct_valid_frames'][item['frame'].hex()] += 1
            g['first_valid_sample'] = g['first_valid_sample'] or sample['utc']
            g['last_valid_sample'] = sample['utc']
            flame_state = bytes.fromhex(sample['native_block'])[5]
            g['flame_valid_samples'] += bool(flame_state & 0x20)
            g['lockout_valid_samples'] += bool(flame_state & 0x40)
            if item['command'] in (0xB1,0xB3) and len(item['payload']) % 2 == 0:
                pairs = item['payload']
                for addr,value in zip(pairs[::2],pairs[1::2]):
                    g['register_pairs'][f'{addr:02x}={value:02x}'] += 1
        else:
            g['crc_invalid_samples'] += 1
        g['labels'][label_for_fields(item['dest'],item['source'],item['command'],
                                     item['slot'],item['payload'],item['crc_valid'])] += 1
    report_groups = []
    for key in sorted(groups):
        g=groups[key]
        head=''.join(f'{byte:02x}' for byte in key)
        label = (g['labels'].most_common(1)[0][0] if g['crc_valid_samples'] == 0
                 else next((x for x,n in g['labels'].most_common()
                            if x!='UNVERIFIED_CRC_RAM_VIEW'),'UNCLASSIFIED'))
        report_groups.append(dict(
            header_hex=head,destination_class=f'0x{key[0]:02x}',
            source_class=f'0x{key[1]:02x}',command=f'0x{key[2]:02x}',
            frame_length=key[3],target_slot=f'0x{key[4]:02x}',
            subclass=f'0x{key[5]:02x}',purpose=label,
            snapshot_count=g['snapshot_count'],crc_valid_samples=g['crc_valid_samples'],
            crc_invalid_samples=g['crc_invalid_samples'],
            distinct_valid_frame_contents=len(g['distinct_valid_frames']),
            valid_snapshot_episodes=g['valid_snapshot_episodes'],
            first_valid_sample_utc=g['first_valid_sample'],
            last_valid_sample_utc=g['last_valid_sample'],
            valid_samples_during_flame=g['flame_valid_samples'],
            valid_samples_during_lockout=g['lockout_valid_samples'],
            most_common_valid_frame=g['distinct_valid_frames'].most_common(1)[0][0]
                if g['distinct_valid_frames'] else None,
            register_pairs_when_crc_valid=dict(g['register_pairs'].most_common(8))
        ))
    remote=[g for g in report_groups if g['purpose']=='VITOTROL_IDENTITY_QUERY']
    return {
        'schema_version':1, 'sample_count':len(samples), 'crc_valid_ram_snapshots':total_valid,
        'crc_invalid_or_bad_length_snapshots':len(samples)-total_valid,
        'invalid_frame_lengths':malformed,
        'header_groups':report_groups,
        'vitotrol_identity_query_destinations':[g['target_slot'] for g in remote],
        'vitotrol_identity_query_crc_valid_snapshots':sum(g['crc_valid_samples'] for g in remote),
        'vitotrol_identity_query_snapshot_episodes':sum(g['valid_snapshot_episodes'] for g in remote),
        'observed_class_0x11_tx':bool(remote),
        'gfa_p06_tachometer_alias_verified':False,
        'uart1_slave_responses_or_rx_verified':False,
        'installed_vitotrol_verified':False,
        'any_new_hardware_access_performed':False,
        'ram_write_or_thermostat_emulation_authorized':False,
        'source_scope':('The public OpenV KM-Bus class/slot table was derived from V200KW2, '
                        'and does not establish the same model-specific participant identity on 20C2.'),
        'sampling_caveat':CAVEAT
    }


def process_bundle(path):
    legacy=load_legacy_auditor()
    raw=legacy.read_bundle(path)
    samples=[json.loads(l) for l in raw['samples.jsonl'].splitlines() if l.strip()]
    records=[json.loads(l) for l in raw['trace.jsonl'].splitlines() if l.strip()]
    measurement=json.loads(raw['measurement.json'])
    if len(samples)!=measurement['sample_count']:
        raise ValueError('night archive metadata does not agree with samples')
    legacy.verify_wire(records,samples)
    report=classify_samples(samples,legacy.kermit)
    report['input_bundle_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('existing_bundle', type=Path, nargs='?')
    p.add_argument('--output',type=Path)
    args=p.parse_args()
    if args.existing_bundle is None:
        print('PLAN ONLY: offline class/slot/CRC analysis of a previously saved archive')
        return
    report=process_bundle(args.existing_bundle)
    print('KMBUS_TX_CLASSIFY_PASS samples=%d crc_valid=%d vitotrol_F8_04_snapshots=%d' %
          (report['sample_count'],report['crc_valid_ram_snapshots'],
           report['vitotrol_identity_query_crc_valid_snapshots']))
    if args.output:
        with args.output.open('x',encoding='utf-8') as stream:
            json.dump(report,stream,indent=2,sort_keys=True,ensure_ascii=False)
            stream.write('\n')


if __name__ == '__main__':main()
