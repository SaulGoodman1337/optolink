"""Offline delayed-byte regression against historic ENQ waits, NO hardware."""
from __future__ import annotations

import statistics
import tempfile
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from handover_acceleration.coordinator import (
    ACK, EOT, STX, VS1_ID, DEVICE_ID, ProtocolError,
    HandoverCoordinator, Mode, PortLease, TX_ALLOW,
)
from handover_acceleration.timing_simulator import (
    ARCHIVED_ENQ_MS, PeerStep, TimedPeer, VirtualClock,
    enq_step, vs1_script, p300_script, compare_profiles,
    simulate_roundtrip, step,
)


class TimedHandoverTests(unittest.TestCase):
    def test_realistic_separate_enq_arrivals(self):
        clock = VirtualClock()
        port = TimedPeer(clock, [enq_step(2, 1998, 2238)])
        from handover_acceleration.coordinator import ReadOnlyWire, WirePhase, ENQ
        wire = ReadOnlyWire(port, clock=clock.monotonic, sleep=clock.sleep)
        wire.phase = WirePhase.VS1_SYNC
        wire.sync(2)
        received = [(t, raw) for kind, raw, t in wire.events if kind == "RX"]
        self.assertEqual([raw for _, raw in received], ["05", "05"])
        self.assertAlmostEqual(received[0][0], 1.998, delta=.002)
        self.assertAlmostEqual(received[1][0] - received[0][0], 2.238, delta=.002)
        self.assertLessEqual(clock.largest_sleep, .0011)
        self.assertFalse(port.pending)

    def test_no_unjustified_sub_second_speedup(self):
        pairs = compare_profiles()
        for i, (baseline, fast) in enumerate(pairs):
            with self.subTest(profile=i):
                self.assertTrue(baseline.all_steps_consumed)
                self.assertTrue(fast.all_steps_consumed)
                self.assertEqual(baseline.control_tx_count, 3)
                self.assertEqual(fast.control_tx_count, 3)
                # Paired fake-peers differ ONLY in additional VS1 ENQ.
                self.assertAlmostEqual(baseline.elapsed_ms - fast.elapsed_ms,
                    ARCHIVED_ENQ_MS[i][2], delta=2.0)
                self.assertGreater(fast.elapsed_ms, 3995.0)
                self.assertLessEqual(fast.largest_host_sleep_ms, 25.001)
                self.assertLessEqual(baseline.largest_host_sleep_ms, 25.001)

    def test_no_sleep_accounts_for_two_second_rx(self):
        sample = simulate_roundtrip(1, 0)
        self.assertGreater(sample.p300_ms, 1996)
        self.assertGreater(sample.return_ms, 1997)
        self.assertLess(sample.largest_host_sleep_ms, 26.0)

    def test_bad_first_vs1_identity_recovers_with_two_enqs(self):
        clock = VirtualClock()
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        first, back, extra = ARCHIVED_ENQ_MS[0]
        steps = (vs1_script(2, back, extra) + p300_script(first) +
                 [enq_step(1, back, extra), step(STX + VS1_ID, (0.021, b"\x00\x00"))] +
                 vs1_script(2, back, extra))
        port = TimedPeer(clock, steps)
        coord = HandoverCoordinator(lambda: port, PortLease(Path(t.name) / 'lease'),
                                    clock=clock.monotonic, sleep=clock.sleep)
        with self.assertRaisesRegex(ProtocolError, 'identity mismatch'):
            with coord:
                coord.p300_window(lambda _: None)
        self.assertEqual(coord.mode, Mode.DETACHED)
        self.assertEqual(coord.history[-2:], [('vs1', 'failed'),
                                              ('vs1', 'verified:2')])
        self.assertNotIn(('vs1', 'verified:1'), coord.history)
        self.assertTrue(port.closed)
        self.assertFalse(port.script)
        self.assertFalse(port.pending)
        self.assertTrue(all(raw in TX_ALLOW for _, raw in port.writes))

    def test_timed_p300_enq_timeout_forces_recovery(self):
        clock = VirtualClock()
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        first, back, extra = ARCHIVED_ENQ_MS[1]
        steps = vs1_script(2, back, extra) + [step(EOT)] + vs1_script(2, back, extra)
        port = TimedPeer(clock, steps)
        coord = HandoverCoordinator(lambda: port, PortLease(Path(t.name) / 'lease'),
                                    clock=clock.monotonic, sleep=clock.sleep)
        with self.assertRaisesRegex(ProtocolError, 'RX deadline'):
            with coord:
                coord.p300_window(lambda _: None)
        self.assertEqual(coord.history[-1], ('vs1', 'verified:2'))
        self.assertIn(('p300', 'failed'), coord.history)
        self.assertEqual(sum(raw == EOT for _, raw in port.writes), 3)
        self.assertTrue(port.closed)
        self.assertFalse(port.script)
        self.assertFalse(port.pending)

    def test_stale_extra_enq_is_not_successful_fast_return(self):
        # An extra, unexpected ENQ during a completed VS1 identity read
        # must not be treated as a verified session by the fake peer.
        clock = VirtualClock()
        from handover_acceleration.coordinator import ReadOnlyWire
        first, back, extra = ARCHIVED_ENQ_MS[2]
        steps = vs1_script(2, back, extra) + p300_script(first) + [
            enq_step(1, back, extra), step(STX + VS1_ID, (0.021, b"\x05\x05")),
        ]
        port = TimedPeer(clock, steps)
        wire = ReadOnlyWire(port, clock=clock.monotonic, sleep=clock.sleep)
        wire.verify_vs1(2)
        wire.verify_p300()
        with self.assertRaisesRegex(ProtocolError, 'identity mismatch'):
            wire.verify_vs1(1)
        self.assertEqual(wire.phase.value, 'failed_closed')


if __name__ == '__main__':
    unittest.main()
