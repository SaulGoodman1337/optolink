"""Versioned staged runtime acceptance: command-free, hash-verified, fail-closed."""
import contextlib
import hashlib
import subprocess
import json
import os
import sys
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from handover_acceleration import hybrid_acceptance as h
from test_handover_dispatcher_patch import UPSTREAM_EXCERPT


class HybridAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name)
        self.source=self.folder/'installed'
        self.source.mkdir()
        (self.source/'optolinkvs2_switch.py').write_text(UPSTREAM_EXCERPT)
        self.session=self.folder/'staged'
        self.session.mkdir(mode=0o700)
        self.source_hash=hashlib.sha256(UPSTREAM_EXCERPT.encode()).hexdigest()
        self.source_stub={'main_sha256':self.source_hash,'shadow_source_copy_supported':True}

    def test_staged_product_includes_real_original_code_but_never_overwrites(self):
        source_before=(self.source/'optolinkvs2_switch.py').read_bytes()
        with patch.object(h,'_verify_original',return_value=self.source_stub):
            manifest=h.stage(self.session,self.source)
            confirmed=h.verify_stage(self.session,self.source)
        self.assertEqual(manifest,confirmed)
        self.assertEqual(manifest['version'],h.VERSION)
        self.assertEqual(len(manifest['source_sha256']),len(h.STAGE_FILES))
        text=(self.session/'optolinkvs2_switch.py').read_text()
        self.assertIn('OPTO_HYBRID_BOOT_ONESHOT',text)
        self.assertIn('handover_legacy_or_shim',text)
        self.assertEqual((self.source/'optolinkvs2_switch.py').read_bytes(),source_before)
        self.assertEqual((self.session/'hybrid_acceptance.py').stat().st_mode&0o077,0)

    def test_staged_worker_import_graph_runs_without_repository_checkout(self):
        with patch.object(h,'_verify_original',return_value=self.source_stub):
            h.stage(self.session,self.source)
        env=dict(os.environ,PYTHONPATH=str(self.session))
        env.pop('INVOCATION_ID',None)
        cmd=[sys.executable,str(self.session/'hybrid_acceptance.py'),
             '--worker',str(self.session)]
        completed=subprocess.run(cmd,cwd=str(self.session),env=env,
                                 capture_output=True,text=True,timeout=10)
        self.assertEqual(completed.returncode,1)
        self.assertIn('supervised systemd unit',completed.stderr)
        self.assertNotIn('ImportError',completed.stderr)

    def test_separate_staged_python_really_imports_new_lock_and_runtime_modules(self):
        with patch.object(h, '_verify_original', return_value=self.source_stub):
            h.stage(self.session, self.source)
        program = (
            'import importlib.util, pathlib; '
            'p=pathlib.Path("hybrid_acceptance.py"); '
            's=importlib.util.spec_from_file_location("staged_worker",p); '
            'm=importlib.util.module_from_spec(s); s.loader.exec_module(m); '
            'assert m.pump_lease.__module__ == "handover_acceleration.port_ownership"; '
            'from handover_acceleration.runtime_admission import RuntimeAdmissionGate; '
            'assert RuntimeAdmissionGate.__name__ == "RuntimeAdmissionGate"; '
            'print("STAGED_DEPENDENCIES=PASS")'
        )
        env=dict(os.environ, PYTHONPATH=str(self.session))
        completed=subprocess.run([sys.executable, '-c', program],
                                 cwd=str(self.session), env=env,
                                 capture_output=True, text=True, timeout=10)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn('STAGED_DEPENDENCIES=PASS', completed.stdout)

    def test_staged_tamper_is_rejected(self):
        with patch.object(h,'_verify_original',return_value=self.source_stub):
            h.stage(self.session,self.source)
            (self.session/'handover_acceleration/hybrid_boot.py').write_text('malicious\n')
            with self.assertRaisesRegex(h.AcceptanceRejected,'changed'):
                h.verify_stage(self.session,self.source)

    def test_changed_production_sha_refuses_stage(self):
        h.stage
        fake=dict(self.source_stub,main_sha256='0'*64)
        with patch.object(h,'_verify_original',return_value=self.source_stub):
            h.stage(self.session,self.source)
        with patch.object(h,'_verify_original',return_value=fake):
            with self.assertRaisesRegex(h.AcceptanceRejected,'production code changed'):
                h.verify_stage(self.session,self.source)

    def test_unsupported_gfa_or_legacy_writes_refused_at_source_audit(self):
        audit={k:True for k in (
            'shadow_source_copy_supported','legacy_gfa_patch_detected',
            'legacy_request_parser_present','legacy_write_commands_present',
            'main_direct_vitoconnect_branch','main_vs1_keepalive',
            'adapter_static_protocol_flag')}
        audit['main_sha256']=h.PINNED_INSTALLED_SHA256
        with patch.object(h,'audit_directory',return_value=audit):
            self.assertEqual(h._verify_original(self.source),audit)
        for key in [k for k,v in audit.items() if v is True]:
            bad=dict(audit,**{key:False})
            with self.subTest(key=key),patch.object(h,'audit_directory',return_value=bad):
                with self.assertRaises(h.AcceptanceRejected):h._verify_original(self.source)

    def test_random_runtime_sha_refused_by_operator_pin(self):
        audit={k:True for k in (
            'shadow_source_copy_supported','legacy_gfa_patch_detected',
            'legacy_request_parser_present','legacy_write_commands_present',
            'main_direct_vitoconnect_branch','main_vs1_keepalive','adapter_static_protocol_flag')}
        audit['main_sha256']='0'*64
        with patch.object(h,'audit_directory',return_value=audit):
            with self.assertRaisesRegex(h.AcceptanceRejected,'SHA256'):
                h._verify_original(self.source)

    @staticmethod
    def good_boot():
        return {'status':'PASS_VERIFIED_BORROWED_PORT_FIXED_FC03',
                'identity_hex':'20c2','gfa_p80_hex':'20','gfa_p06_hex':'00',
                'verified_vs1_return':True,'no_second_serial_open':True,
                'no_device_write':True,'phase_count':1,
                'ram_0f20_32_hex':'7a'*32,'ram_1c60_32_hex':'ae'*32}

    def test_validated_boot_result_requires_full_exact_identity(self):
        good=self.good_boot()
        self.assertTrue(h._verified_boot_record(good))
        for key,value in [('status','PASS'),('identity_hex','9999'),
                          ('gfa_p80_hex','21'),('gfa_p06_hex','ff'),
                          ('gfa_p06_hex',None),('gfa_p06_hex','zz'),('gfa_p06_hex','000'),
                          ('no_second_serial_open',False),
                          ('no_device_write',False),('phase_count',2),
                          ('ram_0f20_32_hex','aa'),('ram_1c60_32_hex','xx')]:
            with self.subTest(key=key,value=value):
                invalid=dict(good,**{key:value})
                self.assertFalse(h._verified_boot_record(invalid))

    def test_report_writer_rejects_overwriting_and_symlinks(self):
        h._atomic_json(self.session,'state.json',{'passed':True})
        with self.assertRaises(FileExistsError):
            h._atomic_json(self.session,'state.json',{'passed':False})
        self.assertEqual(json.loads((self.session/'state.json').read_text()),{'passed':True})
        (self.session/'link.json').symlink_to(self.session/'state.json')
        with self.assertRaises(OSError):
            h._atomic_json(self.session,'link.json',{'passed':False})

    def test_plan_only_refuses_pause_flags_without_execute(self):
        with self.assertRaisesRegex(h.AcceptanceRejected,'no telemetry pause'):
            h.main(['--accept-telemetry-pause','--root',str(self.source)])
        with self.assertRaisesRegex(h.AcceptanceRejected,'opt-in'):
            h.main(['--execute','--root',str(self.source)])

    def test_cli_never_executes_when_only_auditing(self):
        with patch.object(h,'_verify_original',return_value=self.source_stub), \
             patch.object(h,'execute',side_effect=AssertionError('do not execute')):
            self.assertEqual(h.main(['--root',str(self.source)]),0)

    def test_worker_rejected_outside_systemd(self):
        with patch.dict(os.environ,{'INVOCATION_ID':''},clear=True):
            # The systemd-only check requires both the flag AND root; with no
            # flag this is rejected even if the process happens to be root.
            os.environ.pop('INVOCATION_ID',None)
            with self.assertRaisesRegex(h.AcceptanceRejected,'systemd'):
                h.main(['--worker',str(self.session)])


if __name__=='__main__':unittest.main()
