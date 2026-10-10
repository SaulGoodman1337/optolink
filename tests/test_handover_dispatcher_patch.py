"""Static patch only: preserve pinned upstream's MQTT/TCP/poll and writes."""
import sys
from pathlib import Path
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from handover_acceleration.dispatcher_patch import patch_dispatcher, PatchRejected, main

UPSTREAM_EXCERPT='''import requests_util

def tcp_connection_loop():
        tcp_server.command_callback = do_special_command        # type: ignore

def do_poll_item(item, ser):
    retcode, data, val, _ = requests_util.response_to_request(item, ser)
    return retcode

def main():
    global _mock
    serOptolink = object()
    vidata = viconn_util.get_vicon_request()
    result = vs12_adapter.receive_telegr(True, True, serOptolink, serVitoConnnect, vicon_publ_callback)
    if True:
        if True:
                mod_mqtt.connect_mqtt()
                logger.info(f"{spr} protocol initialized")
                if False:
                                retcode = do_poll_item(poll_data, serOptolink, item_index=force_refresh_index)      # type: ignore
                a,b,c,d = requests_util.response_to_request(msg, serOptolink)
                a,b,c,d = requests_util.response_to_request(msg, serOptolink)
                if False:
                        retcode,_,_ = vs12_adapter.read_datapoint_ext(0xf8, 2, serOptolink)     # type: ignore
                # let cpu take a breath if there was nothing to do
'''


class PatchTests(unittest.TestCase):
    def test_all_three_dispatch_sites_are_patched_and_original_kept_as_legacy(self):
        result=patch_dispatcher(UPSTREAM_EXCERPT)
        self.assertEqual(result.count('handover_legacy_or_shim(item, ser)'),1)
        self.assertEqual(result.count('handover_legacy_or_shim(msg, serOptolink)'),2)
        self.assertEqual(result.count('requests_util.response_to_request(request, ser)'),1)
        self.assertEqual(result.count('viconn_util.get_vicon_request()'),1)
        self.assertEqual(result.count('vs12_adapter.read_datapoint_ext(0xf8, 2, serOptolink)'),1)
        self.assertIn('allow_maintenance=False',result)
        self.assertIn('OPTO_RESEARCH_DISPATCH_SHADOW',result)
        self.assertIn('OPTO_HYBRID_RUNTIME_DIAGNOSTIC', result)
        self.assertLess(result.index('install_before_mqtt_connect(mod_mqtt)'),
                        result.index('mod_mqtt.connect_mqtt()'))
        compile(result,'<mock-upstream>','exec')

    def test_feature_off_uses_unmodified_legacy_call(self):
        result=patch_dispatcher(UPSTREAM_EXCERPT)
        import types
        from unittest.mock import patch
        stub=types.ModuleType('requests_util')
        stub.response_to_request=lambda *xs:('delegated',xs)
        ns={}
        with patch.dict(sys.modules,{'requests_util':stub}):
            exec(result,ns)
        self.assertEqual(ns['handover_legacy_or_shim']('w;0x2303;1;1','serial'),
                         ('delegated',('w;0x2303;1;1','serial')))

    def test_shadow_seam_tracks_write_without_changing_legacy_result(self):
        from handover_acceleration.runtime_admission import (
            RuntimeAdmissionGate, DispatcherSnapshot,
        )
        from handover_acceleration.phase_planner import Budget
        from unittest.mock import patch
        import types
        original = []
        serial = object()
        expected = (1, bytearray(b'\\x01'), 1, '1;0x2303;1')
        stub = types.ModuleType('requests_util')
        stub.response_to_request = lambda *a: (original.append(a), expected)[1]
        ns = {}
        with patch.dict(sys.modules, {'requests_util': stub}):
            exec(patch_dispatcher(UPSTREAM_EXCERPT), ns)
        ns['_handover_dispatch_bridge'] = types.SimpleNamespace(
            response_to_request=stub.response_to_request)
        ns['_handover_runtime_gate'] = RuntimeAdmissionGate()
        self.assertIs(ns['handover_legacy_or_shim']('w;0x2303;1;1', serial),
                      expected)
        self.assertEqual(original, [('w;0x2303;1;1', serial)])
        gate = ns['_handover_runtime_gate']
        self.assertTrue(gate.unacknowledged_write)
        safe = DispatcherSnapshot(
            mqtt_pending=0, tcp_pending=0, forced_polls_pending=0,
            pending_readbacks=0, frame_idle=True, external_writers_quiesced=True,
            queue_admission_paused=True, legacy_vs1_verified=True,
            nearest_writer_deadline_ms=12000.0)
        self.assertEqual(gate.decide(safe, Budget()).reason,
                         'WRITE_READBACK_NOT_ACKNOWLEDGED')

    def test_refuse_second_patch(self):
        with self.assertRaises(PatchRejected):patch_dispatcher(patch_dispatcher(UPSTREAM_EXCERPT))

    def test_refuse_wrong_upstream_call_site_counts(self):
        for s in (UPSTREAM_EXCERPT.replace('response_to_request(msg, serOptolink)', 'response_to_request(msg, opto)',1),
                  UPSTREAM_EXCERPT.replace('viconn_util.get_vicon_request()', 'vicon_listener()'),
                  UPSTREAM_EXCERPT.replace('logger.info(f"{spr} protocol initialized")','')):
            with self.subTest(s=s[:80]), self.assertRaises(PatchRejected):patch_dispatcher(s)

    def test_never_modify_source_in_place(self):
        with tempfile.TemporaryDirectory() as d:
            s=Path(d)/'src.py';s.write_text(UPSTREAM_EXCERPT)
            with self.assertRaises(PatchRejected):
                main(['--source',str(s),'--output',str(s)])
            self.assertEqual(s.read_text(),UPSTREAM_EXCERPT)
            dfile=Path(d)/'patched.py'
            self.assertEqual(main(['--source',str(s),'--output',str(dfile)]),0)
            self.assertNotEqual(dfile.read_text(),s.read_text())

    def test_static_source_no_serial_systemd_or_production_mutation(self):
        for module_name in ('dispatcher_bridge.py','dispatcher_patch.py'):
            raw=(Path(__file__).resolve().parents[1]/'tools/handover_acceleration'/module_name).read_text()
            for token in ('import serial','systemctl stop','/opt/optolink/venv','serial_for_url('):
                with self.subTest(module=module_name,token=token):self.assertNotIn(token,raw)


if __name__=='__main__':
    unittest.main()
