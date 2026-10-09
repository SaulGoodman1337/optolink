"""Deterministic guards and lifecycle tests for the short P06-focused logger."""
import importlib.util
from collections import Counter
import contextlib
import hashlib
import json
from pathlib import Path
import signal
import tarfile
import tempfile
import time
import unittest
from unittest.mock import patch

P=Path(__file__).resolve().parents[1]/"tools"/"wb2a-p300-p06-focus.py"
spec=importlib.util.spec_from_file_location("p300_p06_focus",P)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def ref(raw="53", stable=True):
    return {"stable":stable,"identity_verified":True,"p06_raw_unique":[raw],
            "p06_rpm_unique":[int(raw,16)*30],"p06_valid":12,
            "begin_utc":"2026-10-09T00:00:00+00:00",
            "end_utc":"2026-10-09T00:00:03+00:00"}


def status(flame=True):
    p=bytearray(11)
    p[5] = 0x20 if flame else 0
    return {"payload_hex":p.hex(),"flame":flame,"lockout":False,
            "byte7_diagnostic":p[7],"result":"OK"}


class FakeWire:
    def __init__(self, payload=None):
        self.phase="vs1"
        self.packets=[]
        self.payload=payload or {}
    def packet(self,spec):
        self.packets.append(spec)
        blob=self.payload.get(spec[1], bytes([spec[1]&0xff])*32)
        return {"fc":spec[0],"address":f"0x{spec[1]:04x}","length":32,
                "request_hex":m.frame(spec).hex(),"response_hex":"fixture",
                "ack_count":1,"response_message":1,"response_fc":3,
                "response_address":f"0x{spec[1]:04x}","response_length":32,
                "checksum_valid":True,"payload_hex":blob.hex(),"data":blob,
                "tx_utc":"start","rx_utc":"end","tx_monotonic":1.0,
                "rx_monotonic":1.2,"duration_ms":200.0,"result":"OK"}


class Stop:
    signum = None


