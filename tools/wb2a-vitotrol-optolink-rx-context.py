#!/usr/bin/env python3
"""Offline, hash-attested UART1 RX-candidate context and timeline audit.

Only consumes prior, completed P300 tar.gz recordings. No transport, service,
firmware write, SFR probe, port access or controller emulation/injection.
The RX/ISR/INTB relationship is NOT proven by this analysis.
"""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
import importlib.util
import io
import json
import math
from pathlib import Path
import sys
import tarfile

HELPER=Path(__file__).with_name('wb2a-vitotrol-optolink-rx-audit.py')
spec=importlib.util.spec_from_file_location('wb2a_vitotrol_rx_archive_helper',HELPER)
if spec is None or spec.loader is None:
    raise RuntimeError('pinned pure offline archive helper missing')
audit=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=audit
spec.loader.exec_module(audit)

RX_MEM=0x1642
TX_MEM=0x161A
META_MEM=0x166A
POINTER_CANDIDATE=0x0B6D
TRACE_ADDRESS=('0x1660','0x1640','0x1620','0x1600')
FRAME_CLASS11_COMMANDS=frozenset((0x80,0xB1,0xB3,0xBF))


def frame_hits(img:bytes, *, source_class:int=0x11) -> tuple[tuple[int,str], ...]:
    """Scan the captured 20 KiB RAM for complete validated slave-side frames.

    A negative result is *limited to these non-atomic recorded RAM images*;
    it cannot rule out transient UART traffic between 32-byte reads.
    """
    if type(img) is not bytes or len(img)!=20_480 or type(source_class) is not int:
        raise audit.EvidenceRejected('exact historical RAM image/source class required')
    needle=bytes((0,source_class))
    findings=[]
    start=0
    while True:
        idx=img.find(needle,start)
        if idx<0 or idx>len(img)-8:break
        start=idx+1
        cmd=img[idx+2]
        if cmd not in FRAME_CLASS11_COMMANDS:continue
        length=img[idx+3]
        if not 8<=length<=32 or idx+length>len(img):continue
        f=img[idx:idx+length]
        if f[3]!=len(f) or f[4] not in (1,2,3) or f[5]!=1:continue
        if audit.crc16_kermit(f)==0:
            findings.append((0x400+idx,f.hex()))
    return tuple(findings)


def fullram_context(tar:tarfile.TarFile, *, count:int=79,
                    include_block_timeline:bool=True) -> dict:
    if type(count) is not int or not 1<=count<=79:
        raise audit.EvidenceRejected('valid complete snapshot count required')
    mf=audit._manifest(tar,'p300-fullram')
    frames=Counter();meta=Counter();association=Counter()
    pointer_hits=Counter(); class11_hits=[]
    special_samples=[]
    for i in range(1,count+1):
        name=f'snapshots/s{i:05d}'
        obj=json.loads(audit._verified(tar,mf,'p300-fullram',name+'.json',max_size=8_000))
        b=audit._verified(tar,mf,'p300-fullram',name+'.bin',max_size=20_480)
        if (len(b)!=20_480 or obj.get('complete') is not True
            or obj.get('marker')!='COMPLETE' or obj.get('device_id')!='20c2'
            or obj.get('software')!='0103' or obj.get('bytes_stored')!=20_480
            or obj.get('range_start')!='0x0400' or obj.get('range_last_inclusive')!='0x53ff'
            or obj.get('direction') not in ('ascending','descending')):
            raise audit.EvidenceRejected('unverified/malformed fullram snapshot')
        off=0x1640-0x400
        parsed=audit.parse_1640_block(b[off:off+32])
        f=parsed['frame_hex']; m=b[META_MEM-0x400:META_MEM-0x400+3].hex()
        frames[f]+=1;meta[m]+=1;association[(f,m)]+=1
        if b[POINTER_CANDIDATE-0x400:POINTER_CANDIDATE-0x400+2]==RX_MEM.to_bytes(2,'little'):
            pointer_hits[b[POINTER_CANDIDATE-0x400:POINTER_CANDIDATE-0x400+4].hex()]+=1
        class11_hits.extend((i,addr,fhex) for addr,fhex in frame_hits(b))
        if f!=audit.KNOWN_REPLY_HEX[0]:
            tx=b[TX_MEM-0x400:TX_MEM-0x400+22]
            size=tx[3]
            special_samples.append({
                'snapshot_id':i, 'scan_direction':obj['direction'],
                'observed_rx_hex':f, 'neighbor_meta_166a_166c':m,
                'tx_sample_at_161a_hex':tx[:min(size,22)].hex(),
                'tx_rx_atomic':False,
            })
    report={
      'model':'OFFLINE_OPTOLINK_RX_CONTEXT_NOT_LIVE_UART1_RX',
      'complete_snapshots_covered':count,
      'rx_variant_counts':dict(sorted(frames.items())),
      'metadata_166a_166c_counts':dict(sorted(meta.items())),
      'rx_metadata_pairs':[
          {'rx_hex':k[0],'metadata_166a_166c_hex':k[1],'snapshots':v}
          for k,v in sorted(association.items())],
      'class11_slave_frames_found_in_readable_20k_ram':len(class11_hits),
      'class11_slave_frame_hits':[
          {'snapshot_id':i,'address':hex(addr),'frame_hex':f}
          for i,addr,f in class11_hits[:8]],
      'class11_search_scope':'79_INDEPENDENT_NONATOMIC_20K_RAM_SCANS_NOT_ONWIRE_TRAFFIC',
      'possible_pointer_0b6d_to_1642':dict(sorted(pointer_hits.items())),
      'pointer_ownership_proven':False,
      'special_samples':special_samples,
      'physical_uart1_rx_verified':False,
      'controller_write_authorized':False,
      'new_hardware_io':False,
    }
    if include_block_timeline:
        report['snapshot_64_read_timeline']=fullram_snapshot_timeline(tar,mf,64)
    return report


