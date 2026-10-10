"""Independent synthetic fixtures for the Optolink-only RX topology audit."""
from __future__ import annotations
import ast
from collections import Counter
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
import unittest

TOOLS=Path(__file__).resolve().parents[1]/'tools'
SRC=TOOLS/'wb2a-vitotrol-optolink-rx-context.py'
spec=importlib.util.spec_from_file_location('rx_context_testing',SRC)
context=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=context
spec.loader.exec_module(context)
audit=context.audit
B1=bytes.fromhex('0001b10a010110fe23d8')
B1_RARE=bytes.fromhex('0001b10a010100004353')
CLASS11=bytes.fromhex('001180080101f95c')  # externally recorded, CRC-valid


def add(tar:tarfile.TarFile, name:str, content:bytes):
    info=tarfile.TarInfo(name)
    info.size=len(content)
    tar.addfile(info,io.BytesIO(content))


def ram_image(frame, *,meta,vitotrol=False):
    data=bytearray(20480)
    offset=0x1640-0x400
    data[offset:offset+32]=(b'\x00\x00'+frame+bytes.fromhex('fa01fb0122d1')).ljust(32,b'\x00')
    data[0x166a-0x400:0x166a-0x400+3]=bytes.fromhex(meta)
    data[0x0b6d-0x400:0x0b6d-0x400+4]=bytes.fromhex('42160afe')
    if vitotrol:data[0x2000-0x400:0x2000-0x400+len(CLASS11)]=CLASS11
    return bytes(data)


def fake_fullram(*,vitotrol=False):
    buf=io.BytesIO();files={}
    with tarfile.open(fileobj=buf,mode='w:gz') as tar:
        for i,rx,meta in ((1,B1,'060001'),(2,B1_RARE,'0a0401')):
            img=ram_image(rx,meta=meta,vitotrol=vitotrol and i==2)
            m={'device_id':'20c2','software':'0103','marker':'COMPLETE','complete':True,
               'bytes_stored':20480,'range_start':'0x0400','range_last_inclusive':'0x53ff',
               'direction':'ascending' if i==1 else 'descending'}
            for name,data in ((f'snapshots/s{i:05d}.json',json.dumps(m).encode()),
                              (f'snapshots/s{i:05d}.bin',img)):
                add(tar,'p300-fullram/'+name,data)
                files[name]={'size':len(data),'sha256':hashlib.sha256(data).hexdigest()}
        add(tar,'p300-fullram/bundle-manifest.json',json.dumps({'files':files}).encode())
    return buf.getvalue()


def deep_row(index,request,rx,t=100.0):
    assert len(request)==9
    a=bytearray(32)
    b=bytearray(32)
    a[26:]=request[:6]
    b[:3]=request[6:]
    r=(b'\x00\x00'+rx+bytes.fromhex('fa01fb0122d1')).ljust(32,b'\x00')
    def entry(addr,raw,time):
        return {'address':addr,'fc':3,'length':32,'hex':raw.hex(),
                't_monotonic':time,'rx_utc':'2026-10-09T07:09:30+00:00'}
    return {'index':index,'reads':{
        'ram_1600':entry('0x1600',a,t),
        'ram_1620':entry('0x1620',b,t+0.16),
        'ram_1640':entry('0x1640',r,t+0.48),
    }}


def fake_deep(*,bad_address=False):
    row1=deep_row(145,bytes.fromhex('01003109010101074e'),B1_RARE)
    row2=deep_row(1417,bytes.fromhex('01003109010110a6ea'),B1,t=200)
    if bad_address:row1['reads']['ram_1640']['address']='0x1642'
    return _tar_with_deep_rows([row1,row2])