class Tests(unittest.TestCase):
    def test_exact_allowlist_and_no_writes(self):
        self.assertEqual(m.RAM_ADDRESSES,(0xf00,0xf20,0xf40,0x1c40,0x1c60,0x1c80))
        self.assertEqual(len(m.ALLOWED_SPECS),7)
        for spec in m.ALLOWED_SPECS:
            self.assertEqual(len(m.frame(spec)),8)
            self.assertEqual(m.frame(spec)[-1],sum(m.frame(spec)[1:-1])&255)
        for spec in ((4,0x0f20,32),(2,0x0f20,32),(3,0x0f21,32),
                     (3,0x1c60,31),(3,0x03ae,32),(3,0x1600,32),
                     (0xc9,0x4006,1),(1,0x55d3,12)):
            with self.subTest(spec=spec),self.assertRaisesRegex(ValueError,"UNREVIEWED"):
                m.frame(spec)
        base=type("B",(),{})()
        self.assertFalse(m.FocusWire.permitted("p300",m.F.request_frame(3,0x1600,32),base))
        self.assertFalse(m.FocusWire.permitted("p300",bytes.fromhex("410500041600203f"),base))
        self.assertTrue(m.FocusWire.permitted("p300",m.frame((3,0xf20,32)),base))

    def test_candidate_offsets(self):
        blocks={addr:bytearray(32) for addr in m.RAM_ADDRESSES}
        blocks[0xf20][0]=0x54
        blocks[0xf20][9]=0x62
        blocks[0x1c60][0x16]=0x54
        self.assertEqual(m.get_candidates(blocks),{"0x0f20":"54","0x0f29":"62","0x1c76":"54"})
        with self.assertRaisesRegex(RuntimeError,"MISSING"):
            m.get_candidates({0xf20:bytes(32)})

    def test_level_selector_prefers_unseen_nonstandard_rpm(self):
        self.assertEqual(m.select_level(ref("60"),{},100),"HIGH_60")
        self.assertEqual(m.select_level(ref("30"),{},100),"OTHER_30")
        self.assertEqual(m.select_level(ref("53"),{},100),"P06_2490")
        self.assertEqual(m.select_level(ref("00"),{},100),"OFF")
        self.assertIsNone(m.select_level(ref("ff",False),{},100))
        self.assertIsNone(m.select_level(ref("60"),{"HIGH_60":(95,1)},100))
        self.assertIsNone(m.select_level(ref("60"),{"HIGH_60":(-1,3)},100))
        self.assertIsNone(m.select_level(ref("53"),{"P06_2490":(99,1)},100))

    def test_qualification_never_guesses_rpm(self):
        three=[status() for _ in range(3)]
        self.assertEqual(m.classify_capture(ref("00"),ref("00"),three),"STABLE_OFF")
        self.assertEqual(m.classify_capture(ref("53"),ref("53"),three),"STABLE_2490")
        self.assertEqual(m.classify_capture(ref("60"),ref("60"),three),"STABLE_OTHER_POSITIVE")
        self.assertEqual(m.classify_capture(ref("60"),ref("61"),three),"TRANSITION_OR_UNKNOWN")
        self.assertEqual(m.classify_capture(ref("60",False),ref("60"),three),"TRANSITION_OR_UNKNOWN")
        self.assertEqual(m.classify_capture(ref("60"),None,three),"TRANSITION_OR_UNKNOWN")
        self.assertEqual(m.classify_capture(ref("60"),ref("60"),[status(),status(False),status()]),"TRANSITION_OR_UNKNOWN")

    def run_capture(self, mode="ok", stop_during_read=False):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/"captures").mkdir()
            streams={}
            for name in ("vs1","ram","status","switch","trace"):
                streams[name]=(root/(name+".jsonl")).open("w+")
            wire=FakeWire()
            stopper=Stop()
            if stop_during_read:
                old=wire.packet
                def packet(spec):
                    stopper.signum=signal.SIGTERM
                    return old(spec)
                wire.packet=packet
            def sw(wire, stream, reason, to_p300):
                if not to_p300 and mode=="timeout":
                    wire.phase="recovery"
                    raise RuntimeError("receive deadline exceeded")
                wire.phase="p300" if to_p300 else "vs1"
                m.F.write_jsonl(stream,{"reason":reason,"result":"OK"})
            samples=[]
            def st(wire, stream, idx, after):
                s=status()
                samples.append(s)
                m.F.write_jsonl(stream,s)
                return s
            from types import SimpleNamespace
            base=SimpleNamespace(h=SimpleNamespace(atomic_json=lambda path,data:
                 path.write_text(json.dumps(data),encoding="utf-8")))
            try:
                with patch.object(m.F,"switch",side_effect=sw),\
                     patch.object(m.F,"read_status",side_effect=st),\
                     patch.object(m.F,"reference",return_value=ref("60")),\
                     patch.object(m.F.DEEP,"load_local_base",return_value=base):
                    if mode=="timeout":
                        with self.assertRaisesRegex(RuntimeError,"receive deadline exceeded"):
                            m.capture(root,wire,streams,1,ref("60"),stopper)
                    else:
                        m.capture(root,wire,streams,1,ref("60"),stopper)
            finally:
                for stream in streams.values(): stream.close()
            info=json.loads((root/"captures/c00001.json").read_text())
            ram=(root/"ram.jsonl").read_text().splitlines()
            result={"info":info,"ram":ram,"files":{
              p.name:p.read_bytes() for p in (root/"captures").glob("*.bin")}}
            return result

    def test_complete_two_rounds_integrity_and_references(self):
        r=self.run_capture()
        x=r["info"]
        self.assertEqual(x["marker"],"COMPLETE")
        self.assertEqual(x["classification"],"STABLE_OTHER_POSITIVE")
        self.assertEqual(len(r["ram"]),12)
        self.assertEqual(x["rounds_complete"],2)
        self.assertEqual(len(x["statuses"]),3)
        self.assertEqual(len(r["files"]),2)
        for row in x["rounds"]:
            payload=r["files"][row["file"]]
            self.assertEqual(len(payload),192)
            self.assertEqual(hashlib.sha256(payload).hexdigest(),row["sha256"])

    def test_failed_vs1_return_preserves_partial_and_refuses_rpm(self):
        r=self.run_capture("timeout")
        self.assertEqual(r["info"]["packets_ok"],12)
        self.assertEqual(r["info"]["rounds_complete"],2)
        self.assertEqual(r["info"]["marker"],"PARTIAL")
        self.assertIsNone(r["info"]["post"])
        self.assertFalse(r["info"]["p06_alias_verified"])
        self.assertIn("receive deadline exceeded",r["info"]["errors"])

    def test_signal_is_deferred_and_partial_binary_kept(self):
        r=self.run_capture(stop_during_read=True)
        self.assertEqual(r["info"]["marker"],"PARTIAL")
        self.assertEqual(r["info"]["packets_ok"],1)
        self.assertIsNotNone(r["info"]["post"])
        self.assertFalse(r["info"]["p06_alias_verified"])
        self.assertEqual(len(r["ram"]),1)

    def test_small_resource_limits_and_plan(self):
        self.assertEqual(m.DEFAULT_HOURS,1)
        self.assertEqual(m.MAX_HOURS,3)
        self.assertEqual(m.MAX_CAPTURES,100)
        with tempfile.TemporaryDirectory() as td:
            with patch.object(m.shutil,"disk_usage",return_value=type("D",(),{"free":0})()):
                with self.assertRaisesRegex(RuntimeError,"LOW_DISK"):
                    m.storage_guard(Path(td))

    def test_archive_manifest_hashes(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"root";root.mkdir()
            bundles=Path(td)/"bundles";bundles.mkdir()
            s=root/"run-test";s.mkdir()
            (s/"state.json").write_text("{}")
            (s/"state.json").chmod(0o600)
            (s/"captures").mkdir()
            (s/"captures/c00001.partial.bin").write_bytes(b"012")
            (s/"captures/c00001.partial.bin").chmod(0o600)
            if (s/"state.json").stat().st_uid!=0: self.skipTest("root-required archive")
            with patch.object(m,"ROOT",root),patch.object(m,"BUNDLES",bundles):
                tar=m.archive(s)
            with tarfile.open(tar,"r:gz") as f:
                meta=json.load(f.extractfile("p300-p06-focus/bundle-manifest.json"))
                for path,val in meta["files"].items():
                    contents=f.extractfile("p300-p06-focus/"+path).read()
                    self.assertEqual(hashlib.sha256(contents).hexdigest(),val["sha256"])
                    self.assertEqual(len(contents),val["size"])

    def test_recover_defers_helpers_if_main_fails(self):
        from types import SimpleNamespace
        log=[]
        def fail_ready():raise RuntimeError("not ready")
        base=SimpleNamespace(h=SimpleNamespace(
            MAIN="optolink-splitter.service",command=lambda a:log.append(a),
            wait_main_ready=fail_ready,unit_state=lambda u:{"ActiveState":"active"},
            atomic_json=lambda p,d:log.append((p.name,d))),locks=contextlib.nullcontext)
        state={"restore":["optolink-party-emulator.service","optolink-splitter.service"]}
        with patch.object(m,"validate_state",return_value=state),\
             patch.object(m.F.DEEP,"load_local_base",return_value=base),\
             patch.object(m.F.DEEP,"post_restore_health",return_value={"production_main_verified":False}),\
             patch.object(m,"archive",return_value=Path("/tmp/test-focus.tar.gz")):
            self.assertEqual(m.recover(Path("/tmp/test-focus")),1)
        self.assertEqual([x for x in log if isinstance(x,list)],
                         [["systemctl","start","optolink-splitter.service"]])

if __name__=="__main__":unittest.main()
