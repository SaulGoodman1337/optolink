"""Offline-only consistency checks for the P06/P09 pair-recordings auditor."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'tools' / 'audit-gfa-native-pairs.py'
spec = importlib.util.spec_from_file_location('gfa_pair_audit', SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def sample():
    block = '2658970000210b62002121'
    reads = [
        {'name':'p06','raw':'53','sent':1.0,'received':1.1},
        {'name':'p09','raw':'53','sent':1.2,'received':1.3},
        {'name':'native_status','raw':block,'sent':1.4,'received':1.5},
        {'name':'p09','raw':'53','sent':1.6,'received':1.7},
        {'name':'p06','raw':'53','sent':1.8,'received':1.9},
    ]
    row = {
        'index':1, 'utc':'2026-10-08T00:00:00+00:00',
        'flame_bit':True, 'lockout_bit':False,
        'native_block':block,'native_b0':38,'native_b9':33,'native_b7':'62',
        'p06':{'before':'53','after':'53','verdict':'STABLE_REFERENCE','bracket_ms':800.0},
        'p09':{'before':'53','after':'53','verdict':'STABLE_REFERENCE','bracket_ms':400.0},
        'reads':reads, 'stable_raw_p06_p09_differ':False
    }
    summary = {
        'rounds':[copy.deepcopy(row)], 'errors':[], 'device_writes':False,
        'protocol_switched':False, 'services_stopped':False,
        'opening': {'device': {'raw': '20c2'}, 'software': {'raw': '0103'}, 'p80': {'raw': '20'}},
        'closing_p80': {'raw': '20'},
        'comparison':{'sample_count':1,'stable_p06_p09_separation_count':0,
          'production_alias_verified':False,'measured_vs_commanded_source_identified':False,
          'outcome':'PAIRS_RECORDED_NEEDS_ANALYSIS',
          'p06':{'counts':{'STABLE_REFERENCE':1}},'p09':{'counts':{'STABLE_REFERENCE':1}}}
    }
    return row,summary


class AuditTests(unittest.TestCase):
    def audit(self, mutate=None):
        row,summary = sample()
        if mutate:
            mutate(row,summary)
            summary['rounds']=[copy.deepcopy(row)]
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'pairs.jsonl';s=Path(d)/'summary.json'
            p.write_text(json.dumps(row)+'\n');s.write_text(json.dumps(summary))
            return mod.validate(p,s)

    def test_valid(self):
        out=self.audit()
        self.assertEqual(out['rounds_verified'],1)
        self.assertEqual(out['flame_samples'],1)
        self.assertFalse(out['p06_alias_verified'])

    def test_byte_mismatch(self):
        with self.assertRaisesRegex(ValueError,'Decoded native'):
            self.audit(lambda r,s:r.update(native_b9=34))

    def test_fake_read_order(self):
        with self.assertRaisesRegex(ValueError,'read order'):
            self.audit(lambda r,s:r['reads'][0].update(name='p09'))

    def test_false_stable(self):
        with self.assertRaisesRegex(ValueError,'False stable'):
            self.audit(lambda r,s:(r['p06'].update(after='54'), r['reads'][4].update(raw='54')))

    def test_bad_flame(self):
        with self.assertRaisesRegex(ValueError,'Decoded native'):
            self.audit(lambda r,s:r.update(flame_bit=False))

    def test_writes_present(self):
        with self.assertRaisesRegex(ValueError,'error-free VS1'):
            self.audit(lambda r,s:s.update(device_writes=True))

    def test_wrong_sample_count(self):
        with self.assertRaisesRegex(ValueError,'Sample count'):
            self.audit(lambda r,s:s['comparison'].update(sample_count=2))

    def test_wrong_count(self):
        with self.assertRaisesRegex(ValueError,'verdict count'):
            self.audit(lambda r,s:s['comparison']['p09']['counts'].update(STABLE_REFERENCE=0))

    def test_alias_cannot_be_preapproved(self):
        with self.assertRaisesRegex(ValueError,'preapproved'):
            self.audit(lambda r,s:s['comparison'].update(production_alias_verified=True))

    def test_wrong_raw(self):
        with self.assertRaisesRegex(ValueError,'bracket differs'):
            self.audit(lambda r,s:r['reads'][4].update(raw='54'))

    def test_overlapping_timestamps(self):
        with self.assertRaisesRegex(ValueError,'Overlapping'):
            self.audit(lambda r,s:r['reads'][4].update(sent=1.6))


if __name__=='__main__':
    unittest.main()