def _tar_with_deep_rows(rows):
    buf=io.BytesIO();data=('\n'.join(json.dumps(x,separators=(',',':')) for x in rows)+'\n').encode()
    with tarfile.open(fileobj=buf,mode='w:gz') as tar:
        add(tar,'p300-deep/p300.jsonl',data)
        add(tar,'p300-deep/bundle-manifest.json',json.dumps({'files':{
          'p300.jsonl':{'sha256':hashlib.sha256(data).hexdigest(),
                        'size_bytes':len(data)}}}).encode())
    return buf.getvalue()


def fake_timeline(*,tamper=False):
    image=ram_image(B1_RARE,meta='0a0401')
    rows=[]
    for i in range(640):
        address=0x53e0-32*i
        raw=image[address-0x400:address-0x400+32]
        if tamper and address==0x1640:raw=bytes(32)
        rows.append({'snapshot_id':64,'result':'OK','checksum_valid':True,
                     'fc':3,'length':32,'address':hex(address),
                     'response_address':hex(address),'payload_hex':raw.hex(),
                     'rx_monotonic':100+i*0.16,
                     'rx_utc':f'2026-10-09T10:51:{i%60:02d}+00:00'})
    stream=('\n'.join(json.dumps(x,separators=(',',':')) for x in rows)+'\n').encode()
    files={}
    buf=io.BytesIO()
    with tarfile.open(fileobj=buf,mode='w:gz') as tar:
        for name,data in (('blocks.jsonl',stream),('snapshots/s00064.bin',image)):
            add(tar,'p300-fullram/'+name,data)
            files[name]={'sha256':hashlib.sha256(data).hexdigest(),'size':len(data)}
        add(tar,'p300-fullram/bundle-manifest.json',json.dumps({'files':files}).encode())
    return buf.getvalue()


