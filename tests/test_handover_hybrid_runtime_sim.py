"""Compile and EXECUTE the generated original dispatcher under fake modules."""
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from handover_acceleration.dispatcher_patch import patch_dispatcher
from handover_acceleration import hybrid_boot
from test_handover_dispatcher_patch import UPSTREAM_EXCERPT


class OriginalMainloopIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.legacy_calls=[]
        def legacy(request,port):
            self.legacy_calls.append((request,port))
            return (1,bytearray(b'\x20'),'20','1;0x4050;20')
        self.requests=types.ModuleType('requests_util')
        self.requests.response_to_request=legacy
        self.ser_calls=[]
        self.adapter=types.SimpleNamespace(
            reset_vs1sync=lambda:self.ser_calls.append('reset'),
            receive_telegr=lambda *_:None,
            read_datapoint_ext=lambda *_:(1,0xf8,bytearray(b'\x20\xc2')))
        self.settings=types.SimpleNamespace(vs1protocol=True,port_vitoconnect=None)
        self.runtime={
            'settings':self.settings,
            'spr':'VS1',
            'serVitoConnnect':None,
            'vicon_publ_callback':None,
            'msg':'read;0x4006;1;raw;False',
            'mod_mqtt':types.SimpleNamespace(connect_mqtt=lambda:None,
                                              _hybrid_readback_ledger=None),
            'viconn_util':types.SimpleNamespace(get_vicon_request=lambda:None),
            'vs12_adapter':self.adapter,
            'logger':types.SimpleNamespace(info=lambda *_:None,error=lambda *_:None,exception=lambda *_:None),
        }
        self.program=patch_dispatcher(UPSTREAM_EXCERPT)

    def test_one_shot_exits_before_any_legacy_mqtt_or_tcp_dispatch(self):
        def fake_run(port,settings,legacy,resume,directory):
            self.ser_calls.append(('borrowed',port,settings,legacy,resume,directory))
            return {'status':'PASS_VERIFIED_BORROWED_PORT_FIXED_FC03'}
        env={'OPTO_RESEARCH_DISPATCH_SHADOW':'1',
             'OPTO_HYBRID_BOOT_ONESHOT':'confirmed-readonly',
             'OPTO_HYBRID_REPORT_DIR':'/tmp/private-hybrid-session'}
        with patch.dict(sys.modules,{'requests_util':self.requests}), \
             patch.dict(os.environ,env), \
             patch.object(hybrid_boot,'run_one_shot',side_effect=fake_run):
            exec(self.program,self.runtime)
            with self.assertRaises(SystemExit) as exc:self.runtime['main']()
        self.assertEqual(exc.exception.code,0)
        self.assertEqual(self.legacy_calls,[])
        self.assertEqual(self.ser_calls[0][0],'borrowed')
        self.assertIs(self.ser_calls[0][2],self.settings)
        self.assertIs(self.ser_calls[0][3],self.requests.response_to_request)
        self.assertIs(self.ser_calls[0][4],self.adapter.reset_vs1sync)

    def test_wrong_vitoconnect_profile_exits_before_any_probe(self):
        self.settings.port_vitoconnect='/dev/ttyS1'
        env={'OPTO_RESEARCH_DISPATCH_SHADOW':'1',
             'OPTO_HYBRID_BOOT_ONESHOT':'confirmed-readonly'}
        with patch.dict(sys.modules,{'requests_util':self.requests}), \
             patch.dict(os.environ,env), \
             patch.object(hybrid_boot,'run_one_shot',side_effect=AssertionError('forbidden')):
            exec(self.program,self.runtime)
            with self.assertRaises(SystemExit) as exc:self.runtime['main']()
        self.assertEqual(exc.exception.code,76)
        self.assertEqual(self.legacy_calls,[])

    def test_without_shadow_flag_boot_optin_is_rejected(self):
        env={'OPTO_HYBRID_BOOT_ONESHOT':'confirmed-readonly'}
        with patch.dict(sys.modules,{'requests_util':self.requests}), \
             patch.dict(os.environ,env,clear=True):
            exec(self.program,self.runtime)
            with self.assertRaises(SystemExit) as exc:self.runtime['main']()
        self.assertEqual(exc.exception.code,76)
        self.assertFalse(self.legacy_calls)

    def test_boot_failure_exits_nonzero_before_legacy_writes(self):
        env={'OPTO_RESEARCH_DISPATCH_SHADOW':'1',
             'OPTO_HYBRID_BOOT_ONESHOT':'confirmed-readonly',
             'OPTO_HYBRID_REPORT_DIR':'/tmp/private-hybrid-session'}
        with patch.dict(sys.modules,{'requests_util':self.requests}), \
             patch.dict(os.environ,env), \
             patch.object(hybrid_boot,'run_one_shot',side_effect=RuntimeError('crc bad')):
            exec(self.program,self.runtime)
            with self.assertRaises(SystemExit) as exc:self.runtime['main']()
        self.assertEqual(exc.exception.code,78)
        self.assertEqual(self.legacy_calls,[])

    def test_auto_never_starts_without_actual_enrolment(self):
        from handover_acceleration import runtime_enrollment
        from handover_acceleration.ingress_epoch import IngressEpoch
        import types
        fake_mqtt=types.SimpleNamespace(
            mqtt_client=None,cmnd_queue=[],lst_force_refresh=[],
            on_message=lambda *a:None,
            connect_mqtt=lambda:None,
            is_forced=lambda:None,force_delayed=lambda *a:None)
        class FakeTcp:
            def __init__(self,*a,**kw):self.received_data=''
            def _listen(self):pass
            def get_request(self):return ''
            def send(self,*a):pass
            def stop(self):pass
        self.runtime['mod_mqtt']=fake_mqtt
        self.runtime['c_tcpserver']=types.SimpleNamespace(TcpServer=FakeTcp)
        self.settings.mqtt_topic='research'
        self.settings.tcpip_port=None
        env={'OPTO_RESEARCH_DISPATCH_SHADOW':'1',
             'OPTO_HYBRID_RUNTIME_AUTO':'fenced-readonly'}
        with patch.dict(sys.modules,{'requests_util':self.requests}), \
             patch.dict(os.environ,env,clear=True), \
             patch.object(runtime_enrollment,'all_writers_attested',
                          return_value=False):
            exec(self.program,self.runtime)
            with self.assertRaises(SystemExit) as caught:
                self.runtime['main']()
        self.assertEqual(caught.exception.code,76)
        self.assertEqual(self.legacy_calls,[])
        self.assertTrue(callable(fake_mqtt._hybrid_complete_forced))
        self.assertIsInstance(self.runtime['_hybrid_ingress'],IngressEpoch)

    def test_auto_enrolled_shadow_sets_runtime_without_serial_io(self):
        from handover_acceleration import runtime_enrollment
        fake_mqtt=types.SimpleNamespace(
            mqtt_client=None,cmnd_queue=[],lst_force_refresh=[],
            on_message=lambda *a:None,
            connect_mqtt=lambda:None,
            is_forced=lambda:None,force_delayed=lambda *a:None)
        class FakeTcp:
            def __init__(self,*a,**kw):self.received_data=''
            def _listen(self):pass
            def get_request(self):return ''
            def send(self,*a):pass
            def stop(self):pass
        self.runtime['mod_mqtt']=fake_mqtt
        self.runtime['c_tcpserver']=types.SimpleNamespace(TcpServer=FakeTcp)
        self.settings.mqtt_topic='research'
        self.settings.tcpip_port=None
        env={'OPTO_RESEARCH_DISPATCH_SHADOW':'1',
             'OPTO_HYBRID_RUNTIME_AUTO':'fenced-readonly'}
        with patch.dict(sys.modules,{'requests_util':self.requests}), \
             patch.dict(os.environ,env,clear=True), \
             patch.object(runtime_enrollment,'all_writers_attested',
                          return_value=True):
            exec(self.program,self.runtime)
            self.runtime['main']()
        self.assertIsNotNone(self.runtime['_hybrid_auto'])
        self.assertIs(self.runtime['_hybrid_auto'].gate,
                      self.runtime['_handover_runtime_gate'])
        self.assertEqual(len(self.legacy_calls),2)
        self.assertEqual(self.ser_calls,[])

    def test_without_optin_original_mqtt_tcp_and_poll_seams_remain_legacy(self):
        # The feature may be deployed disabled without changing any request.
        with patch.dict(sys.modules,{'requests_util':self.requests}), \
             patch.dict(os.environ,{},clear=True):
            exec(self.program,self.runtime)
            self.runtime['main']()
        self.assertEqual(len(self.legacy_calls),2)
        self.assertEqual(self.legacy_calls[0][0],self.runtime['msg'])
        self.assertIn('legacy',str(self.program).lower())


if __name__=='__main__':unittest.main()
