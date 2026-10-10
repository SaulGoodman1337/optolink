"""Patched original entrypoint to full fake-wire FC03 batch and GFA return."""
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from handover_acceleration.dispatcher_patch import patch_dispatcher
from handover_acceleration.coordinator import EOT, P300_ID, DEVICE_ID
from test_handover_acceleration import FakePort, expect_vs1, expect_attached_vs1, expect_p300, p300_reply
from test_handover_fc03_fixed import response
from test_handover_dispatcher_patch import UPSTREAM_EXCERPT


class EntryPointEndToEndTests(unittest.TestCase):
    def test_actual_patch_entrypoint_borrows_exact_original_port_and_restores_gfa(self):
        seq = (expect_attached_vs1() + expect_p300() +
               [(P300_ID,p300_reply(0x00f8,DEVICE_ID)),(b'\x06',b'')] +
               response('ram_0f20_32') + response('ram_1c60_32') + expect_vs1(1))
        port=FakePort(seq)
        # Exercise same main function, actual bridge, coordinator and fixed
        # transport frames. The only fake parts are the serial peer and the
        # read-only original MQTT GFA parser.
        source=UPSTREAM_EXCERPT.replace('serOptolink = object()',
                                        'serOptolink = ORIGINAL_SERIAL')
        original_requests=[]
        def legacy(req,handle):
            self.assertIs(handle,port)
            original_requests.append(req)
            raw=b'\x20' if '0x4050' in req else b'\x00'
            return (1,bytearray(raw),raw.hex(),'1;0x4050;'+raw.hex())
        requests=types.ModuleType('requests_util')
        requests.response_to_request=legacy
        adapter=types.SimpleNamespace(reset_vs1sync=lambda:None,
                         read_datapoint_ext=lambda *_:None,receive_telegr=lambda *_:None)
        with tempfile.TemporaryDirectory() as d:
            scope={
                'ORIGINAL_SERIAL':port,
                'settings':types.SimpleNamespace(vs1protocol=True,port_vitoconnect=None),
                'viconn_util':types.SimpleNamespace(get_vicon_request=lambda:None),
                'vs12_adapter':adapter,
                'serVitoConnnect':None,
                'vicon_publ_callback':None,
                'spr':'VS1',
                'logger':types.SimpleNamespace(info=lambda *_:None,exception=lambda *_:None),
            }
            env={'OPTO_RESEARCH_DISPATCH_SHADOW':'1',
                 'OPTO_HYBRID_BOOT_ONESHOT':'confirmed-readonly',
                 'OPTO_HYBRID_REPORT_DIR':d}
            with patch.dict(sys.modules,{'requests_util':requests}),patch.dict(os.environ,env):
                exec(patch_dispatcher(source),scope)
                with self.assertRaises(SystemExit) as caught:
                    scope['main']()
            self.assertEqual(caught.exception.code,0)
            record=json.loads((Path(d)/'hybrid-result.json').read_text())
            self.assertEqual(record['status'],'PASS_VERIFIED_BORROWED_PORT_FIXED_FC03')
            self.assertEqual(record['phase_count'],1)
            self.assertEqual(record['identity_hex'],'20c2')
            self.assertEqual(record['gfa_p06_hex'],'00')
            self.assertTrue(record['verified_vs1_return'])
        self.assertEqual(port.writes.count(EOT),2)
        self.assertEqual(port.script,[])
        self.assertFalse(port.closed)
        self.assertEqual(original_requests,['gfaread;0x4050;1;raw;False',
                                            'gfaread;0x4006;1;raw;False'])


if __name__=='__main__':unittest.main()
