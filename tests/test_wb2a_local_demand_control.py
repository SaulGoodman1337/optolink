"""Root-only local on-demand P300 command/results; zero productive serial IO."""
from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from handover_acceleration.continuous_runtime import (
    LocalDemandControl, DemandControlRejected,
)
from handover_acceleration.scheduler import ReadKind
from test_wb2a_on_demand_runtime import DemandRuntimeTests

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("local_operator",ROOT/"tools/optolink-hybrid.py")
operator=importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(operator)


class LocalControlTests(unittest.TestCase):
    def setUp(self):
        self.fixture=DemandRuntimeTests("test_no_demand_means_no_serial_or_identity_work")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.runtime=self.fixture.runtime
        self.directory=self.fixture.root/"local-gateway"
        self.directory.mkdir(mode=0o700)
        self.path=self.directory/"p300-demand.sock"
        self.control=LocalDemandControl(
            self.runtime,path=self.path,clock=self.fixture.clock.monotonic)
        self.a="a"*32
        self.b="b"*32

    def payload(self,*,kind="p300_ram_0f20_32",ttl=90,request_id=None):
        return {"v":1,"op":"submit","request_id":request_id or self.a,
                "kind":kind,"ttl_s":ttl}

    def request(self,message):
        return self.control._dispatch(json.dumps(message).encode())

    def status(self,request_id=None,epoch=None,op="status"):
        return self.request({"v":1,"op":op,"request_id":request_id or self.a,
                             "session":epoch or self.control.epoch})

    def test_control_is_disabled_until_explicit_start(self):
        with self.assertRaises(DemandControlRejected):
            self.control.poll()
        self.assertFalse(self.path.exists())
        self.assertEqual(self.fixture.port.writes,[])

    def test_creates_private_socket_and_removes_only_owned_inode(self):
        self.control.start()
        self.addCleanup(self.control.close)
        st=self.path.lstat()
        self.assertEqual(st.st_mode & 0o777,0o600)
        self.assertEqual(st.st_uid,os.geteuid())
        self.assertEqual(self.control.records,{})
        self.control.close()
        self.assertFalse(self.path.exists())

    def test_wrong_parent_permissions_and_symlink_are_rejected(self):
        self.directory.chmod(0o755)
        with self.assertRaises(DemandControlRejected):
            self.control.start()
        self.directory.chmod(0o700)
        self.path.symlink_to(self.directory/"missing")
        with self.assertRaises(DemandControlRejected):
            self.control.start()
        self.assertTrue(self.path.is_symlink())
        self.path.unlink()

    def test_unprivileged_kernel_peer_is_rejected(self):
        if os.geteuid()==0:
            self.skipTest("requires non-root local test account")
        self.control.start()
        self.addCleanup(self.control.close)
        with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as cli:
            cli.settimeout(1)
            cli.connect(str(self.path))
            cli.sendall(json.dumps(self.payload()).encode())
            self.control.poll()
            ans=json.loads(cli.recv(512))
        self.assertEqual(ans["error"],"ROOT_PEER_REQUIRED")
        self.assertEqual(self.runtime.demands.pending_count(),0)
        self.assertEqual(self.fixture.port.writes,[])

    def test_authenticated_socket_request_and_stable_epoch(self):
        self.control.start()
        self.addCleanup(self.control.close)
        with patch.object(LocalDemandControl,"_peer_uid",return_value=0):
            with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as cli:
                cli.settimeout(1)
                cli.connect(str(self.path))
                cli.sendall(json.dumps(self.payload()).encode())
                self.control.poll()
                result=json.loads(cli.recv(512))
        self.assertTrue(result["ok"])
        self.assertEqual(result["state"],"queued")
        self.assertEqual(result["session"],self.control.epoch)
        self.assertEqual(len(result["session"]),32)
        self.assertNotIn("result",result)
        self.assertEqual(self.fixture.port.writes,[])

    def test_idempotency_and_conflicting_parameters(self):
        a=self.request(self.payload())
        repeat=self.request(self.payload())
        self.assertEqual(a,repeat)
        self.assertEqual(self.runtime.demands.pending_count(),1)
        self.assertEqual(self.request(self.payload(ttl=100))["error"],
                         "IDEMPOTENCY_CONFLICT")
        self.assertEqual(self.request(self.payload(kind="p300_identity"))["error"],
                         "IDEMPOTENCY_CONFLICT")
        self.assertEqual(self.fixture.port.writes,[])

    def test_single_full_p300_result_is_attested_vs1_only(self):
        accepted=self.request(self.payload())
        self.assertEqual(accepted["state"],"queued")
        self.fixture.valid_gfa()
        outcome=self.runtime.tick()
        self.assertEqual(outcome.status,"VERIFIED_SWITCH")
        # The ticket is completed, but not externally visible until proof
        # was attached by the owner after the fully verified outcome.
        self.assertEqual(self.status()["error"],"UNVERIFIED_RESULT")
        self.control.note_outcome(outcome)
        status=self.status()
        self.assertEqual(status["state"],"completed")
        result=status["result"]
        self.assertEqual(result["raw_hex"],outcome.replies[0].raw_hex)
        self.assertEqual(len(result["raw_hex"]),64)
        self.assertTrue(result["verified_vs1"])
        self.assertEqual(result["vs1_p80"],"20")
        self.assertEqual(result["vs1_p06"],"53")
        self.assertEqual(result["elapsed_ms"],outcome.result.elapsed_ms)
        self.assertEqual(result["origin"],
                         "P300_RAW_DIAGNOSTIC_NOT_ACTUAL_RPM")
        self.assertEqual(self.fixture.port.script,[])

    def test_expired_before_admission_never_sends_p300(self):
        self.request(self.payload(ttl=5))
        self.fixture.clock.sleep(6)
        self.control._prune()
        self.assertEqual(self.status()["state"],"expired")
        self.assertNotIn("result",self.status())
        self.assertEqual(self.fixture.port.writes,[])


    def test_cancel_only_queued_and_never_switches(self):
        self.request(self.payload())
        self.assertEqual(self.status(op="cancel")["state"],"cancelled")
        self.assertEqual(self.status(op="cancel")["error"],"NOT_CANCELLABLE")
        self.assertEqual(self.runtime.demands.pending_count(),0)
        self.assertFalse(self.runtime.due())
        self.assertFalse(self.fixture.port.writes)

    def test_wrong_session_must_never_return_old_results(self):
        self.request(self.payload())
        self.assertEqual(self.status(epoch=self.b)["error"],"STALE_SESSION")
        self.assertEqual(self.status(epoch=self.b,op="cancel")["error"],
                         "STALE_SESSION")
        self.assertEqual(self.runtime.demands.pending_count(),1)

    def test_refusals_are_visible_but_cannot_forge_success(self):
        self.request(self.payload())
        self.runtime.note_keepalive(1)
        out=self.runtime.tick()
        self.assertEqual(out.reason,"REAL_GFA_P06_NOT_FRESH")
        self.control.note_outcome(out)
        status=self.status()
        self.assertEqual(status["state"],"queued")
        self.assertEqual(status["last_refusal"],"REAL_GFA_P06_NOT_FRESH")
        self.assertNotIn("result",status)
        self.assertFalse(self.fixture.port.writes)

    def test_crc_failure_never_exposes_raw_result(self):
        self.fixture.port=self.fixture.fake_port(corrupt=True)
        self.runtime.port=self.fixture.port
        self.request(self.payload())
        self.fixture.valid_gfa()
        with self.assertRaises(Exception):
            self.runtime.tick()
        self.assertEqual(self.status()["state"],"failed")
        self.assertNotIn("result",self.status())
        self.assertEqual(self.request(self.payload(request_id=self.b))["error"],
                         "HYBRID_FAILED_CLOSED")

    def test_malformed_unknown_and_write_frames_are_rejected_without_io(self):
        samples=[
            (b'{"v":1,"v":1,"op":"submit"}',"INVALID_JSON"),
            (b'{"v":true,"op":"submit"}',"INVALID_VERSION"),
            (b'{"v":NaN,"op":"submit"}',"INVALID_JSON"),
            (b'{"v":1,"op":"write","request_id":"'+self.a.encode()+
             b'"}',"OPERATION_FORBIDDEN"),
            (b"\xff","INVALID_JSON"),
            (b"x"*513,"INVALID_PACKET_SIZE"),
            (b"","INVALID_PACKET_SIZE"),
        ]
        for message,error in samples:
            with self.subTest(error=error):
                self.assertEqual(self.control._dispatch(message)["error"],error)
        for payload,expected in (
                ({**self.payload(), "raw":"w;0x2303;1;1"},"INVALID_FIELDS"),
                (self.payload(kind="read;0x0f20;32"),"READ_KIND_FORBIDDEN"),
                (self.payload(ttl=True),"TTL_OUT_OF_RANGE"),
                (self.payload(ttl=121),"TTL_OUT_OF_RANGE"),
                (self.payload(ttl=4),"TTL_OUT_OF_RANGE"),
                (self.payload(request_id="X"*32),"INVALID_REQUEST_ID")):
            with self.subTest(payload=payload):
                self.assertEqual(self.request(payload)["error"],expected)
        self.assertEqual(self.runtime.demands.pending_count(),0)
        self.assertEqual(self.fixture.port.writes,[])

    def test_record_backpressure_bounded_and_no_serial_actions(self):
        self.control.MAX_RECORDS=2
        self.request(self.payload())
        self.request(self.payload(request_id=self.b))
        self.assertEqual(self.request(self.payload(request_id="c"*32))["error"],
                         "RECORDS_FULL")
        self.assertEqual(self.runtime.demands.pending_count(),2)
        self.assertEqual(self.fixture.port.writes,[])

    def test_expired_and_complete_records_pruned(self):
        self.request(self.payload(ttl=5))
        self.fixture.clock.sleep(181)
        self.control._prune()
        self.assertEqual(self.control.records,{})
        self.assertEqual(self.status()["error"],"UNKNOWN_REQUEST")
        # The same idempotency key must never trigger a SECOND hardware read
        # after its terminal result retention interval has passed.
        self.assertEqual(
            self.request(self.payload(ttl=5))["error"],"REQUEST_ID_RETIRED")
        self.assertEqual(self.fixture.port.writes,[])

    def test_session_id_budget_fails_closed_without_serial_io(self):
        self.control.MAX_SESSION_IDS=1
        self.request(self.payload())
        self.assertEqual(
            self.request(self.payload(request_id=self.b))["error"],
            "SESSION_REQUEST_LIMIT")
        self.assertEqual(self.runtime.demands.pending_count(),1)
        self.assertEqual(self.fixture.port.writes,[])

    def test_operator_requires_explicit_root_consent_and_no_raw_addresses(self):
        with patch.object(operator,"_require_root",return_value=None),\
             patch.object(operator,"_local_demand_rpc",return_value={"v":1,"ok":True}) as rpc:
            with self.assertRaisesRegex(operator.OperatorRejected,"Explizites"):
                operator.demand_request("p300_ram_0f20_32",90,acknowledged=False)
            rpc.assert_not_called()
            with self.assertRaises(operator.OperatorRejected):
                operator.demand_request("write",90,acknowledged=True)
            with self.assertRaises(operator.OperatorRejected):
                operator.demand_request("p300_identity",True,acknowledged=True)
            result=operator.demand_request(
                "p300_ram_0f20_32",90,acknowledged=True,request_id=self.a)
            self.assertTrue(result["ok"])
            rpc.assert_called_once()
            self.assertEqual(rpc.call_args.args[0]["request_id"],self.a)

    def test_operator_fails_closed_without_socket_or_attested_pid(self):
        with patch.object(operator,"_require_root",return_value=None),\
             patch.object(operator.continuous_runtime,"DEMAND_SOCKET_PATH",
                          self.path):
            with self.assertRaisesRegex(operator.OperatorRejected,"nicht aktiv"):
                operator._local_demand_rpc(self.payload())

    def test_cli_and_real_unix_socket_peer_identity_pinned_to_main(self):
        self.control.start()
        self.addCleanup(self.control.close)
        actual=SimpleNamespace(pw_uid=os.geteuid(),pw_gid=os.getegid())
        answer={}
        def client():
            try:
                answer["response"]=operator._local_demand_rpc(self.payload())
            except BaseException as exc:
                answer["error"]=repr(exc)
        with patch.object(LocalDemandControl,"_peer_uid",return_value=0),\
             patch.object(operator,"_require_root",return_value=None),\
             patch.object(operator.continuous_runtime,"DEMAND_SOCKET_PATH",
                          self.path),\
             patch.object(operator.pwd,"getpwnam",return_value=actual),\
             patch.object(operator.subprocess,"check_output",
                          return_value=str(os.getpid())):
            thread=threading.Thread(target=client)
            thread.start()
            for _ in range(150):
                self.control.poll()
                if not thread.is_alive():
                    break
                time.sleep(0.005)
            thread.join(timeout=1)
        self.assertNotIn("error",answer,answer)
        self.assertEqual(answer["response"]["state"],"queued")
        self.assertEqual(answer["response"]["session"],self.control.epoch)

    def test_owner_thread_required_even_for_socket_accept(self):
        self.control.start()
        self.addCleanup(self.control.close)
        failures=[]
        def worker():
            try:
                self.control.poll()
            except DemandControlRejected:
                failures.append("blocked")
        t=threading.Thread(target=worker)
        t.start()
        t.join()
        self.assertEqual(failures,["blocked"])


    def test_both_additional_allowlisted_reads_are_typed_only(self):
        one=self.request(self.payload(kind="p300_identity"))
        two=self.request(self.payload(kind="p300_ram_1c60_32",request_id=self.b))
        self.assertEqual(one["kind"],"p300_identity")
        self.assertEqual(two["kind"],"p300_ram_1c60_32")
        self.assertEqual(self.runtime.demands.pending_count(),2)
        self.assertEqual(self.fixture.port.writes,[])

    def test_explicit_1640_rx_diagnostic_is_root_socket_queue_only(self):
        req=self.request(self.payload(kind='p300_ram_1640_32'))
        self.assertTrue(req['ok'])
        self.assertEqual(req['kind'],'p300_ram_1640_32')
        self.assertEqual(self.runtime.demands.pending_count(),1)
        self.assertEqual(self.fixture.port.writes,[])
        for bad_kind in ('p300_ram_1642_32','p300_fc04_1640_32',
                         'p300_ram_1640_write'):
            rejected=self.request(self.payload(kind=bad_kind,request_id=self.b))
            self.assertFalse(rejected['ok'])
            self.assertEqual(self.runtime.demands.pending_count(),1)
        self.assertEqual(self.fixture.port.writes,[])

    def test_duplicate_socket_bind_must_not_unlink_original_owner(self):
        self.control.start()
        self.addCleanup(self.control.close)
        other=LocalDemandControl(self.runtime,path=self.path)
        with self.assertRaises(DemandControlRejected):
            other.start()
        self.assertTrue(self.path.is_socket())
        self.assertIsNotNone(self.control.server)

    def test_no_outcome_proof_never_becomes_result(self):
        from handover_acceleration.continuous_runtime import DemandTickOutcome
        self.request(self.payload())
        with self.assertRaises(DemandControlRejected):
            self.control.note_outcome(DemandTickOutcome("VERIFIED_SWITCH"))
        self.assertEqual(self.status()["state"],"queued")
        self.assertNotIn("result",self.status())
        self.assertFalse(self.fixture.port.writes)

    def test_root_client_rejects_other_server_pid(self):
        self.control.start()
        self.addCleanup(self.control.close)
        actual=SimpleNamespace(pw_uid=os.geteuid(),pw_gid=os.getegid())
        with patch.object(operator,"_require_root",return_value=None),\
             patch.object(operator.continuous_runtime,"DEMAND_SOCKET_PATH",
                          self.path),\
             patch.object(operator.pwd,"getpwnam",return_value=actual),\
             patch.object(operator.subprocess,"check_output",
                          return_value=str(os.getpid()+1)):
            with self.assertRaisesRegex(operator.OperatorRejected,"nicht der attestierte"):
                operator._local_demand_rpc(self.payload())
        self.assertEqual(self.runtime.demands.pending_count(),0)
        self.assertEqual(self.fixture.port.writes,[])


if __name__=="__main__":
    unittest.main()