class RxContextTests(unittest.TestCase):
    def test_fullram_matrix_correlation_and_only_candidate_pointer(self):
        with tarfile.open(fileobj=io.BytesIO(fake_fullram()),mode='r:gz') as tar:
            report=context.fullram_context(tar,count=2,include_block_timeline=False)
        self.assertEqual(report['complete_snapshots_covered'],2)
        self.assertEqual(report['rx_variant_counts'],{B1.hex():1,B1_RARE.hex():1})
        self.assertEqual(report['metadata_166a_166c_counts'],
                         {'060001':1,'0a0401':1})
        self.assertEqual(report['possible_pointer_0b6d_to_1642'],{'42160afe':2})
        # Synthetic images contain one intentional little-endian RX literal.
        self.assertEqual(report['literal_16bit_address_occurrences_by_ram_offset']
                         ['0x1642'],{'0x0b6d':2})
        self.assertFalse(report['literal_address_match_proves_pointer'])
        self.assertEqual(report['class11_slave_frames_found_in_readable_20k_ram'],0)
        self.assertEqual(report['special_samples'][0]['snapshot_id'],2)
        self.assertFalse(report['pointer_ownership_proven'])
        self.assertFalse(report['physical_uart1_rx_verified'])
        self.assertFalse(report['controller_write_authorized'])

    def test_fullram_class11_positive_control_and_negative_control(self):
        with tarfile.open(fileobj=io.BytesIO(fake_fullram(vitotrol=True)),mode='r:gz') as tar:
            report=context.fullram_context(tar,count=2,include_block_timeline=False)
        self.assertEqual(report['class11_slave_frames_found_in_readable_20k_ram'],1)
        self.assertEqual(report['class11_slave_frame_hits'][0]['address'],'0x2000')
        self.assertEqual(report['class11_slave_frame_hits'][0]['frame_hex'],CLASS11.hex())
        data=bytearray(ram_image(B1,meta='060001',vitotrol=True))
        data[0x2000-0x400+7]^=1
        self.assertEqual(context.frame_hits(bytes(data)),())
        self.assertEqual(context.frame_hits(ram_image(B1,meta='060001')),())

    def test_fullram_rejects_invalid_count_and_image_size(self):
        for x in (None,0,False,-1,80,3.5):
            with self.subTest(x=x),self.assertRaises(audit.EvidenceRejected):
                with tarfile.open(fileobj=io.BytesIO(fake_fullram()),mode='r:gz') as tar:
                    context.fullram_context(tar,count=x,include_block_timeline=False)
        with self.assertRaises(audit.EvidenceRejected):
            context.frame_hits(b'\x00'*400)

    def test_crc_invalid_torn_tx_frame_not_claimed_sent(self):
        with tarfile.open(fileobj=io.BytesIO(fake_deep()),mode='r:gz') as tar:
            r=context.deep_context(tar)
        self.assertEqual(r['paired_1640_contexts'],2)
        self.assertEqual(r['paired_tx_header_counts'],{'010031':2})
        self.assertEqual(r['tx_crc_validity'],{'UNVERIFIED_NONATOMIC':1,'VALID':1})
        self.assertEqual([x['index'] for x in r['special_events']],[145,1417])
        self.assertIsNone(r['special_events'][0]['uart1_master_tx_hex'])
        self.assertEqual(r['special_events'][0]['observed_rx_hex'],B1_RARE.hex())
        self.assertEqual(r['special_events'][1]['uart1_master_tx_hex'],
                         '01003109010110a6ea')
        self.assertEqual(r['special_events'][0]['rx_minus_tx1600_ms'],480.0)
        self.assertFalse(r['special_events'][0]['causality_proven'])
        self.assertFalse(r['controller_write_authorized'])

    def test_deep_invalid_address_and_timing_fails_closed(self):
        with tarfile.open(fileobj=io.BytesIO(fake_deep(bad_address=True)),mode='r:gz') as tar:
            with self.assertRaises(audit.EvidenceRejected):
                context.deep_context(tar)
        row=deep_row(145,bytes.fromhex('01003109010101074e'),B1_RARE)
        row['reads']['ram_1640']['t_monotonic']=99
        with tarfile.open(fileobj=io.BytesIO(_tar_with_deep_rows([row])),mode='r:gz') as tar:
            with self.assertRaises(audit.EvidenceRejected):
                context.deep_context(tar)

    def test_timeline_exact_640_trace_records_and_payload(self):
        with tarfile.open(fileobj=io.BytesIO(fake_timeline()),mode='r:gz') as tar:
            manifest=audit._manifest(tar,'p300-fullram')
            r=context.fullram_snapshot_timeline(tar,manifest)
        self.assertEqual(r['blocks_verified_for_snapshot'],640)
        self.assertEqual(r['read_order'],
                         ['0x1660','0x1640','0x1620','0x1600'])
        self.assertEqual([round(x['delta_from_first_ms']) for x in r['events']],
                         [0,160,320,480])
        self.assertFalse(r['all_reads_atomic'])
        self.assertFalse(r['true_uart1_interrupt_timing_proven'])

    def test_timeline_tampered_payload_fails_despite_hash_correct(self):
        with tarfile.open(fileobj=io.BytesIO(fake_timeline(tamper=True)),mode='r:gz') as tar:
            manifest=audit._manifest(tar,'p300-fullram')
            with self.assertRaises(audit.EvidenceRejected):
                context.fullram_snapshot_timeline(tar,manifest)

    def test_unknown_archives_rejected_and_no_live_io(self):
        for kind in ('fullr','Vitosoft','serial',''):
            with self.subTest(kind=kind),self.assertRaises(audit.EvidenceRejected):
                context.inspect_bundle(kind,b'invalid')
        tree=ast.parse(SRC.read_text())
        imports=set()
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):
                imports.update(a.name.split('.')[0] for a in node.names)
            if isinstance(node,ast.ImportFrom) and node.module:
                imports.add(node.module.split('.')[0])
        self.assertFalse(imports & {'serial','socket','paho','subprocess',
                                    'requests','ctypes','paramiko'})


if __name__=='__main__':
    unittest.main()
