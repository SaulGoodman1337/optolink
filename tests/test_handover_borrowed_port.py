"""Full no-EOT attach to the existing owner: fresh identity, no new port/close."""
import sys
import tempfile
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from handover_acceleration.coordinator import (
    HandoverCoordinator, PortLease, Mode, EOT, STX, VS1_ID, GFA, ProtocolError, BusyError,
)
from test_handover_acceleration import FakeClock, FakePort, expect_vs1, expect_attached_vs1, expect_p300


class ExistingOwnerAttachTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.clock=FakeClock()
        self.lock=Path(self.temp.name)/'owner.lease'

    def create(self,seq):
        port=FakePort(seq)
        owner=HandoverCoordinator.borrow_existing_vs1(port,PortLease(self.lock),
                clock=self.clock.monotonic,sleep=self.clock.sleep)
        return owner,port

    def test_verified_existing_vs1_session_no_eot_and_no_port_close(self):
        owner,port=self.create(expect_attached_vs1()+[(GFA['P09'],b'\x00')])
        with owner:
            self.assertEqual(owner.mode,Mode.VS1_VERIFIED)
            self.assertEqual(owner.history,[('vs1_attached','verified_without_eot')])
            self.assertEqual(owner.verified_gfa_snapshot()['P80'],b'\x20')
            self.assertEqual(owner.verified_gfa_snapshot()['P06'],b'\x00')
            self.assertEqual(owner.gfa_read('P09'),b'\x00')
        self.assertEqual(port.writes.count(EOT),0)
        self.assertIn(VS1_ID, port.writes)
        self.assertNotIn(STX + VS1_ID, port.writes)
        self.assertFalse(port.closed)
        self.assertEqual(port.script,[])
        self.assertEqual(owner.mode,Mode.DETACHED)

    def test_inprocess_window_uses_exactly_two_eots_not_cold_setup(self):
        owner,port=self.create(expect_attached_vs1()+expect_p300()+expect_vs1(1))
        with owner:
            owner.to_p300()
            owner.to_vs1_fast()
        self.assertEqual(port.writes.count(EOT),2)
        self.assertFalse(port.closed)
        self.assertEqual(port.script,[])

    def test_wrong_device_and_software_never_claim_attached_verified(self):
        for kw in ({'device':b'\x20\xc3'}, {'software':b'\x01\x04'}):
            with self.subTest(kw=kw):
                owner,port=self.create(expect_attached_vs1(**kw))
                with self.assertRaises(ProtocolError):
                    with owner:pass
                self.assertEqual(owner.mode,Mode.FAILED_CLOSED)
                self.assertFalse(port.closed)
                self.assertNotIn(('vs1_attached','verified_without_eot'),owner.history)

    def test_invalid_p80_p06_fail_closed_without_new_eot(self):
        for kw in ({'p80':b'\x21'},{'p06':b'\xff'}):
            with self.subTest(kw=kw):
                owner,port=self.create(expect_attached_vs1(**kw))
                with self.assertRaises(ProtocolError):
                    with owner:pass
                self.assertEqual(port.writes.count(EOT),0)
                self.assertFalse(port.closed)
                self.assertEqual(owner.mode,Mode.FAILED_CLOSED)

    def test_exclusive_lease_blocks_second_manager_before_any_frame(self):
        owner,port=self.create(expect_attached_vs1())
        competitor=HandoverCoordinator.borrow_existing_vs1(port,PortLease(self.lock),
                 clock=self.clock.monotonic,sleep=self.clock.sleep)
        with owner:
            before=len(port.writes)
            with self.assertRaises(BusyError):
                with competitor:pass
            self.assertEqual(len(port.writes),before)
        self.assertFalse(port.closed)

    def test_refuse_missing_existing_port(self):
        with self.assertRaises(ProtocolError):
            HandoverCoordinator.borrow_existing_vs1(None,PortLease(self.lock))


if __name__=='__main__':unittest.main()
