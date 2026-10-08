#!/usr/bin/env python3
"""Offline read-only differential audit of previously saved WB2A physical RAM passes.

Does not import serial/MQTT or connect to the appliance. The single historical
DMA0 source value 0x161B is an *interface clue*, NOT a verified GFA/RPM source.
Only data already captured by tools/physical-ram-snapshot.py are considered.
"""
import argparse
import hashlib
import json
from pathlib import Path
import stat

BASE = 0x0400
END = 0x53FF
SIZE = END - BASE + 1
CHUNK = 32
DMA0_SAR0_OBSERVED = 0x161B
DMA0_TCR0_OBSERVED = 0x0008
FOCUS_START = 0x15E0
FOCUS_END = 0x165F
SOURCE_CONTEXT_START = 0x1600
SOURCE_CONTEXT_END = 0x163F
# All these are already explained by the local *Optolink* request/response
# implementation and must not be promoted as GFA telemetry based on changes.
OPTO_EXCLUSION = [
    (0x192C, 0x1952, 'P300 parser request / payload scratch'),
    (0x196C, 0x19AB, 'P300 received request workspace'),
    (0x19AE, 0x19ED, 'P300 outgoing response workspace'),
    (0x19EE, 0x1A6D, 'P300 Optolink communication ring'),
]
MAX_METADATA = 1_000_000


