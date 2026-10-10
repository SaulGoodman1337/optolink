"""Fail-closed tests for the offline-only WB2A P06 11-byte source audit."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

PATH = Path(__file__).resolve().parents[1] / 'tools' / 'audit-vdensho1-fan-source.py'
spec = importlib.util.spec_from_file_location('fan_source_audit', PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture():
    raw = '2658970000210b62002121'
    names = ['p06', 'p09', 'native_status', 'p09', 'p06']
    raws = ['53', '53', raw, '53', '53']
    reads = [
        {'name': n, 'raw': v, 'sent':1+i*0.2, 'received':1.1+i*0.2}
        for i,(n,v) in enumerate(zip(names,raws))
    ]
    row = {
        'index':1, 'reads':reads, 'native_block':raw,
        'native_b0':38, 'native_b9':33, 'native_b7':'62',
        'flame_bit':True, 'lockout_bit':False,
        'p06':{'before':'53','after':'53','verdict':'STABLE_REFERENCE','bracket_ms':800},
        'p09':{'before':'53','after':'53','verdict':'STABLE_REFERENCE','bracket_ms':400}}
    summary={
        'rounds':[copy.deepcopy(row)], 'errors':[],
        'protocol_switched':False,'services_stopped':False,'device_writes':False,
        'opening':{'device':{'raw':'20c2'},'software':{'raw':'0103'},'p80':{'raw':'20'}},
        'closing_p80':{'raw':'20'},
        'comparison':{'sample_count':1,'stable_p06_p09_separation_count':0,
                      'production_alias_verified':False,
                      'measured_vs_commanded_source_identified':False,
                      'p06':{'counts':{'STABLE_REFERENCE':1}},
                      'p09':{'counts':{'STABLE_REFERENCE':1}}}}
    return row,summary


class FanSourceAuditTests(unittest.TestCase):
    def audit(self, mutate=None):
        row,summary=fixture()
        if mutate:
            mutate(row,summary)
            summary['rounds']=[copy.deepcopy(row)]
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'pairs.jsonl'
            q=Path(folder)/'summary.json'
            p.write_text(json.dumps(row)+'\n')
            q.write_text(json.dumps(summary))
            return module.audit(p,q)

    def test_valid(self):
        result=self.audit()
        self.assertEqual(result['sample_count'],1)
        self.assertEqual(result['flame_samples'],1)
        self.assertFalse(result['found_production_p06_alias'])
        self.assertFalse(result['p300_production_approved'])
        self.assertTrue(all(not x['validated_independent_fan_actual'] for x in result['bytes']))

    def test_wrong_identity(self):
        with self.assertRaisesRegex(ValueError,'unexpected device'):
            self.audit(lambda row,summary:summary['opening']['device'].update(raw='20cb'))

    def test_wrong_p80(self):
        with self.assertRaisesRegex(ValueError,'unexpected device'):
            self.audit(lambda row,summary:summary['closing_p80'].update(raw='21'))

    def test_wrong_software(self):
        with self.assertRaisesRegex(ValueError,'unexpected device'):
            self.audit(lambda row,summary:summary['opening']['software'].update(raw='0104'))

    def test_write_rejected(self):
        with self.assertRaisesRegex(ValueError,'VS1-only'):
            self.audit(lambda row,summary:summary.update(device_writes=True))

    def test_switch_rejected(self):
        with self.assertRaisesRegex(ValueError,'VS1-only'):
            self.audit(lambda row,summary:summary.update(protocol_switched=True))

    def test_missing_sample_rejected(self):
        with self.assertRaisesRegex(ValueError,'rounds are incomplete'):
            self.audit(lambda row,summary:summary['comparison'].update(sample_count=2))

    def test_read_order_rejected(self):
        with self.assertRaisesRegex(ValueError,'read order'):
            self.audit(lambda row,summary:row['reads'][2].update(name='p06'))

    def test_wrong_status_length_rejected(self):
        with self.assertRaisesRegex(ValueError,'eleven-byte'):
            self.audit(lambda row,summary:(
                row.update(native_block='ab'), row['reads'][2].update(raw='ab')))

    def test_wrong_decoded_status_rejected(self):
        with self.assertRaisesRegex(ValueError,'source bytes'):
            self.audit(lambda row,summary:row.update(native_b9=99))

    def test_flame_decoding_rejected(self):
        with self.assertRaisesRegex(ValueError,'source bytes'):
            self.audit(lambda row,summary:row.update(flame_bit=False))

    def test_stale_raw_response_rejected(self):
        with self.assertRaisesRegex(ValueError,'source read'):
            self.audit(lambda row,summary:row['reads'][4].update(raw='54'))

    def test_false_stable_rejected(self):
        with self.assertRaisesRegex(ValueError,'invalid stable'):
            self.audit(lambda row,summary:(
                row['p06'].update(after='54'), row['reads'][4].update(raw='54')))

    def test_bad_bracket_timing_rejected(self):
        with self.assertRaisesRegex(ValueError,'timing inconsistent'):
            self.audit(lambda row,summary:row['p06'].update(bracket_ms=10))

    def test_bad_summary_counts_rejected(self):
        with self.assertRaisesRegex(ValueError,'counts disagree'):
            self.audit(lambda row,summary:summary['comparison']['p09']['counts'].update(STABLE_REFERENCE=2))

    def test_no_preapproved_alias(self):
        with self.assertRaisesRegex(ValueError,'unverified conversion'):
            self.audit(lambda row,summary:summary['comparison'].update(production_alias_verified=True))


if __name__=='__main__':
    unittest.main()
