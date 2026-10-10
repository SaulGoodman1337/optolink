"""Pure message/analysis tests plus a simulated MQTT peer; no network or serial."""
import ast
import contextlib
import io
import os
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

PATH = Path(__file__).parents[1] / 'tools/wb2a-p87-mirror-check.py'
spec = importlib.util.spec_from_file_location('p87_check', PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

CONFIG = '''
vs1protocol=True
port_vitoconnect=None
mqtt_broker="localhost:1883"
mqtt_user="user:password"
mqtt_listen="openv/cmnd"
mqtt_respond="openv/resp"
'''


def read(name, raw, sent, received):
    return dict(name=name, raw=raw, sent=sent, received=received)


def triple(before='60', value='60', after='60', span=.6):
    data = bytearray(11); data[7] = int(value, 16)
    return m.bracket(read('p87', before, .0, .1),
                     read('native_status', data.hex(), .2, .3),
                     read('p87', after, .4, .1+span))


class FormatTests(unittest.TestCase):
    def test_plan_does_not_import_network_client(self):
        out = subprocess.run([sys.executable, str(PATH)], capture_output=True, text=True, check=True)
        self.assertIn('PLAN ONLY', out.stdout)
        self.assertNotIn('paho', m.__dict__)
        self.assertNotIn('serial', m.__dict__)

    def test_six_fixed_read_requests_only(self):
        self.assertEqual(len(m.READS), 6)
        for command, address, width in m.READS.values():
            self.assertTrue(command.startswith(('r;', 'gfaread;')))
        self.assertNotIn(0x20A5, m.ADDRESSES)
        self.assertNotIn(0x55DA, m.ADDRESSES)

    def test_config_unchanged_value_and_secret_not_in_plan(self):
        self.assertTrue(m.config(CONFIG)['vs1protocol'])

    def test_conditional_settings_refused(self):
        with self.assertRaises(m.CheckError): m.config(CONFIG + '\nif True:\n mqtt_broker="x:1"\n')

    def test_dynamic_settings_refused(self):
        with self.assertRaises(m.CheckError): m.config(CONFIG + '\nmqtt_broker=str(123)\n')

    def test_other_protocol_refused(self):
        with self.assertRaises(m.CheckError): m.config(CONFIG.replace('True', 'False'))

    def test_wildcard_or_identical_topics_refused(self):
        for cfg in (CONFIG.replace('openv/resp', 'openv/#'), CONFIG.replace('openv/resp', 'openv/cmnd')):
            with self.assertRaises(m.CheckError): m.config(cfg)

    def test_nondefault_response_format_refused(self):
        with self.assertRaises(m.CheckError): m.config(CONFIG + '\nretcode_format="x"\n')

    def test_valid_response(self):
        self.assertEqual(m.response('1;0x4057;60',0x4057,1), b'\x60')

    def test_invalid_response_code_length_and_address(self):
        for s in ('3;0x4057;60','1;0x4056;60','1;0x4057;0060','1;0x4057;zz','1;0x4057;60;x'):
            with self.assertRaises(m.CheckError): m.response(s,0x4057,1)

    def test_gfa_ff_rejected(self):
        with self.assertRaises(m.CheckError): m.response('1;0x4057;ff',0x4057,1)


class ReceiverTests(unittest.TestCase):
    def setUp(self): self.r = m.Receiver(clock=lambda: 1.0)

    def echo(self):
        cmd=self.r.begin('p87'); self.r.message('command',cmd.encode())

    def test_retained_response_ignored(self):
        self.echo(); self.r.message('response',b'1;0x4057;60',True)
        self.assertIsNone(self.r.pending['value'])
        self.assertEqual(self.r.retained_ignored,1)

    def test_response_before_command_echo_refused(self):
        self.r.begin('p87');self.r.message('response',b'1;0x4057;60')
        with self.assertRaises(m.CheckError):self.r.finish()

    def test_own_echo_then_reply(self):
        self.echo();self.r.message('response',b'1;0x4057;60')
        self.assertEqual(self.r.finish()['raw'],'60')

    def test_second_command_refused(self):
        self.echo();self.r.message('command',m.READS['p87'][0].encode())
        with self.assertRaises(m.CheckError):self.r.finish()

    def test_unrelated_response_ignored(self):
        self.echo();self.r.message('response',b'1;0x0810;c801')
        self.assertIsNone(self.r.pending['value']);self.assertIsNone(self.r.error)

    def test_duplicate_response_refused(self):
        self.echo();self.r.message('response',b'1;0x4057;60');self.r.message('response',b'1;0x4057;60')
        with self.assertRaises(m.CheckError):self.r.finish()

    def test_idle_other_client_conflict(self):
        self.r.message('command',m.READS['native_status'][0].encode())
        self.assertEqual(self.r.error,'CONCURRENT_TRACKED_COMMAND')

    def test_generic_read_same_address_is_conflict(self):
        self.r.message('command',b'request;0x01;0x4057;1')
        self.assertEqual(self.r.error,'CONCURRENT_TRACKED_COMMAND')

    def test_unlisted_command_name_refused(self):
        with self.assertRaises(m.CheckError):self.r.begin('write')


class BracketTests(unittest.TestCase):
    def test_match(self): self.assertEqual(triple()['verdict'],'STABLE_MATCH')
    def test_mismatch(self): self.assertEqual(triple(value='62')['verdict'],'STABLE_MISMATCH')
    def test_transition_not_mismatch(self): self.assertEqual(triple(after='62')['verdict'],'TRANSITION_AMBIGUOUS')
    def test_wide_bracket_not_validated(self): self.assertEqual(triple(span=3)['verdict'],'BRACKET_TOO_WIDE')
    def test_no_samples_inconclusive(self):self.assertEqual(m.summarize([])['outcome'],'INCONCLUSIVE_STATE_COVERAGE')
    def test_many_zeros_inconclusive(self):
        self.assertEqual(m.summarize([triple('00','00','00')]*100)['outcome'],'INCONCLUSIVE_STATE_COVERAGE')
    def test_one_static_nonzero_inconclusive(self):
        self.assertEqual(m.summarize([triple()]*100)['outcome'],'INCONCLUSIVE_STATE_COVERAGE')
    def test_dynamic_matches_support_only_candidate(self):
        rows=[triple(x,x,x) for x in ['00','20','40','60','62']]*3
        out=m.summarize(rows)
        self.assertEqual(out['outcome'],'CANDIDATE_SUPPORTED_ON_SAMPLED_STATES')
        self.assertFalse(out['production_alias_verified']);self.assertFalse(out['p300_freshness_verified'])
    def test_any_mismatch_not_hidden(self):
        out=m.summarize([triple()]*20 + [triple(value='62')])
        self.assertEqual(out['outcome'],'MISMATCH_OBSERVED_NEEDS_REVIEW')
    def test_timestamp_order_checked(self):
        with self.assertRaises(m.CheckError):
            m.bracket(read('p87','60',1,2),read('native_status','00'*11,1,2),read('p87','60',3,4))


class SimulatedMQTTTests(unittest.TestCase):
    def test_subscribe_publish_and_reply(self):
        clock=[0.0];holder={}
        good=SimpleNamespace(is_failure=False)
        class FakeClient:
            def __init__(self,*args,**kwargs): self.events=[];self.sent=[];holder['client']=self
            def username_pw_set(self,*args):pass
            def connect(self,*args,**kwargs):self.events.append(lambda:self.on_connect(self,None,None,good,None))
            def subscribe(self,topics):
                self.events.append(lambda:self.on_subscribe(self,None,7,[good,good],None));return 0,7
            def publish(self,topic,payload,**kwargs):
                self.sent.append((topic,payload,kwargs))
                self.events.extend([
                  lambda:self.on_message(self,None,SimpleNamespace(topic='openv/cmnd',payload=payload.encode(),retain=False)),
                  lambda:self.on_message(self,None,SimpleNamespace(topic='openv/resp',payload=b'1;0x4057;60',retain=False))])
                return SimpleNamespace(rc=0)
            def loop(self,timeout):
                clock[0]+=.05
                if self.events:self.events.pop(0)()
                return 0
            def disconnect(self):pass
        fake=SimpleNamespace(Client=FakeClient,CallbackAPIVersion=SimpleNamespace(VERSION2=2),MQTTv311=4)
        with patch.dict(sys.modules,{'paho':SimpleNamespace(mqtt=SimpleNamespace(client=fake)),
                                    'paho.mqtt':SimpleNamespace(client=fake),'paho.mqtt.client':fake}), \
             patch.object(m.time,'monotonic',side_effect=lambda:clock[0]):
            client=m.MQTT(m.config(CONFIG))
            row=client.read('p87'); client.close()
        self.assertEqual(row['raw'],'60')
        self.assertEqual(holder['client'].sent[0][2],dict(qos=0,retain=False))


class ExecutionTests(unittest.TestCase):
    def exercise(self, wrong_identity=False):
        clock=[100.0]; calls=[]
        class FakeMQTT:
            def __init__(self, values):self.receiver=SimpleNamespace(retained_ignored=0)
            def read(self, name):
                calls.append(name); sent=clock[0];clock[0]+=.1
                raw={'device': '0000' if wrong_identity else '20c2', 'software':'0103',
                     'p80':'20','native_type':'20','p87':'00','native_status':'00'*11}[name]
                return read(name,raw,sent,clock[0])
            def pump(self, seconds):clock[0]+=seconds
            def close(self):calls.append('close')
        with tempfile.TemporaryDirectory() as td:
            real_open=os.open
            def open_lock(path,flags,mode):return real_open(str(Path(td)/'lock'),flags,mode)
            old_mask=os.umask(0o077)
            try:
                with patch.object(m,'ROOT',Path(td)/'results'),patch.object(m,'preflight',return_value={}), \
                     patch.object(m,'MQTT',FakeMQTT),patch.object(m.os,'open',side_effect=open_lock), \
                     patch.object(m.time,'monotonic',side_effect=lambda:clock[0]), \
                     patch.object(m.signal,'signal'),contextlib.redirect_stdout(io.StringIO()):
                    rc=m.execute(30)
                report_path=next((Path(td)/'results').glob('run-*/summary.json'))
                report=json.loads(report_path.read_text())
                self.assertEqual(report_path.stat().st_mode & 0o777,0o600)
            finally:os.umask(old_mask)
        return rc,report,calls

    def test_complete_idle_observation_remains_inconclusive(self):
        rc,report,calls=self.exercise()
        self.assertEqual(rc,0)
        self.assertEqual(report['comparison']['outcome'],'INCONCLUSIVE_STATE_COVERAGE')
        self.assertEqual(calls[:4],['device','software','p80','native_type'])
        self.assertFalse(report['services_stopped'])

    def test_wrong_device_stops_before_any_gfa(self):
        rc,report,calls=self.exercise(wrong_identity=True)
        self.assertEqual(rc,1)
        self.assertEqual(calls,['device','close'])
        self.assertEqual(report['comparison']['outcome'],'INCOMPLETE_OR_FAILED')


if __name__ == '__main__': unittest.main()
