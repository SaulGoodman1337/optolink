#!/usr/bin/env python3
"""Audit public ORIGINAL Vitotrol 300 UART-TX ZIP, purely offline.

No serial, Optolink, MQTT, boiler-state writes, or network access. The
original source is openv/openv issue #387, comment #435796559. These are
external Vitotrol-to-controller bytes, NOT proven WB2A/20C2 UART1 RX.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import zipfile

SOURCE = Path(__file__).resolve().with_name('wb2a-vitotrol-offline.py')
SPEC = importlib.util.spec_from_file_location('wb2a_vitotrol_capture_core', SOURCE)
core = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = core
SPEC.loader.exec_module(core)
MAX_SOURCE_BYTES = 1_000_000


def parse_external_slave_tx(data: bytes) -> dict:
    """Parse continuous original slave-TX frames and permit a short EOF cut.

    CRC and boundaries must validate *every* complete frame. This intentionally
    refuses to silently skip corrupted offsets and invent success statistics.
    """
    if type(data) is not bytes or not 8 <= len(data) <= MAX_SOURCE_BYTES:
        raise core.FrameRejected('bounded raw capture bytes required')
    pos = 0
    counts = Counter()
    records = Counter()
    frames = 0
    identities = []
    reg00_values = []
    temperatures = []
    trailing = b''
    while pos < len(data):
        remaining = data[pos:]
        if len(remaining) < 8:
            if not remaining.startswith(b'\x00\x11'):
                raise core.FrameRejected(f'invalid trailing prefix at {pos}')
            if len(remaining) >= 4 and not 8 <= remaining[3] <= 64:
                raise core.FrameRejected(f'invalid trailing length at {pos}')
            trailing = remaining
            break
        if remaining[:2] != b'\x00\x11' or not 8 <= remaining[3] <= 64:
            raise core.FrameRejected(f'invalid frame boundary at {pos}')
        n = remaining[3]
        if len(remaining) < n:
            raise core.FrameRejected(f'incomplete frame larger than small EOF tail at {pos}')
        frame = core.validate_frame(remaining[:n])
        cmd = frame[2]
        counts[f'{cmd:02X}'] += 1
        if cmd == core.SEND_MULTIPLE and n == 16 and frame[6:14:2] == b'\xf8\xf9\xfa\xfb':
            identities.append(core.decode_candidate_slave_reply(frame)['identity_bytes'])
        if cmd == 0xB1 and n == 10 and frame[6] == 0x00:
            reg00_values.append(frame[7])
        if cmd == 0xBF and n >= 9:
            records[f'{frame[6]:02X}'] += 1
            if frame[6] in (0x20, 0x21, 0x22):
                temperatures.append(core.decode_candidate_slave_room_temp(frame)['temperature_tenths_c'])
        frames += 1
        pos += n
    return {
        'provenance': 'EXTERNAL_ORIGINAL_VITOTROL300_UART_TX_NOT_WB2A_RX',
        'raw_sha256': hashlib.sha256(data).hexdigest(),
        'raw_bytes': len(data),
        'crc_valid_complete_frames': frames,
        'command_counts': dict(sorted(counts.items())),
        'bf_record_counts': dict(sorted(records.items())),
        'f8_fb_identities': identities,
        'reg00_values': reg00_values,
        'room_temp_tenths_c': temperatures,
        'trailing_incomplete_hex': trailing.hex(),
        'full_frames_rejected': 0,
        'physical_wb2a_slave_rx_verified': False,
        'timestamps_available': False,
    }


def audit_zip(path: Path, *, expected_sha256: str | None = None) -> dict:
    """ZIP reader only; no extraction, imports of ZIP code, or I/O to devices."""
    path=Path(path)
    if path.stat().st_size > MAX_SOURCE_BYTES + 4096:
        raise core.FrameRejected('public archive file too large')
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise core.FrameRejected('public archive SHA256 mismatch')
    with zipfile.ZipFile(path, 'r') as archive:
        items=archive.infolist()
        if len(items)!=1 or items[0].filename != 'log.bin':
            raise core.FrameRejected('only the documented log.bin member accepted')
        if not 8 <= items[0].file_size <= MAX_SOURCE_BYTES:
            raise core.FrameRejected('invalid archive content size')
        data=archive.read('log.bin')
    report=parse_external_slave_tx(data)
    report['archive_sha256']=digest
    return report


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('zip',type=Path,help='previously downloaded original openv log.zip')
    p.add_argument('--expected-sha256',help='optional archive provenance hash')
    args=p.parse_args()
    print(json.dumps(audit_zip(args.zip, expected_sha256=args.expected_sha256),indent=2,sort_keys=True))


if __name__ == '__main__':
    main()
