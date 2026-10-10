import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

P=Path(__file__).resolve().parents[1]/'tools/wb2a-gfa-native-pair-check.py'
spec=importlib.util.spec_from_file_location('gfa_pair',P)
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)


def reading(name,raw,at):
    return {'name':name,'raw':raw,'sent':at,'received':at+.1,'latency_ms':100.}


def rows(p06a='93',p06b='93',p09a='93',p09b='93'):
    return [reading('p06',p06a,0),reading('p09',p09a,.2),
            reading('native_status','45abab0000210b62004221',.4),
            reading('p09',p09b,.6),reading('p06',p06b,.8)]


class PairTests(unittest.TestCase):
    def test_same_reference_not_auto_alias(self):
        r=a.pair(*rows());s=a.summarize([r]);self.assertFalse(s['production_alias_verified'])
        self.assertFalse(s['measured_vs_commanded_source_identified']);self.assertTrue(r['flame_bit'])
    def test_raw_values_kept_separate_from_percent(self):
        r=a.pair(*rows());self.assertEqual(r['p09']['before'],'93')
        self.assertEqual(r['native_b0'],69);self.assertEqual(r['native_b9'],66)
    def test_only_one_reference_changes(self):
        r=a.pair(*rows(p06b='94'));self.assertEqual(r['p06']['verdict'],'REFERENCE_CHANGED')
        self.assertEqual(r['p09']['verdict'],'STABLE_REFERENCE')
    def test_second_reference_changes(self):
        r=a.pair(*rows(p09b='91'));self.assertEqual(r['p09']['verdict'],'REFERENCE_CHANGED')
    def test_wide_outer_bracket(self):
        x=rows();x[-1]['sent']=3.;x[-1]['received']=3.1
        r=a.pair(*x);self.assertEqual(r['p06']['verdict'],'BRACKET_TOO_WIDE')
    def test_changed_and_stable_separation_not_conflated(self):
        r=a.pair(*rows(p06a='91',p06b='92'));self.assertFalse(r['stable_raw_p06_p09_differ'])
    def test_measured_demand_separation_visible(self):
        r=a.pair(*rows(p06a='91',p06b='91'));self.assertTrue(r['stable_raw_p06_p09_differ'])
    def test_static_zeros_inconclusive(self):
        r=a.pair(*rows('00','00','00','00'));self.assertEqual(a.summarize([r]*100)['outcome'],'INCONCLUSIVE_REFERENCE_COVERAGE')
    def test_empty_inconclusive(self):
        self.assertEqual(a.summarize([])['sample_count'],0)
    def test_ff_rejected_both_channels(self):
        for name in ('p06','p09'):
            with self.subTest(name=name),self.assertRaises(a.Error):a.valid_read(reading(name,'ff',0),name)
    def test_native_length_checked(self):
        x=rows();x[2]['raw']='00'
        with self.assertRaises(a.Error):a.pair(*x)
    def test_order_checked(self):
        x=rows();x[2]['sent']=0
        with self.assertRaises(a.Error):a.pair(*x)
    def test_unknown_read_denied(self):
        with self.assertRaises(a.Error):a.h.Receiver().begin('write')
    def test_exact_six_commands(self):
        self.assertEqual(len(a.h.READS),6)
        self.assertTrue(all(r[0].startswith(('r;','gfaread;')) for r in a.h.READS.values()))
        self.assertNotIn(0x4057,a.h.ADDRESSES)
    def test_retained_ignored_and_echo_required(self):
        rx=a.h.Receiver();cmd=rx.begin('p06');rx.message('response',b'1;0x4006;93',True)
        self.assertIsNone(rx.pending['value']);rx.message('command',cmd.encode())
        rx.message('response',b'1;0x4006;93');self.assertEqual(rx.finish()['raw'],'93')
    def test_collision_aborts(self):
        rx=a.h.Receiver();rx.begin('p06');rx.message('command',a.h.READS['p09'][0].encode())
        self.assertEqual(rx.error,'CONCURRENT_TRACKED_COMMAND')
    def test_fixed_round_order(self):
        class Client:
            def __init__(self):self.calls=[]
            def read(self,name):
                self.calls.append(name)
                raw={'p80':'20','p06':'93','p09':'93','native_status':'45abab0000210b62004221'}[name]
                return reading(name,raw,len(self.calls)*.2)
        c=Client();a.sample(c)
        self.assertEqual(c.calls,['p80','p06','p09','native_status','p09','p06'])
    def test_wrong_p80_stops(self):
        class Client:
            def __init__(self):self.calls=[]
            def read(self,name):self.calls.append(name);return reading(name,'21',0)
        c=Client()
        with self.assertRaises(a.Error):a.sample(c)
        self.assertEqual(c.calls,['p80'])
    def test_invalid_p06_stops_before_next_request(self):
        class Client:
            def __init__(self):self.calls=[]
            def read(self,name):self.calls.append(name);return reading(name,'20' if name=='p80' else 'ff',len(self.calls))
        c=Client()
        with self.assertRaises(a.Error):a.sample(c)
        self.assertEqual(c.calls,['p80','p06'])


class ExecutionTests(unittest.TestCase):
    def test_plan_inert(self):
        r=subprocess.run([sys.executable,str(P)],capture_output=True,text=True)
        self.assertEqual(r.returncode,0);self.assertIn('PLAN ONLY',r.stdout)
        self.assertNotIn('SESSION=',r.stdout)
    def test_duration_bounds(self):
        for seconds in ('0','901'):
            r=subprocess.run([sys.executable,str(P),'--seconds',seconds],capture_output=True)
            self.assertNotEqual(r.returncode,0)
    def test_helper_hash_required(self):
        with patch.object(a,'HELPER_SHA256','bad'),self.assertRaises(RuntimeError):a.load_helper()
    def test_complete_mocked_execution(self):
        class Receiver:retained_ignored=0
        class Client:
            def __init__(self,*args):self.receiver=Receiver();self.clock=0.;self.closed=False
            def read(self,name):
                raw={'device':'20c2','software':'0103','p80':'20','p06':'93','p09':'93','native_status':'45abab0000210b62004221'}[name]
                self.clock+=.2;return reading(name,raw,self.clock)
            def pump(self,seconds):pass
            def close(self):self.closed=True
        with tempfile.TemporaryDirectory() as temp,patch.object(a,'ROOT',Path(temp)/'results'),patch.object(a.h,'preflight',return_value={}),patch.object(a.h,'MQTT',Client),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(a.execute(30),0)
            report=json.loads(next(a.ROOT.glob('*/summary.json')).read_text())
        self.assertFalse(report['services_stopped']);self.assertFalse(report['device_writes'])
        self.assertEqual(len(report['rounds']),6)
        self.assertFalse(report['comparison']['production_alias_verified'])


if __name__=='__main__':unittest.main()
