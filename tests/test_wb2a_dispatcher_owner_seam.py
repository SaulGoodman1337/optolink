"""Actual generated upstream shim -> original VS1 P06 -> fenced fake P300."""
from __future__ import annotations
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from handover_acceleration.continuous_runtime import OnDemandReadonlyRuntime
from handover_acceleration.ingress_epoch import IngressEpoch
from handover_acceleration.pending_refresh import PendingReadbackLedger
from handover_acceleration.phase_planner import Budget
from handover_acceleration.scheduler import ReadKind, StaleReading
from handover_acceleration.dispatcher_patch import patch_dispatcher
from test_handover_dispatcher_patch import UPSTREAM_EXCERPT
from test_handover_acceleration import (
    FakeClock, FakePort, expect_attached_vs1, expect_p300, expect_vs1)
from test_handover_fc03_fixed import response


class DispatcherOwnerSeamTests(unittest.TestCase):
    def setUp(self):
        td=tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root=Path(td.name)
        producer=self.root/"producer"
        producer.write_bytes(b"")
        producer.chmod(0o600)
        self.clock=FakeClock()
        self.port=FakePort(expect_attached_vs1()+expect_p300()
                           + response("ram_0f20_32")
                           + expect_vs1(1,p06=b"\x53"))
        self.mqtt=types.SimpleNamespace(cmnd_queue=[],lst_force_refresh=[],
                       _hybrid_readback_ledger=PendingReadbackLedger())
        self.requests=[]
        def genuine_legacy(request,ser):
            self.assertIs(ser,self.port)
            self.requests.append(request)
            if isinstance(request,(tuple,list)):
                addr=request[1]
            else:
                addr=int(request.split(";")[1],0)
            raw=b"\x20" if addr==0x4050 else b"\x53"
            return 1,bytearray(raw),raw.hex(),"original"
        self.genuine_legacy=genuine_legacy
        self.runtime=OnDemandReadonlyRuntime(
            port=self.port,legacy_dispatch=self.genuine_legacy,
            resume_vs1=lambda:None,mqtt=self.mqtt,
            tcp_state=lambda:0,ingress=IngressEpoch(),
            all_writers_attested=lambda:True,
            lease_path=producer,serial_lease_path=self.root/"serial",
            budget=Budget(max_vs1_unavailable_ms=8000,max_p06_age_ms=9000),
            clock=self.clock.monotonic,sleep=self.clock.sleep,
            min_interval_s=60)
        stub=types.ModuleType("requests_util")
        stub.response_to_request=self.genuine_legacy
        with patch.dict(sys.modules,{"requests_util":stub}):
            self.ns={}
            exec(patch_dispatcher(UPSTREAM_EXCERPT),self.ns)
        self.ns["_handover_dispatch_bridge"]=types.SimpleNamespace(
            response_to_request=self.genuine_legacy)
        self.ns["_handover_runtime_gate"]=self.runtime.gate
        self.ns["_hybrid_auto"]=self.runtime
        self.shim=self.ns["handover_legacy_or_shim"]

    def test_real_shim_requires_original_gfa_p80_and_p06_before_p300(self):
        self.shim(("gfa_p80_typ",0x4050,1,"gfa:raw",False),self.port)
        self.shim(("geblaesedrehzahl_gfa_p06",0x4006,1,"gfa:30",False),self.port)
        self.runtime.note_keepalive(1)
        ticket=self.runtime.submit_internal(ReadKind.P300_RAM_0F20_32)
        out=self.runtime.tick()
        self.assertEqual(out.status,"VERIFIED_SWITCH")
        self.assertEqual(len(out.replies),1)
        self.assertEqual(out.replies[0].sequence,ticket.sequence)
        self.assertEqual(self.requests[:2],[
            ("gfa_p80_typ",0x4050,1,"gfa:raw",False),
            ("geblaesedrehzahl_gfa_p06",0x4006,1,"gfa:30",False)])
        self.assertEqual(self.port.script,[])

    def test_raw_vs1_virtual_read_cannot_fake_p06(self):
        self.shim(("gfa_p80_typ",0x4050,1,"gfa:raw",False),self.port)
        self.shim("r;0x4006;1;raw;False",self.port)
        self.runtime.note_keepalive(1)
        self.runtime.submit_internal(ReadKind.P300_RAM_0F20_32)
        self.assertEqual(self.runtime.tick().reason,
                         "REAL_GFA_P06_NOT_FRESH")
        self.assertEqual(self.port.writes,[])

    def test_original_gfa_failure_invalidates_proof(self):
        self.shim(("gfa_p80_typ",0x4050,1,"gfa:raw",False),self.port)
        self.shim(("geblaesedrehzahl_gfa_p06",0x4006,1,"gfa:30",False),self.port)
        self.shim("gfaread;0x4006;1;30;False",self.port)
        # A formatted read is NOT a raw original proof; original remains.
        self.runtime.note_keepalive(1)
        self.assertLessEqual(
            self.runtime.provenance.require_age_ms(max_age_ms=9000),1.0)


if __name__=="__main__":
    unittest.main()
