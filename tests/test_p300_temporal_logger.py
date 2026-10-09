"""Read-only temporal P300 recorder: determinism, framing, purity and rollback."""
import contextlib
import hashlib
import importlib.util
import json
from pathlib import Path
import signal
import tarfile
import tempfile
import unittest
from unittest.mock import patch

path=Path(__file__).resolve().parents[1]/"tools"/"wb2a-p300-temporal-logger.py"
spec=importlib.util.spec_from_file_location("p300_temporal_logger",path)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def native_payload(flame=False,p87=0x62,mod=33):
    data=bytearray(11)
    data[0],data[5],data[7],data[9]=mod,0x20 if flame else 0,p87,mod
    return bytes(data)


def ram_payload(address, candidate=0x54, p87=0x62):
    data=bytearray(32)
    if address==0x0f20:
        data[0],data[7],data[8],data[9]=candidate,0x21,0x0b,p87
    if address==0x1c60:
        data[0x16],data[0x1d],data[0x1e]=candidate,0x0b,p87
    return bytes(data)


class FakeWire:
    phase="p300"
    def __init__(self,flame=False,p87=0x62,candidate=0x54,fail_at=None):
        self.flame=flame
        self.p87=p87
        self.candidate=candidate
        self.calls=[]
        self.fail_at=fail_at

    def packet(self, spec):
        self.calls.append(spec)
        if self.fail_at and len(self.calls)==self.fail_at:
            raise m.F.PacketError("receive deadline exceeded",
                received=bytes.fromhex("064105"),tx_utc="start",tx_monotonic=12.0)
        blob=(native_payload(self.flame,self.p87) if spec==m.STATUS_SPEC
              else ram_payload(spec[1],self.candidate,self.p87))
        return {"fc":spec[0],"address":f"0x{spec[1]:04x}","length":spec[2],
                "request_hex":m.frame(spec).hex(),"response_hex":"fixture",
                "ack_count":1,"host_ack_hex":"06","checksum_valid":True,
                "response_message":1,"response_fc":spec[0],
                "response_address":f"0x{spec[1]:04x}",
                "response_length":spec[2],"payload_hex":blob.hex(),
                "data":blob,"tx_utc":"start","rx_utc":"end",
                "tx_monotonic":12.0,"rx_monotonic":12.1,
                "duration_ms":100.0,"result":"OK"}


class Stop:
    signum=None


