#!/usr/bin/env python3
"""Read-only offline validation of paired WB2A VS1 P06/P09 and 55D3 samples.

Never opens network or serial ports; never fits a conversion or promotes an alias.
The raw input files belong to the user and are not copied into the public repo.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path


def read_json(path):
    data = Path(path).read_bytes()
    if len(data) > 6_000_000:
        raise ValueError('Input exceeds 6MB')
    return json.loads(data), hashlib.sha256(data).hexdigest()


def validate(pairs_path, summary_path):
    pair_bytes = Path(pairs_path).read_bytes()
    if len(pair_bytes) > 6_000_000:
        raise ValueError('Pairs file exceeds 6MB')
    rounds = [json.loads(line) for line in pair_bytes.splitlines() if line.strip()]
    summary, summary_sha = read_json(summary_path)
    if not rounds or summary.get('rounds') != rounds:
        raise ValueError('Full JSONL rounds differ from summary.json or are empty')
    if summary.get('errors') or summary.get('device_writes') is not False or summary.get('protocol_switched') is not False or summary.get('services_stopped') is not False:
        raise ValueError('Expected error-free VS1 MQTT-only observation')
    if summary['comparison']['sample_count'] != len(rounds):
        raise ValueError('Sample count differs')
    if (summary['opening']['device']['raw'] != '20c2'
            or summary['opening']['software']['raw'] != '0103'
            or summary['opening']['p80']['raw'] != '20'
            or summary['closing_p80']['raw'] != '20'):
        raise ValueError('Unverified 20C2/0103 GFA P80 identity')

    counts = collections.defaultdict(collections.Counter)
    p06_stable_states = set()
    p09_stable_states = set()
    flame_indices = []
    stable_differences = []
    snapshots = []
    first_native_rx = rounds[0]['reads'][2]['received']
    selected = {110, 111, 112, 114, 116, 120, 122, 135, 136, 137}

    for n, row in enumerate(rounds, start=1):
        if row['index'] != n:
            raise ValueError('Round indices are not sequential')
        block = bytes.fromhex(row['native_block'])
        if len(block) != 11:
            raise ValueError('Invalid native status length')
        if (row['native_b0'] != block[0] or row['native_b9'] != block[9]
                or row['native_b7'].lower() != f'{block[7]:02x}'
                or row['flame_bit'] is not bool(block[5] & 0x20)
                or row['lockout_bit'] is not bool(block[5] & 0x40)):
            raise ValueError('Decoded native fields contradict raw status')
        reads = row['reads']
        if [x['name'] for x in reads] != ['p06', 'p09', 'native_status', 'p09', 'p06']:
            raise ValueError('Unexpected read order')
        if reads[2]['raw'] != row['native_block']:
            raise ValueError('Native read differs from payload')
        for i, read in enumerate(reads):
            if read['received'] < read['sent'] or (i and read['sent'] < reads[i-1]['received']):
                raise ValueError('Overlapping or reversed host timestamps')
        for name, left, right in [('p06', reads[0], reads[4]), ('p09', reads[1], reads[3])]:
            record = row[name]
            if abs(record['bracket_ms'] - (right['received'] - left['received']) * 1000) > 2:
                raise ValueError(f'{name} incorrect bracket timing')
            if record['before'] != left['raw'] or record['after'] != right['raw']:
                raise ValueError(f'{name} bracket differs from reads')
            before, after = bytes.fromhex(record['before']), bytes.fromhex(record['after'])
            if len(before) != 1 or len(after) != 1:
                raise ValueError('Unexpected GFA raw length')
            if record['verdict'] not in ('STABLE_REFERENCE', 'REFERENCE_CHANGED', 'BRACKET_TOO_WIDE'):
                raise ValueError('Unexpected bracket verdict')
            counts[name][record['verdict']] += 1
            if record['verdict'] == 'STABLE_REFERENCE':
                if before != after or record['bracket_ms'] > 2000:
                    raise ValueError('False stable bracket verdict')
                if before != b'\x00':
                    (p06_stable_states if name == 'p06' else p09_stable_states).add(record['before'].lower())
            elif record['verdict'] == 'REFERENCE_CHANGED' and before == after:
                raise ValueError('False changed bracket verdict')
        if row['flame_bit']:
            flame_indices.append(n)
        differing = (row['p06']['verdict'] == 'STABLE_REFERENCE'
                     and row['p09']['verdict'] == 'STABLE_REFERENCE'
                     and row['p06']['before'] != row['p09']['before'])
        if bool(row.get('stable_raw_p06_p09_differ')) != differing:
            raise ValueError('Inconsistent P06/P09 separation flag')
        if differing:
            stable_differences.append(n)
        if n in selected:
            snapshots.append({
                'round': n, 'elapsed_s': round(reads[2]['received']-first_native_rx, 3),
                'flame_bit': row['flame_bit'], 'p06_before': row['p06']['before'],
                'p06_after': row['p06']['after'], 'p09': row['p09']['before'],
                'native_b0': block[0], 'native_b9': block[9], 'native_b7': f'{block[7]:02x}'
            })

    for name in ('p06', 'p09'):
        if dict(counts[name]) != summary['comparison'][name]['counts']:
            raise ValueError(f'{name} verdict count inconsistent with summary')
    if len(stable_differences) != summary['comparison']['stable_p06_p09_separation_count']:
        raise ValueError('P06/P09 separation count inconsistent with summary')
    if summary['comparison']['production_alias_verified'] or summary['comparison']['measured_vs_commanded_source_identified']:
        raise ValueError('Unexpectedly preapproved sensor alias')

    windows = []
    for index in flame_indices:
        if not windows or index > windows[-1]['last_flame_round'] + 1:
            windows.append({'first_flame_round': index, 'last_flame_round': index})
        else:
            windows[-1]['last_flame_round'] = index
    for w in windows:
        w['first_nonflame_after_round'] = w['last_flame_round']+1 if w['last_flame_round'] < len(rounds) else None
    return {
        'schema_version': 1,
        'input_sha256': {'pairs.jsonl': hashlib.sha256(pair_bytes).hexdigest(), 'summary.json': summary_sha},
        'rounds_verified': len(rounds), 'summary_matches_jsonl': True,
        'time_utc': [rounds[0]['utc'], rounds[-1]['utc']],
        'protocol_switched': False, 'device_writes': False, 'services_stopped': False,
        'observation_outcome': summary['comparison']['outcome'],
        'flame_samples': len(flame_indices), 'flame_windows': windows,
        'p06_verdicts': dict(counts['p06']), 'p09_verdicts': dict(counts['p09']),
        'p06_stable_nonzero_states': sorted(p06_stable_states),
        'p09_stable_nonzero_states': sorted(p09_stable_states),
        'stable_p06_p09_differences_at_rounds': stable_differences,
        'snapshots': snapshots,
        'p06_alias_verified': False, 'p09_alias_verified': False,
        'notes': ['Host-sequential reads are not simultaneous; no exact sensor latency inferred.',
                  'GFA P06 raw uses the locally documented x30 rpm; P09 uses its own documented scaling.',
                  'Native byte 9 is previously identified modulation, not independently verified P06 rpm.',
                  'No conversion fitted from this single natural burner phase.']
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pairs', help='pairs.jsonl from the existing VS1 observer')
    parser.add_argument('summary', help='summary.json from that same session')
    parser.add_argument('--output', help='Write derived evidence; never copies raw rounds')
    args = parser.parse_args()
    result = validate(args.pairs, args.summary)
    encoded = json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + '\n'
    if args.output:
        output = Path(args.output)
        if output.exists():
            raise SystemExit('Refusing to overwrite output file')
        output.write_text(encoded)
    print(f"AUDIT_PASS rounds={result['rounds_verified']} flame_samples={result['flame_samples']} P06_changed={result['p06_verdicts'].get('REFERENCE_CHANGED', 0)}")
    if args.output:
        print(f'REPORT={args.output}')


if __name__ == '__main__':
    main()
