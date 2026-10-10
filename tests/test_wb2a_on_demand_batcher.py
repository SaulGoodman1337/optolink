"""Offline-only demand scheduler: no port or controller I/O."""
from __future__ import annotations

from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from handover_acceleration.phase_planner import Budget
from handover_acceleration.scheduler import (
    BoundedDemandBatcher, DemandSelection, P300_DEMAND_KINDS,
    ReadKind, SchedulingError, QueueBusy, TicketState,
)
from test_handover_acceleration import FakeClock


class DemandBatchTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.q = BoundedDemandBatcher(clock=self.clock.monotonic)
        self.budget = Budget(max_vs1_unavailable_ms=8000,
                             max_p06_age_ms=9000,
                             max_queue_wait_ms=9000)

    def test_only_known_fixed_size_p300_reads_admitted(self):
        self.assertEqual(len(P300_DEMAND_KINDS),4)
        for kind in ReadKind:
            if kind in P300_DEMAND_KINDS:
                self.assertEqual(self.q.submit(kind).state,TicketState.QUEUED)
            else:
                with self.subTest(kind=kind),self.assertRaises(SchedulingError):
                    self.q.submit(kind)
        for invalid in ("w;0x20a5", "fc03;0x2000", None, True):
            with self.subTest(invalid=invalid),self.assertRaises(SchedulingError):
                self.q.submit(invalid)

    def test_rx_candidate_never_scheduled_unless_explicitly_submitted(self):
        self.assertIsNone(self.q.select(self.budget,initial_p06_age_ms=0))
        t=self.q.submit(ReadKind.P300_RAM_1640_32)
        planned=self.q.select(self.budget,initial_p06_age_ms=0)
        self.assertEqual(planned.tickets,(t,))
        self.assertEqual([j.kind for j in planned.jobs],[ReadKind.P300_RAM_1640_32])
        self.assertEqual(planned.phase_plan.p300_windows,1)
        self.assertEqual(planned.phase_plan.handovers,2)
        self.assertEqual(t.state,TicketState.QUEUED)
        self.assertTrue(self.q.cancel(t))
        self.assertEqual(self.q.pending_count(),0)

    def test_coalesces_duplicate_reads_in_one_simulated_roundtrip(self):
        a=self.q.submit(ReadKind.P300_RAM_0F20_32)
        b=self.q.submit(ReadKind.P300_RAM_0F20_32)
        c=self.q.submit(ReadKind.P300_RAM_1C60_32)
        sel=self.q.select(self.budget,initial_p06_age_ms=100)
        self.assertEqual(len(sel.tickets),3)
        self.assertEqual(len(sel.jobs),2)
        self.assertEqual(sel.phase_plan.p300_windows,1)
        self.assertEqual(sel.phase_plan.handovers,2)
        self.assertEqual(sel.phase_plan.status,
                         "SIMULATED_ONLY_NO_HARDWARE_TIMING_GUARANTEE")
        self.assertTrue(all(t.state is TicketState.QUEUED for t in (a,b,c)))
        self.q.reserve(sel)
        self.assertEqual(self.q.pending_count(),0)
        self.q.complete(success=True,verified_vs1=True)
        self.assertTrue(all(t.state is TicketState.COMPLETED for t in (a,b,c)))

    def test_deadline_before_complete_roundtrip_refused_without_consuming(self):
        t=self.q.submit(ReadKind.P300_RAM_0F20_32,ttl_s=2)
        self.assertIsNone(self.q.select(self.budget,initial_p06_age_ms=0))
        self.assertEqual(self.q.pending_count(),1)
        self.assertEqual(t.state,TicketState.QUEUED)
        self.clock.sleep(2)
        self.assertIsNone(self.q.select(self.budget,initial_p06_age_ms=0))
        self.assertEqual(t.state,TicketState.EXPIRED)

    def test_p06_age_can_refuse_while_read_is_pending(self):
        t=self.q.submit(ReadKind.P300_ID)
        self.assertIsNone(self.q.select(self.budget,initial_p06_age_ms=6000))
        self.assertEqual(t.state,TicketState.QUEUED)
        self.assertIsNotNone(self.q.select(self.budget,initial_p06_age_ms=0))

    def test_cooldown_blocks_new_batch_without_losing_pending(self):
        self.q.submit(ReadKind.P300_ID)
        s=self.q.select(self.budget,initial_p06_age_ms=0)
        self.q.reserve(s)
        self.q.complete(success=True,verified_vs1=True)
        self.clock.sleep(59.99)
        t=self.q.submit(ReadKind.P300_RAM_0F20_32)
        self.assertIsNone(self.q.select(self.budget,initial_p06_age_ms=0))
        self.clock.sleep(0.01)
        self.assertIsNotNone(self.q.select(self.budget,initial_p06_age_ms=0))
        self.assertEqual(t.state,TicketState.QUEUED)

    def test_expired_request_never_promoted(self):
        expired=self.q.submit(ReadKind.P300_ID,ttl_s=1)
        self.clock.sleep(1.1)
        live=self.q.submit(ReadKind.P300_RAM_1C60_32)
        s=self.q.select(self.budget,initial_p06_age_ms=0)
        self.assertEqual(expired.state,TicketState.EXPIRED)
        self.assertEqual(s.tickets,(live,))

    def test_capacity_refusal_and_cancel(self):
        q=BoundedDemandBatcher(clock=self.clock.monotonic,capacity=1)
        t=q.submit(ReadKind.P300_ID)
        with self.assertRaises(QueueBusy):
            q.submit(ReadKind.P300_RAM_0F20_32)
        self.assertTrue(q.cancel(t))
        self.assertEqual(t.state,TicketState.CANCELLED)
        self.assertFalse(q.cancel(t))
        self.assertEqual(q.pending_count(),0)

    def test_reserve_cannot_follow_expiration_or_cancellation(self):
        t=self.q.submit(ReadKind.P300_ID)
        sel=self.q.select(self.budget,initial_p06_age_ms=0)
        self.q.cancel(t)
        with self.assertRaises(SchedulingError):
            self.q.reserve(sel)

    def test_reservation_cannot_be_reserved_twice(self):
        self.q.submit(ReadKind.P300_ID)
        sel=self.q.select(self.budget,initial_p06_age_ms=0)
        self.q.reserve(sel)
        with self.assertRaises(QueueBusy):
            self.q.reserve(sel)
        self.assertIsNone(self.q.select(self.budget,initial_p06_age_ms=0))

    def test_no_success_without_verified_return(self):
        t=self.q.submit(ReadKind.P300_RAM_1C60_32)
        self.q.reserve(self.q.select(self.budget,initial_p06_age_ms=0))
        self.q.complete(success=True,verified_vs1=False)
        self.assertEqual(t.state,TicketState.FAILED)
        self.assertTrue(self.q.failed_closed)
        with self.assertRaises(SchedulingError):
            self.q.submit(ReadKind.P300_ID)

    def test_failure_closed_without_clear_or_retry(self):
        t=self.q.submit(ReadKind.P300_ID)
        self.q.reserve(self.q.select(self.budget,initial_p06_age_ms=0))
        self.q.complete(success=False,verified_vs1=False)
        self.assertEqual(t.state,TicketState.FAILED)
        self.assertTrue(self.q.failed_closed)
        self.assertIsNone(self.q.select(self.budget,initial_p06_age_ms=0))

    def test_wrong_thread_cannot_schedule_or_reserve(self):
        self.q.submit(ReadKind.P300_ID)
        result=[]
        def worker():
            try:
                self.q.select(self.budget,initial_p06_age_ms=0)
                result.append("unexpected")
            except QueueBusy:
                result.append("blocked")
        thread=threading.Thread(target=worker)
        thread.start(); thread.join()
        self.assertEqual(result,["blocked"])
        self.assertEqual(self.q.pending_count(),1)

    def test_cross_thread_submit_is_queue_only_no_bus_action(self):
        produced=[]
        def enqueue():
            produced.append(self.q.submit(ReadKind.P300_ID))
        thread=threading.Thread(target=enqueue)
        thread.start(); thread.join()
        self.assertEqual(len(produced),1)
        self.assertIsNotNone(self.q.select(self.budget,initial_p06_age_ms=0))

    def test_explicit_p06_age_validation(self):
        self.q.submit(ReadKind.P300_ID)
        for age in (-1,True,float("nan"),float("inf"),"0"):
            with self.subTest(age=age),self.assertRaises(SchedulingError):
                self.q.select(self.budget,initial_p06_age_ms=age)

    def test_constructor_bounds_reject_invalid_values(self):
        for opts in ({"capacity":0},{"capacity":129},
                     {"max_distinct_reads":4},{"min_spacing_s":0},
                     {"min_spacing_s":float("inf")}):
            with self.subTest(opts=opts),self.assertRaises(ValueError):
                BoundedDemandBatcher(clock=self.clock.monotonic,**opts)

    def test_different_kinds_bounded_and_preserve_sequence(self):
        q=BoundedDemandBatcher(clock=self.clock.monotonic,max_distinct_reads=1)
        first=q.submit(ReadKind.P300_RAM_1C60_32)
        next_one=q.submit(ReadKind.P300_ID)
        last_same=q.submit(ReadKind.P300_RAM_1C60_32)
        sel=q.select(self.budget,initial_p06_age_ms=0)
        self.assertEqual(sel.tickets,(first,))
        self.assertEqual(next_one.state,TicketState.QUEUED)
        self.assertEqual(last_same.state,TicketState.QUEUED)

    def test_selection_type_enforced(self):
        self.q.submit(ReadKind.P300_ID)
        with self.assertRaises(SchedulingError):
            self.q.reserve("untrusted selection")

    def test_counterfeit_selection_is_never_reservable(self):
        self.q.submit(ReadKind.P300_ID)
        authentic=self.q.select(self.budget,initial_p06_age_ms=0)
        forged=DemandSelection(authentic.tickets,authentic.jobs,authentic.phase_plan)
        with self.assertRaisesRegex(SchedulingError,"untrusted"):
            self.q.reserve(forged)
        self.q.reserve(authentic)
        self.q.complete(success=True,verified_vs1=True)

    def test_stale_selection_requires_new_admission_proof(self):
        self.q.submit(ReadKind.P300_ID)
        old=self.q.select(self.budget,initial_p06_age_ms=0)
        self.clock.sleep(1.01)
        with self.assertRaisesRegex(SchedulingError,"expired batch selection"):
            self.q.reserve(old)
        updated=self.q.select(self.budget,initial_p06_age_ms=0)
        self.q.reserve(updated)
        self.q.complete(success=True,verified_vs1=True)

    def test_verified_late_response_is_expired_not_fresh(self):
        ticket=self.q.submit(ReadKind.P300_ID,ttl_s=30)
        self.q.reserve(self.q.select(self.budget,initial_p06_age_ms=0))
        self.clock.sleep(31)
        self.q.complete(success=True,verified_vs1=True)
        self.assertEqual(ticket.state,TicketState.EXPIRED)
        self.assertFalse(self.q.failed_closed)

    def test_unhashable_untrusted_kind_refused_without_crash(self):
        with self.assertRaises(SchedulingError):
            self.q.submit(["w", "0x20a5"])


if __name__ == "__main__":
    unittest.main()
