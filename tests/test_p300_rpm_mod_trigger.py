"""Offline tests for NATURAL high/low modulation P300->VS1 P06 experiment."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / "tools" / "wb2a-p300-rpm-mod-trigger.py"
spec = importlib.util.spec_from_file_location("rpm_mod_trigger", PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def sample(byte0=69, byte9=66, ram=0x54, flame=True, p87=0x62,
           coherent=True, lockout=False, cycle=1):
    status = {"flame":flame, "lockout":lockout,
              "byte0":byte0, "byte5":32 if flame else 0,
              "byte7":p87, "byte9":byte9, "payload_hex":"00"*11}
    return {
        "cycle":cycle, "first_status":status, "last_status":dict(status),
        "candidates":{"0f20":ram,"1c76":ram,"0f27":0,"0f28":0,
                      "0f29":p87,"1c7d":0,"1c7e":p87,"copies_equal":True},
        "quality":{"status_coherent":coherent},
        "core_payload":bytes([ram])*64,"context_payload":None,
        "start_utc":"2026-10-09T18:16:55Z",
        "end_utc":"2026-10-09T18:16:56Z",
        "duration_s":0.2
    }


class ModulationPlateau(unittest.TestCase):
    def test_inert_import_and_limits(self):
        self.assertIn("modulation-two-plateau", m.VERSION)
        self.assertEqual(m.UNIT,"optolink-p300-rpm-mod.service")
        self.assertEqual(m.CANDIDATE_RUNNING_RAW,0x54)
        self.assertEqual(m.HIGH_MODULATION_BYTE0,60)
        self.assertEqual(m.LOW_MODULATION_BYTE0,42)
        self.assertEqual(m.MIN_HIGH_CYCLES,4)
        self.assertEqual(m.TRIGGER_COOLDOWN_SECONDS,15)
        self.assertEqual(m.MAX_TRIGGERS,2)
        self.assertEqual(m.CANARY_SECONDS,300)

    def test_strict_allowlist_including_no_unknown_alias(self):
        self.assertEqual(m.ALLOWED_P300_SPECS, frozenset({
            (1,0x55d3,11),(3,0x0f20,32),(3,0x1c60,32)}))
        for item in m.ALLOWED_P300_SPECS:
            frame=m.frame(item)
            self.assertTrue(m.TriggerWire.permitted("p300",frame,None))
        for item in [(1,0x4006,1),(1,0x7650,1),(3,0x03ae,1),
                     (3,0x0f00,32),(3,0x1c40,32),
                     (201,0x4006,1),(7,0x4006,1),(9,0x4006,1),
                     (4,0x0f20,32)]:
            with self.subTest(item=item),self.assertRaises(ValueError):
                m.frame(item)
        self.assertFalse(m.TriggerWire.permitted("p300",b"\x04",None))

    def test_high_plateau_from_old_20261009_short_run(self):
        high=[sample(byte0=69,byte9=66,cycle=i) for i in range(1,5)]
        self.assertTrue(all(m.high_candidate(x) for x in high))
        self.assertTrue(m.trigger_eligible(high,-999,100,0))
        self.assertFalse(m.trigger_eligible(high[:3],-999,100,0))
        self.assertFalse(m.trigger_eligible(high,90,100,0))
        self.assertFalse(m.trigger_eligible(high,-999,100,1,low_armed=True))
        self.assertFalse(m.trigger_eligible(high,-999,100,2,low_armed=True))

    def test_low_plateau_after_high_only_same_flame(self):
        low=[sample(byte0=38,byte9=33,cycle=i) for i in range(8,12)]
        self.assertTrue(all(m.low_candidate(x) for x in low))
        self.assertFalse(m.trigger_eligible(low,-999,100,0))
        self.assertFalse(m.trigger_eligible(low,90,100,1,low_armed=True))
        self.assertFalse(m.trigger_eligible(low,0,10,1,low_armed=True))
        self.assertFalse(m.trigger_eligible(low,0,100,1,low_armed=False))
        self.assertTrue(m.trigger_eligible(low,10,100,1,low_armed=True))
        self.assertFalse(m.trigger_eligible(low,10,700,1,low_armed=True))
        self.assertFalse(m.trigger_eligible(low,10,100,2,low_armed=True))

    def test_fails_closed_flame_lockout_status_and_raw(self):
        for bad in [
            sample(flame=False),sample(lockout=True),sample(coherent=False),
            sample(ram=0),sample(ram=0xac),sample(byte0=59),
            sample(byte9=54)
        ]:
            self.assertFalse(m.high_candidate(bad))
        for bad in [
            sample(byte0=43,byte9=33),sample(byte0=38,byte9=41),
            sample(byte0=38,byte9=33,ram=0),sample(byte0=38,byte9=33,flame=False),
            sample(byte0=38,byte9=33,lockout=True)
        ]:
            self.assertFalse(m.low_candidate(bad))
        with self.assertRaises(ValueError):
            m.modulation_plateau(sample(),"BAD")

    def test_native_status_changes_within_frame_pair_are_excluded(self):
        high=sample()
        high["last_status"]["byte0"]=30
        # Core temporal status_coherent ignores byte0 changes by design,
        # therefore our high/low predicate checks BOTH status endpoints.
        self.assertFalse(m.high_candidate(high))
        low=sample(38,33)
        low["last_status"]["byte9"]=65
        self.assertFalse(m.low_candidate(low))

    def test_summary_never_calls_p300_actual_p06_verified(self):
        pre=[sample(cycle=i) for i in (1,2,3,4)]
        post=[sample(cycle=i) for i in (5,6)]
        measured={"identity_verified":True,"stable":True,
                  "p06_invalid_ff":0,"p06_rpm_unique":[3990]}
        report=m.summarize_capture(pre,measured,post)
        self.assertEqual(report["quality"],"P06_PLUS_ONE_NUMERIC_MISMATCH")
        self.assertEqual(report["predicted_rpm_hypothetical"],2490)
        self.assertEqual(report["delta_real_minus_predicted_rpm"],1500)
        self.assertFalse(report["p300_actual_p06_verified"])
        measured["stable"]=False
        self.assertEqual(m.summarize_capture(pre,measured,post)["quality"],
                         "TRANSITION_OR_UNKNOWN")
        post[0]["candidates"]["0f20"]=0
        measured["stable"]=True
        self.assertEqual(m.summarize_capture(pre,measured,post)["quality"],
                         "TRANSITION_OR_UNKNOWN")

    def test_canary_pinned_hash_required(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"root";root.mkdir()
            bundle=Path(td)/"bundles";bundle.mkdir()
            session=root/"run-test";session.mkdir()
            (session/"state.json").write_text(json.dumps({
                "mode":"canary","logger_sha256":"FAKE_SOURCE_HASH"}))
            (session/"measurement.json").write_text(json.dumps({
                "observation_complete":True, "worker_vs1_restored":True,
                "errors":[],"signal":None, "counts":{"CYCLES":200},
                "p300_stream_seconds_approx":260}))
            (session/"recovery.json").write_text(json.dumps({"services_restored":True}))
            (session/"health.json").write_text(json.dumps({
                "production_main_verified":True, "gfa_reads":{
                    "P80":{"format_and_identity_verified":True},
                    "P06":{"format_and_identity_verified":True,
                           "p06_non_ff_verified":True}}}))
            (bundle/("p300-rpm-trigger-"+session.name+"-bundle.tar.gz")).write_bytes(b"x")
            with patch.object(m,"ROOT",root),patch.object(m,"BUNDLES",bundle),\
                 patch.object(m.F,"sha256",return_value="GOOD_SOURCE_HASH"):
                self.assertFalse(m.canary_qualified())
            with patch.object(m,"ROOT",root),patch.object(m,"BUNDLES",bundle),\
                 patch.object(m.F,"sha256",return_value="FAKE_SOURCE_HASH"):
                self.assertTrue(m.canary_qualified())

    def test_other_rpm_logger_active_blocks_start(self):
        base=SimpleNamespace(h=SimpleNamespace(
            unit_state=lambda unit:{"ActiveState":"active" if
                unit=="optolink-p300-rpm-trigger.service" else "inactive"}))
        with self.assertRaisesRegex(RuntimeError,"COMPETING_LOGGER"):
            m.competing(base)

    def test_vs1_read_only_summary_and_timeout_inherited(self):
        self.assertEqual(m.STATUS_SPEC,(1,0x55d3,11))
        self.assertEqual(m.CORE_SPECS,((3,0x0f20,32),(3,0x1c60,32)))
        self.assertEqual(m.TRIGGER_COOLDOWN_SECONDS,15)
        self.assertIn("TRIGGER_CROSSCHECK_ABORT_TO_RECOVERY",
            PATH.read_text(encoding="utf-8"))
        self.assertIn("WORKER_EXITED_RECOVERY_PENDING",
            PATH.read_text(encoding="utf-8"))


if __name__=="__main__":
    unittest.main()
