"""Pure offline regression for a newly found 0x1642 Optolink RAM RX candidate."""
from __future__ import annotations
import ast
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
import unittest

SRC=Path(__file__).resolve().parents[1]/'tools'/'wb2a-vitotrol-optolink-rx-audit.py'
spec=importlib.util.spec_from_file_location('wb2a_vitotrol_rx_audit',SRC)
mod=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=mod
spec.loader.exec_module(mod)


FIRST=bytes.fromhex('0001b10a010110fe23d8')
SECOND=bytes.fromhex('0001b10a010100004353')
TRAIL=bytes.fromhex('fa01fb0122d1')


def block(frame=FIRST,trail=TRAIL):
    return (b'\x00\x00'+frame+trail).ljust(32,b'\x00')


def member(tar,prefix,name,data):
    info=tarfile.TarInfo(prefix+'/'+name)
    info.size=len(data)
    tar.addfile(info,io.BytesIO(data))


def fake_fullram(*,malformed=False,include_partial=True):
    buf=io.BytesIO()
    files={}
    with tarfile.open(fileobj=buf,mode='w:gz') as tar:
        for i,fr in ((1,FIRST),(2,SECOND)):
            raw=bytearray(20480)
            start=0x1640-0x400
            raw[start:start+32]=block(fr)
            bin_name=f'snapshots/s{i:05}.bin'
            json_name=f'snapshots/s{i:05}.json'
            blob=bytes(raw)
            if malformed and i==2:
                blob=blob[:-1]
            meta={'device_id':'20c2','software':'0103','marker':'COMPLETE','complete':True,
                  'bytes_stored':20480,'range_start':'0x0400','range_last_inclusive':'0x53ff',
                  'direction':'ascending' if i==1 else 'descending',
                  'sha256':hashlib.sha256(bytes(raw)).hexdigest()}
            for name,data in ((bin_name,blob),(json_name,json.dumps(meta).encode())):
                member(tar,'p300-fullram',name,data)
                files[name]={'sha256':hashlib.sha256(data).hexdigest(),'size':len(data)}
        if include_partial:
            member(tar,'p300-fullram','snapshots/s00080.partial.bin',b'\x00'*20480)
        member(tar,'p300-fullram','bundle-manifest.json',json.dumps({'files':files}).encode())
    return buf.getvalue()


def fake_deep(*,wrong_fc=False):
    buf=io.BytesIO()
    rows=[{'index':1,'reads':{'native_55d3':{'hex':'00'}}},
          {'index':2,'reads':{'ram_1640':{'fc':3 if not wrong_fc else 4,
              'address':'0x1640','length':32,'hex':block().hex()}}},
          {'index':3,'reads':{'ram_1640':{'fc':3,
              'address':'0x1640','length':32,'hex':block(SECOND).hex()}}}]
    data=('\n'.join(json.dumps(x) for x in rows)+'\n').encode()
    files={'p300.jsonl':{'sha256':hashlib.sha256(data).hexdigest(),'size':len(data)}}
    with tarfile.open(fileobj=buf,mode='w:gz') as tar:
        member(tar,'p300-deep','p300.jsonl',data)
        member(tar,'p300-deep','bundle-manifest.json',json.dumps({'files':files}).encode())
    return buf.getvalue()


