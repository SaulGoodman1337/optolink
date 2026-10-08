import copy
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

P=Path(__file__).resolve().parents[1]/'tools/audit-p87-full-recordings.py'
spec=importlib.util.spec_from_file_location('audit_full',P)
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)


def reply(data):
    f=bytes.fromhex('4110010155d30b')+data
    return b'\x06'+f+bytes([sum(f[1:])&255])


def measurement():
    rows=[];trace=[]
    for i,(stamp,block) in enumerate([(10.1,'00abab0000010000000001'),(11.2,'45abab0000210b60004221'),(12.3,'00abab0000010000000001')],1):
        raw=bytes.fromhex(block)
        trace.extend([{'direction':'TX','hex':a.REQUEST,'t_monotonic':stamp},
                      {'direction':'RX','hex':reply(raw).hex(),'t_monotonic':stamp+.05},
                      {'direction':'TX','hex':'06','t_monotonic':stamp+.051}])
        rows.append({'index':i,'elapsed_s':stamp+.062-10,'native_block':block,'native_b7':f'{raw[7]:02x}'})
    return {'p300_phase_start_monotonic':10.,'p300_phase_end_monotonic':13.,'samples':rows,'trace':trace}


class WireAuditTests(unittest.TestCase):
    def test_valid_matching_frames(self):
        r=a.audit_trace(measurement());self.assertEqual(r['valid_matching_replies'],3)
    def test_payload_tamper_detected(self):
        m=measurement();m['samples'][0]['native_block']='01'+m['samples'][0]['native_block'][2:]
        with self.assertRaises(a.AuditError):a.audit_trace(m)
    def test_checksum_tamper_detected(self):
        m=measurement();m['trace'][1]['hex']=m['trace'][1]['hex'][:-2]+'00'
        with self.assertRaises(a.AuditError):a.audit_trace(m)
    def test_unexpected_gfa_tx_detected(self):
        m=measurement();m['trace'].insert(1,{'direction':'TX','hex':'6b400601','t_monotonic':10.12})
        with self.assertRaises(a.AuditError):a.audit_trace(m)
    def test_response_ack_required(self):
        m=measurement();m['trace'][2]['hex']='04'
        with self.assertRaises(a.AuditError):a.audit_trace(m)
    def test_trace_order_required(self):
        m=measurement();m['trace'][1]['t_monotonic']=1.
        with self.assertRaises(a.AuditError):a.audit_trace(m)
    def test_sample_count_required(self):
        m=measurement();m['samples'].pop()
        with self.assertRaises(a.AuditError):a.audit_trace(m)
    def test_wrong_address_rejected(self):
        raw=bytearray(reply(bytes(11)));raw[6]=0xd4;raw[-1]=sum(raw[2:-1])&255
        with self.assertRaises(a.AuditError):a.decode_reply(bytes(raw))
    def test_extra_ack_reported(self):
        m=measurement();m['trace'][1]['hex']='06'+m['trace'][1]['hex']
        self.assertEqual(a.audit_trace(m)['request_ack_repetitions'],1)
    def test_flame_sample_windows(self):
        r=a.flag_windows(measurement()['samples']);self.assertEqual(len(r),1)
        self.assertEqual(r[0]['on_sample_count'],1)
        self.assertLess(r[0]['sample_bracket_min_s'],r[0]['sample_bracket_max_s'])


class InputTests(unittest.TestCase):
    def archive(self,name,kind=None):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        path=Path(self.tmp.name)/'a.tar.gz'
        with tarfile.open(path,'w:gz') as t:
            info=tarfile.TarInfo(name);info.size=2
            if kind:info.type=kind;info.linkname='/etc/passwd';info.size=0
            t.addfile(info,io.BytesIO(b'{}') if not kind else None)
        return path
    def test_path_escape(self):
        with self.assertRaises(a.AuditError):a.read_archive(self.archive('../measurement.json'))
    def test_symlink_refused(self):
        with self.assertRaises(a.AuditError):a.read_archive(self.archive('run-20261008T134132Z-1/measurement.json',tarfile.SYMTYPE))
    def test_incomplete_refused(self):
        with self.assertRaises(a.AuditError):a.read_archive(self.archive('run-20261008T134132Z-1/measurement.json'))
    def test_duplicate_json_key(self):
        with self.assertRaises(a.AuditError):a.decode('{"x":1,"x":2}')
    def test_nonfinite_json(self):
        with self.assertRaises(a.AuditError):a.decode('{"x":NaN}')


if __name__=='__main__':unittest.main()