def fullram_snapshot_timeline(tar:tarfile.TarFile, manifest:dict,
                              snapshot_id:int=64) -> dict:
    """Independently hash the 34.6 MB block trace before reporting read order.

    The metadata and RX frame in snapshot 64 were from different FC03 reads.
    We must NEVER call them simultaneous or infer ISR causality.
    """
    if type(snapshot_id) is not int or not 1<=snapshot_id<=79:
        raise audit.EvidenceRejected('only complete historical snapshots allowed')
    raw=audit._verified(tar,manifest,'p300-fullram','blocks.jsonl',max_size=36_000_000)
    hits={};rows=0
    for line in raw.splitlines():
        # Filter before JSON decoding to avoid materializing 51,200 full records.
        if f'"snapshot_id":{snapshot_id},'.encode() not in line and not line.endswith(f'"snapshot_id":{snapshot_id}}}'.encode()):
            continue
        rec=json.loads(line)
        rows+=1
        address=rec.get('address')
        if address not in TRACE_ADDRESS:continue
        if (address in hits or rec.get('result')!='OK'
                or rec.get('checksum_valid') is not True
                or rec.get('fc')!=3 or rec.get('length')!=32
                or rec.get('response_address')!=address):
            raise audit.EvidenceRejected('timeline integrity/duplicate FC03 block')
        hits[address]=rec
    if rows!=640 or set(hits)!=set(TRACE_ADDRESS):
        raise audit.EvidenceRejected('fullram 640-block snapshot timeline incomplete')
    ordered=sorted(hits.values(),key=lambda x:x['rx_monotonic'])
    order=[x['address'] for x in ordered]
    # Byte payload crosscheck against the independently verified image.
    name=f'snapshots/s{snapshot_id:05d}.bin'
    image=audit._verified(tar,manifest,'p300-fullram',name,max_size=20_480)
    timeline=[]
    start=ordered[0]['rx_monotonic']
    for rec in ordered:
        address=rec['address'];i=int(address,16)-0x400
        data=bytes.fromhex(rec['payload_hex'])
        if len(data)!=32 or image[i:i+32]!=data:
            raise audit.EvidenceRejected('block payload disagrees with archived RAM image')
        timeline.append({'address':address,'rx_utc':rec['rx_utc'],
                         'delta_from_first_ms':round((rec['rx_monotonic']-start)*1000,3)})
    return {'snapshot_id':snapshot_id,'blocks_verified_for_snapshot':rows,
            'read_order':order,'events':timeline,'all_reads_atomic':False,
            'true_uart1_interrupt_timing_proven':False}


def _block(obj:dict,name:str,addr:str) -> bytes:
    entry=obj.get('reads',{}).get(name)
    if not isinstance(entry,dict) or entry.get('address')!=addr or \
        entry.get('fc')!=3 or entry.get('length')!=32:
        raise audit.EvidenceRejected('unverified Deep source block: '+name)
    try:data=bytes.fromhex(entry['hex'])
    except (KeyError,ValueError,TypeError) as exc:
        raise audit.EvidenceRejected('malformed Deep source hex: '+name) from exc
    if len(data)!=32:
        raise audit.EvidenceRejected('Deep source length mismatch: '+name)
    return data


