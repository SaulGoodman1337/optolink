"""Research-only integration patch test: does not contact a heating appliance."""
from __future__ import annotations
import ast
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
import sys

PATCH = Path(__file__).resolve().parents[1] / 'tools' / 'optolink-apply-gwg-readonly-patch.py'
spec = importlib.util.spec_from_file_location('gwg_patch_offline', PATCH)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

ADAPTER = '''import serial
import optolinkvs2
import optolinkvs1
import viconn_util
from c_settings_adapter import settings

VS2 = not settings.vs1protocol

def init_protocol(ser:serial.Serial) -> bool:
    if(VS2):
        return optolinkvs2.init_vs2(ser)
    else:
        return optolinkvs1.init_protocol(ser)

def read_datapoint_ext(addr:int, rdlen:int, ser:serial.Serial) -> tuple[int,int,bytearray]:
    if(VS2):
        return optolinkvs2.read_datapoint_ext(addr, rdlen, ser)
    else:
        return optolinkvs1.read_datapoint_ext(addr, rdlen, ser)

def read_gfa_ext(addr:int, rdlen:int, ser:serial.Serial) -> tuple[int,int,bytearray]:
    if VS2:
        return 0xAF, addr, bytearray()
    return optolinkvs1.read_gfa_ext(addr, rdlen, ser)

def write_datapoint_ext(addr:int, data:bytes, ser:serial.Serial) -> tuple[int,int,bytearray]:
    if(VS2):
        return optolinkvs2.write_datapoint_ext(addr, data, ser)
    else:
        return optolinkvs1.write_datapoint_ext(addr, data, ser)
'''
REQUESTS = '''def response_to_request(request, serViDev):
    cmnd = request
    parts = str(request).split(';')
    numelms = len(parts)
    data = bytearray()
    retcode = 0
    addr = 0
    val = None
    retstr = None
    if True:
        if cmnd == 'noop':
            pass
        elif(cmnd in ["write", "w"]):
            pass
    return retcode, data, val, retstr
'''


