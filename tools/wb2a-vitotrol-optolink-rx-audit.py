#!/usr/bin/env python3
"""Offline UART1 receive-buffer hypothesis audit, WB2A 20C2, P300 archives.

This is NOT a controller client. It neither opens serial nor accesses a
controller, service, socket, MQTT, memory interface or firmware. Its only
inputs are captured archives (including standard input) and 32-byte FC03
0x1640 fixtures. Never treat this as authorization to write RAM.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile

MAX_ARCHIVE_BYTES=16_000_000
RAM_START=0x0400
TX_START=0x161A
RX_START=0x1642
FC03_START=0x1640
FC03_LENGTH=32
KNOWN_ARCHIVES={
    'fullram':'94d5842b6dc5759ecb446a4c617b60b72873b639885d116032f783abdef8431c',
    'deep':'f0f015032edb94459ff2259a81ef2b84bf23253570d91cc6ba658c8160f5c2af',
}
KNOWN_REPLY_HEX=(
    '0001b10a010110fe23d8',
    '0001b10a010100004353',
)
TRAIL='fa01fb0122d1'


class EvidenceRejected(ValueError):
    """Reject malformed or unattributed evidence; never infer controller state."""


def crc16_kermit(data: bytes) -> int:
    if type(data) is not bytes:
        raise EvidenceRejected('exact bytes required')
    crc=0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc=(crc>>1) ^ (0x8408 if crc&1 else 0)
    return crc&0xFFFF


def parse_1640_block(raw: bytes) -> dict:
    """Parse a non-atomic archived RAM read at 1640/32; no RX proof implied."""
    if type(raw) is not bytes or len(raw)!=FC03_LENGTH:
        raise EvidenceRejected('historical FC03 1640 block must be exactly 32 bytes')
    if raw[:2]!=b'\x00\x00':
        raise EvidenceRejected('two-byte observed prefix at 1640 absent')
    body=raw[2:]
    if len(body)<8 or body[0]!=0 or body[1]==0 or body[1]==0xff:
        raise EvidenceRejected('not a candidate slave-to-controller frame')
    n=body[3]
    if not 8 <= n <= len(body) or body[2] not in (0x80,0xB1,0xB3,0xBF):
        raise EvidenceRejected('unsupported RX-candidate length/command')
    frame=body[:n]
    if crc16_kermit(frame)!=0:
        raise EvidenceRejected('candidate RX frame CRC invalid')
    if frame[4] not in (1,2,3) or frame[5]!=1:
        raise EvidenceRejected('candidate RX frame slot/subclass invalid')
    return {
        'candidate_ram_address':'0x1642',
        'provenance':'RAM_CONTENT_RX_DIRECTION_NOT_PHYSICAL_UART1_RX_PROOF',
        'src_class':f'{frame[1]:02x}',
        'cmd':f'{frame[2]:02x}',
        'slot':frame[4],
        'frame_hex':frame.hex(),
        'suffix_hex':body[n:n+6].hex(),
        'uart1_rx_isr_proven':False,
        'controller_write_authorized':False,
    }


def reconstruct_stale_identity(suffix: bytes) -> dict:
    """CRC-constrained hypothesis; NEVER claim full original B3 was captured.

    A B1 overwrote ten bytes of an apparently longer prior buffer. Given
    *assumed* B3 F8/F9/FA/FB form for class 01, determine one missing F9.
    A unique CRC solution remains a reconstruction, NOT direct measurement.
    """
    if type(suffix) is not bytes or len(suffix)!=6:
        raise EvidenceRejected('six observed residual bytes required')
    solutions=[]
    for f9 in range(256):
        frame=(bytes.fromhex('0001b3100101f801f9')+bytes((f9,))+suffix)
        if crc16_kermit(frame)==0 and frame[10:14:2]==bytes.fromhex('fafb'):
            solutions.append((f9,frame.hex()))
    return {
        'status':'CRC_CONSTRAINED_HYPOTHESIS_NOT_OBSERVED_FRAME',
        'solutions':len(solutions),
        'hypothetical_f9_values':[f'{x:02x}' for x,_ in solutions],
        'candidate_frame_hex':[f for _,f in solutions],
        'physical_rx_verified':False,
    }


def _member(tar: tarfile.TarFile, path: str, *, max_size: int) -> bytes:
    try:
        item=tar.getmember(path)
    except KeyError as exc:
        raise EvidenceRejected(f'missing archived member: {path}') from exc
    if not item.isfile() or item.size<0 or item.size>max_size:
        raise EvidenceRejected(f'unsafe/unexpected member: {path}')
    reader=tar.extractfile(item)
    if reader is None:
        raise EvidenceRejected('archive content unavailable')
    data=reader.read(max_size+1)
    if len(data)!=item.size:
        raise EvidenceRejected(f'member size mismatch: {path}')
    return data


def _manifest(tar: tarfile.TarFile, prefix: str) -> dict:
    content=_member(tar,prefix+'/bundle-manifest.json',max_size=160_000)
    model=json.loads(content)
    if not isinstance(model,dict) or not isinstance(model.get('files'),dict):
        raise EvidenceRejected('missing manifest hash inventory')
    return model['files']


def _verified(tar: tarfile.TarFile, manifest: dict, prefix: str,
              suffix: str, *, max_size: int) -> bytes:
    filename=prefix+'/'+suffix
    data=_member(tar,filename,max_size=max_size)
    entry=manifest.get(suffix)
    declared_size=(entry.get('size',entry.get('size_bytes'))
                   if isinstance(entry,dict) else None)
    if (not isinstance(entry,dict) or declared_size!=len(data)
            or ('size' in entry and 'size_bytes' in entry
                and entry['size']!=entry['size_bytes'])
            or entry.get('sha256')!=hashlib.sha256(data).hexdigest()):
        raise EvidenceRejected('manifest SHA256/size mismatch: '+suffix)
    return data


def _aggregate(samples: list[tuple[int,bytes]], kind: str) -> dict:
    frame_count=Counter()
    suffix_count=Counter()
    for _,raw in samples:
        p=parse_1640_block(raw)
        frame_count[p['frame_hex']]+=1
        suffix_count[p['suffix_hex']]+=1
    stale=reconstruct_stale_identity(bytes.fromhex(TRAIL))
    return {
        'archive_kind':kind,
        'candidate_address':'0x1642',
        'last_known_master_tx_address':'0x161a',
        'tx_to_rx_distance_bytes':RX_START-TX_START,
        'frames_sampled':len(samples),
        'candidate_frames_crc_valid':sum(frame_count.values()),
        'unique_frames':dict(sorted(frame_count.items())),
        'suffix_counts':dict(sorted(suffix_count.items())),
        'stale_identity_if_suffix_matches':stale if TRAIL in suffix_count else None,
        'evidence_bound':'READ_ONLY_ARCHIVED_RAM_NO_PROOF_OF_PHYSICAL_RX_OR_WRITABLE_RX_MAILBOX',
        'physical_uart1_rx_verified':False,
        'controller_write_authorized':False,
        'new_hardware_io':False,
    }


def audit_fullram(tar:tarfile.TarFile, *, n:int=79) -> dict:
    if type(n) is not int or not 1<=n<=79:
        raise EvidenceRejected('bounded historical complete snapshot count required')
    prefix='p300-fullram'
    manifest=_manifest(tar,prefix)
    samples=[]
    directions=Counter()
    for i in range(1,n+1):
        suffix=f'snapshots/s{i:05d}'
        info=json.loads(_verified(tar,manifest,prefix,suffix+'.json',max_size=8_000))
        data=_verified(tar,manifest,prefix,suffix+'.bin',max_size=20_480)
        if (info.get('device_id')!='20c2' or info.get('software')!='0103'
                or info.get('marker')!='COMPLETE' or info.get('complete') is not True
                or info.get('bytes_stored')!=20_480 or len(data)!=20_480
                or info.get('sha256')!=hashlib.sha256(data).hexdigest()
                or info.get('range_start')!='0x0400' or info.get('range_last_inclusive')!='0x53ff'
                or info.get('direction') not in ('ascending','descending')):
            raise EvidenceRejected(f'non-canonical/unverified snapshot {i}')
        # COMPLETE images are canonical by ascending RAM address even when
        # the physical scan was descending. Snapshot 80 is omitted entirely.
        directions[info['direction']]+=1
        offset=FC03_START-RAM_START
        samples.append((i,data[offset:offset+FC03_LENGTH]))
    report=_aggregate(samples,'fullram')
    report['direction_counts']=dict(sorted(directions.items()))
    report['partial_snapshot_80_included']=False
    return report


def audit_deep(tar:tarfile.TarFile) -> dict:
    prefix='p300-deep'
    manifest=_manifest(tar,prefix)
    data=_verified(tar,manifest,prefix,'p300.jsonl',max_size=5_000_000)
    samples=[]
    seen=set()
    for line in data.splitlines():
        row=json.loads(line)
        index=row.get('index')
        if type(index) is not int or index<=0 or index in seen:
            raise EvidenceRejected('invalid or duplicate deep record index')
        seen.add(index)
        probe=row.get('reads',{}).get('ram_1640')
        if probe is None:continue
        if (probe.get('address')!='0x1640' or probe.get('fc')!=3
                or probe.get('length')!=32):
            raise EvidenceRejected('unexpected deep FC03 request semantics')
        try:raw=bytes.fromhex(probe['hex'])
        except (TypeError,ValueError,KeyError) as exc:
            raise EvidenceRejected('invalid deep FC03 hex') from exc
        samples.append((index,raw))
    if not samples:
        raise EvidenceRejected('no actual 1640/32 deep read recorded')
    return _aggregate(samples,'deep')


def audit_bundle(kind: str, blob:bytes, *, known_hash:bool=True) -> dict:
    if kind not in KNOWN_ARCHIVES or type(blob) is not bytes or not 0<len(blob)<=MAX_ARCHIVE_BYTES:
        raise EvidenceRejected('exact archive kind and finite bytes required')
    digest=hashlib.sha256(blob).hexdigest()
    if known_hash and digest!=KNOWN_ARCHIVES[kind]:
        raise EvidenceRejected('historical archive SHA256 does not match pinned source')
    with tarfile.open(fileobj=io.BytesIO(blob),mode='r:gz') as tar:
        report=audit_fullram(tar) if kind=='fullram' else audit_deep(tar)
    report['archive_sha256']=digest
    report['full_archive_hash_verified']=known_hash
    return report


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--fullram',action='store_true')
    source.add_argument('--deep',action='store_true')
    source.add_argument('--sample-1640',type=str,metavar='HEX')
    parser.add_argument('--archive',default='-',help='source .tar.gz path or - for stdin (root-only source via sudo cat)')
    args=parser.parse_args()
    if args.sample_1640 is not None:
        try:sample=bytes.fromhex(args.sample_1640)
        except ValueError as exc:raise SystemExit('invalid hex') from exc
        result=parse_1640_block(sample)
    else:
        if args.archive=='-':
            blob=sys.stdin.buffer.read(MAX_ARCHIVE_BYTES+1)
        else:
            path=Path(args.archive)
            if path.stat().st_size>MAX_ARCHIVE_BYTES:
                raise EvidenceRejected('archive exceeds bounded input size')
            blob=path.read_bytes()
        result=audit_bundle('fullram' if args.fullram else 'deep',blob)
    print(json.dumps(result,sort_keys=True,indent=2))


if __name__=='__main__':
    main()
