"""Offline/no-boiler tests: bounded P300 candidate -> true VS1 GFA P06 crosscheck."""
import contextlib
import importlib.util
import json
from pathlib import Path
import signal
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1]/"tools"/"wb2a-p300-rpm-trigger.py"
spec = importlib.util.spec_from_file_location("p300_rpm_trigger",PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def sample(x=0xAC, y=None, flame=True, lockout=False, coherent=True, ident=1):
    if y is None:y=x
    a = {"flame":flame,"lockout":lockout,"byte0":38,"byte7":0x62,
         "byte9":33,"payload_hex":"00"*11}
    return {"cycle":ident,"candidates":{"0f20":x,"1c76":y,"0f29":0x62,
            "0f27":0,"0f28":0,"1c7d":0,"1c7e":0,
            "copies_equal":x==y},
            "first_status":dict(a),"last_status":dict(a),
            "quality":{"status_coherent":coherent},
            "core_payload":bytes([x])*32+bytes([y])*32,
            "context_payload":None, "core_sha256":"f"*64,
            "context_sha256":None,"start_utc":"before","end_utc":"after",
            "start_monotonic":1.0,"end_monotonic":1.1,"duration_s":.1}


def reference(rpm=5130, stable=True, ff=0):
    return {"identity_verified":True,"stable":stable,"p06_invalid_ff":ff,
            "p06_valid":12 if ff==0 else 11,
            "p06_rpm_unique":[rpm], "p06_raw_unique":[f"{rpm//30:02x}"]}


class Stop:
    signum = None


class OfflineGuards(unittest.TestCase):
    def test_import_inert_and_settings(self):
        self.assertEqual(m.VERSION,"1.0.0-rpm-triggered-vs1-crosscheck")
        self.assertEqual(m.MAX_TRIGGERS,4)
        self.assertEqual(m.TRIGGER_COOLDOWN_SECONDS,600)
        self.assertEqual(m.CANARY_SECONDS,300)
        self.assertEqual(m.MAX_HOURS,2)
        self.assertEqual(len(m.ALLOWED_P300_SPECS),3)

    def test_strict_read_only_p300_allowlist(self):
        self.assertEqual(m.ALLOWED_P300_SPECS,
                         frozenset(((1,0x55d3,11),(3,0x0f20,32),
                                    (3,0x1c60,32))))
        for spec in m.ALLOWED_P300_SPECS:
            raw=m.frame(spec)
            self.assertEqual(len(raw),8)
            self.assertEqual(raw[-1],sum(raw[1:-1])&255)
            self.assertTrue(m.TriggerWire.permitted("p300",raw,None))
        for invalid in ((3,0x1c40,32),(3,0x0f00,32),(3,0x0f21,32),
                        (3,0x03ae,1),(4,0x0f20,32),
                        (7,0x4006,1),(9,0x4006,1),
                        (201,0x4006,1),(1,0x55d3,12)):
            with self.subTest(invalid=invalid),\
                 self.assertRaisesRegex(ValueError,"UNREVIEWED"):
                m.frame(invalid)
        self.assertFalse(m.TriggerWire.permitted("p300",b"\x04",None))
        self.assertFalse(m.TriggerWire.permitted("p300",
                         m.F.request_frame(3,0x0f00,32),None))
        self.assertTrue(m.TriggerWire.permitted("p300",b"\x06",None))

    def test_trigger_requires_natural_two_high_coherent_cycles(self):
        a,b=sample(0xAC,ident=1),sample(0xA9,0xAA,ident=2)
        self.assertTrue(m.status_safe(a))
        self.assertTrue(m.high_candidate(a))
        self.assertTrue(m.trigger_eligible([a,b],-1e9,1000,0))
        self.assertFalse(m.trigger_eligible([a],-1e9,1000,0))
        self.assertFalse(m.trigger_eligible([a,b],950,1000,0))
        self.assertFalse(m.trigger_eligible([a,b],-1e9,1000,4))
        for bad in (sample(0x87),sample(0x90,0x80),
                    sample(0xAC,flame=False),sample(0xAC,lockout=True),
                    sample(0xAC,coherent=False)):
            self.assertFalse(m.trigger_eligible([a,bad],-1e9,1000,0))

    def test_never_claim_actual_p300_rpm(self):
        before=[sample(0xAC,ident=11),sample(0xAC,ident=12)]
        post=[sample(0xAC,ident=13),sample(0xAC,ident=14)]
        match=m.summarize_capture(before,reference(5130),post)
        self.assertEqual(match["quality"],"NUMERICALLY_CONSISTENT_NOT_VERIFIED")
        self.assertEqual(match["predicted_rpm_hypothetical"],5130)
        self.assertIs(match["p300_actual_p06_verified"],False)
        mismatch=m.summarize_capture(before,reference(3900),post)
        self.assertEqual(mismatch["quality"],"P06_PLUS_ONE_NUMERIC_MISMATCH")
        self.assertEqual(mismatch["delta_real_minus_predicted_rpm"],-1230)
        self.assertFalse(mismatch["p300_actual_p06_verified"])
        self.assertEqual(m.summarize_capture(before,reference(5130,False),post)["quality"],
                         "TRANSITION_OR_UNKNOWN")
        self.assertEqual(m.summarize_capture(before,reference(5130,True,1),post)["quality"],
                         "TRANSITION_OR_UNKNOWN")
        post_changed=[sample(0x90),sample(0x90)]
        self.assertEqual(m.summarize_capture(before,reference(5130),post_changed)["quality"],
                         "TRANSITION_OR_UNKNOWN")
        self.assertEqual(m.summarize_capture(before,reference(5130),post[:1])["quality"],
                         "TRANSITION_OR_UNKNOWN")

    def setup_streams(self,root):
        return {name:(root/(name+".bin" if name=="corebin"
                            else name+".jsonl")).open("w+b" if name=="corebin" else "w+")
                for name in ("vs1","switch","trace","packets","cycles",
                             "triggers","corebin")}

    def test_trigger_complete_records_raw_phase_and_real_vs1(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            streams=self.setup_streams(root)
            phase=SimpleNamespace(phase="p300")
            seen=[]
            def sw(wire,stream,reason,to_p300):
                wire.phase="p300" if to_p300 else "vs1"
                seen.append((reason,to_p300))
                m.F.write_jsonl(stream,{"reason":reason,"result":"OK"})
            n=iter([sample(0xAC,ident=3),sample(0xAC,ident=4)])
            counter=m.Counter(CYCLES=2,PACKETS=8)
            try:
                with patch.object(m.F,"switch",side_effect=sw),\
                     patch.object(m.F,"reference",return_value=reference()),\
                     patch.object(m.T,"observation_cycle",side_effect=lambda *a,**k:next(n)):
                    rec=m.crosscheck(root,phase,streams,1,
                             [sample(0xAC,ident=1),sample(0xAC,ident=2)],
                             counter,Stop(),m.time.monotonic()+300)
            finally:
                for out in streams.values():out.close()
            self.assertEqual(rec["result"],"COMPLETE")
            self.assertEqual(rec["quality"],"NUMERICALLY_CONSISTENT_NOT_VERIFIED")
            self.assertFalse(rec["p300_actual_p06_verified"])
            self.assertTrue(rec["switch_back_to_p300"])
            self.assertEqual([x[1] for x in seen],[False,True])
            self.assertEqual(counter["CYCLES"],4)
            self.assertEqual(counter["PACKETS"],16)
            self.assertEqual(len((root/"corebin.bin").read_bytes()),128)
            self.assertEqual(len((root/"cycles.jsonl").read_text().splitlines()),2)
            self.assertEqual(len((root/"triggers.jsonl").read_text().splitlines()),1)

    def test_identity_timeout_is_partial_not_a_fake_rpm(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);streams=self.setup_streams(root)
            try:
                with patch.object(m.F,"switch",side_effect=RuntimeError("receive deadline exceeded")),\
                     patch.object(m.F,"reference",side_effect=AssertionError("no fake reference")):
                    with self.assertRaisesRegex(RuntimeError,"receive deadline exceeded"):
                        m.crosscheck(root,SimpleNamespace(phase="recovery"),streams,
                                     1,[sample(),sample()],m.Counter(),Stop(),
                                     m.time.monotonic()+300)
            finally:
                for out in streams.values():out.close()
            row=json.loads((root/"triggers.jsonl").read_text().splitlines()[0])
            self.assertEqual(row["result"],"PARTIAL")
            self.assertIsNone(row["vs1"])
            self.assertFalse(row["p300_actual_p06_verified"])
            self.assertIn("receive deadline exceeded",row["errors"])

    def test_stop_between_vs1_and_post_read_keeps_vs1_safe(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);streams=self.setup_streams(root)
            stop=Stop()
            phase=SimpleNamespace(phase="p300")
            def sw(wire,stream,reason,to_p300):
                self.assertFalse(to_p300)
                wire.phase="vs1"
            def ref(*args,**kwargs):
                stop.signum=signal.SIGTERM
                return reference()
            try:
                with patch.object(m.F,"switch",side_effect=sw),\
                     patch.object(m.F,"reference",side_effect=ref),\
                     patch.object(m.T,"observation_cycle",
                                  side_effect=AssertionError("no P300 after stop")):
                    result=m.crosscheck(root,phase,streams,1,[sample(),sample()],
                                        m.Counter(),stop,m.time.monotonic()+300)
            finally:
                for out in streams.values():out.close()
            self.assertEqual(result["result"],"STOP_AFTER_SAFE_VS1_READ")
            self.assertFalse(result["switch_back_to_p300"])
            self.assertFalse(result["p300_actual_p06_verified"])

    def test_resource_guard_disk(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(m.shutil,"disk_usage",return_value=SimpleNamespace(free=1)):
                with self.assertRaisesRegex(RuntimeError,"LOW_DISK"):
                    m.resource_guard(Path(td))

    def test_session_mode_and_pinned_hashes(self):
        state={"mode":"canary","hours":1,"duration_seconds":300,
               "temporal_sha256":"A","focus_sha256":"B","fullram_sha256":"C"}
        with patch.object(m.F,"validate_state",return_value=state),\
             patch.object(m.F.DEEP,"check_hash") as chk:
            self.assertEqual(m.validate_state(Path("/tmp/session")),state)
            self.assertEqual(chk.call_count,3)
            state["mode"]="full";state["hours"]=2;state["duration_seconds"]=7200
            self.assertEqual(m.validate_state(Path("/tmp/session")),state)
            state["duration_seconds"]=100
            with self.assertRaisesRegex(RuntimeError,"FULL_STATE"):
                m.validate_state(Path("/tmp/session"))

    def test_no_parallel_logger(self):
        base=SimpleNamespace(h=SimpleNamespace(unit_state=lambda unit:
                            {"ActiveState":"active" if unit==m.T.UNIT else "inactive"}))
        with self.assertRaisesRegex(RuntimeError,"COMPETING_LOGGER"):
            m.competing(base)

    def test_require_prior_full_and_successful_restore(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"temporal";root.mkdir()
            bundle=Path(td)/"bundles";bundle.mkdir()
            session=root/"run-1";session.mkdir()
            (session/"state.json").write_text(json.dumps({"mode":"full"}))
            (session/"measurement.json").write_text(json.dumps({
                "observation_complete":True,"worker_vs1_restored":True,"errors":[]}))
            (session/"recovery.json").write_text(json.dumps({"services_restored":True}))
            (session/"health.json").write_text(json.dumps({
                "production_main_verified":True,"gfa_reads":{
                "P80":{"format_and_identity_verified":True},
                "P06":{"p06_non_ff_verified":True}}}))
            (bundle/("p300-temporal-"+session.name+"-bundle.tar.gz")).write_bytes(b"x")
            with patch.object(m,"PRIOR_TEMPORAL_ROOT",root),patch.object(m,"BUNDLES",bundle):
                self.assertIsNone(m.previous_temporal_restored())
                (session/"health.json").write_text("{}")
                with self.assertRaisesRegex(RuntimeError,"HEALTH_NOT_VERIFIED"):
                    m.previous_temporal_restored()

    def test_canary_must_have_health_archive_and_240s(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"root";root.mkdir()
            bundle=Path(td)/"bundles";bundle.mkdir()
            session=root/"run-1";session.mkdir()
            (session/"state.json").write_text(json.dumps({"mode":"canary"}))
            (session/"measurement.json").write_text(json.dumps({
                "observation_complete":True,"worker_vs1_restored":True,
                "errors":[],"signal":None,"counts":{"CYCLES":200},
                "p300_stream_seconds_approx":255}))
            (session/"recovery.json").write_text(json.dumps({"services_restored":True}))
            (session/"health.json").write_text(json.dumps({
                "production_main_verified":True,"gfa_reads":{
                  "P06":{"p06_non_ff_verified":True}}}))
            (bundle/("p300-rpm-trigger-"+session.name+"-bundle.tar.gz")).write_bytes(b"x")
            with patch.object(m,"ROOT",root),patch.object(m,"BUNDLES",bundle):
                self.assertTrue(m.canary_qualified())
                (session/"health.json").write_text("{}")
                self.assertFalse(m.canary_qualified())

    def test_archive_checks_manifest_and_0700(self):
        # The source code is exercised in offline CI as non-root.
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"root";root.mkdir()
            bundles=Path(td)/"bundles";bundles.mkdir()
            session=root/"run-test";session.mkdir(mode=0o700)
            sample_file=session/"measurement.json"
            sample_file.write_text('{"observation_complete":true}')
            sample_file.chmod(0o600)
            if sample_file.stat().st_uid!=0:self.skipTest("root-only archive audit")
            with patch.object(m,"ROOT",root),patch.object(m,"BUNDLES",bundles):
                saved=m.archive(session)
            import tarfile,hashlib
            with tarfile.open(saved,"r:gz") as tf:
                manifest=json.load(tf.extractfile(
                    "p300-rpm-trigger/bundle-manifest.json"))
                for name,info in manifest["files"].items():
                    raw=tf.extractfile("p300-rpm-trigger/"+name).read()
                    self.assertEqual(hashlib.sha256(raw).hexdigest(),info["sha256"])
                    self.assertEqual(len(raw),info["size"])


if __name__=="__main__":
    unittest.main()
