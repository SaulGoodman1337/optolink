"""Read-only queue batching and sensor freshness, no real serial I/O."""
from __future__ import annotations

import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from handover_acceleration.scheduler import (
    BoundedReadQueue, GfaFreshnessLedger, QueueBusy, ReadKind,
    SchedulingError, StaleReading, TicketState,
)
from test_handover_acceleration import FakeClock


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.queue = BoundedReadQueue(capacity=5, max_same_mode=2,
                                      clock=self.clock.monotonic)

    def test_readonly_kinds_reject_raw_and_write(self):
        with self.assertRaises(SchedulingError):
            self.queue.submit("writeraw;0x4006;ff")
        with self.assertRaises(SchedulingError):
            self.queue.submit("C9")
        self.assertEqual(self.queue.pending_count(), 0)

    def test_capacity_is_bounded(self):
        tickets = [self.queue.submit(ReadKind.VS1_P06) for _ in range(5)]
        with self.assertRaises(QueueBusy):
            self.queue.submit(ReadKind.P300_ID)
        self.assertTrue(self.queue.cancel(tickets[0]))
        self.queue.submit(ReadKind.P300_ID)
        self.assertEqual(self.queue.pending_count(), 5)

    def test_expired_read_is_never_dispatched(self):
        ticket = self.queue.submit(ReadKind.VS1_P06, ttl_s=1)
        self.clock.sleep(1.01)
        self.assertEqual(self.queue.pending_count(), 0)
        self.assertEqual(ticket.state, TicketState.EXPIRED)
        self.assertIsNone(self.queue.take())

    def test_bad_unbounded_deadline_rejected(self):
        for ttl in (float("inf"), float("nan"), 0, -1, True):
            with self.subTest(ttl=ttl), self.assertRaises(SchedulingError):
                self.queue.submit(ReadKind.VS1_P80, ttl_s=ttl)

    def test_cancel_queued_but_never_mid_frame(self):
        a = self.queue.submit(ReadKind.VS1_P80)
        b = self.queue.submit(ReadKind.P300_ID)
        self.assertTrue(self.queue.cancel(b))
        self.assertFalse(self.queue.cancel(b))
        self.assertIs(self.queue.take(), a)
        self.assertFalse(self.queue.cancel(a))
        with self.assertRaises(QueueBusy):
            self.queue.close()
        self.queue.finish(a, success=True)
        self.assertEqual(a.state, TicketState.COMPLETED)
        self.assertIsNone(self.queue.take())

    def test_only_one_inflight_and_one_owner(self):
        a = self.queue.submit(ReadKind.VS1_P06)
        b = self.queue.submit(ReadKind.P300_ID)
        self.assertIs(self.queue.take(), a)
        with self.assertRaises(QueueBusy):
            self.queue.take()
        results=[]
        def compete():
            try:
                self.queue.take()
            except QueueBusy:
                results.append("blocked")
        thread=threading.Thread(target=compete)
        thread.start(); thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(results,["blocked"])
        self.queue.finish(a,success=True)
        self.assertIs(self.queue.take(), b)
        self.queue.finish(b,success=False)
        self.assertEqual(b.state,TicketState.FAILED)

    def test_prefer_current_mode_but_bound_starvation(self):
        q=BoundedReadQueue(capacity=10,max_same_mode=2,
                           clock=self.clock.monotonic)
        for _ in range(4): q.submit(ReadKind.VS1_P06)
        for _ in range(2): q.submit(ReadKind.P300_ID)
        chosen=[]
        while q.pending_count():
            ticket=q.take(preferred_mode="vs1")
            chosen.append(ticket.kind.mode)
            q.finish(ticket,success=True)
        self.assertEqual(chosen,["vs1","vs1","p300","vs1","vs1","p300"])

    def test_finish_rejects_wrong_ticket_and_invalid_completion(self):
        a=self.queue.submit(ReadKind.VS1_P06)
        b=self.queue.submit(ReadKind.VS1_P80)
        self.queue.take()
        with self.assertRaises(SchedulingError):
            self.queue.finish(b,success=True)
        with self.assertRaises(SchedulingError):
            self.queue.finish(a,success=1)
        self.queue.finish(a,success=False)
        self.assertEqual(a.state,TicketState.FAILED)

    def test_close_cancels_pending_and_refuses_new_read(self):
        a=self.queue.submit(ReadKind.VS1_P06)
        b=self.queue.submit(ReadKind.P300_ID)
        self.queue.close()
        self.assertEqual(a.state,TicketState.CANCELLED)
        self.assertEqual(b.state,TicketState.CANCELLED)
        with self.assertRaises(SchedulingError):
            self.queue.submit(ReadKind.VS1_P06)


