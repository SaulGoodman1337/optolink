#!/usr/bin/env python3
"""Offline, SHA-attested near-KM-RX ROM-looking three-byte values in 20C2 RAM.

Read-only: 79 previously recorded, non-atomic Physical_READ 20-KiB images.
Pointer-looking SRAM triples do not establish executable pointers, ISR
ownership, a working INTB location, a ROM image or safe P300 code execution.
"""
from __future__ import annotations
from collections import Counter
import importlib.util
import io
import json
from pathlib import Path
import stat
import sys
import tarfile

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location(
    "wb2a_vitotrol_archive_pointer_helper",
    HERE/"wb2a-vitotrol-optolink-rx-context.py")
if spec is None or spec.loader is None:
    raise RuntimeError('archive verifier unavailable')
ctx=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=ctx
spec.loader.exec_module(ctx)
audit=ctx.audit
ROM=(0xC0000,0xFFFFF)
CANDIDATES={
    "comparison_0ab8":0x0AB8,
    "neighbor_0b5c":0x0B5C,
    "near_rx_descriptor_0b74":0x0B74,
    "near_rx_descriptor_0b7e":0x0B7E,
    "other_uart0_context_1a7d":0x1A7D,
    "other_uart0_context_18f8":0x18F8,
}
CANDIDATE_RX_DESCRIPTOR=0x0B6D
CANDIDATE_RX_BODY=0x1642

class CandidateRejected(ValueError):pass

def inspect(images):
    if not isinstance(images,(list,tuple)) or not 1<=len(images)<=79:
        raise CandidateRejected('1..79 verified fullram images required')
    if any(type(x) is not bytes or len(x)!=20480 for x in images):
        raise CandidateRejected('complete immutable 20480-byte SRAM images required')
    matches=[]
    for name,addr in CANDIDATES.items():
        off=addr-0x400
        vals=Counter(int.from_bytes(x[off:off+3],'little') for x in images)
        trailing=Counter(x[off+3] for x in images)
        inrange=sum(c for v,c in vals.items() if ROM[0]<=v<=ROM[1])
        matches.append({
            "label":name,
            "cpu_ram_location":f'0x{addr:04x}',
            "distinct_le24_values":len(vals),
            "le24_hex_counts":{
                f'0x{v:05x}':c for v,c in sorted(vals.items())
            },
            "m30624_program_address_range_sample_count":inrange,
            "fourth_byte_counts":{f'{v:02x}':c for v,c in sorted(trailing.items())},
            "typed_as_executable_callback":False,
            "proven_uart1_rx_parser_address":False,
        })
    off=CANDIDATE_RX_DESCRIPTOR-0x400
    descriptor=Counter(x[off:off+4].hex() for x in images)
    rxoffset=CANDIDATE_RX_BODY-0x400
    match=sum(x[off:off+2]==bytes.fromhex('4216')
        and x[off+2]==x[rxoffset+3] for x in images)
    return {
        "source":"HISTORIC_20C2_0103_P300_NONATOMIC_FULLRAM",
        "images":len(images),
        "descriptor_0b6d_fourbyte_counts":dict(sorted(descriptor.items())),
        "descriptor_rx_candidate_length_alignment_samples":match,
        "near_rx_far_address_lookalikes":matches,
        "mcu_program_flash_image_present":False,
        "isr_vector20_handler_resolved":False,
        "interrupt_can_be_injected_via_optolink":False,
        "physical_rom_word_read_back_verified":False,
        "controller_code_execution_requested":False,
        "serial_or_controller_io":False,
        "candidate_addresses_are_not_call_targets":True,
    }

def inspect_verified_archive(blob:bytes):
    if type(blob) is not bytes or not 0<len(blob)<=audit.MAX_ARCHIVE_BYTES:
        raise CandidateRejected('bounded original archive required')
    archiveinfo=audit.audit_bundle('fullram',blob)
    images=[]
    with tarfile.open(fileobj=io.BytesIO(blob),mode='r:gz') as tf:
        manifest=audit._manifest(tf,"p300-fullram")
        for i in range(1,80):
            key=f'snapshots/s{i:05d}'
            meta=json.loads(audit._verified(
                tf,manifest,'p300-fullram',key+'.json',max_size=8000))
            data=audit._verified(
                tf,manifest,'p300-fullram',key+'.bin',max_size=20480)
            if (meta.get('marker')!='COMPLETE' or meta.get('complete') is not True
                or meta.get('device_id')!='20c2' or meta.get('software')!='0103'
                or meta.get('bytes_stored')!=20480
                or meta.get('range_start')!='0x0400'
                or meta.get('range_last_inclusive')!='0x53ff'
                or len(data)!=20480):
                raise CandidateRejected('historical image metadata not attested')
            images.append(data)
    result=inspect(images)
    result['source_zip_bundle_sha256']=archiveinfo['archive_sha256']
    result['source_original_sha256_verified']=True
    return result

def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',required=True,type=Path)
    a=p.parse_args()
    if (a.archive.is_symlink()
        or a.archive.suffixes[-2:]!=['.tar','.gz']
        or not stat.S_ISREG(a.archive.stat().st_mode)
        or a.archive.stat().st_size>audit.MAX_ARCHIVE_BYTES):
        p.error('regular bounded pinned tar.gz required')
    print(json.dumps(inspect_verified_archive(a.archive.read_bytes()),
                     sort_keys=True,indent=2))

if __name__=='__main__':main()