def regular_file_bytes(path: Path, max_bytes: int) -> bytes:
    path = Path(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
        raise ValueError('not a regular, permitted-size file: ' + str(path))
    data = path.read_bytes()
    if len(data) > max_bytes:
        raise ValueError('file grew unexpectedly: ' + str(path))
    return data


def load_capture(report: Path | None = None, pass1: Path | None = None,
                 pass2: Path | None = None) -> tuple[bytes, bytes, dict]:
    if report is not None:
        if pass1 is not None or pass2 is not None:
            raise ValueError('use either report or explicit pair')
        p = Path(report)
        info = json.loads(regular_file_bytes(p, MAX_METADATA))
        for key, value in [('ram_start', BASE), ('ram_end', END),
                           ('size', SIZE), ('chunk', CHUNK)]:
            if info.get(key) != value:
                raise ValueError('unexpected snapshot geometry: '+key)
        a_path = Path(info['pass1'])
        b_path = Path(info['pass2'])
        if not a_path.is_absolute() or not b_path.is_absolute() or a_path == b_path:
            raise ValueError('invalid pass file paths in report')
    elif pass1 is not None and pass2 is not None:
        a_path, b_path = Path(pass1), Path(pass2)
        if a_path == b_path:
            raise ValueError('two different RAM passes required')
        info = {}
    else:
        raise ValueError('provide one historical report or both RAM passes')

    a = regular_file_bytes(a_path, SIZE)
    b = regular_file_bytes(b_path, SIZE)
    if len(a) != SIZE or len(b) != SIZE:
        raise ValueError('wrong RAM pass size; expected 0x5000 bytes each')
    count = sum(x != y for x, y in zip(a, b))
    if 'changed_bytes' in info and count != info['changed_bytes']:
        raise ValueError('RAM passes disagree with historical report changed_bytes')
    if 'stable_bytes' in info and SIZE-count != info['stable_bytes']:
        raise ValueError('RAM passes disagree with historical report stable_bytes')
    metadata = {
        'pass1_path': str(a_path),
        'pass2_path': str(b_path),
        'pass1_sha256': hashlib.sha256(a).hexdigest(),
        'pass2_sha256': hashlib.sha256(b).hexdigest(),
        'historical_report_sha256': (hashlib.sha256(
            regular_file_bytes(Path(report), MAX_METADATA)).hexdigest() if report else None),
    }
    return a, b, metadata


def slab(b: bytes, start: int, stop_inclusive: int) -> bytes:
    if start < BASE or stop_inclusive > END or stop_inclusive < start:
        raise ValueError('RAM slice out of bounds')
    return b[start-BASE:stop_inclusive+1-BASE]


def excluded(address: int) -> bool:
    return any(lo <= address <= hi for lo, hi, _ in OPTO_EXCLUSION)


def analyze_passes(a: bytes, b: bytes, source: dict | None = None) -> dict:
    if len(a) != SIZE or len(b) != SIZE:
        raise ValueError('expected two complete 20KiB read-only RAM captures')
    diffs = [BASE+i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    focus = [n for n in diffs if FOCUS_START <= n <= FOCUS_END]
    source_context = [
        {'address': f'0x{addr:04x}',
         'pass1': f'0x{a[addr-BASE]:02x}',
         'pass2': f'0x{b[addr-BASE]:02x}'}
        for addr in range(SOURCE_CONTEXT_START, SOURCE_CONTEXT_END+1)
        if a[addr-BASE] != b[addr-BASE]
    ]
    # Rank non-Optolink 32-byte windows, but do not make semantic claims
    # from 2 unsynchronised snapshots alone.
    top = []
    for start in range(BASE, END+1, CHUNK):
        stop = start+CHUNK-1
        allowed = [n for n in range(start, stop+1) if not excluded(n)]
        changed = [n for n in allowed if a[n-BASE] != b[n-BASE]]
        if changed:
            top.append({
                'start': f'0x{start:04x}', 'end': f'0x{stop:04x}',
                'changed_unexcluded': len(changed),
                'eligible_bytes': len(allowed),
                'intersects_uart1_focus': start <= FOCUS_END and stop >= FOCUS_START
            })
    top.sort(key=lambda row: (-row['changed_unexcluded'],
                              -row['eligible_bytes'], row['start']))
    focus_changed = len(focus)
    report = {
        'schema_version': 1,
        'source': source or {},
        'ram_window': {'start':f'0x{BASE:04x}', 'end':f'0x{END:04x}',
                       'bytes':SIZE, 'chunk':CHUNK},
        'changed_total': len(diffs),
        'unchanged_total': SIZE - len(diffs),
        'historical_hardware_anchor': {
            'DMA0_SAR0_observed': f'0x{DMA0_SAR0_OBSERVED:04x}',
            'DMA0_TCR0_observed': f'0x{DMA0_TCR0_OBSERVED:04x}',
            'DMA0_destination': '0x03AA (UART1 TX register U1TB)',
            'one_point_in_time': True,
            'UART1_connected_to_GFA_proven': False
        },
        'uart1_source_focus': {
            'start': f'0x{FOCUS_START:04x}', 'end': f'0x{FOCUS_END:04x}',
            'observed_dma_source_address':f'0x{DMA0_SAR0_OBSERVED:04x}',
            'changed_bytes':focus_changed,
            'changed_addresses':[f'0x{x:04x}' for x in focus],
            'source_context_start': f'0x{SOURCE_CONTEXT_START:04x}',
            'source_context_end': f'0x{SOURCE_CONTEXT_END:04x}',
            'pass1_context_hex':slab(a, SOURCE_CONTEXT_START, SOURCE_CONTEXT_END).hex(),
            'pass2_context_hex':slab(b, SOURCE_CONTEXT_START, SOURCE_CONTEXT_END).hex(),
            'source_context_changed_bytes':source_context,
            'interpretation': ('DIFFERENCES_PRESENT_SOURCE_UNKNOWN' if focus_changed
                               else 'NO_DIFFERENCE_IN_TWO_CAPTURED_PASSES'),
        },
        'own_optolink_exclusion': [
            {'start':f'0x{lo:04x}', 'end':f'0x{hi:04x}', 'reason':label}
            for lo,hi,label in OPTO_EXCLUSION
        ],
        'changed_within_own_optolink_exclusion':
            sum(excluded(addr) for addr in diffs),
        'ranked_other_windows_top12': top[:12],
        'candidate_gfa_ram_address_verified': False,
        'production_alias_approved': False,
        'physical_ram_write_approved': False,
        'live_read_approved_from_this_offline_result': False,
        'appliance_access_performed': False,
        'limitations': [
            'Both passes originate from a single legacy P300 acquisition and have no simultaneous P06 reference.',
            'DMA0 SAR0=0x161B was sampled once; a TX source pointer is not a fan-speed sensor.',
            'Two snapshots cannot prove sensor freshness or identify the internal GFA bus.',
            'The ranked changed regions are memory activity, not candidate RPM identities.',
            'Known P300 host Optolink workspaces are excluded to avoid false GFA hits.'
        ]
    }
    return report


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    source=p.add_mutually_exclusive_group()
    source.add_argument('--report',type=Path,help='Old physical-ram-...-report.json')
    source.add_argument('--pass1',type=Path,help='Old 20KiB first snapshot (also supply --pass2)')
    p.add_argument('--pass2',type=Path)
    p.add_argument('--output',type=Path,help='New JSON report; never overwrites')
    args=p.parse_args()
    if not args.report and not args.pass1 and not args.pass2:
        print('PLAN ONLY: analyze prior 0x0400..0x53ff two-pass RAM files;'
              ' focus 0x15e0..0x165f around DMA0 UART1 SAR0=0x161b.')
        print('No serial/MQTT/service/network activity, no firmware reads, no RAM writes.')
        print('Use --report /tmp/physical-ram-*-report.json for saved images.')
        return 0
    a,b,provenance=load_capture(args.report,args.pass1,args.pass2)
    result=analyze_passes(a,b,provenance)
    print('RAM_OFFLINE_PASS changed=%d/20480 uart1_focus_changed=%d optolink_excluded_changed=%d' %
          (result['changed_total'],result['uart1_source_focus']['changed_bytes'],
           result['changed_within_own_optolink_exclusion']))
    print('UART1_GFA_LINK=NOT_PROVEN P06_RAM_ALIAS=NOT_PROVEN NO_LIVE_PROBE_APPROVED')
    if args.output:
        if args.output.is_symlink():
            raise ValueError('output is a symlink')
        with args.output.open('x',encoding='utf-8') as fd:
            json.dump(result, fd, indent=2, ensure_ascii=False, sort_keys=True)
            fd.write('\n')
        print('OFFLINE_REPORT='+str(args.output))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
