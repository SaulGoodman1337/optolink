"""Offline bridge: reviewed P300 demand -> existing admission -> fake UART."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from handover_acceleration.coordinator import PortLease
from handover_acceleration.phase_planner import Budget
from handover_acceleration.runtime_admission import DispatcherSnapshot, RuntimeAdmissionGate
from handover_acceleration.scheduler import (
    BoundedDemandBatcher, ReadKind, TicketState,
)
from test_handover_acceleration import (
    FakeClock, FakePort, ACK, DEVICE_ID, P300_ID,
    expect_attached_vs1, expect_p300, p300_reply, expect_vs1,
)
from test_handover_fc03_fixed import response


class DemandIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.clock=FakeClock()
        self.queue=BoundedDemandBatcher(clock=self.clock.monotonic)
        self.gate=RuntimeAdmissionGate(clock=self.clock.monotonic)
        self.budget=Budget(max_vs1_unavailable_ms=8000.0,
                           max_p06_age_ms=9000.0,max_queue_wait_ms=9000.0)
        self.safe=DispatcherSnapshot(
            mqtt_pending=0,tcp_pending=0,forced_polls_pending=0,
            pending_readbacks=0,frame_idle=True,
            external_writers_quiesced=True,queue_admission_paused=True,
            legacy_vs1_verified=True,nearest_writer_deadline_ms=12000.0)

    def _port(self):
        return FakePort(
            expect_attached_vs1()
            + expect_p300()
            + response("ram_0f20_32")
            + expect_vs1(1,p06=b"\x53"))

    def _legacy(self, request, port):
        raw=b"\x20" if "4050" in request else b"\x53"
        return (1,bytearray(raw),raw.hex(),"test")

    def test_admitted_one_demand_uses_original_fake_handle_and_vs1_proof(self):
        port=self._port()
        first=self.queue.submit(ReadKind.P300_RAM_0F20_32)
        duplicate=self.queue.submit(ReadKind.P300_RAM_0F20_32)
        selected=self.queue.select(self.budget,initial_p06_age_ms=0)
        self.assertTrue(self.gate.decide(self.safe,self.budget).admitted)
        self.queue.reserve(selected)
        outcome=self.gate.run_readonly_batch(
            self.safe,self.budget,port=port,legacy_dispatch=self._legacy,
            resume_vs1=lambda:None,lease=PortLease(self.root/"lease"),
            jobs=selected.jobs,clock=self.clock.monotonic,sleep=self.clock.sleep)
        self.queue.complete(success=outcome is not None and outcome.verified_vs1,
                            verified_vs1=outcome is not None and outcome.verified_vs1)
        self.assertEqual([name for name,_ in outcome.reads],
                         ["p300_ram_0f20_32"])
        self.assertEqual(outcome.p80_hex,"20")
        self.assertEqual(outcome.p06_hex,"53")
        self.assertEqual(outcome.p300_windows,1)
        self.assertFalse(port.closed)
        self.assertEqual(port.script,[])
        self.assertEqual(first.state,TicketState.COMPLETED)
        self.assertEqual(duplicate.state,TicketState.COMPLETED)

    def test_unverified_writers_refuse_with_zero_uart_and_keep_request(self):
        class NoPort:
            writes=[]
            def write(self,data):
                raise AssertionError("no IO allowed during refusal")
        port=NoPort()
        ticket=self.queue.submit(ReadKind.P300_RAM_0F20_32)
        selected=self.queue.select(self.budget,initial_p06_age_ms=0)
        blocked=replace(self.safe,external_writers_quiesced=False)
        self.assertFalse(self.gate.decide(blocked,self.budget).admitted)
        outcome=self.gate.run_readonly_batch(
            blocked,self.budget,port=port,
            legacy_dispatch=lambda *_: self.fail("not allowed"),
            resume_vs1=lambda: self.fail("not allowed"),
            lease=PortLease(self.root/"lease"),jobs=selected.jobs)
        self.assertIsNone(outcome)
        self.assertEqual(ticket.state,TicketState.QUEUED)
        self.assertEqual(self.queue.pending_count(),1)
        self.assertFalse((self.root/"lease").exists())

    def test_missing_vs1_p06_age_stops_before_gate(self):
        self.queue.submit(ReadKind.P300_RAM_1C60_32)
        self.assertIsNone(self.queue.select(
            self.budget,initial_p06_age_ms=6500))
        self.assertFalse((self.root/"lease").exists())


if __name__ == "__main__":
    unittest.main()
