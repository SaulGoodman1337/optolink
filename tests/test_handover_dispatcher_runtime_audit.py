"""No live access: static installed-source compatibility audit regressions."""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from handover_acceleration.dispatcher_runtime_audit import (
    AuditRejected, source_audit, audit_directory, main,
)
from test_handover_dispatcher_patch import UPSTREAM_EXCERPT

REQUESTS='''\ndef response_to_request(request, ser):\n    if(cmnd in ["write", "w"]): pass\n    if(cmnd in ["writeraw", "wraw"]): pass\n    gfaread = 'valid_read_command'\n'''
ADAPTER='VS2 = not settings.vs1protocol\n'

class RuntimeAuditTests(unittest.TestCase):
    def test_exact_original_three_seams_supported(self):
        r=source_audit(UPSTREAM_EXCERPT,REQUESTS,ADAPTER)
        self.assertTrue(r['shadow_source_copy_supported'])
        self.assertEqual(r['main_legacy_poll_calls'],1)
        self.assertEqual(r['main_mqtt_tcp_calls'],2)
        self.assertTrue(r['legacy_write_commands_present'])
        self.assertTrue(r['legacy_gfa_patch_detected'])
        self.assertTrue(r['main_direct_vitoconnect_branch'])
        self.assertTrue(r['main_vs1_keepalive'])
        self.assertFalse(r['production_changes_performed'])
        self.assertEqual(len(r['main_sha256']),64)

    def test_installed_custom_mainloop_differences_reported_not_patched(self):
        original=UPSTREAM_EXCERPT.replace('response_to_request(msg, serOptolink)',
                                          'response_to_request(msg, opto)',1)
        r=source_audit(original,REQUESTS,ADAPTER)
        self.assertFalse(r['shadow_source_copy_supported'])
        self.assertEqual(r['main_mqtt_tcp_calls'],1)
        self.assertIn('call count',r['shadow_reason'])

    def test_absent_gfa_patch_and_legacy_writes_report_false(self):
        r=source_audit(UPSTREAM_EXCERPT,'def response_to_request():pass',ADAPTER)
        self.assertFalse(r['legacy_gfa_patch_detected'])
        self.assertFalse(r['legacy_write_commands_present'])

    def test_audit_directory_no_modifications(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for f,text in (('optolinkvs2_switch.py',UPSTREAM_EXCERPT),
                           ('requests_util.py',REQUESTS),('vs12_adapter.py',ADAPTER)):
                (root/f).write_text(text)
            before={p.name:p.read_bytes() for p in root.iterdir()}
            result=audit_directory(root)
            self.assertTrue(result['shadow_source_copy_supported'])
            self.assertEqual({p.name:p.read_bytes() for p in root.iterdir()},before)
            buf=io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(main(['--root',str(root)]),0)
            self.assertIn('SOURCE_AUDIT_ONLY_NO_HARDWARE_IO',buf.getvalue())

    def test_symlink_is_refused_before_read(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'optolinkvs2_switch.py').symlink_to('/etc/passwd')
            (root/'requests_util.py').write_text(REQUESTS)
            (root/'vs12_adapter.py').write_text(ADAPTER)
            with self.assertRaises(AuditRejected):audit_directory(root)

    def test_missing_source_refused(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(AuditRejected):audit_directory(Path(d))

    def test_statically_disallows_code_execution_import_serial_and_service_change(self):
        p=Path(__file__).resolve().parents[1]/'tools/handover_acceleration/dispatcher_runtime_audit.py'
        code=p.read_text()
        for forbidden in ('import serial','systemctl','subprocess','importlib.import_module','exec(', 'eval('):
            with self.subTest(t=forbidden):self.assertNotIn(forbidden,code)

if __name__=='__main__':unittest.main()
