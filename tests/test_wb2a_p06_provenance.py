"""Original VS1 GFA P06/P80 witness: negative and generation tests."""
from __future__ import annotations
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from handover_acceleration.scheduler import (
    OwnerGfaProvenance, ReadKind, QueueBusy, SchedulingError, StaleReading,
)
from test_handover_acceleration import FakeClock


class P06ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.clock=FakeClock()
        self.ledger=OwnerGfaProvenance(clock=self.clock.monotonic)

    @staticmethod
    def result(raw, *, rc=1):
        return (rc,bytearray(raw),str(raw.hex()),"frame")

    def p80(self, value=b"\x20"):
        return self.ledger.observe_original(
            "gfaread;0x4050;1;raw;False",self.result(value))

    def p06(self, value=b"\x00"):
        return self.ledger.observe_original(
            ("geblaesedrehzahl_gfa_p06",0x4006,1,"gfa:30",False),
            self.result(value))

    def test_original_raw_positive_and_zero_preserve_age(self):
        self.assertTrue(self.p80())
        self.assertTrue(self.p06(b"\x00"))
        self.clock.sleep(.25)
        self.assertAlmostEqual(self.ledger.require_age_ms(max_age_ms=2000),250.0)
        self.p06(b"\x53")
        self.assertAlmostEqual(self.ledger.require_age_ms(max_age_ms=2000),0.0)

    def test_p80_required_before_any_p06(self):
        self.p06(b"\x53")
        with self.assertRaises(StaleReading):
            self.ledger.require_age_ms(max_age_ms=2000)

    def test_p80_failure_invalidates_even_good_p06(self):
        self.p80();self.p06()
        self.assertFalse(self.p80(b"\x21"))
        with self.assertRaises(StaleReading):
            self.ledger.require_age_ms(max_age_ms=2000)

    def test_ff_and_failed_p06_invalidate(self):
        for bad,rc in ((b"\xff",1),(b"\x00",255),(b"",1),(b"\x11\x22",1)):
            with self.subTest(bad=bad,rc=rc):
                self.p80();self.p06(b"\x53")
                self.assertFalse(self.ledger.observe_original(
                    "gr;0x4006;1;raw;False",self.result(bad,rc=rc)))
                with self.assertRaises(StaleReading):
                    self.ledger.require_age_ms(max_age_ms=2000)

    def test_virtual_poll_and_formatted_mqtt_do_not_refresh_gfa(self):
        for source in (
            "r;0x4006;1;raw;False",
            "gfaread;0x4006;1;30;False",
            "gfaread;0x4006;1;raw;True",
            ("fan",0x4006,1,30,False),
            ("fan",0x4006,1,"gfa:30",True),
            ("fan",0x4007,1,"gfa:30",False),
            ("fan",0x4006,2,"gfa:30",False),
            "raw;4105000100f80200",
            "p300_fc03;0x0f20;32",
        ):
            with self.subTest(source=source):
                self.assertFalse(self.ledger.observe_original(
                    source,self.result(b"\x53")))
        with self.assertRaises(StaleReading):
            self.ledger.require_age_ms(max_age_ms=2000)

    def test_stale_p06_refused_even_with_fresh_p80(self):
        self.p80();self.p06()
        self.clock.sleep(2.001)
        self.p80()
        with self.assertRaises(StaleReading):
            self.ledger.require_age_ms(max_age_ms=2000)

    def test_stale_p80_refused_even_with_fresh_p06(self):
        self.p80();self.p06()
        self.clock.sleep(2.001)
        self.p06()
        with self.assertRaises(StaleReading):
            self.ledger.require_age_ms(max_age_ms=2000)

    def test_protocol_generation_never_reuses_old_p06(self):
        self.p80();self.p06(b"\x53")
        self.ledger.before_transfer()
        with self.assertRaises(StaleReading):
            self.ledger.require_age_ms(max_age_ms=2000)
        with self.assertRaises(SchedulingError):
            self.p06()
        self.ledger.after_verified_return(p80_hex="20",p06_hex="53")
        self.assertEqual(self.ledger.generation,2)
        self.assertEqual(self.ledger.require_age_ms(max_age_ms=2000),0)
        self.assertFalse(self.ledger.in_transfer)

    def test_wrong_return_identity_and_ff_keep_fence(self):
        for identity,raw in (("21","53"),("20","ff"),("20","xx"),("20","")):
            with self.subTest(identity=identity,raw=raw):
                item=OwnerGfaProvenance(clock=self.clock.monotonic)
                item.before_transfer()
                with self.assertRaises(SchedulingError):
                    item.after_verified_return(p80_hex=identity,p06_hex=raw)
                with self.assertRaises(StaleReading):
                    item.require_age_ms(max_age_ms=2000)

    def test_no_unverified_return_without_transfer(self):
        with self.assertRaises(SchedulingError):
            self.ledger.after_verified_return(p80_hex="20",p06_hex="53")

    def test_failed_epoch_cannot_inherit_old_identity(self):
        self.p80();self.p06()
        self.ledger.fail_closed()
        with self.assertRaises(StaleReading):
            self.ledger.require_age_ms(max_age_ms=2000)

    def test_nonfinite_age_refused(self):
        self.p80();self.p06()
        for value in (-1,0,True,float("nan"),float("inf")):
            with self.subTest(value=value),self.assertRaises(SchedulingError):
                self.ledger.require_age_ms(max_age_ms=value)

    def test_owner_only_records_and_validates(self):
        results=[]
        def other():
            try:
                self.p80()
            except QueueBusy:
                results.append("blocked")
        thread=threading.Thread(target=other)
        thread.start();thread.join()
        self.assertEqual(results,["blocked"])
        with self.assertRaises(StaleReading):
            self.ledger.require_age_ms(max_age_ms=2000)


if __name__=="__main__":
    unittest.main()
