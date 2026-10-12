#!/usr/bin/env python3
"""Audit ORIGINAL Vitotrol-300 TX ordering and emulator fidelity, offline.

Strictly consumes the SHA-pinned 2018 OpenV #387 original Vitotrol-300
UART-TX archive; no boiler hardware, serial, network or controller writes.
The recording contains NO master traffic, timestamps or local WB2A RX proof.
Any field interpretation of BF/15 is intentionally withheld.
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

ROOT=Path(__file__).resolve().parent

def _load(filename:str,module_name:str):
    spec=importlib.util.spec_from_file_location(module_name,ROOT/filename)
    if spec is None or spec.loader is None:
        raise RuntimeError('offline dependency missing')
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    spec.loader.exec_module(module)
    return module

core=_load('wb2a-vitotrol-offline.py','wb2a_v300_sequence_core')
public=_load('wb2a-vitotrol-public-capture-audit.py','wb2a_v300_sequence_public')
ZIP_SHA256='eb398ec9b4b174354425d2615f7d76937acaf5e0e1cde4df154fee78425bab93'
RAW_SHA256='b6d5b0526d0b0a96e5bc3369de639763ef95db9786ee51a1c0b26ecbb229d068'
KNOWN_EXTERNAL_REG00_QUERY=bytes.fromhex('11003109010100ee4f')
KNOWN_EXTERNAL_PING=bytes.fromhex('1100000801010888')
KNOWN_LOCAL_DISCOVERY=bytes.fromhex(core.KNOWN_MASTER_HEX[0])


def split_original_tx(data:bytes) -> tuple[tuple[bytes,...],bytes]:
    """Decode contiguous original TX frames without resync or inferred timing."""
    if type(data) is not bytes or not 8<=len(data)<=public.MAX_SOURCE_BYTES:
        raise core.FrameRejected('bounded exact capture bytes required')
    frames=[];pos=0
    while pos+8<=len(data):
        if data[pos:pos+2]!=b'\x00\x11':
            raise core.FrameRejected('invalid original slave start, no resync')
        n=data[pos+3]
        if not 8<=n<=64 or pos+n>len(data):
            raise core.FrameRejected('truncated/oversize source frame')
        frame=core.validate_frame(data[pos:pos+n])
        if frame[4]!=1 or frame[5]!=1:
            raise core.FrameRejected('not original observed Vitotrol slot-1 frame')
        frames.append(frame)
        pos+=n
    tail=data[pos:]
    if tail and (len(tail)>=8 or not tail.startswith(b'\x00\x11')
                 or (len(tail)>=4 and not 8<=tail[3]<=64)):
        raise core.FrameRejected('invalid short EOF fragment')
    if not frames:
        raise core.FrameRejected('no complete original frames')
    return tuple(frames),tail


def _reconstruct_known_response(f:bytes) -> bytes|None:
    if f[2]==0x80 and len(f)==8:
        return core.model_pong(KNOWN_EXTERNAL_PING)
    if f[2]==0xB3 and len(f)==16 and f[6:14:2]==b'\xf8\xf9\xfa\xfb':
        return core.model_identity_reply(KNOWN_LOCAL_DISCOVERY,
                                         identity=core.IDENTITY_V300_ORIGINAL)
    if f[2]==0xB1 and len(f)==10 and f[6]==0:
        return core.model_register_00_reply(KNOWN_EXTERNAL_REG00_QUERY,
                                           value=core.REGISTER_00_V300_ORIGINAL)
    if f[2]==0xBF and len(f)==12 and f[6]==0x20:
        temperature=core.decode_candidate_slave_room_temp(f)['temperature_tenths_c']
        return core.model_room_temp_record(1,temperature)
    return None


def summarize_original_frames(frames:tuple[bytes,...],tail:bytes) -> dict:
    if type(frames) is not tuple or not frames or type(tail) is not bytes:
        raise core.FrameRejected('exact original frame sequence required')
    counts=Counter();matches=Counter();unmodelled=Counter()
    idx15=[];r15=[];indices_nonpong=[]
    for index,frame in enumerate(frames):
        frame=core.validate_frame(frame)
        if frame[:2]!=b'\x00\x11' or frame[4:6]!=b'\x01\x01':
            raise core.FrameRejected('wrong original device/slot in stream')
        counts[f'{frame[2]:02x}']+=1
        if frame[2]!=0x80:indices_nonpong.append(index)
        proposed=_reconstruct_known_response(frame)
        if proposed is not None:
            if proposed != frame:
                raise core.FrameRejected('generated offline reply differs from original TX')
            matches[f'{frame[2]:02x}']+=1
        else:
            key=f'{frame[2]:02x}/{frame[6]:02x}'
            unmodelled[key]+=1
        if frame[2]==0xBF and frame[6]==0x15:
            if len(frame)!=17:
                raise core.FrameRejected('original BF15 shape unexpected')
            desc=core.decode_candidate_slave_record_15(frame)
            if desc['controller_write_authorized']:
                raise core.FrameRejected('BF15 mutation not allowed')
            decoded=bytes.fromhex(desc['xor_decoded_payload_hex'])
            if len(decoded)!=8:
                raise core.FrameRejected('BF15 projection must be 8 bytes')
            idx15.append(index);r15.append(decoded)
    byte_values=[sorted({frame[i] for frame in r15}) for i in range(8)] if r15 else []
    constants={str(i):f'{a[0]:02x}' for i,a in enumerate(byte_values) if len(a)==1}
    return {
        'source_type':'EXTERNAL_ORIGINAL_VITOTROL300_TX_ONLY',
        'total_complete_frames':len(frames),
        'crc_valid_frame_count':len(frames),
        'command_counts':dict(sorted(counts.items())),
        'byte_exact_modelled_frame_count':sum(matches.values()),
        'modelled_counts_by_command':dict(sorted(matches.items())),
        'unmodelled_counts_by_command_record':dict(sorted(unmodelled.items())),
        'bf15_record_count':len(r15),
        'bf15_unique_8byte_xor_projections':len(set(r15)),
        'bf15_xor_byte_distinct_counts':list(map(len,byte_values)),
        'bf15_xor_constant_positions':constants,
        'bf15_record_stream_indices':idx15,
        'bf15_last_seven_first_xor_bytes':[
           f'{rec[0]:02x}' for rec in r15[-7:]],
        'bf15_field_semantics_verified':False,
        'bf15_emission_implemented':False,
        'rolling_code_semantics_proven':False,
        'trailing_incomplete_hex':tail.hex(),
        'external_master_queries_recorded':False,
        'wall_clock_timing_available':False,
        'local_wb2a_uart1_rx_verified':False,
        'optolink_injection_authorized':False,
        'no_hardware_io':True,
    }


def audit_original_zip(path:Path) -> dict:
    path=Path(path)
    baseline=public.audit_zip(path,expected_sha256=ZIP_SHA256)
    with zipfile.ZipFile(path,'r') as z:
        data=z.read('log.bin')
    if hashlib.sha256(data).hexdigest()!=RAW_SHA256:
        raise core.FrameRejected('unexpected original Vitotrol raw source hash')
    frames,tail=split_original_tx(data)
    report=summarize_original_frames(frames,tail)
    if (report['total_complete_frames']!=baseline['crc_valid_complete_frames']
            or report['command_counts']!={k.lower():v for k,v in baseline['command_counts'].items()}
            or report['trailing_incomplete_hex']!=baseline['trailing_incomplete_hex']):
        raise core.FrameRejected('sequence summary disagrees with source audit')
    report['archive_sha256']=ZIP_SHA256
    report['raw_sha256']=RAW_SHA256
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('zip',type=Path,help='Previously downloaded ORIGINAL OpenV log.zip')
    args=p.parse_args()
    print(json.dumps(audit_original_zip(args.zip),sort_keys=True,indent=2))


if __name__=='__main__':
    main()
