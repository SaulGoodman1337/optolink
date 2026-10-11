"""Native-P300 RX-RAM Vitotrol bridge: simulated controller and fail-closed tests."""
from __future__ import annotations
import ast
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE=Path(__file__).resolve().parents[1]/'tools'/'wb2a-vitotrol-p300-bridge.py'
spec=importlib.util.spec_from_file_location('wb2a_p300_bridge_test',SOURCE)
m=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=m
spec.loader.exec_module(m)

BASE_RX=(bytes.fromhex('00000001b10a010110fe23d8fa01fb0122d1')
         +bytes(14))


class FakeController:
    def __init__(self,*,accept=False,fail_first_write=False,
                 readback_corrupt=False,bad_initial=False):
        self.config={
            0x27A0:bytearray(b'\x01' if bad_initial else b'\x00'),
            0x27B0:bytearray(b'\x00'),
            0x7342:bytearray(b'\x00'),
            0x0A5C:bytearray(b'\x00\x00\x00\x00'),
            0x0896:bytearray(b'\xc8\x00'),
            0x089C:bytearray(b'\x03'),
            0x5738:bytearray(b'\x00'),
        }
        self.rx=bytearray(BASE_RX)
        self.writes=[]
        self.accept=accept
        self.fail_first_write=fail_first_write
        self.readback_corrupt=readback_corrupt
        self.phase=0

    def read(self,addr,n):
        if addr==0xF8:
            return m.DEVICE
        if addr not in self.config or len(self.config[addr])!=n:
            raise m.BridgeRejected('not an expected simulated register')
        return bytes(self.config[addr])

    def physical_read(self):
        if not self.readback_corrupt or not self.phase:
            return bytes(self.rx)
        b=bytearray(self.rx)
        b[7]^=1
        return bytes(b)

    def write_config(self,addr,val):
        if (addr,val) not in {
            (0x27A0,0),(0x27A0,1),(0x27B0,0),(0x27B0,3),
            (0x7342,0),(0x7342,0x74)
        }:raise AssertionError('unsafe config')
        self.writes.append(('config',addr,val))
        self.config[addr]=bytearray([val])
        if addr==0x27B0 and val==0:
            self.config[0x0A5C]=bytearray(4)
            self.config[0x089C]=bytearray(b'\x03')

    def physical_write(self,addr,data):
        assert addr==0x1642 and 8<=len(data)<=30
        if self.fail_first_write:
            self.fail_first_write=False
            raise m.BridgeRejected('injected test P300 write failure')
        self.writes.append(('physical',addr,bytes(data)))
        self.rx[2:2+len(data)]=data
        self.phase+=1
        if self.accept and data==m.FRAME_ORIGINAL_PONG:
            self.config[0x0A5C]=bytearray.fromhex('01000000')
            self.config[0x089C]=bytearray(b'\x00')
            self.config[0x0896]=bytearray.fromhex('ce00')


