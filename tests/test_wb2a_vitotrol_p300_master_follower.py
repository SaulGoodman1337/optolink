"""Pure simulation of CRC-qualified master discovery -> original V300 reply."""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import sys
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/"tools"/"wb2a-vitotrol-p300-master-follower.py"
spec=importlib.util.spec_from_file_location("wb2a_native_follower_test",SCRIPT)
follower=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=follower
spec.loader.exec_module(follower)
bridge=follower.bridge
orig_rx=(bytes.fromhex('00000001b10a010110fe23d8fa01fb0122d1')+
         bytes(14))
MASTER_DISCOVERY=bytes.fromhex('1100330a0101f80449ef')
MASTER_REG00=bridge.model.append_crc(bytes.fromhex('11003109010100'))
MASTER_PING=bytes.fromhex('1100000801010888')
MASTER_OTHER=bytes.fromhex('0100b10a01010106c731')
assert all(bridge.model.crc16_kermit(frame)==0
           for frame in (MASTER_DISCOVERY,MASTER_REG00,MASTER_PING,MASTER_OTHER))


class Clock:
    def __init__(self):self.value=0.0
    def __call__(self):
        self.value+=.2
        return self.value


class Dummy:
    def __init__(self,frames):
        self.config={
            0x27A0:b'\x00', 0x27B0:b'\x00',0x7342:b'\x00',
            0x0A5C:bytes(4), 0x0896:bytes.fromhex('c800'),
            0x089C:b'\x03',0x5738:b'\x00'}
        self.rx=bytearray(orig_rx)
        self.frames=iter(frames)
        self.sent=[]
        self.codes=[]

    def read(self,a,n):
        if a==0xF8:return bridge.DEVICE
        return self.config[a]

    def write_config(self,a,v):
        self.codes.append((a,v))
        self.config[a]=bytes((v,))

    def physical_read(self):
        return bytes(self.rx)

    def physical_write(self,a,v):
        if a!=0x1642 or len(v)>30:raise RuntimeError('unexpected RAM access')
        self.rx[2:2+len(v)]=v
        self.sent.append(bytes(v))

    def request(self,command,expected_address):
        if command!="request;3;0x161a;32" or expected_address!=0x161A:
            raise AssertionError('bad master TX RAM access')
        try:frame=next(self.frames)
        except StopIteration:frame=MASTER_OTHER
        if len(frame)>32:raise AssertionError()
        return bridge.Response(1,0x161A,frame.ljust(32,b'\x00'))


class TestMasterFollower(unittest.TestCase):
    def test_discovery_register_and_pings_stage_original_v300_frames(self):
        x=Dummy([MASTER_OTHER,MASTER_DISCOVERY,MASTER_REG00,MASTER_PING,
                 MASTER_PING,MASTER_OTHER,MASTER_PING])
        clock=Clock()
        obj=follower.NativeP300MasterFollower(x,now=clock,pause=lambda _:None)
        result=obj.run(duration_s=4.0,configure_type=True)
        self.assertIn('110033',result['master_frame_counts'])
        self.assertGreaterEqual(result['staged_frame_count'],4)
        self.assertEqual([x['response'] for x in result['staged_frames'][:4]],
                         [b.hex() for b in bridge.REPLAY])
        self.assertTrue(all(x['response']==bridge.FRAME_ORIGINAL_PONG.hex()
                            for x in result['staged_frames'][4:]))
        self.assertTrue(all(x['readback_exact'] for x in result['staged_frames']))
        self.assertEqual(bytes(x.rx),orig_rx)
        self.assertFalse(result['controller_acknowledged_remote'])
        self.assertFalse(result['physical_controller_uart1_rx_interrupt_verified'])
        self.assertFalse(result['master_frame_wire_send_timestamp_proven'])
        self.assertEqual(result['restored']['a0'],'00')
        self.assertEqual(result['restored']['b0'],'00')
        self.assertEqual(result['restored']['type'],'00')

    def test_unknown_or_crc_invalid_master_tx_does_not_trigger_write(self):
        bad=bytearray(MASTER_DISCOVERY)
        bad[-1]^=1
        self.assertIsNone(follower.parse_master_tx_snapshot(bytes(bad).ljust(32,b'\x00')))
        self.assertIsNone(follower.parse_master_tx_snapshot(bytes(32)))
        with self.assertRaises(bridge.BridgeRejected):
            follower.parse_master_tx_snapshot(bytes(31))
        x=Dummy([bytes(bad),MASTER_OTHER,bytes(32)])
        state=bridge.model.original_v300_offline_profile()
        state.update_temperature(206,at_s=1)
        obj=follower.NativeP300MasterFollower(x,now=lambda:2)
        for _ in range(3):
            self.assertFalse(obj.poll_once(state,at_s=2)['staged'])
        self.assertFalse(x.sent)

    def test_slot2_discovery_not_replied_using_original_slot1_profile(self):
        slot2=bytes.fromhex('1100330a0201f80484ca')
        assert bridge.model.crc16_kermit(slot2)==0
        x=Dummy([slot2])
        state=bridge.model.original_v300_offline_profile()
        state.update_temperature(206,at_s=1)
        result=follower.NativeP300MasterFollower(x).poll_once(state,at_s=2)
        self.assertFalse(result['staged'])
        self.assertEqual(result['master_status'],'110033')
        self.assertFalse(x.sent)

    def test_invalid_duration_rejected_before_coding_writes(self):
        x=Dummy([MASTER_DISCOVERY])
        obj=follower.NativeP300MasterFollower(x)
        for value in (-1,0,181,float('inf'),True,'long'):
            with self.subTest(value=value),self.assertRaises(bridge.BridgeRejected):
                obj.run(duration_s=value)
        self.assertEqual(x.codes,[])

    def test_original_v300_identity_only_after_master_discovery(self):
        x=Dummy([MASTER_PING,MASTER_REG00,MASTER_DISCOVERY])
        state=bridge.model.original_v300_offline_profile()
        state.update_temperature(206,at_s=1)
        obj=follower.NativeP300MasterFollower(x)
        self.assertFalse(obj.poll_once(state,at_s=2)['staged'])
        self.assertFalse(obj.poll_once(state,at_s=3)['staged'])
        self.assertTrue(obj.poll_once(state,at_s=4)['staged'])
        self.assertEqual(x.sent[0],bridge.FRAME_ORIGINAL_B3)

    def test_no_serial_or_network_import_path_other_than_injected_transport(self):
        tree=ast.parse(SCRIPT.read_text())
        imports=set()
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):
                imports.update(x.name.split('.')[0] for x in node.names)
            elif isinstance(node,ast.ImportFrom) and node.module:
                imports.add(node.module.split('.')[0])
        self.assertFalse(imports & {'serial','socket','paho','paramiko','ctypes'})


if __name__=='__main__':
    unittest.main()
