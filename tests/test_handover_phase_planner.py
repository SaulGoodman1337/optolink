"""Only synthetic read-only phase planning; no serial/systemd operations."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from handover_acceleration.phase_planner import (
    Budget, ReadJob, PlanRejected, plan_phase_windows)
from handover_acceleration.scheduler import ReadKind


class PhasePlannerTests(unittest.TestCase):
    def setUp(self):
        self.budget = Budget(max_vs1_unavailable_ms=9000,
                             max_p06_age_ms=9000,
                             max_queue_wait_ms=30000)

    def task(self, i, mode, *, independent=True, deadline=30000, duration=45, queued=0):
        return ReadJob(str(i), ReadKind.P300_ID if mode == 'p300' else ReadKind.VS1_P06,
                       duration, deadline, queued, independent)

    def test_24_independent_tasks_one_verified_p300_window(self):
        tasks = [self.task(f'{i}-{m}', m) for i in range(12) for m in ('vs1', 'p300')]
        r = plan_phase_windows(tasks, self.budget)
        self.assertEqual(r.p300_windows, 1)
        self.assertEqual(r.handovers, 2)
        self.assertEqual(len([s for s in r.steps if s.kind == 'read']), 24)
        self.assertLess(r.duration_ms, 6000)
        self.assertEqual(r.steps[-1].kind, 'verified_vs1_return')
        self.assertEqual(r.status, 'SIMULATED_ONLY_NO_HARDWARE_TIMING_GUARANTEE')

    def test_p06_2100_ms_goal_refuses_even_single_zero_payload_window(self):
        job = self.task('p', 'p300', duration=1)
        b = Budget(max_vs1_unavailable_ms=9000, max_p06_age_ms=2100)
        with self.assertRaisesRegex(PlanRejected, 'P06'):
            plan_phase_windows([job], b)

    def test_strict_order_barrier_prevents_crossing(self):
        jobs = [self.task('a','p300'),self.task('b','vs1',independent=False),
                self.task('c','p300')]
        r = plan_phase_windows(jobs,self.budget)
        self.assertEqual(r.request_order, ('a','b','c'))
        self.assertEqual(r.p300_windows,2)
        self.assertEqual(r.handovers,4)

    def test_independent_is_local_and_stable_within_modes(self):
        jobs=[self.task('p1','p300'),self.task('v1','vs1'),
              self.task('p2','p300'),self.task('v2','vs1'),
              self.task('barrier','vs1',independent=False),
              self.task('p3','p300'),self.task('v3','vs1')]
        r=plan_phase_windows(jobs,self.budget)
        self.assertEqual(r.request_order,('v1','v2','p1','p2','barrier','v3','p3'))
        self.assertEqual(r.p300_windows,2)

    def test_previous_p06_age_is_included_in_max_gap(self):
        one=self.task('p','p300',duration=150)
        b=Budget(max_vs1_unavailable_ms=5000,max_p06_age_ms=4900)
        with self.assertRaisesRegex(PlanRejected,'P06'):
            plan_phase_windows([one],b,initial_p06_age_ms=500)

    def test_maximum_vs1_absence_explicitly_enforced(self):
        b=Budget(max_vs1_unavailable_ms=4000,max_p06_age_ms=9000)
        with self.assertRaisesRegex(PlanRejected,'unavailability'):
            plan_phase_windows([self.task('p','p300')],b)

    def test_deadline_can_reject_reordered_request(self):
        jobs=[self.task('p1','p300',deadline=9000),
              self.task('v1','vs1',deadline=15)]
        with self.assertRaisesRegex(PlanRejected, 'deadline'):
            plan_phase_windows(jobs,self.budget)

    def test_queued_wait_deadline_does_not_hide_handover(self):
        b=Budget(max_vs1_unavailable_ms=9000,max_p06_age_ms=9000,
                 max_queue_wait_ms=100)
        with self.assertRaisesRegex(PlanRejected,'queued request wait'):
            plan_phase_windows([self.task('p','p300')],b)

    def test_non_reorderable_alternation_preserved_no_fake_gain(self):
        jobs=[self.task(str(i),m,independent=False) for i,m in enumerate(
               ('p300','vs1','p300','vs1','p300','vs1'))]
        r=plan_phase_windows(jobs,self.budget)
        self.assertEqual(r.p300_windows,3)
        self.assertEqual(r.handovers,6)

    def test_invalid_payloads_and_unbounded_jobs_refused(self):
        bad = [
            lambda: ReadJob('bad','w;0x4050',10,30000),
            lambda: ReadJob('bad',ReadKind.P300_ID,float('nan'),30000),
            lambda: ReadJob('bad',ReadKind.P300_ID,10,float('inf')),
            lambda: ReadJob('bad',ReadKind.P300_ID,10,100,independent='yes'),
            lambda: Budget(enter_p300_ms=float('inf')),
        ]
        for factory in bad:
            with self.subTest(factory=factory), self.assertRaises(PlanRejected):
                factory()
        with self.assertRaises(PlanRejected):
            plan_phase_windows([self.task('x','p300'),self.task('x','vs1')],self.budget)

    def test_future_unarrived_tasks_not_eligible(self):
        with self.assertRaisesRegex(PlanRejected,'not-yet-arrived'):
            plan_phase_windows([self.task('late','p300',queued=10)],self.budget,now_ms=0)

    def test_non_p300_tasks_need_no_transition(self):
        jobs=[self.task('v1','vs1'),self.task('v2','vs1')]
        r=plan_phase_windows(jobs,self.budget)
        self.assertEqual(r.handovers,0)
        self.assertEqual(r.p300_windows,0)
        self.assertEqual(r.duration_ms,90)

    def test_hard_limits_are_declared_estimates_not_real_time_proofs(self):
        r=plan_phase_windows([self.task('p','p300')],self.budget)
        self.assertIn('SIMULATED_ONLY',r.status)
        self.assertAlmostEqual(r.max_vs1_unavailable_ms,2175.657+45+2295.102)
        self.assertAlmostEqual(r.max_p06_gap_ms,2175.657+45+2295.102)


if __name__ == '__main__':
    unittest.main()