class FreshnessTests(unittest.TestCase):
    def setUp(self):
        self.clock=FakeClock()
        self.ledger=GfaFreshnessLedger(clock=self.clock.monotonic)

    def test_real_p06_raw_zero_is_valid_with_provenance(self):
        reading=self.ledger.record(ReadKind.VS1_P06,b"\x00",
                                   session_generation=1,vs1_verified=True)
        self.assertEqual(reading.raw,b"\x00")
        self.assertEqual(reading.source,"verified_vs1_gfa")
        self.assertEqual(self.ledger.fresh(ReadKind.VS1_P06,
                         current_generation=1,max_age_s=0).raw,b"\x00")

    def test_generation_change_never_reuses_old_sample(self):
        self.ledger.record(ReadKind.VS1_P06,b"\x28",
                           session_generation=7,vs1_verified=True)
        with self.assertRaises(StaleReading):
            self.ledger.fresh(ReadKind.VS1_P06,current_generation=8,max_age_s=10)

    def test_expired_sample_is_stale_not_fake_current(self):
        self.ledger.record(ReadKind.VS1_P06,b"\x11",
                           session_generation=2,vs1_verified=True)
        self.clock.sleep(3.0)
        with self.assertRaises(StaleReading):
            self.ledger.fresh(ReadKind.VS1_P06,current_generation=2,max_age_s=2)

    def test_ff_invalidates_previous_p06_sample(self):
        self.ledger.record(ReadKind.VS1_P06,b"\x01",
                           session_generation=1,vs1_verified=True)
        with self.assertRaises(SchedulingError):
            self.ledger.record(ReadKind.VS1_P06,b"\xff",
                               session_generation=1,vs1_verified=True)
        with self.assertRaises(StaleReading):
            self.ledger.fresh(ReadKind.VS1_P06,current_generation=1,max_age_s=10)

    def test_wrong_p80_invalidates_identity_gate(self):
        self.ledger.record(ReadKind.VS1_P80,b"\x20",
                           session_generation=1,vs1_verified=True)
        with self.assertRaises(SchedulingError):
            self.ledger.record(ReadKind.VS1_P80,b"\x21",
                               session_generation=1,vs1_verified=True)
        with self.assertRaises(StaleReading):
            self.ledger.fresh(ReadKind.VS1_P80,current_generation=1,max_age_s=10)

    def test_p09_does_not_satisfy_p06_actual_rpm(self):
        self.ledger.record(ReadKind.VS1_P09,b"\x60",
                           session_generation=1,vs1_verified=True)
        with self.assertRaises(StaleReading):
            self.ledger.fresh(ReadKind.VS1_P06,current_generation=1,max_age_s=10)
        with self.assertRaises(SchedulingError):
            self.ledger.record(ReadKind.P300_ID,b"\x00",
                               session_generation=1,vs1_verified=True)

    def test_unverified_sample_refused_and_invalidated(self):
        self.ledger.record(ReadKind.VS1_P06,b"\x01",
                           session_generation=1,vs1_verified=True)
        with self.assertRaises(SchedulingError):
            self.ledger.record(ReadKind.VS1_P06,b"\x01",
                               session_generation=1,vs1_verified=False)
        with self.assertRaises(StaleReading):
            self.ledger.fresh(ReadKind.VS1_P06,current_generation=1,max_age_s=10)

    def test_invalidate_all_on_switchover(self):
        self.ledger.record(ReadKind.VS1_P80,b"\x20",
                           session_generation=1,vs1_verified=True)
        self.ledger.invalidate_all()
        with self.assertRaises(StaleReading):
            self.ledger.fresh(ReadKind.VS1_P80,current_generation=1,max_age_s=10)


if __name__ == '__main__':
    unittest.main()
