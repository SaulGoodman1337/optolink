"""Verify actual injected wire sequence for cost-aware P300 batching offline."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from handover_acceleration.coordinator import (
    DEVICE_ID, EOT, GFA, HandoverCoordinator, Mode, PortLease, P300_ID, ProtocolError,
)
from handover_acceleration.scheduler import GfaFreshnessLedger, ReadKind, StaleReading
from handover_acceleration.phase_planner import Budget, ReadJob, PlanRejected
from handover_acceleration.phase_executor import (
    execute_read_phases, ExecutionRejected,
)
from test_handover_acceleration import FakeClock,FakePort,expect_vs1,expect_p300,p300_reply,ACK


def job(name,kind,*,independent=True,deadline_ms=18000):
    return ReadJob(name=name,kind=kind,duration_ms=50,deadline_ms=deadline_ms,
                   independent=independent)


def extra_identity_reads(count):
    return [(P300_ID,p300_reply(0x00f8,DEVICE_ID)),(ACK,b'')]*count


class OfflineSingleOwnerBatchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.clock=FakeClock()
        self.ledger=GfaFreshnessLedger(clock=self.clock.monotonic)
        self.lock=Path(self.temp.name)/'port.lease'

    def manager(self,script):
        port=FakePort(script)
        manager=HandoverCoordinator(lambda:port,PortLease(self.lock),
                                    clock=self.clock.monotonic,sleep=self.clock.sleep)
        return manager,port

    def test_six_p300_reads_share_one_verified_window(self):
        jobs=[job('gfa_before',ReadKind.VS1_P80)]+[
            job('p300_'+str(i),ReadKind.P300_ID) for i in range(6)]
        jobs.insert(4,job('vs1_mid',ReadKind.VS1_P06))
        script=(expect_vs1(2)+[(GFA['P80'],b'\x20'),(GFA['P06'],b'\x01')]
                +expect_p300()+extra_identity_reads(6)+expect_vs1(1))
        manager,port=self.manager(script)
        with manager:
            result=execute_read_phases(manager,jobs,Budget(),ledger=self.ledger)
            self.assertEqual(manager.mode,Mode.VS1_VERIFIED)
            p06=self.ledger.fresh(ReadKind.VS1_P06,
                                  current_generation=result.generation,max_age_s=0.75)
            self.assertEqual(p06.raw,b'\x00')
        self.assertTrue(result.verified_vs1_at_end)
        self.assertEqual(result.p300_entry_count,1)
        self.assertEqual(result.plan.p300_windows,1)
        self.assertEqual(port.writes.count(EOT),3)
        self.assertEqual(port.writes.count(P300_ID),7) # 1 identity gate + 6 reads
        self.assertEqual(port.script,[])
        self.assertTrue(port.closed)
        self.assertEqual(len(result.reads),len(jobs))

    def test_verified_vs1_session_no_extra_handshake_if_only_gfa(self):
        manager,port=self.manager(expect_vs1(2)+[(GFA['P06'],b'\x00')])
        with manager:
            result=execute_read_phases(manager,[job('rpm',ReadKind.VS1_P06)],Budget())
        self.assertEqual(result.p300_entry_count,0)
        self.assertEqual(port.writes.count(EOT),1) # only initial cold setup
        self.assertEqual(result.reads[0].raw,b'\x00')
        self.assertEqual(port.script,[])

    def test_explicit_non_independent_barrier_prevents_illegal_reordering(self):
        jobs=[job('p300_a',ReadKind.P300_ID),
              job('barrier',ReadKind.VS1_P06,independent=False),
              job('p300_b',ReadKind.P300_ID)]
        script=(expect_vs1(2)+expect_p300()+extra_identity_reads(1)+
                expect_vs1(1)+[(GFA['P06'],b'\x02')]+
                expect_p300()+extra_identity_reads(1)+expect_vs1(1))
        manager,port=self.manager(script)
        with manager:
            result=execute_read_phases(manager,jobs,Budget())
        self.assertEqual(result.p300_entry_count,2)
        self.assertEqual(port.writes.count(EOT),5) # cold + two roundtrips
        self.assertEqual([x.name for x in result.reads],['p300_a','barrier','p300_b'])
        self.assertEqual(port.script,[])

    def test_2100ms_freshness_requirement_rejects_even_one_p300_window_before_io(self):
        manager,port=self.manager(expect_vs1(2))
        with manager:
            before=len(port.writes)
            with self.assertRaises(PlanRejected):
                execute_read_phases(manager,[job('p300',ReadKind.P300_ID)],
                    Budget(max_p06_age_ms=2100,max_vs1_unavailable_ms=2100),
                    ledger=self.ledger)
            self.assertEqual(len(port.writes),before)
            self.assertEqual(manager.mode,Mode.VS1_VERIFIED)
        self.assertEqual(port.script,[])

    def test_p300_crc_error_invalidates_results_then_conservative_restore(self):
        script=(expect_vs1(2)+expect_p300()+extra_identity_reads(1)+
                [(P300_ID,p300_reply(0x00f8,DEVICE_ID,bad_crc=True))]+
                expect_vs1(2))
        manager,port=self.manager(script)
        with self.assertRaises(ProtocolError):
            with manager:
                execute_read_phases(manager,[job('a',ReadKind.P300_ID),
                                             job('b',ReadKind.P300_ID)],
                                    Budget(),ledger=self.ledger)
        self.assertEqual(port.writes.count(EOT),3) # cold + P300 + conservative recovery
        self.assertIn(('vs1','verified:2'),manager.history)
        self.assertEqual(manager.mode,Mode.DETACHED)
        self.assertTrue(port.closed)
        self.assertEqual(port.script,[])
        with self.assertRaises(StaleReading):
            self.ledger.fresh(ReadKind.VS1_P06,current_generation=1,max_age_s=10)

    def test_invalid_argument_is_rejected_before_switch(self):
        manager,port=self.manager(expect_vs1(2))
        with manager:
            before=len(port.writes)
            for bad in ['r;1234',object(),1]:
                with self.subTest(bad=str(bad)),self.assertRaises(PlanRejected):
                    execute_read_phases(manager,[bad],Budget())
            self.assertEqual(len(port.writes),before)
        self.assertEqual(port.script,[])

    def test_ledger_is_not_required(self):
        manager,port=self.manager(expect_vs1(2)+expect_p300()+extra_identity_reads(2)+expect_vs1(1))
        with manager:
            result=execute_read_phases(manager,[job('a',ReadKind.P300_ID),
                                               job('b',ReadKind.P300_ID)],Budget())
        self.assertEqual(len(result.reads),2)
        self.assertEqual(port.script,[])

    def test_coordinator_must_be_verified_and_in_existing_context(self):
        manager,_port=self.manager(expect_vs1(2))
        with self.assertRaises(ExecutionRejected):
            execute_read_phases(manager,[job('x',ReadKind.VS1_P80)],Budget())

    def test_bad_ledger_type_rejected(self):
        manager,port=self.manager(expect_vs1(2))
        with manager:
            with self.assertRaises(ExecutionRejected):
                execute_read_phases(manager,[job('x',ReadKind.VS1_P80)],Budget(),ledger='wrong')
        self.assertEqual(port.script,[])

    def test_no_direct_device_imports_or_services(self):
        import handover_acceleration.phase_executor as m
        content=Path(m.__file__).read_text()
        for forbidden in ('import serial','Serial(', 'systemctl', 'subprocess.run(', '/dev/tty'):
            with self.subTest(token=forbidden):self.assertNotIn(forbidden,content)


if __name__=='__main__':
    unittest.main()
