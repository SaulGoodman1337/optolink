#!/usr/bin/env python3
"""Offline audit of pinned, already collected sources. No appliance/network I/O.

Public CI uses the pinned research corpus. --metadata-root additionally accepts
an explicitly provided *private* v6 text export. Only reviewed small derivations
are emitted; full manufacturer tables and raw captures are never copied.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
from collections import Counter

RESEARCH_REF = '79f222c7f3a11b848a6a8ac8ece50e24deede823'
ARCHIVE_SHA256 = '3d31380d6dfabf8ede9e305b115e847fb0670511e253a4ed4e59feef2f7adfee'
PREFIX = 'config/optolink-splitter/research/'
SOURCES = {
    PREFIX + 'device-vdensho1-20c2-wb2a.md': '1ac69b312252b3c37b040fc7b2d56a2c1bda0f1120e131b184ad73a42c95c9a8',
    PREFIX + 'vitosoft/gfa-triggered-startup-2026-09-24-evidence.json': '834a9c06c4765b5b01f0ce1a1d5572dc18adc4a3d0c85f802b5db14a0bd681e9',
    'docs/gfa-live-checkpoint.md': '9a2800579522e117a6bfb14ded9168744e87200c5af77dc23f192431ccea96f5',
    PREFIX + 'physical-ram-optolink-map-2026-09-26.md': 'edabd57e299042aaa8f0888da28db07e2d374e5508175b54e46e1e7010935463',
    PREFIX + 'vitosoft/vdensho1-events.csv': '486f707dd0c2a73b8a173ee8a4bfc248559900d8d7ae48325519e54584aa20ed',
}
TARGET = 'VDensHO1'
TARGET_ID = '60'
# Deliberately small, reviewed set, not a republishing of a manufacturer table.
EVENT_IDS = {'600', '697', '8395', '8175', '8230', '8178', '8233', '8259',
             '8211', '4722', '7963', '11284', '11288'}
EXPORT_FIELDS = ('event_id', 'name_de', 'token', 'address', 'fc_read',
                 'block_length', 'byte_position', 'byte_length',
                 'conversion', 'conversion_factor', 'unit')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding='utf-8-sig', newline='') as source:
        return list(csv.DictReader(source))


def is_target(row: dict[str, str]) -> bool:
    # Substring membership would incorrectly include VDensHO1_100 etc.
    return TARGET in row['devices'].split(';')


def fan_speed_label(row: dict[str, str]) -> bool:
    text = ' '.join(row.get(k, '') for k in
                    ('name_de', 'name_en', 'description_de', 'description_en', 'token')).lower()
    fan = any(term in text for term in ('gebl', 'blower', 'fan', 'ventilator'))
    speed = any(term in text for term in ('drehzahl', 'speed', 'rpm'))
    return fan and speed


def summarize_metadata(events: list[dict[str, str]], links: list[dict[str, str]]) -> dict:
    required = set(EXPORT_FIELDS) | {'devices', 'device_ids'}
    if not events or any(not required <= set(row) for row in events):
        raise ValueError('missing event export fields')
    if len({e['event_id'] for e in events}) != len(events):
        raise ValueError('duplicate event IDs')
    local = [e for e in events if is_target(e)]
    if any(TARGET_ID not in e['device_ids'].split(';') for e in local):
        raise ValueError('target name/ID association mismatch')
    linked_ids = {r['event_id'] for r in links if r['device'] == TARGET and r['device_id'] == TARGET_ID}
    if linked_ids != {e['event_id'] for e in local}:
        raise ValueError('event membership disagrees with link table')
    candidates = [e for e in events if fan_speed_label(e) and e['fc_read'] != 'GFA_READ']
    selected = []
    for e in events:
        if e['event_id'] in EVENT_IDS:
            out = {k: e[k] for k in EXPORT_FIELDS}
            out['exact_target_member'] = is_target(e)
            if not out['exact_target_member']:
                out['other_profiles'] = e['devices'].split(';') if e['devices'] else []
            selected.append(out)
    return {
        'event_rows': len(events), 'target_event_links': len(local),
        'target_address_count': len({e['address'] for e in local if e['address']}),
        'target_read_function_counts': dict(sorted(Counter(e['fc_read'] or '<empty>' for e in local).items())),
        'label_search': {
            'method': 'fan/blower/Geblaese/Ventilator plus speed/rpm/Drehzahl, non-GFA_READ; exact profile membership',
            'global_matches': len(candidates),
            'exact_target_matches': sum(is_target(e) for e in candidates),
            'not_a_firmware_unavailability_proof': True,
        },
        'selected_events': selected,
        'physical_ram_addresses_inferred_from_virtual_addresses': False,
    }


def collapse(values: list[str]) -> list[str]:
    return [x for i, x in enumerate(values) if i == 0 or values[i - 1] != x]


def public_audit(root: Path) -> dict:
    for path, expected in SOURCES.items():
        p = root / path
        if p.is_symlink() or digest(p) != expected:
            raise ValueError('pinned source hash mismatch: ' + path)
    device = (root / (PREFIX + 'device-vdensho1-20c2-wb2a.md')).read_text()
    anchor = 'A high-resolution 2026-09-22 start captured this byte-5/6/7 state sequence:'
    section = device.split(anchor, 1)[1].split('```text', 1)[1].split('```', 1)[0]
    phase_rows = re.findall(r'^([0-9a-f]{2}) ([0-9a-f]{2}) ([0-9a-f]{2}) +[^\n]+$', section, re.M | re.I)
    # The header b5 b6 b7 is itself hex-looking, but is not a sample.
    phase_rows = [row for row in phase_rows if row != ('b5', 'b6', 'b7')]
    native = collapse([row[2].lower() for row in phase_rows])
    obj = json.loads((root / (PREFIX + 'vitosoft/gfa-triggered-startup-2026-09-24-evidence.json')).read_text())
    gfa = [row['raw'].lower() for row in obj['observed_startup']['P87_first_states']]
    if not native or not gfa:
        raise ValueError('source sequence not found')
    return {
        'schema_version': 1,
        'research_commit': RESEARCH_REF,
        'public_source_hashes': SOURCES,
        'ui_export_rows_not_complete_profile': len(csv_rows(root / (PREFIX + 'vitosoft/vdensho1-events.csv'))),
        'p87_hypothesis': {
            'virtual_request': {'address': '0x55D3', 'length': 11, 'zero_based_byte': 7},
            'gfa_request': {'command': 'VS1/6B', 'address': '0x4057', 'length': 1},
            'native_observed_sequence_20260922': native,
            'gfa_observed_sequence_20260924': gfa,
            'nonzero_sequence_equal': [x for x in native if x != '00'] == gfa,
            'same_session': False,
            'verdict': 'HYPOTHESIS_CROSS_SESSION_SEQUENCE_MATCH_ONLY',
            'independent_read_at_0x55DA_tested': False,
        },
        'ram_source_boundary': {
            'physical_read_range_documented': ['0x0400', '0x53FF'],
            'all_bin_paths_in_public_corpus': sorted(str(p.relative_to(root)) for p in root.rglob('*.bin')),
            'original_dynamic_ram_dumps_available_in_this_corpus': False,
            'exclude_own_optolink_buffers_before_claiming_live_sensor': True,
            'second_uart_external_protocol_identified': False,
        },
        'production_replacement_approved': False,
        'appliance_access': False,
    }


def metadata_audit(root: Path) -> dict:
    # Verify selected extraction against its manifest; archive verification
    # belongs to the private extraction workflow, not to this local assertion.
    if (root / 'archive-ref.txt').read_text().strip() != 'archive_sha256=' + ARCHIVE_SHA256:
        raise ValueError('unexpected source archive reference')
    manifest = (root / 'selected-sha256.txt').read_text().splitlines()
    verified = {}
    for line in manifest:
        sha, name = line.split('  ', 1)
        path = root / name
        if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink() or digest(path) != sha:
            raise ValueError('private text extraction integrity failure')
        verified[str(Path(name))] = sha
    event_path = 'derived/all-devices/all-events.csv'
    link_path = 'derived/all-devices/all-device-event-links.csv'
    for name in (event_path, link_path):
        if name not in verified:
            raise ValueError('required metadata missing from extraction manifest')
    result = summarize_metadata(csv_rows(root / event_path), csv_rows(root / link_path))
    result['source_files_sha256'] = {name: verified[name] for name in (event_path, link_path)}
    result['source_archive_sha256'] = ARCHIVE_SHA256
    result['extracted_text_files_verified'] = len(verified)
    result['full_manufacturer_tables_exported'] = False
    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--research-root', type=Path, required=True)
    p.add_argument('--metadata-root', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    report = public_audit(args.research_root)
    report['metadata'] = metadata_audit(args.metadata_root) if args.metadata_root else {
        'status': 'PRIVATE_METADATA_NOT_PROVIDED', 'not_a_negative_search_result': True}
    # Refuse accidental overwriting of sources or prior evidence.
    with args.output.open('x', encoding='utf-8') as out:
        json.dump(report, out, indent=2, ensure_ascii=False, sort_keys=True)
        out.write('\n')
    print('OFFLINE_AUDIT_WRITTEN; no hardware or production change')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
