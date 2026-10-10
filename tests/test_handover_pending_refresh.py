"""HA delayed write-readback accounting against the actual queue contract."""
from __future__ import annotations

from pathlib import Path
import sys
import threading
import types
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from handover_acceleration.pending_refresh import (
    PendingReadbackLedger, RefreshLedgerRejected, install_before_mqtt_connect,
)


class ManualThread:
    launched = []

    def __init__(self, *, target, daemon):
        self.target = target
        self.daemon = daemon

    def start(self):
        self.launched.append(self)


class FailedThread(ManualThread):
    def start(self):
        raise RuntimeError("cannot start")


class PendingHARefreshTests(unittest.TestCase):
    def setUp(self):
        ManualThread.launched = []
        self.sleep_calls = []
        self.fake_mqtt = types.SimpleNamespace(
            mqtt_client=None, lst_force_refresh=[])
        def legacy_force_delayed(index, delay=1):
            raise AssertionError("original timer must be replaced")
        def legacy_is_forced():
            if self.fake_mqtt.lst_force_refresh:
                return self.fake_mqtt.lst_force_refresh.pop(0)
            return None
        self.fake_mqtt.force_delayed = legacy_force_delayed
        self.fake_mqtt.is_forced = legacy_is_forced

    def install(self, thread_type=ManualThread):
        return install_before_mqtt_connect(
            self.fake_mqtt, thread_type=thread_type,
            sleep=self.sleep_calls.append)

    def test_pending_set_writeback_exists_before_timer_wakes(self):
        ledger = self.install()
        for delay in (0.25, 1, 2.5, 5.0):
            self.fake_mqtt.force_delayed(17, delay)
        self.assertEqual(ledger.pending_count, 4)
        self.assertEqual(self.fake_mqtt.lst_force_refresh, [])
        self.assertIsNone(self.fake_mqtt.is_forced())
        for expected, thread in enumerate(ManualThread.launched, start=1):
            self.assertTrue(thread.daemon)
            thread.target()
            self.assertEqual(ledger.pending_count, 5-expected)
            self.assertEqual(self.fake_mqtt.is_forced(), 17)
            self.assertEqual(ledger.pending_count, 5-expected)
            ledger.complete_forced(1)
            self.assertEqual(ledger.pending_count, 4-expected)
        self.assertEqual(self.sleep_calls, [0.25, 1, 2.5, 5.0])
        self.assertEqual(ledger.total_registered, 4)

    def test_duplicate_datapoint_indices_are_distinct_transactions(self):
        ledger = self.install()
        self.fake_mqtt.force_delayed(19, .5)
        self.fake_mqtt.force_delayed(19, 1)
        ManualThread.launched[1].target()
        self.assertEqual(self.fake_mqtt.is_forced(), 19)
        self.assertEqual(ledger.pending_count, 2)
        ledger.complete_forced(1)
        self.assertEqual(ledger.pending_count, 1)
        ManualThread.launched[0].target()
        self.assertEqual(self.fake_mqtt.is_forced(), 19)
        self.assertEqual(ledger.pending_count, 1)
        ledger.complete_forced(1)
        self.assertEqual(ledger.pending_count, 0)

    def test_forced_refresh_from_other_source_does_not_ack_ha_write(self):
        ledger = self.install()
        self.fake_mqtt.force_delayed(8, 5)
        self.fake_mqtt.lst_force_refresh.append(8)
        self.assertEqual(self.fake_mqtt.is_forced(), 8)
        self.assertEqual(ledger.pending_count, 1)
        ManualThread.launched[0].target()
        self.assertEqual(self.fake_mqtt.is_forced(), 8)
        self.assertEqual(ledger.pending_count, 1)
        ledger.complete_forced(1)
        self.assertEqual(ledger.pending_count, 0)

    def test_loss_of_forced_queue_fails_closed_instead_of_claiming_idle(self):
        ledger = self.install()
        self.fake_mqtt.force_delayed(4, 5)
        ManualThread.launched[0].target()
        self.fake_mqtt.lst_force_refresh = []  # legacy force-poll/reset path
        self.assertIsNone(self.fake_mqtt.is_forced())
        self.assertEqual(ledger.pending_count, 1)

    def test_pop_without_actual_readback_is_not_a_completion(self):
        ledger=self.install()
        self.fake_mqtt.force_delayed(3, .25)
        ManualThread.launched[0].target()
        self.assertEqual(self.fake_mqtt.is_forced(),3)
        self.assertEqual(ledger.pending_count,1)
        self.fake_mqtt._hybrid_complete_forced(0xff)
        self.assertEqual(ledger.pending_count,1)
        self.assertTrue(ledger.failed_closed)
        # A later unrelated success can never erase a failed /set readback.
        self.fake_mqtt._hybrid_complete_forced(1)
        self.assertEqual(ledger.pending_count,1)

    def test_idle_guard_checks_inflight_and_stale_failed_readback(self):
        ledger=self.install()
        ledger.require_idle_for_p300()
        self.fake_mqtt.force_delayed(3, .25)
        with self.assertRaises(RefreshLedgerRejected):
            ledger.require_idle_for_p300()
        ManualThread.launched[0].target()
        self.assertEqual(self.fake_mqtt.is_forced(),3)
        with self.assertRaises(RefreshLedgerRejected):
            ledger.require_idle_for_p300()
        ledger.complete_forced(1)
        ledger.require_idle_for_p300()
        self.fake_mqtt.force_delayed(3, .25)
        ManualThread.launched[1].target()
        self.assertEqual(self.fake_mqtt.is_forced(),3)
        ledger.complete_forced(255)
        with self.assertRaises(RefreshLedgerRejected):
            ledger.require_idle_for_p300()

    def test_forged_or_duplicate_ticket_refused(self):
        ledger = self.install()
        token = ledger.register(1)
        self.assertEqual(ledger.consume(token), 1)
        for bad in (token, (token[0], token[1], 2)):
            with self.subTest(bad=bad):
                with self.assertRaises(RefreshLedgerRejected):
                    ledger.consume(bad)

    def test_refuse_installing_after_mqtt_is_already_running(self):
        self.fake_mqtt.mqtt_client=object()
        with self.assertRaisesRegex(RefreshLedgerRejected,"before MQTT"):
            self.install()
        self.assertFalse(hasattr(self.fake_mqtt,"_hybrid_readback_ledger"))

    def test_double_install_refused_without_losing_pending(self):
        ledger=self.install()
        self.fake_mqtt.force_delayed(1, 1)
        with self.assertRaisesRegex(RefreshLedgerRejected,"already installed"):
            self.install()
        self.assertEqual(ledger.pending_count, 1)

    def test_failure_to_start_worker_clears_only_never_started_ticket(self):
        ledger=self.install(thread_type=FailedThread)
        with self.assertRaisesRegex(RuntimeError,"cannot start"):
            self.fake_mqtt.force_delayed(3, .5)
        self.assertEqual(ledger.pending_count, 0)

    def test_wrong_or_unbounded_inputs_dont_enqueue(self):
        ledger=self.install()
        for bad_index in (-1, True, False, "0", None):
            with self.subTest(index=bad_index), self.assertRaises(RefreshLedgerRejected):
                self.fake_mqtt.force_delayed(bad_index, 1)
        for bad_delay in (-1, 61, True, None):
            with self.subTest(delay=bad_delay), self.assertRaises(RefreshLedgerRejected):
                self.fake_mqtt.force_delayed(1, bad_delay)
        self.assertEqual(ledger.pending_count, 0)

    def test_unrelated_default_poll_remains_untouched(self):
        ledger=self.install()
        self.fake_mqtt.lst_force_refresh.append(11)
        self.assertEqual(self.fake_mqtt.is_forced(),11)
        self.assertEqual(ledger.pending_count,0)


if __name__ == "__main__":
    unittest.main()
