#!/usr/bin/env python3
"""Offline-only screen of VDensHO1 20C2 P06 against all 11 bytes of 55D3.

Consumes existing user-provided JSONL/JSON. No Optolink, MQTT, serial, RAM,
network, firmware or heater writes. A correlation is never an RPM alias.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

MAX_SIZE = 6_000_000
READ_ORDER = ['p06', 'p09', 'native_status', 'p09', 'p06']
KNOWN = {0: 'control_drive', 5: 'flags', 6: 'status_aux',
         7: 'P87_status_candidate', 9: 'modulation_control', 10: 'flags'}


def read_bytes(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_SIZE:
        raise ValueError('missing, symlink or oversized file: ' + str(path))
    return path.read_bytes()


def audit(pairs, summary):
    pair_bytes, sum_bytes = read_bytes(pairs), read_bytes(summary)
    rows = [json.loads(s) for s in pair_bytes.splitlines() if s.strip()]
    obj = json.loads(sum_bytes)
    if not rows or obj.get('rounds') != rows or len(rows) != obj['comparison']['sample_count']:
        raise ValueError('rounds are incomplete or disagree with summary')
    if obj.get('errors') or any(obj.get(k) is not False for k in
            ('protocol_switched', 'services_stopped', 'device_writes')):
        raise ValueError('not a successful VS1-only, read-only recording')
    opening = obj['opening']
    if (opening['device']['raw'] != '20c2' or
            opening['software']['raw'] != '0103' or
            opening['p80']['raw'] != '20' or obj['closing_p80']['raw'] != '20'):
        raise ValueError('unexpected device, firmware, or GFA type')
    byte_samples = [[] for _ in range(11)]
    off_nonzero = [0]*11
    verdicts = {'p06': Counter(), 'p09': Counter()}
    nonzero_p06 = Counter()
    flame_count = 0
    changed_indices = []
    different_stable = []
    selected = {}
    for i, row in enumerate(rows, 1):
        if row['index'] != i or [r['name'] for r in row['reads']] != READ_ORDER:
            raise ValueError('unexpected index or read order')
        block = bytes.fromhex(row['native_block'])
        if len(block) != 11 or row['reads'][2]['raw'] != row['native_block']:
            raise ValueError('invalid eleven-byte status block')
        if (row['native_b0'] != block[0] or row['native_b9'] != block[9] or
                row['native_b7'].lower() != f'{block[7]:02x}' or
                row['flame_bit'] != bool(block[5] & 0x20) or
                row['lockout_bit'] != bool(block[5] & 0x40)):
            raise ValueError('native fields do not match the source bytes')
        flame_count += bool(row['flame_bit'])
        for j, b in enumerate(block):
            byte_samples[j].append(b)
            if row['p06']['verdict'] == 'STABLE_REFERENCE' and row['p06']['before'] == '00' and b:
                off_nonzero[j] += 1
        for name, before, after in [('p06', 0, 4), ('p09', 1, 3)]:
            ref = row[name]
            left, right = row['reads'][before], row['reads'][after]
            if ref['before'] != left['raw'] or ref['after'] != right['raw']:
                raise ValueError('GFA reference disagrees with source read')
            if len(bytes.fromhex(ref['before'])) != 1 or len(bytes.fromhex(ref['after'])) != 1:
                raise ValueError('reference byte length is wrong')
            if left['received'] >= right['received'] or abs(ref['bracket_ms'] -
                    1000 * (right['received']-left['received'])) > 2:
                raise ValueError('GFA bracket timing inconsistent')
            if ref['verdict'] not in ('STABLE_REFERENCE', 'REFERENCE_CHANGED', 'BRACKET_TOO_WIDE'):
                raise ValueError('unknown GFA bracket verdict')
            if ref['verdict'] == 'STABLE_REFERENCE' and (ref['before'] != ref['after'] or
                                                       ref['bracket_ms'] > 2000):
                raise ValueError('invalid stable reference')
            if ref['verdict'] == 'REFERENCE_CHANGED' and ref['before'] == ref['after']:
                raise ValueError('invalid changed reference')
            verdicts[name][ref['verdict']] += 1
        if row['p06']['verdict'] == 'REFERENCE_CHANGED':
            changed_indices.append(i)
        if row['p06']['verdict'] == 'STABLE_REFERENCE' and row['p06']['before'] != '00':
            nonzero_p06[row['p06']['before']] += 1
        if (row['p06']['verdict'] == row['p09']['verdict'] == 'STABLE_REFERENCE'
                and row['p06']['before'] != row['p09']['before']):
            different_stable.append(i)
        if i in (110,111,112,114,116,122,135,136,137):
            selected[str(i)] = {'flame': row['flame_bit'],
                'p06_before':row['p06']['before'], 'p06_after':row['p06']['after'],
                'p09_before':row['p09']['before'], 'native_b0':block[0],
                'native_b9':block[9], 'native_b7':f'{block[7]:02x}'}
    if any(dict(verdicts[n]) != obj['comparison'][n]['counts'] for n in verdicts):
        raise ValueError('verdict counts disagree with summary')
    if len(different_stable) != obj['comparison']['stable_p06_p09_separation_count']:
        raise ValueError('P06/P09 separation counts disagree with summary')
    if obj['comparison'].get('production_alias_verified') or obj['comparison'].get('measured_vs_commanded_source_identified'):
        raise ValueError('source marked an unverified conversion as proven')
    return {
        'schema_version': 1,
        'input_sha256': {
            'pairs.jsonl':hashlib.sha256(pair_bytes).hexdigest(),
            'summary.json':hashlib.sha256(sum_bytes).hexdigest()},
        'device':'VDensHO1 20C2 firmware 0103 GFA P80 20',
        'sample_count':len(rows), 'flame_samples':flame_count,
        'p06_verdicts':dict(verdicts['p06']), 'p09_verdicts':dict(verdicts['p09']),
        'stable_nonzero_p06_values':dict(sorted(nonzero_p06.items())),
        'changed_p06_indices':changed_indices, 'stable_p06_p09_differences':different_stable,
        'bytes':[{'index':i, 'distinct':len(set(v)), 'min':min(v), 'max':max(v),
                  'nonzero_when_p06_stably_zero':off_nonzero[i],
                  'known_type':KNOWN.get(i,'unlabelled'),
                  'validated_independent_fan_actual':False}
                 for i,v in enumerate(byte_samples)],
        'anchor_rounds':selected, 'found_production_p06_alias':False,
        'p300_production_approved':False, 'ram_write_approved':False,
        'not_an_exhaustive_undocumented_ram_search':True
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('pairs'); p.add_argument('summary'); p.add_argument('--output')
    args=p.parse_args()
    result=audit(args.pairs, args.summary)
    if args.output:
        target=Path(args.output)
        with target.open('x') as f:
            json.dump(result,f,indent=2,sort_keys=True)
            f.write('\n')
    print('FAN_SOURCE_AUDIT_PASS samples=%d flame=%d P06_changed=%d alias=NONE' %
          (result['sample_count'],result['flame_samples'],
           result['p06_verdicts'].get('REFERENCE_CHANGED',0)))


if __name__ == '__main__':
    main()