class TemporalTests(unittest.TestCase):
    def test_allowlist_exactly_matches_previously_verified_reads(self):
        self.assertEqual(len(m.SPECS),7)
        self.assertEqual(len(m.CORE_SPECS),2)
        self.assertEqual(len(m.CONTEXT_SPECS),4)
        self.assertEqual(set(m.SPECS),set(m.FOCUS.ALLOWED_SPECS))
        for x in m.SPECS:
            message=m.frame(x)
            self.assertEqual(len(message),8)
            self.assertEqual(message[0],0x41)
            self.assertEqual(message[-1],sum(message[1:-1])&0xff)
            self.assertIn(x[0],(1,3))
        for x in ((0xc9,0x4050,1),(9,0x4006,1),(4,0xf20,32),
                  (3,0x1c76,1),(1,0x7650,1),(3,0x03ae,32),
                  (7,0x4006,1),(3,0xf20,31)):
            with self.subTest(x=x),self.assertRaisesRegex(ValueError,"UNREVIEWED"):
                m.frame(x)

    def test_real_wire_guard_rejects_other_frames(self):
        base=object()
        self.assertTrue(m.FOCUS.FocusWire.permitted("p300",m.frame(m.CORE_SPECS[0]),base))
        self.assertFalse(m.FOCUS.FocusWire.permitted(
            "p300",m.F.request_frame(3,0x1500,32),base))
        self.assertFalse(m.FOCUS.FocusWire.permitted(
            "p300",bytes.fromhex("410500c940500160"),base))

    def test_candidate_offsets_and_mirror(self):
        data=m.candidate_bytes({0x0f20:ram_payload(0x0f20),0x1c60:ram_payload(0x1c60)})
        self.assertEqual(data["0f20"],0x54)
        self.assertEqual(data["1c76"],0x54)
        self.assertEqual(data["0f29"],0x62)
        self.assertEqual(data["1c7e"],0x62)
        self.assertTrue(data["copies_equal"])
        bad=ram_payload(0x1c60,candidate=0x55)
        self.assertFalse(m.candidate_bytes({0x0f20:ram_payload(0x0f20),0x1c60:bad})["copies_equal"])

    def test_status_bracket_never_converts_modulation_to_rpm(self):
        x=m.native({"data":native_payload(False,p87=0x62,mod=42),
                    "rx_utc":"now","rx_monotonic":11.0})
        y=m.native({"data":native_payload(True,p87=0x72,mod=55),
                    "rx_utc":"now","rx_monotonic":12.0})
        self.assertFalse(m.classify_temporal(x,y,
                         m.candidate_bytes({0x0f20:ram_payload(0x0f20),
                         0x1c60:ram_payload(0x1c60)}))["status_coherent"])
        self.assertFalse(m.classify_temporal(x,x,
                         m.candidate_bytes({0x0f20:ram_payload(0x0f20),
                         0x1c60:ram_payload(0x1c60)}))[
                         "gfa_p06_actual_rpm_available_during_p300"])
        with self.assertRaisesRegex(RuntimeError,"P87_FF"):
            m.native({"data":native_payload(p87=0xff),
                      "rx_utc":"now","rx_monotonic":11.0})

    def test_native_flame_burst_and_cooldown(self):
        x=m.native({"data":native_payload(False,0),"rx_utc":"x","rx_monotonic":10})
        y=m.native({"data":native_payload(True,0),"rx_utc":"x","rx_monotonic":11})
        until,mod=m.update_burst(100,x,x,y,{"burst_until":0},-1e12)
        self.assertGreaterEqual(until,135)
        self.assertEqual(mod,-1e12)
        z=m.native({"data":native_payload(True,0,60),"rx_utc":"x","rx_monotonic":11})
        until,mod=m.update_burst(150,y,z,z,{"burst_until":0},-1e12)
        self.assertGreaterEqual(until,158)
        until2,mod2=m.update_burst(151,z,x,x,{"burst_until":until},mod)
        self.assertGreaterEqual(until2,until)
        self.assertEqual(mod2,mod)

    @staticmethod
    @contextlib.contextmanager
    def streams():
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            streams={}
            for name in ("vs1","switch","trace","packets","cycles","events"):
                streams[name]=(root/(name+".jsonl")).open("w+")
            for name in ("corebin","contextbin"):
                streams[name]=(root/(name+".bin")).open("wb+")
            try:yield root,streams
            finally:
                for stream in streams.values():stream.close()

    def test_one_temporal_cycle_has_two_native_brackets_and_raw_payload(self):
        with self.streams() as (root,streams):
            wire=FakeWire()
            result=m.observation_cycle(wire,streams,1,use_context=True)
            self.assertEqual(wire.calls,
                             [m.STATUS_SPEC,*m.CORE_SPECS,m.STATUS_SPEC,*m.CONTEXT_SPECS])
            self.assertEqual(len(result["core_payload"]),64)
            self.assertEqual(len(result["context_payload"]),128)
            self.assertEqual(result["candidates"]["0f20"],0x54)
            self.assertTrue(result["quality"]["status_coherent"])
            self.assertFalse(result["quality"]["gfa_p06_actual_rpm_available_during_p300"])
            self.assertEqual(hashlib.sha256(result["core_payload"]).hexdigest(),
                             result["core_sha256"])
            for stream in streams.values():stream.flush()
            self.assertEqual(len((root/"packets.jsonl").read_text().splitlines()),8)

    def test_failed_packet_keeps_utc_and_raw_bytes_without_success(self):
        with self.streams() as (root,streams):
            with self.assertRaisesRegex(m.F.PacketError,"receive deadline exceeded"):
                m.observation_cycle(FakeWire(fail_at=3),streams,1)
            for stream in streams.values():stream.flush()
            log=[json.loads(x) for x in (root/"packets.jsonl").read_text().splitlines()]
            self.assertEqual(len(log),3)
            self.assertEqual(log[-1]["result"],"ERROR")
            self.assertEqual(log[-1]["rx_observed_hex"],"064105")
            self.assertEqual(log[-1]["request_hex"],m.frame(m.CORE_SPECS[1]).hex())
            self.assertFalse((root/"cycles.jsonl").read_text())

    def test_stream_signal_end_of_cycle_and_binary_crosscheck(self):
        stop=Stop()
        counters=m.Counter()
        with self.streams() as (root,streams):
            def after(cycle,result):
                if cycle==3:stop.signum=signal.SIGTERM
            with patch.object(m.time,"sleep",return_value=None):
                summary=m.measurement_stream(root,FakeWire(),streams,stop,
                      m.time.monotonic()+20,counters,pulse=after)
            for stream in streams.values():stream.flush()
            self.assertEqual(summary["cycles"],3)
            self.assertTrue(summary["no_vs1_during_stream"])
            self.assertFalse(summary["actual_rpm_during_stream_measured"])
            self.assertEqual(counters["CYCLES"],3)
            packets=[json.loads(x) for x in (root/"packets.jsonl").read_text().splitlines()]
            self.assertGreaterEqual(len(packets),12)
            core=(root/"corebin.bin").read_bytes()
            self.assertEqual(len(core),3*64)
            lines=[json.loads(x) for x in (root/"cycles.jsonl").read_text().splitlines()]
            self.assertEqual(len(lines),3)
            for i,line in enumerate(lines):
                expected=core[i*64:(i+1)*64]
                self.assertEqual(line["core_offset"],i*64)
                self.assertEqual(hashlib.sha256(expected).hexdigest(),line["core_sha256"])
                self.assertFalse(line["quality"]["gfa_p06_actual_rpm_available_during_p300"])

    def test_disallow_competing_running_focus(self):
        from types import SimpleNamespace
        fake=SimpleNamespace(h=SimpleNamespace(
            unit_state=lambda unit:{"ActiveState":"active" if unit==m.CURRENT_UNIT else "inactive"}))
        with self.assertRaisesRegex(RuntimeError,"COMPETING"):
            m.competing(fake)

    def test_previous_focus_restore_requires_non_ff_valid_gfa(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            session=root/"run-20261009T000000Z-1"
            session.mkdir()
            with self.assertRaisesRegex(RuntimeError,"RECOVERY_NOT_COMPLETE"):
                m.guard_finished_focus(root)
            (session/"recovery.json").write_text(json.dumps(
                {"services_restored":True,"errors":[]}))
            health={"production_main_verified":True,
                "gfa_reads":{"P80":{"format_and_identity_verified":True},
                             "P06":{"format_and_identity_verified":True,
                                    "p06_non_ff_verified":False}}}
            (session/"health.json").write_text(json.dumps(health))
            with self.assertRaisesRegex(RuntimeError,"HEALTH_UNRESOLVED"):
                m.guard_finished_focus(root)
            health["gfa_reads"]["P06"]["p06_non_ff_verified"]=True
            (session/"health.json").write_text(json.dumps(health))
            self.assertIsNone(m.guard_finished_focus(root))
            (session/"recovery.json").write_text(json.dumps(
                {"services_restored":False,"errors":["test"]}))
            with self.assertRaisesRegex(RuntimeError,"HEALTH_UNRESOLVED"):
                m.guard_finished_focus(root)

    def test_archive_manifest_replay(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"runs";root.mkdir()
            bundle=Path(td)/"bundles";bundle.mkdir()
            session=root/"run-test";session.mkdir()
            a=session/"cycles.jsonl";a.write_text('{"test":1}\n')
            a.chmod(0o600)
            c=session/"core-pairs.bin";c.write_bytes(bytes(range(64)))
            c.chmod(0o600)
            if a.stat().st_uid!=0:self.skipTest("archive enforces root ownership")
            with patch.object(m,"ROOT",root),patch.object(m,"BUNDLES",bundle):
                dest=m.archive(session)
            with tarfile.open(dest) as f:
                manifest=json.load(f.extractfile("p300-temporal/bundle-manifest.json"))
                self.assertEqual(len(manifest["files"]),2)
                for rel,v in manifest["files"].items():
                    data=f.extractfile("p300-temporal/"+rel).read()
                    self.assertEqual(v["size"],len(data))
                    self.assertEqual(v["sha256"],hashlib.sha256(data).hexdigest())

    def test_restore_defers_helpers_if_main_unavailable(self):
        from types import SimpleNamespace
        calls=[]
        def fail():
            raise RuntimeError("main not ready")
        h=SimpleNamespace(MAIN="optolink-splitter.service",
          command=lambda a:calls.append(a),wait_main_ready=fail,
          unit_state=lambda n:{"ActiveState":"inactive"},
          atomic_json=lambda p,obj:calls.append((p.name,obj)))
        base=SimpleNamespace(h=h,locks=contextlib.nullcontext)
        state={"restore":["optolink-party-emulator.service",h.MAIN]}
        with tempfile.TemporaryDirectory() as td:
            session=Path(td)
            with patch.object(m,"validate_state",return_value=state),\
                 patch.object(m.F.DEEP,"load_local_base",return_value=base),\
                 patch.object(m.F.DEEP,"post_restore_health",return_value={"production_main_verified":False}),\
                 patch.object(m,"archive",return_value=Path("/tmp/unused.tgz")):
                self.assertEqual(m.recover(session),1)
        self.assertEqual([x for x in calls if isinstance(x,list)],
                         [["systemctl","start","optolink-splitter.service"]])

    def test_config_limits_and_false_rpm_alias(self):
        self.assertEqual(m.DEFAULT_HOURS,2)
        self.assertEqual(m.MAX_HOURS,3)
        self.assertEqual(m.MAX_CYCLES,24000)
        self.assertEqual(m.ROOT.name,"p300-temporal-results")
        self.assertEqual(m.CURRENT_UNIT,"optolink-p300-p06-focus.service")
        self.assertEqual(m.CORE_ADDRESSES,(0x0f20,0x1c76))

if __name__=="__main__":
    unittest.main()