def deep_context(tar:tarfile.TarFile) -> dict:
    mf=audit._manifest(tar,'p300-deep')
    data=audit._verified(tar,mf,'p300-deep','p300.jsonl',max_size=5_000_000)
    kinds=Counter();valid=Counter();events=[];total=0
    for line in data.splitlines():
        r=json.loads(line)
        if 'ram_1640' not in r.get('reads',{}):continue
        total+=1
        a=_block(r,'ram_1600','0x1600')
        b=_block(r,'ram_1620','0x1620')
        rx=_block(r,'ram_1640','0x1640')
        rx_decoded=audit.parse_1640_block(rx)['frame_hex']
        # Master TX spans two successive, non-atomic FC03 reads.
        tx=a[TX_MEM-0x1600:]+b
        size=tx[3]
        tx_frame=tx[:size] if 8<=size<=22 else b''
        tx_ok=(len(tx_frame)==size and tx_frame[3]==size
               and audit.crc16_kermit(tx_frame)==0)
        kinds[tx[:3].hex()]+=1
        valid['VALID' if tx_ok else 'UNVERIFIED_NONATOMIC']+=1
        if rx_decoded!=audit.KNOWN_REPLY_HEX[0] or (tx[:3]==b'\x01\x00\x31' and size==9):
            timing=r['reads']
            t1=timing['ram_1600'].get('t_monotonic')
            t2=timing['ram_1620'].get('t_monotonic')
            t3=timing['ram_1640'].get('t_monotonic')
            if (any(type(x) not in (int,float) or not math.isfinite(x)
                    for x in (t1,t2,t3)) or not t1<t2<t3):
                raise audit.EvidenceRejected('Deep sampling order is not verified')
            events.append({
                'index':r['index'],'uart1_master_tx_hex':tx_frame.hex() if tx_ok else None,
                'uart1_master_tx_header_hex':tx[:3].hex(),
                'observed_rx_hex':rx_decoded,
                'rx_minus_tx1600_ms':round((t3-t1)*1000,3),
                'rx_minus_tx1620_ms':round((t3-t2)*1000,3),
                'reads_are_simultaneous':False,
                'causality_proven':False,
            })
    if total<1:
        raise audit.EvidenceRejected('Deep no historical RX candidate samples')
    return {
       'model':'OFFLINE_OPTOLINK_RX_TX_CORRELATION_NOT_ONWIRE_CAUSALITY',
       'paired_1640_contexts':total,
       'paired_tx_header_counts':dict(sorted(kinds.items())),
       'tx_crc_validity':dict(sorted(valid.items())),
       'special_events':events,
       'proven_vitotrol_slave_responses':0,
       'physical_uart1_rx_verified':False,
       'controller_write_authorized':False,
       'new_hardware_io':False,
    }


def inspect_bundle(kind:str,raw:bytes) -> dict:
    if kind not in audit.KNOWN_ARCHIVES or type(raw) is not bytes or \
       not 0<len(raw)<=audit.MAX_ARCHIVE_BYTES:
        raise audit.EvidenceRejected('bounded historical archive source required')
    # Reuse the prior hash-attested baseline; verify original SHA and members.
    baseline=audit.audit_bundle(kind,raw)
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as tar:
        context=(fullram_context(tar) if kind=='fullram' else deep_context(tar))
    return {'archive_kind':kind,'archive_sha256':baseline['archive_sha256'],
            'verified_baseline_crc_samples':baseline['frames_sampled'],
            'context':context,'live_controller_reads':0,'live_controller_writes':0}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind',required=True,choices=tuple(audit.KNOWN_ARCHIVES))
    parser.add_argument('--archive',default='-',help='offline archive path, or - for binary stdin')
    args=parser.parse_args()
    if args.archive=='-':
        raw=sys.stdin.buffer.read(audit.MAX_ARCHIVE_BYTES+1)
    else:
        path=Path(args.archive)
        if path.stat().st_size>audit.MAX_ARCHIVE_BYTES:
            raise audit.EvidenceRejected('oversize archive')
        raw=path.read_bytes()
    print(json.dumps(inspect_bundle(args.kind,raw),sort_keys=True,indent=2))


if __name__=='__main__':
    main()
