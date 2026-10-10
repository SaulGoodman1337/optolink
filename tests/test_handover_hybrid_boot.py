"""Full fake-wire one-shot acceptance: borrowed port, 2 FC03, VS1 original-GFA."""
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from handover_acceleration.hybrid_boot import (
    _legacy_gfa, run_one_shot, BootRejected, _private_report_dir)
from handover_acceleration.coordinator import EOT, GFA, P300_ID, DEVICE_ID, ProtocolError
from test_handover_acceleration import FakePort, FakeClock, expect_vs1, expect_attached_vs1, expect_p300, p300_reply
from test_handover_fc03_fixed import response


class HybridBootTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)
        self.clock=FakeClock()
        self.settings=types.SimpleNamespace(vs1protocol=True,port_vitoconnect=None)
        self.calls=[]
        self.resumed=[]

    def script(self,*,corrupt=False,identity=DEVICE_ID):
        seq=expect_attached_vs1(device=identity)+expect_p300()
        seq += [(P300_ID,p300_reply(0x00F8,DEVICE_ID)),(b'\x06',b'')]
        seq += response('ram_0f20_32',bad_crc=corrupt)
        if not corrupt:
            seq += response('ram_1c60_32')
            seq += expect_vs1(1)
        else:
            # The bogus response never receives ACK; conservative VS1 recovery.
            seq.pop()
            seq += expect_vs1(2)
        return seq

    def legacy(self,request,port):
        self.calls.append(request)
        if request == 'gfaread;0x4050;1;raw;False':
            raw=b'\x20'
        elif request == 'gfaread;0x4006;1;raw;False':
            raw=b'\x00'
        else:
            raise AssertionError('unexpected legacy address')
        return (1,bytearray(raw),raw.hex(),f'1;0x0000;{raw.hex()}')

    def run_case(self,port,*,settings=None,legacy=None,report=None):
        return run_one_shot(port,settings or self.settings,legacy or self.legacy,
                            lambda:self.resumed.append('resume'),
                            report or self.path,clock=self.clock.monotonic,
                            sleep=self.clock.sleep)

    def test_realistic_fixed_ram_batch_without_cold_eot(self):
        port=FakePort(self.script())
        result=self.run_case(port)
        self.assertEqual(result['status'],'PASS_VERIFIED_BORROWED_PORT_FIXED_FC03')
        self.assertEqual(result['phase_count'],1)
        self.assertEqual(result['gfa_p80_hex'],'20')
        self.assertEqual(result['gfa_p06_hex'],'00')
        self.assertEqual(len(bytes.fromhex(result['ram_0f20_32_hex'])),32)
        self.assertEqual(len(bytes.fromhex(result['ram_1c60_32_hex'])),32)
        self.assertEqual(port.writes.count(EOT),2)
        self.assertEqual(port.script,[])
        self.assertFalse(port.closed)
        self.assertEqual(self.calls,['gfaread;0x4050;1;raw;False',
                                      'gfaread;0x4006;1;raw;False'])
        self.assertEqual(self.resumed,['resume'])
        self.assertEqual(json.loads((self.path/'hybrid-result.json').read_text()),result)
        self.assertEqual((self.path/'hybrid-result.json').stat().st_mode&0o077,0)

    def test_failing_fc03_checksum_stops_batch_and_restores_vs1(self):
        port=FakePort(self.script(corrupt=True))
        with self.assertRaises(ProtocolError):self.run_case(port)
        self.assertEqual(port.script,[])
        self.assertFalse(port.closed)
        self.assertEqual(port.writes.count(EOT),2)
        self.assertEqual(self.calls,[])
        self.assertFalse((self.path/'hybrid-result.json').exists())

    def test_attach_wrong_identity_refused_without_eot(self):
        port=FakePort(expect_attached_vs1(device=b'\x12\x34'))
        with self.assertRaisesRegex(ProtocolError,'identity mismatch'):
            self.run_case(port)
        self.assertEqual(port.writes.count(EOT),0)
        self.assertEqual(self.calls,[])
        self.assertFalse(port.closed)
        self.assertFalse((self.path/'hybrid-result.json').exists())

    def test_original_gfa_p80_mismatch_never_reports_success(self):
        port=FakePort(self.script())
        def bad_gfa(cmd,handle):
            if '4050' in cmd:return (1,bytearray(b'\x21'),'21','1;0x4050;21')
            return self.legacy(cmd,handle)
        with self.assertRaisesRegex(BootRejected,'P80 identity mismatch'):
            self.run_case(port,legacy=bad_gfa)
        self.assertEqual(port.script,[])
        self.assertFalse((self.path/'hybrid-result.json').exists())

    def test_original_gfa_p06_ff_is_invalid_not_real_rpm(self):
        port=FakePort(self.script())
        def invalid(cmd,handle):
            return (1,bytearray(b'\xff'),'ff','1;0x4006;ff') if '4006' in cmd else self.legacy(cmd,handle)
        with self.assertRaisesRegex(BootRejected,'sample invalid'):
            self.run_case(port,legacy=invalid)
        self.assertFalse((self.path/'hybrid-result.json').exists())

    def test_original_gfa_valid_p06_zero_is_permitted(self):
        self.assertEqual(_legacy_gfa(self.legacy,object(),0x4006),b'\x00')

    def test_original_gfa_rc_zero_rejected(self):
        with self.assertRaisesRegex(BootRejected,'rejected'):
            _legacy_gfa(lambda *_:(0,bytearray(b'\x20'),'20','invalid'),object(),0x4050)

    def test_original_gfa_malformed_tuple_rejected(self):
        for result in ('1;...',[],(1,None,0,'0'),(True,bytearray(b'\x20'),0,'ok')):
            with self.subTest(result=result),self.assertRaises(BootRejected):
                _legacy_gfa(lambda *_:result,object(),0x4050)

    def test_wrong_vitoconnect_or_transport_fail_before_wire(self):
        for settings in (types.SimpleNamespace(vs1protocol=False,port_vitoconnect=None),
                         types.SimpleNamespace(vs1protocol=True,port_vitoconnect='/dev/ttyS2')):
            port=FakePort([])
            with self.subTest(settings=settings),self.assertRaises(BootRejected):
                self.run_case(port,settings=settings)
            self.assertEqual(port.writes,[])

    def test_non_private_directory_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d).chmod(0o755)
            port=FakePort([])
            with self.assertRaisesRegex(BootRejected,'owner-only'):
                self.run_case(port,report=Path(d))
            self.assertEqual(port.writes,[])

    def test_symlink_report_dir_rejected(self):
        link=self.path/'shortcut'
        link.symlink_to(self.path)
        with self.assertRaisesRegex(BootRejected,'absolute report directory'):
            _private_report_dir(link)

    def test_existing_result_refused_before_wire(self):
        (self.path/'hybrid-result.json').write_text('{}')
        port=FakePort([])
        with self.assertRaisesRegex(BootRejected,'already exists'):
            self.run_case(port)
        self.assertEqual(port.writes,[])

    def test_existing_symlink_result_refused(self):
        (self.path/'hybrid-result.json').symlink_to(self.path/'something')
        port=FakePort([])
        with self.assertRaises(BootRejected):self.run_case(port)
        self.assertEqual(port.writes,[])

    def test_repeated_call_not_allowed_or_republish_as_fresh(self):
        port=FakePort(self.script())
        self.run_case(port)
        with self.assertRaises(BootRejected):self.run_case(port)
        self.assertEqual(port.writes.count(EOT),2)


if __name__=='__main__':unittest.main()