class IntegrationPatchTests(unittest.TestCase):
    def test_adapter_ast(self):
        ast.parse(mod.patch_adapter(ADAPTER))

    def test_requests_ast(self):
        ast.parse(mod.patch_requests(REQUESTS))

    def test_adapter_idempotent(self):
        first = mod.patch_adapter(ADAPTER)
        self.assertEqual(mod.patch_adapter(first), first)

    def test_requests_idempotent(self):
        first = mod.patch_requests(REQUESTS)
        self.assertEqual(mod.patch_requests(first), first)

    def test_adapter_has_gwg_single_owner(self):
        out = mod.patch_adapter(ADAPTER)
        self.assertIn('read_gwg_ext(addr:int, rdlen:int, ser:serial.Serial', out)
        self.assertIn('optolinkgwg.read_datapoint_ext(', out)
        self.assertIn('addr, rdlen, ser, retries=retries', out)
        self.assertIn('GWG_C7 TX/RX %s', out)
        self.assertNotIn('serial.Serial(', out)

    def test_adapter_enforces_vs1_mode(self):
        self.assertIn('if VS2:\n        return 0xAF', mod.patch_adapter(ADAPTER))

    def test_adapter_forces_sync_before_followup_read(self):
        out = mod.patch_adapter(ADAPTER)
        self.assertIn('_gwg_resync_kw_if_needed()\n        return optolinkvs1.read_datapoint_ext', out)

    def test_adapter_forces_sync_before_followup_write(self):
        out = mod.patch_adapter(ADAPTER)
        self.assertIn('_gwg_resync_kw_if_needed()\n        return optolinkvs1.write_datapoint_ext', out)

    def test_adapter_forces_sync_before_gfa(self):
        out = mod.patch_adapter(ADAPTER)
        self.assertIn('_gwg_resync_kw_if_needed()\n    return optolinkvs1.read_gfa_ext', out)

    def test_adapter_guards_retries(self):
        out = mod.patch_adapter(ADAPTER)
        self.assertIn('if retries not in (0, 1):', out)

    def test_request_command_routes_owned_port(self):
        out = mod.patch_requests(REQUESTS)
        self.assertIn('read_gwg_ext(addr, rdlen, serViDev, retries)', out)
        self.assertIn('elif(cmnd == "gwgread"):', out)

    def test_request_rejects_extra_parts(self):
        out = mod.patch_requests(REQUESTS)
        self.assertIn('if numelms not in (3, 4):', out)

    def test_request_does_not_inject_raw_opcode(self):
        out = mod.patch_requests(REQUESTS)
        self.assertNotIn('sendraw', out)
        self.assertNotIn('sendbytes', out)

    def test_wrong_import_fails_closed(self):
        with self.assertRaises(mod.UnsafePatch):
            mod.patch_adapter(ADAPTER.replace('import optolinkvs1', 'import optolinkvs22'))

    def test_missing_adapter_anchor_fails_closed(self):
        with self.assertRaises(mod.UnsafePatch):
            mod.patch_adapter(ADAPTER.replace('    return optolinkvs1.read_gfa_ext', '    return mystery.read_gfa_ext'))

    def test_double_request_anchor_fails_closed(self):
        with self.assertRaises(mod.UnsafePatch):
            mod.patch_requests(REQUESTS.replace('    return retcode, data, val, retstr',
                                                '        elif(cmnd in ["write", "w"]):\n            pass\n    return retcode, data, val, retstr'))

    def test_crlf_preservation(self):
        out = mod.patch_adapter(ADAPTER.replace('\n', '\r\n'))
        self.assertIn('\r\n', out)
        self.assertEqual(out.count('\n'), out.count('\r\n'))

    def test_patch_has_pinned_sha_for_real_runtime(self):
        self.assertEqual(mod.BASE_SHA256['vs12_adapter.py'],
                         '67a760e925719225d61e375e9c976743b7bfb2d6bec8a9ea59d612397c4b3de2')
        self.assertEqual(mod.BASE_SHA256['requests_util.py'],
                         '7cc01e2fb41a56adf0f395a86a2a352411c9632032744eeb59ebfd669c51f790')

    def test_unknown_source_refuses_patch(self):
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            (root / 'vs12_adapter.py').write_text('modified unknown file')
            (root / 'requests_util.py').write_text(REQUESTS)
            with self.assertRaises(mod.UnsafePatch):
                mod.stage(root)
            self.assertFalse((root / 'optolinkgwg.py').exists())

    def test_staging_in_fixture_and_idempotent(self):
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            (root / 'vs12_adapter.py').write_text(ADAPTER)
            (root / 'requests_util.py').write_text(REQUESTS)
            old = dict(mod.BASE_SHA256)
            try:
                for name in mod.BASE_SHA256:
                    mod.BASE_SHA256[name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
                mod.stage(root)
                first = [(root / name).read_bytes() for name in (*mod.BASE_SHA256, 'optolinkgwg.py')]
                mod.stage(root)
                second = [(root / name).read_bytes() for name in (*mod.BASE_SHA256, 'optolinkgwg.py')]
                self.assertEqual(first, second)
                for name in mod.BASE_SHA256:
                    ast.parse((root / name).read_text())
            finally:
                mod.BASE_SHA256.update(old)

    def test_production_hotpatch_is_blocked(self):
        with self.assertRaises(mod.UnsafePatch):
            mod.stage(mod.ROOT_PRODUCTION)

    def test_missing_runtime_reports_missing(self):
        with tempfile.TemporaryDirectory() as path:
            report = mod.verify_root(Path(path))
            self.assertEqual(report['vs12_adapter.py'], 'missing')
            self.assertEqual(report['requests_util.py'], 'missing')


if __name__ == '__main__':
    unittest.main()
