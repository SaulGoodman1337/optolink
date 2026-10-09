"""Research early-start frames, pure fake serial, no hardware/client calls."""
import tempfile
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from handover_acceleration.coordinator import (
    HandoverCoordinator, PortLease, Mode, EOT, ACK, P300_ID, P300_SOFTWARE,
    DEVICE_ID, SOFTWARE, ProtocolError,
)
from test_handover_acceleration import FakePort, FakeClock, expect_vs1, p300_reply


def speculative_early_start(*, start_reply=ACK):
    """Known frame sequence, but intentionally BEFORE expected controller ENQ."""
    return [(EOT, b''),
            (b'\x16\x00\x00', start_reply),
            (P300_ID, p300_reply(0xf8, DEVICE_ID)),
            (ACK, b''),
            (P300_SOFTWARE, p300_reply(0x778c, SOFTWARE)),
            (ACK, b'')]


class EarlyStartOfflineTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.clock = FakeClock()

    def manager(self, script):
        port=FakePort(script)
        m=HandoverCoordinator(lambda: port,
                              PortLease(Path(self.t.name)/'lease'),
                              clock=self.clock.monotonic, sleep=self.clock.sleep)
        return m,port

    def test_early_p300_start_known_frame_then_full_identity(self):
        m,p = self.manager(expect_vs1(2) + speculative_early_start() + expect_vs1(1))
        with m:
            m.to_p300_early_start_experiment()
            self.assertIs(m.mode, Mode.P300_VERIFIED)
            self.assertIn(('p300_early_start','verified'),m.history)
            m.to_vs1_fast()
        self.assertEqual(p.writes.count(EOT),3)
        self.assertEqual(p.writes.count(b'\x16\x00\x00'),1)
        self.assertFalse(p.script)
        self.assertTrue(p.closed)

    def test_early_start_nack_is_failure_then_conservative_vs1_restore(self):
        script=expect_vs1(2) + [(EOT,b''),(b'\x16\x00\x00',b'\x15')] + expect_vs1(2)
        m,p=self.manager(script)
        with m:
            with self.assertRaisesRegex(ProtocolError,'unexpected control'):
                m.to_p300_early_start_experiment()
            self.assertIs(m.mode, Mode.FAILED_CLOSED)
            self.assertIn(('p300_early_start','failed'),m.history)
        self.assertIn(('vs1','verified:2'),m.history)
        self.assertNotIn(('p300_early_start','verified'),m.history)
        self.assertFalse(p.script)

    def test_early_start_unanswered_ack_deadline_then_recovery(self):
        script=expect_vs1(2) + [(EOT,b''),(b'\x16\x00\x00',b'')] + expect_vs1(2)
        m,p=self.manager(script)
        with m:
            before=self.clock.now
            with self.assertRaisesRegex(ProtocolError,'RX deadline'):
                m.to_p300_early_start_experiment()
            elapsed=self.clock.now-before
            self.assertGreaterEqual(elapsed,.35)
            self.assertLess(elapsed,.5)
        self.assertFalse(p.script)
        self.assertTrue(p.closed)

    def test_early_start_rejected_from_unknown_or_p300(self):
        m,p=self.manager(expect_vs1(2) + speculative_early_start() + expect_vs1(1))
        with self.assertRaisesRegex(ProtocolError,'requires verified VS1'):
            m.to_p300_early_start_experiment()
        with m:
            m.to_p300_early_start_experiment()
            with self.assertRaisesRegex(ProtocolError,'requires verified VS1'):
                m.to_p300_early_start_experiment()
            m.to_vs1_fast()
        self.assertFalse(p.script)

    def test_unexpected_enq_is_not_misread_as_early_ack(self):
        script=expect_vs1(2) + [(EOT,b''),(b'\x16\x00\x00',b'\x05')] + expect_vs1(2)
        m,p=self.manager(script)
        with m:
            with self.assertRaisesRegex(ProtocolError,'unexpected control'):
                m.to_p300_early_start_experiment()
        self.assertFalse(p.script)
        self.assertIn(('vs1','verified:2'),m.history)

    def test_bad_identity_cannot_be_accepted_even_with_early_ack(self):
        script=expect_vs1(2)+[(EOT,b''),(b'\x16\x00\x00',ACK),
                              (P300_ID,p300_reply(0xf8,b'\x20\x99'))]+expect_vs1(2)
        m,p=self.manager(script)
        with m:
            with self.assertRaisesRegex(ProtocolError,'identity mismatch'):
                m.to_p300_early_start_experiment()
            self.assertIs(m.mode,Mode.FAILED_CLOSED)
        self.assertIn(('vs1','verified:2'),m.history)
        self.assertFalse(p.script)


if __name__=='__main__':
    unittest.main()
