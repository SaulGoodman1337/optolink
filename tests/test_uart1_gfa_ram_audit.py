"""Fail-closed tests for offline-only second UART RAM differential audit."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

TOOL = Path(__file__).resolve().parents[1] / 'tools' / 'audit-uart1-gfa-ram.py'
spec=importlib.util.spec_from_file_location('uart1_audit',TOOL)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def captures():
    a=bytearray(mod.SIZE)
    b=bytearray(mod.SIZE)
    a[0x161B-mod.BASE] = 0x7A
    b[0x161B-mod.BASE] = 0x8A
    a[0x161C-mod.BASE] = 0x13
    b[0x161C-mod.BASE] = 0x13
    a[0x196C-mod.BASE] = 0xFF
    b[0x196C-mod.BASE] = 0x01
    a[0x0700-mod.BASE] = 0x30
    b[0x0700-mod.BASE] = 0x40
    return bytes(a),bytes(b)


class UART1ArchiveTests(unittest.TestCase):
    def test_counts_and_source_focus(self):
        a,b=captures()
        out=mod.analyze_passes(a,b)
        self.assertEqual(out['changed_total'],3)
        self.assertEqual(out['uart1_source_focus']['changed_bytes'],1)
        self.assertEqual(out['uart1_source_focus']['changed_addresses'],['0x161b'])
        self.assertEqual(out['changed_within_own_optolink_exclusion'],1)
        self.assertEqual(out['uart1_source_focus']['interpretation'],
                         'DIFFERENCES_PRESENT_SOURCE_UNKNOWN')
        self.assertFalse(out['candidate_gfa_ram_address_verified'])

    def test_exclusion_wins_over_strong_optolink_activity(self):
        a=bytes(mod.SIZE); b=bytearray(a)
        for addr in range(0x196C,0x19EC):
            b[addr-mod.BASE]=0xF1
        out=mod.analyze_passes(a,bytes(b))
        self.assertEqual(out['changed_within_own_optolink_exclusion'],128)  # include unknown RX/TX gap conservatively
        self.assertEqual(out['ranked_other_windows_top12'],[])
        self.assertEqual(out['uart1_source_focus']['changed_bytes'],0)

    def test_source_without_change_not_semantically_rejected(self):
        a=bytes(mod.SIZE)
        out=mod.analyze_passes(a,a)
        self.assertEqual(out['uart1_source_focus']['interpretation'],
                         'NO_DIFFERENCE_IN_TWO_CAPTURED_PASSES')
        self.assertFalse(out['production_alias_approved'])

    def test_slab_fails_out_of_bounds(self):
        with self.assertRaises(ValueError):
            mod.slab(bytes(mod.SIZE),mod.BASE-1,mod.BASE)
        with self.assertRaises(ValueError):
            mod.slab(bytes(mod.SIZE),mod.END,mod.END+1)

    def test_short_capture_fails(self):
        with self.assertRaises(ValueError):
            mod.analyze_passes(b'', bytes(mod.SIZE))

    def test_excludes_only_known_optolink_ranges(self):
        self.assertTrue(mod.excluded(0x192C))
        self.assertTrue(mod.excluded(0x1933))
        self.assertTrue(mod.excluded(0x19AE))
        self.assertTrue(mod.excluded(0x1A6D))
        self.assertFalse(mod.excluded(0x161B))
        self.assertFalse(mod.excluded(0x1953))
        self.assertFalse(mod.excluded(0x1A6E))

    def create_report(self,folder,a,b,**changes):
        root=Path(folder)
        pa=root/'physical-ram-pass1.bin'; pb=root/'physical-ram-pass2.bin'
        pa.write_bytes(a);pb.write_bytes(b)
        obj={'ram_start':mod.BASE,'ram_end':mod.END,'chunk':mod.CHUNK,
             'size':mod.SIZE,
             'changed_bytes':sum(x!=y for x,y in zip(a,b)),
             'stable_bytes':sum(x==y for x,y in zip(a,b)),
             'pass1':str(pa),'pass2':str(pb)}
        obj.update(changes)
        rp=root/'physical-ram-report.json'
        rp.write_text(json.dumps(obj))
        return rp,pa,pb

    def test_load_legacy_report(self):
        with tempfile.TemporaryDirectory() as d:
            a,b=captures(); rp,pa,pb=self.create_report(d,a,b)
            aa,bb,meta=mod.load_capture(report=rp)
            self.assertEqual((aa,bb),(a,b))
            self.assertEqual(len(meta['pass1_sha256']),64)
            self.assertTrue(meta['historical_report_sha256'])

    def test_load_explicit_pair(self):
        with tempfile.TemporaryDirectory() as d:
            a,b=captures();rp,pa,pb=self.create_report(d,a,b)
            self.assertEqual(mod.load_capture(pass1=pa,pass2=pb)[:2],(a,b))

    def test_prevent_mixed_sources(self):
        with tempfile.TemporaryDirectory() as d:
            a,b=captures();rp,pa,pb=self.create_report(d,a,b)
            with self.assertRaisesRegex(ValueError,'either report'):
                mod.load_capture(report=rp,pass1=pa)

    def test_mismatched_legacy_report_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a,b=captures()
            rp,_,_=self.create_report(d,a,b,changed_bytes=100)
            with self.assertRaisesRegex(ValueError,'changed_bytes'):
                mod.load_capture(report=rp)

    def test_wrong_ram_range_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a,b=captures()
            rp,_,_=self.create_report(d,a,b,ram_end=0x52FF)
            with self.assertRaisesRegex(ValueError,'ram_end'):
                mod.load_capture(report=rp)

    def test_short_ram_capture_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a,b=captures()
            rp,pa,pb=self.create_report(d,a,b)
            pb.write_bytes(b[:900])
            with self.assertRaisesRegex(ValueError,'wrong RAM pass size'):
                mod.load_capture(report=rp)

    def test_symlink_input_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a,b=captures()
            rp,pa,pb=self.create_report(d,a,b)
            pa.unlink()
            pa.symlink_to(pb)
            with self.assertRaisesRegex(ValueError,'not a regular'):
                mod.load_capture(report=rp)

    def test_source_pointer_context_is_64_bytes(self):
        a,b=captures()
        result=mod.analyze_passes(a,b)
        self.assertEqual(len(result['uart1_source_focus']['pass1_context_hex']),128)
        self.assertEqual(len(result['uart1_source_focus']['pass2_context_hex']),128)

    def test_cli_plan_is_inert(self):
        import unittest.mock
        with unittest.mock.patch.object(sys,'argv',['audit-uart1-gfa-ram.py']):
            sink=io.StringIO()
            with contextlib.redirect_stdout(sink):
                self.assertEqual(mod.main(),0)
            self.assertIn('PLAN ONLY',sink.getvalue())
            self.assertIn('No serial/MQTT',sink.getvalue())

    def test_cli_report_is_offline_and_written_once(self):
        import unittest.mock
        with tempfile.TemporaryDirectory() as d:
            a,b=captures()
            rp,_,_=self.create_report(d,a,b)
            target=Path(d)/'result.json'
            args=['audit-uart1-gfa-ram.py','--report',str(rp),'--output',str(target)]
            with unittest.mock.patch.object(sys,'argv',args):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(mod.main(),0)
                with self.assertRaises(FileExistsError):
                    mod.main()
            obj=json.loads(target.read_text())
            self.assertFalse(obj['appliance_access_performed'])
            self.assertFalse(obj['live_read_approved_from_this_offline_result'])

    def test_same_pass_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a,b=captures()
            rp,pa,pb=self.create_report(d,a,b)
            with self.assertRaisesRegex(ValueError,'two different'):
                mod.load_capture(pass1=pa,pass2=pa)


if __name__=='__main__':
    unittest.main()