class BridgeTests(unittest.TestCase):
    def test_real_original_v300_frames_byte_valid_and_limited_to_exact_four(self):
        for frame in m.REPLAY:
            self.assertIs(m.validate_v300_frame(frame),frame)
            self.assertEqual(m.model.crc16_kermit(frame),0)
            self.assertEqual(frame[0:2],b'\x00\x11')
        self.assertEqual([x[2] for x in m.REPLAY],[0xb3,0xb1,0xbf,0x80])
        self.assertEqual(m.model.decode_candidate_slave_room_temp(
            m.FRAME_ORIGINAL_ROOM_206)['temperature_tenths_c'],206)
        bad=bytearray(m.FRAME_ORIGINAL_B1)
        bad[-1]^=1
        with self.assertRaises(m.model.FrameRejected):
            m.validate_v300_frame(bytes(bad))
        other=m.model.model_pong(bytes.fromhex('1100000802014589')) if False else (
            m.model.append_crc(bytes.fromhex('001180080201')))
        with self.assertRaises(m.BridgeRejected):
            m.validate_v300_frame(other)

    def test_no_effect_on_controller_state_even_when_all_frames_staged(self):
        controller=FakeController()
        r=m.VitotrolP300Stager(controller,pause=lambda _:None).experiment(
            configure_type=True)
        self.assertFalse(r['remote_accepted_by_controller'])
        self.assertTrue(all(x['physical_readback_exact'] for x in r['frames_staged']))
        self.assertEqual(len(r['frames_staged']),4)
        self.assertEqual(r['last_active_acceptance_check']['software_index_nonzero'],False)
        self.assertFalse(r['last_active_acceptance_check']['accepted_remote_proven'])
        self.assertFalse(r['km_bus_uart_rx_interrupt_triggered'])
        self.assertTrue(r['rx_buffer_restored_first_16_bytes'])
        self.assertEqual(bytes(controller.rx),BASE_RX)
        self.assertEqual(bytes(controller.config[0x27A0]),b'\x00')
        self.assertEqual(bytes(controller.config[0x27B0]),b'\x00')
        self.assertEqual(bytes(controller.config[0x7342]),b'\x00')
        self.assertIn(('config',0x7342,0x74),controller.writes)
        self.assertEqual(len([v for v in controller.writes if v[0]=='physical']),5)

    def test_two_distinct_positive_controller_readbacks_required_for_acceptance(self):
        controller=FakeController(accept=True)
        r=m.VitotrolP300Stager(controller,pause=lambda _:None).experiment()
        self.assertTrue(r['last_active_acceptance_check']['accepted_remote_proven'])
        self.assertTrue(r['last_active_acceptance_check']['two_separated_participant_and_room_readbacks'])
        self.assertTrue(r['remote_accepted_by_controller'])
        self.assertFalse(r['km_bus_uart_rx_interrupt_triggered'])
        self.assertEqual(bytes(controller.rx),BASE_RX)

    def test_firmware_writes_can_succeed_without_acceptance(self):
        status={'swindex':'00000000','room_raw':'c800','sensor':'03','type':'74'}
        r=m.acceptance(status)
        self.assertFalse(r['accepted_remote_proven'])
        self.assertFalse(r['candidate_participant_and_room_acknowledgement'])
        self.assertTrue(r['type_is_not_necessarily_registered'])
        status['swindex']='01000000'
        self.assertFalse(m.acceptance(status)['candidate_participant_and_room_acknowledgement'])
        status['sensor']='00'
        self.assertFalse(m.acceptance(status)['candidate_participant_and_room_acknowledgement'])

    def test_preflight_rejects_wrong_baseline_or_identity(self):
        c=FakeController(bad_initial=True)
        with self.assertRaisesRegex(m.BridgeRejected,'baseline'):
            m.VitotrolP300Stager(c).check_preflight()
        c=FakeController()
        c.read=lambda a,n:b'\x00'*n
        with self.assertRaisesRegex(m.BridgeRejected,'not the expected'):
            m.VitotrolP300Stager(c).check_preflight()

    def test_errors_during_active_injection_still_restore_previous_buffer_and_codings(self):
        for cause in ('write','readback'):
            with self.subTest(cause=cause):
                c=FakeController(fail_first_write=cause=='write',
                                 readback_corrupt=cause=='readback')
                with self.assertRaises(m.BridgeRejected):
                    m.VitotrolP300Stager(c,pause=lambda _:None).experiment()
                self.assertEqual(bytes(c.config[0x27A0]),b'\x00')
                self.assertEqual(bytes(c.config[0x27B0]),b'\x00')
                self.assertEqual(bytes(c.config[0x7342]),b'\x00')
                self.assertEqual(bytes(c.rx),BASE_RX)

    def test_native_mode_readback_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'settings.py'
            for mode in ('False','True'):
                path.write_text(f'vs1protocol = {mode}\n')
                if mode=='False':
                    m.require_native_p300(path,require_root=False)
                else:
                    with self.assertRaisesRegex(m.BridgeRejected,'native P300'):
                        m.require_native_p300(path,require_root=False)
            path.write_text('vs1protocol = False\nvs1protocol = True\n')
            with self.assertRaises(m.BridgeRejected):
                m.require_native_p300(path,require_root=False)

    def test_fake_mqtt_request_response_and_transport_whitelist(self):
        history=[]
        def runner(argv,**kw):
            self.assertEqual(argv[0:2],['optolink-debug','request'])
            self.assertTrue(kw['capture_output'])
            history.append(argv[2])
            parts=argv[2].split(';')
            addr=int(parts[1],0) if parts[0] in ('read','writeraw') else int(parts[2],0)
            if parts[0]=='read':
                val='20c2000300000103' if addr==0xf8 else '00'
            elif parts[0]=='request' and parts[1]=='3':
                val=BASE_RX.hex()
            else:
                val='none'
            return subprocess.CompletedProcess(argv,0,f'{argv[2]} <- openv/resp: 1;0x{addr:x};{val}\n','')
        t=m.OptolinkP300Client(runner=runner)
        self.assertEqual(t.read(0xf8,8),m.DEVICE)
        self.assertEqual(t.physical_read(),BASE_RX)
        t.write_config(0x27A0,1)
        t.physical_write(0x1642,m.FRAME_ORIGINAL_B3)
        self.assertEqual(len(history),4)
        with self.assertRaises(m.BridgeRejected):
            t.physical_write(0x161a,m.FRAME_ORIGINAL_B3)
        with self.assertRaises(m.BridgeRejected):
            t.write_config(0x27A0,0xff)
        with self.assertRaises(m.BridgeRejected):
            t.read(0x1642,10)

    def test_bad_response_crc_alias_address_and_type_are_not_accepted(self):
        for val in ('3;0x1642;01','1;0x1643;none','1;0x1642;hello',
                    '1;0x1642;none\n<- openv/resp: 1;0x1642;none'):
            with self.subTest(data=val),self.assertRaises(m.BridgeRejected):
                m.parse_response('<- openv/resp: '+val,0x1642)

    def test_import_has_no_device_open_or_active_controller_io(self):
        src=ast.parse(SOURCE.read_text())
        imports=set()
        for n in ast.walk(src):
            if isinstance(n,ast.Import):imports.update(x.name.split('.')[0] for x in n.names)
            elif isinstance(n,ast.ImportFrom) and n.module:imports.add(n.module.split('.')[0])
        self.assertFalse(imports & {'socket','serial','paho','ctypes','paramiko'})
        self.assertIn('controller_firmware_state_commit_proven',m.AUDIT_FLAGS)
        self.assertFalse(m.AUDIT_FLAGS['controller_firmware_state_commit_proven'])


if __name__=='__main__':
    unittest.main()
