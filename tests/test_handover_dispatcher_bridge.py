"""In-process seam keeps all original read/write/readback paths unchanged."""
import threading
import tempfile
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from handover_acceleration.coordinator import EOT, GFA, HandoverCoordinator, Mode, P300_RAM_READS, PortLease, ProtocolError
from handover_acceleration.dispatcher_bridge import InProcessDispatchBridge, BridgeRejected
from handover_acceleration.phase_planner import ReadJob, Budget
from handover_acceleration.scheduler import ReadKind
from test_handover_acceleration import FakePort, FakeClock, expect_vs1, expect_p300
from test_handover_fc03_fixed import response


class DispatcherBridgeTests(unittest.TestCase):
    def setUp(self):
        self.serial = object()
        self.calls = []
        self.legacy_answer = (1, bytearray(b'\x00'), '00', '1;0x4006;00')
        def legacy(req, port):
            self.calls.append((req,port))
            return self.legacy_answer
        self.legacy = legacy

    def bridge(self, serial=None, *, enabled=False, resume=None):
        return InProcessDispatchBridge(
            self.serial if serial is None else serial, self.legacy,
            vs1protocol=True, vitoconnect_port=None,
            allow_maintenance=enabled, resume_vs1=resume)

    def test_poll_mqtt_tcp_and_legacy_writes_have_identical_return_values(self):
        b=self.bridge()
        examples=['gfaread;0x4006;1;raw;False', 'r;0x2303;1;1;False',
                  'w;0x2303;1;1', 'writeraw;0x27D4;2A',
                  'request;0x01;0x00f8;2', 'raw;4105000100F80200',
                  '4105000100F80200', ['Betriebsart', '0x2323', '1', 'raw']]
        for msg in examples:
            with self.subTest(msg=msg):
                self.assertIs(b.response_to_request(msg,self.serial),self.legacy_answer)
        self.assertEqual([r for r,p in self.calls], examples)
        self.assertTrue(all(p is self.serial for r,p in self.calls))
        self.assertEqual(b.legacy_calls,len(examples))

    def test_maintenance_off_by_default_even_for_valid_types(self):
        b=self.bridge()
        with self.assertRaisesRegex(BridgeRejected, 'disabled'):
            b.execute_maintenance(tuple(),Budget())

    def test_reject_other_serial_handle_before_legacy_io(self):
        b=self.bridge()
        with self.assertRaisesRegex(BridgeRejected,'second owner'):
            b.response_to_request('r;0x1000;1;raw;False',object())
        self.assertFalse(self.calls)

    def test_only_main_loop_thread_may_own_serial(self):
        b=self.bridge()
        errors=[]
        t=threading.Thread(target=lambda: errors.append(self._thread_call(b)))
        t.start();t.join(timeout=2)
        self.assertFalse(t.is_alive())
        self.assertIn('serial-owner',errors[0])
        self.assertFalse(self.calls)

    def _thread_call(self,bridge):
        try:
            bridge.response_to_request('read;...',self.serial)
        except BridgeRejected as e:
            return str(e)
        return 'unexpected success'

    def test_vitoconnect_and_wrong_original_protocol_fail_on_construct(self):
        for vs1, vicon in ((False,None),(True,'/dev/ttyS1')):
            with self.subTest(vs1=vs1, vicon=vicon),self.assertRaises(BridgeRejected):
                InProcessDispatchBridge(self.serial,self.legacy,vs1protocol=vs1,vitoconnect_port=vicon)

    def test_enabled_requires_explicit_resume_callback(self):
        with self.assertRaisesRegex(BridgeRejected,'callback'):
            self.bridge(enabled=True)

    def test_write_readback_pair_is_one_atomic_group(self):
        b=self.bridge()
        with b.legacy_transaction():
            self.assertEqual(b.response_to_request('w;0x2303;1;1',self.serial),self.legacy_answer)
            self.assertEqual(b.response_to_request('r;0x2303;1;1;False',self.serial),self.legacy_answer)
            with self.assertRaisesRegex(BridgeRejected,'disabled'):
                b.execute_maintenance(tuple(),Budget())
        self.assertEqual(b.legacy_calls,2)

    def test_reentrant_legacy_dispatch_rejected_without_second_wire_transaction(self):
        b=self.bridge()
        def recursive(req,port):
            with self.assertRaisesRegex(BridgeRejected,'reentrant'):
                b.response_to_request(req,port)
            return self.legacy_answer
        b.legacy_dispatch=recursive
        b.response_to_request('r;0x4006;1;raw;False',self.serial)
        self.assertEqual(b.legacy_calls,1)

    def test_same_port_verified_session_one_fc03_window_then_legacy_read(self):
        clock=FakeClock()
        port=FakePort(expect_vs1(2)[1:]+expect_p300()+response('ram_0f20_32')+
                      response('ram_1c60_32')+expect_vs1(1))
        self.serial=port
        with tempfile.TemporaryDirectory() as d:
            owner=HandoverCoordinator.borrow_existing_vs1(port, PortLease(Path(d)/'lease'),
                                      clock=clock.monotonic, sleep=clock.sleep)
            resumed=[]
            b=self.bridge(enabled=True,resume=lambda:resumed.append('sync_reset'))
            with owner:
                b.bind_verified_coordinator(owner)
                jobs=(ReadJob('ram0',ReadKind.P300_RAM_0F20_32,85,25000,independent=True),
                      ReadJob('ram1',ReadKind.P300_RAM_1C60_32,85,25000,independent=True))
                result=b.execute_maintenance(jobs,Budget())
                self.assertEqual(owner.mode,Mode.VS1_VERIFIED)
                self.assertEqual(len(result.reads),2)
                self.assertEqual([len(r.raw) for r in result.reads],[32,32])
                self.assertEqual(b.response_to_request('r;0x4006;1;raw;False',port),
                                 self.legacy_answer)
                self.assertFalse(b.failed_closed)
                with self.assertRaisesRegex(BridgeRejected,'stale coordinator'):
                    b.bind_verified_coordinator(owner)
                with self.assertRaisesRegex(BridgeRejected,'fresh verified'):
                    b.execute_maintenance(jobs,Budget())
            self.assertEqual(resumed,['sync_reset'])
            self.assertEqual(port.writes.count(EOT),2)
            self.assertEqual(port.script,[])
            self.assertFalse(port.closed)  # existing production serial owner retains handle

    def test_invalid_maintenance_budget_leaves_original_vs1_usable(self):
        clock=FakeClock()
        port=FakePort(expect_vs1(2)[1:])
        self.serial=port
        with tempfile.TemporaryDirectory() as d:
            owner=HandoverCoordinator.borrow_existing_vs1(port,PortLease(Path(d)/'lease'),
                                      clock=clock.monotonic,sleep=clock.sleep)
            bridge=self.bridge(enabled=True,resume=lambda:None)
            with owner:
                bridge.bind_verified_coordinator(owner)
                before=len(port.writes)
                with self.assertRaises(Exception):
                    bridge.execute_maintenance((ReadJob('ram',ReadKind.P300_RAM_0F20_32,
                        duration_ms=85,deadline_ms=25000,independent=True),),
                        Budget(max_p06_age_ms=2100,max_vs1_unavailable_ms=2100))
                self.assertEqual(len(port.writes),before)
                self.assertFalse(bridge.failed_closed)
                bridge.response_to_request('r;0x4006;1;raw;False',port)
            self.assertFalse(port.closed)

    def test_corrupt_fc03_halts_legacy_even_after_verified_context_recovery(self):
        clock=FakeClock()
        port=FakePort(expect_vs1(2)[1:]+expect_p300()+response('ram_0f20_32',bad_crc=True)[:1]+expect_vs1(2))
        self.serial=port
        with tempfile.TemporaryDirectory() as d:
            owner=HandoverCoordinator.borrow_existing_vs1(port,PortLease(Path(d)/'lease'),
                                      clock=clock.monotonic,sleep=clock.sleep)
            b=self.bridge(enabled=True,resume=lambda:None)
            with owner:
                b.bind_verified_coordinator(owner)
                jobs=(ReadJob('ram',ReadKind.P300_RAM_0F20_32,85,25000,independent=True),)
                with self.assertRaises(ProtocolError):
                    b.execute_maintenance(jobs,Budget())
                self.assertTrue(b.failed_closed)
                with self.assertRaisesRegex(BridgeRejected,'failed closed'):
                    b.response_to_request('w;0x2303;1;1',port)
                # Explicit conservative restore is done by coordinator after failed read.
                owner.restore_vs1()
            self.assertFalse(self.calls)
            self.assertEqual(port.script,[])

    def test_legacy_calls_invalidate_maintenance_attestation(self):
        clock=FakeClock()
        port=FakePort(expect_vs1(2)[1:])
        self.serial=port
        with tempfile.TemporaryDirectory() as d:
            owner=HandoverCoordinator.borrow_existing_vs1(port,PortLease(Path(d)/'lease'),
                                      clock=clock.monotonic,sleep=clock.sleep)
            b=self.bridge(enabled=True,resume=lambda:None)
            with owner:
                b.bind_verified_coordinator(owner)
                b.response_to_request('r;0x2323;1;raw;False',port)
                with self.assertRaises(BridgeRejected):
                    b.execute_maintenance(tuple(),Budget())
            self.assertEqual(port.script,[])


if __name__=='__main__':
    unittest.main()