class OptolinkRxCandidateTests(unittest.TestCase):
    def test_two_exact_existing_class01_candidates(self):
        for f in (FIRST,SECOND):
            with self.subTest(f=f):
                d=mod.parse_1640_block(block(f))
                self.assertEqual(d['candidate_ram_address'],'0x1642')
                self.assertEqual(d['frame_hex'],f.hex())
                self.assertEqual(d['src_class'],'01')
                self.assertEqual(d['cmd'],'b1')
                self.assertFalse(d['uart1_rx_isr_proven'])
                self.assertFalse(d['controller_write_authorized'])
                self.assertEqual(mod.crc16_kermit(f),0)

    def test_rejects_wrong_direction_and_crc(self):
        for i in (0,1,2,4,5,7,8,9):
            raw=bytearray(block())
            raw[2+i]^=1
            with self.subTest(index=i),self.assertRaises(mod.EvidenceRejected):
                mod.parse_1640_block(bytes(raw))
        with self.assertRaises(mod.EvidenceRejected):
            mod.parse_1640_block(block().replace(b'\x00\x00',b'\x01\x00',1))

    def test_no_arbitrary_lengths_or_buffers_accepted(self):
        for val in (b'',b'\x00'*31,b'\x00'*33,bytes(range(32))):
            with self.subTest(val=val.hex()),self.assertRaises(mod.EvidenceRejected):
                mod.parse_1640_block(val)

    def test_crc_constrained_prior_identity_is_hypothetical(self):
        recovered=mod.reconstruct_stale_identity(TRAIL)
        self.assertEqual(recovered['status'],'CRC_CONSTRAINED_HYPOTHESIS_NOT_OBSERVED_FRAME')
        self.assertEqual(recovered['solutions'],1)
        self.assertEqual(recovered['hypothetical_f9_values'],['11'])
        self.assertEqual(recovered['candidate_frame_hex'],
                         ['0001b3100101f801f911fa01fb0122d1'])
        self.assertFalse(recovered['physical_rx_verified'])
        self.assertNotEqual(mod.reconstruct_stale_identity(b'\xff'*6)['solutions'],1)

    def test_fullram_alt_scan_directions_but_canonical_bytes(self):
        with tarfile.open(fileobj=io.BytesIO(fake_fullram()),mode='r:gz') as tar:
            report=mod.audit_fullram(tar,n=2)
        self.assertEqual(report['frames_sampled'],2)
        self.assertEqual(report['candidate_frames_crc_valid'],2)
        self.assertEqual(report['unique_frames'],{FIRST.hex():1,SECOND.hex():1})
        self.assertEqual(report['direction_counts'],{'ascending':1,'descending':1})
        self.assertFalse(report['partial_snapshot_80_included'])
        self.assertFalse(report['physical_uart1_rx_verified'])
        self.assertFalse(report['controller_write_authorized'])

    def test_fullram_malformed_length_and_member_hash_rejected(self):
        with tarfile.open(fileobj=io.BytesIO(fake_fullram(malformed=True)),mode='r:gz') as tar:
            with self.assertRaises(mod.EvidenceRejected):
                mod.audit_fullram(tar,n=2)
        for count in (-1,0,80,3.14,True):
            with self.subTest(count=count),self.assertRaises(mod.EvidenceRejected):
                with tarfile.open(fileobj=io.BytesIO(fake_fullram()),mode='r:gz') as tar:
                    mod.audit_fullram(tar,n=count)

    def test_deep_archive_exact_fc03_requests(self):
        blob=fake_deep()
        with tarfile.open(fileobj=io.BytesIO(blob),mode='r:gz') as tar:
            report=mod.audit_deep(tar)
        self.assertEqual(report['frames_sampled'],2)
        self.assertEqual(report['unique_frames'],{FIRST.hex():1,SECOND.hex():1})
        self.assertFalse(report['physical_uart1_rx_verified'])
        with tarfile.open(fileobj=io.BytesIO(fake_deep(wrong_fc=True)),mode='r:gz') as tar:
            with self.assertRaises(mod.EvidenceRejected):
                mod.audit_deep(tar)

    def test_archive_provenance_checked_before_parsing(self):
        blob=fake_deep()
        with self.assertRaises(mod.EvidenceRejected):
            mod.audit_bundle('deep',blob)
        report=mod.audit_bundle('deep',blob,known_hash=False)
        self.assertEqual(report['archive_sha256'],hashlib.sha256(blob).hexdigest())
        self.assertFalse(report['full_archive_hash_verified'])
        for bad in ('wrong','full_ram',''):
            with self.assertRaises(mod.EvidenceRejected):
                mod.audit_bundle(bad,blob,known_hash=False)

    def test_no_controller_transport_in_auditor(self):
        tree=ast.parse(SRC.read_text())
        imports=set()
        calls=set()
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):
                imports.update(i.name.split('.')[0] for i in node.names)
            if isinstance(node,ast.ImportFrom):
                imports.add((node.module or '').split('.')[0])
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
                if (node.func.attr!='open'
                        or not isinstance(node.func.value,ast.Name)
                        or node.func.value.id!='tarfile'):
                    calls.add(node.func.attr)
        self.assertFalse(imports & {'serial','socket','paho','subprocess','requests','ctypes'})
        self.assertFalse(calls & {'open','write','send','connect','publish','extract','extractall'})


if __name__=='__main__':
    unittest.main()
