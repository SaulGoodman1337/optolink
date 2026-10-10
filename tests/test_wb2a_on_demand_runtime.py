"""Fully fenced on-demand runtime with injected fake UART and owner-only GFA."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from handover_acceleration.continuous_runtime import (
    OnDemandReadonlyRuntime, DemandReply,
)
from handover_acceleration.ingress_epoch import IngressEpoch
from handover_acceleration.pending_refresh import PendingReadbackLedger
from handover_acceleration.phase_planner import Budget
from handover_acceleration.producer_fence import writer_transaction
from handover_acceleration.scheduler import ReadKind, TicketState
from test_handover_acceleration import (
    FakeClock, FakePort, expect_attached_vs1, expect_p300, expect_vs1,
)
from test_handover_fc03_fixed import response


class DemandRuntimeTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.lock=self.root/"producer.lock"
        self.lock.write_bytes(b"")
        self.lock.chmod(0o600)
        self.serial=self.root/"serial.lock"
        self.clock=FakeClock()
        self.ingress=IngressEpoch()
        self.mqtt=types.SimpleNamespace(
            cmnd_queue=[],lst_force_refresh=[],
            _hybrid_readback_ledger=PendingReadbackLedger())
        self.enrolled=True
        self.legacy_calls=[]
        self.restores=[]
        self.port=self.fake_port()
        self.runtime=OnDemandReadonlyRuntime(
            port=self.port,legacy_dispatch=self.legacy,
            resume_vs1=lambda:self.restores.append("reset"),
            mqtt=self.mqtt,tcp_state=lambda:0,
            ingress=self.ingress,
            all_writers_attested=lambda:self.enrolled,
            lease_path=self.lock,serial_lease_path=self.serial,
            budget=Budget(max_vs1_unavailable_ms=8000,
                          max_p06_age_ms=9000,max_queue_wait_ms=9000),
            clock=self.clock.monotonic,sleep=self.clock.sleep,
            min_interval_s=60)

    @staticmethod
    def fake_port(*,corrupt=False):
        if corrupt:
            sequence=(expect_attached_vs1()+expect_p300()
                      + response("ram_0f20_32",bad_crc=True)[:1]
                      + expect_vs1(2))
        else:
            sequence=(expect_attached_vs1()+expect_p300()
                      + response("ram_0f20_32")
                      + expect_vs1(1,p06=b"\x53"))
        return FakePort(sequence)

    def legacy(self,request,port):
        self.assertIs(port,self.port)
        self.legacy_calls.append(request)
        raw=b"\x20" if "4050" in request else b"\x53"
        return (1,bytearray(raw),raw.hex(),"original_gfa")

    def valid_gfa(self, *, p80=b"\x20",p06=b"\x53"):
        self.runtime.observe_original_result(
            ("gfa_p80_typ",0x4050,1,"gfa:raw",False),
            (1,bytearray(p80),p80.hex(),"original"))
        self.runtime.observe_original_result(
            ("geblaesedrehzahl_gfa_p06",0x4006,1,"gfa:30",False),
            (1,bytearray(p06),p06.hex(),"original"))
        self.runtime.note_keepalive(1)

    def submit(self,kind=ReadKind.P300_RAM_0F20_32,*,ttl_s=30):
        return self.runtime.submit_internal(kind,ttl_s=ttl_s)

    def test_no_demand_means_no_serial_or_identity_work(self):
        self.valid_gfa()
        self.assertFalse(self.runtime.due())
        self.assertEqual(self.runtime.tick().status,"NO_DEMAND")
        self.assertEqual(self.port.writes,[])

    def test_complete_one_demand_with_original_p06_and_fenced_single_port(self):
        ticket=self.submit()
        self.valid_gfa()
        self.assertTrue(self.runtime.due())
        outcome=self.runtime.tick()
        self.assertEqual(outcome.status,"VERIFIED_SWITCH")
        self.assertEqual(ticket.state,TicketState.COMPLETED)
        self.assertEqual(len(outcome.replies),1)
        reply=outcome.replies[0]
        self.assertIsInstance(reply,DemandReply)
        self.assertEqual(reply.kind,ReadKind.P300_RAM_0F20_32.value)
        self.assertEqual(len(reply.raw_hex),64)
        self.assertEqual(reply.origin,"P300_RAW_DIAGNOSTIC_NOT_ACTUAL_RPM")
        self.assertEqual(outcome.result.p80_hex,"20")
        self.assertEqual(outcome.result.p06_hex,"53")
        self.assertFalse(self.port.closed)
        self.assertEqual(self.port.script,[])
        self.assertEqual(self.lock.read_bytes(),b"")
        self.assertEqual(self.restores,["reset"])
        self.assertEqual(self.runtime.provenance.generation,2)
        self.assertEqual(
            self.runtime.provenance.require_age_ms(max_age_ms=9000),0.0)
        self.assertFalse(self.runtime.due())

    def test_large_real_monotonic_epoch_uses_consistent_absolute_deadlines(self):
        # Regression for 2026-10-10 first live canary: bridge used now_ms=0
        # while demand jobs had real absolute monotonic queued timestamps.
        self.clock.sleep(1_234_567.25)
        self.submit()
        self.valid_gfa()
        result=self.runtime.tick()
        self.assertEqual(result.status,"VERIFIED_SWITCH")
        self.assertEqual(len(result.replies),1)
        self.assertEqual(self.port.script,[])

    def test_duplicate_demand_one_physical_read_two_responses(self):
        a=self.submit()
        b=self.submit()
        self.valid_gfa()
        out=self.runtime.tick()
        self.assertEqual(out.status,"VERIFIED_SWITCH")
        self.assertEqual(len(out.result.reads),1)
        self.assertEqual({x.sequence for x in out.replies},{a.sequence,b.sequence})
        self.assertEqual({x.raw_hex for x in out.replies},
                         {out.result.reads[0][1]})

    def test_identity_does_not_prove_missing_p06(self):
        self.submit()
        self.runtime.note_keepalive(1)
        self.assertEqual(self.runtime.tick().reason,
                         "REAL_GFA_P06_NOT_FRESH")
        self.assertEqual(self.port.writes,[])

    def test_stale_p06_does_not_start_any_p300(self):
        self.submit()
        self.valid_gfa()
        self.clock.sleep(9.01)
        self.runtime.note_keepalive(1)
        self.assertEqual(self.runtime.tick().reason,
                         "REAL_GFA_P06_NOT_FRESH")
        self.assertEqual(self.port.writes,[])

    def test_p80_mismatch_never_allows_a_request(self):
        self.submit()
        self.valid_gfa(p80=b"\x21")
        self.assertEqual(self.runtime.tick().reason,
                         "REAL_GFA_P06_NOT_FRESH")
        self.assertEqual(self.port.writes,[])

    def test_unknown_writers_refuse_without_serial_or_consumption(self):
        t=self.submit()
        self.valid_gfa()
        self.enrolled=False
        self.assertEqual(self.runtime.tick().reason,
                         "WRITER_ENROLMENT_NOT_ATTESTED")
        self.assertEqual(t.state,TicketState.QUEUED)
        self.assertEqual(self.port.writes,[])

    def test_pending_ha_write_readback_blocks_switch(self):
        t=self.submit()
        self.valid_gfa()
        ledger=self.mqtt._hybrid_readback_ledger
        item=ledger.register(3)
        self.assertEqual(self.runtime.tick().reason,"HA_READBACK_PENDING")
        self.assertEqual(self.port.writes,[])
        self.assertEqual(t.state,TicketState.QUEUED)
        ledger.consume(item)
        ledger.complete_forced(1)
        self.clock.sleep(3)
        self.valid_gfa()
        self.assertEqual(self.runtime.tick().status,"VERIFIED_SWITCH")

    def test_external_writer_lease_refuses_and_does_not_spend_ticket(self):
        t=self.submit()
        self.valid_gfa()
        with writer_transaction("party",path=self.lock):
            self.assertEqual(self.runtime.tick().reason,
                             "WRITER_LEASE_BUSY_OR_UNVERIFIED")
            self.assertEqual(self.port.writes,[])
            self.assertEqual(t.state,TicketState.QUEUED)
        self.clock.sleep(3)
        self.valid_gfa()
        self.assertEqual(self.runtime.tick().status,"VERIFIED_SWITCH")

    def test_queued_external_mqtt_request_blocks_switch(self):
        t=self.submit()
        self.valid_gfa()
        self.mqtt.cmnd_queue.append("w;0x2303;1;1")
        self.assertEqual(self.runtime.tick().reason,"PENDING_LEGACY_WORK")
        self.assertEqual(t.state,TicketState.QUEUED)
        self.assertFalse(self.port.writes)

    def test_unacknowledged_write_refuses_even_after_settle(self):
        self.submit()
        self.valid_gfa()
        self.runtime.gate.observe_legacy("w;0x2303;1;1")
        self.assertEqual(self.runtime.tick().reason,
                         "WRITE_READBACK_NOT_ACKNOWLEDGED")
        self.assertEqual(self.port.writes,[])

    def test_bad_crc_latches_fence_and_never_marks_success(self):
        self.port=self.fake_port(corrupt=True)
        self.runtime.port=self.port
        t=self.submit()
        self.valid_gfa()
        with self.assertRaises(Exception):
            self.runtime.tick()
        self.assertEqual(t.state,TicketState.FAILED)
        self.assertTrue(self.runtime.demands.failed_closed)
        self.assertTrue(self.runtime.gate.failed_closed)
        self.assertEqual(self.lock.read_bytes(),b"P300_FAILED")
        self.assertFalse(self.runtime.due())
        self.assertEqual(self.runtime.tick().status,"FAIL_CLOSED")

    def test_no_write_kind_and_mqtt_raw_injection(self):
        for payload in ("w;0x2303;1;1", "hybrid;p300;0x4006", None):
            with self.assertRaises(Exception):
                self.runtime.submit_internal(payload)
        self.assertEqual(self.port.writes,[])

    def test_only_owner_thread_may_tick(self):
        self.submit()
        self.valid_gfa()
        collected=[]
        def worker():
            try: self.runtime.tick()
            except Exception: collected.append("owner_rejected")
        t=threading.Thread(target=worker)
        t.start();t.join()
        self.assertEqual(collected,["owner_rejected"])
        self.assertEqual(self.port.writes,[])


if __name__=="__main__":
    unittest.main()
