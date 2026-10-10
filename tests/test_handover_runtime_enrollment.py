"""Fail-closed enrollment proof using simulated root metadata and unit states."""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from handover_acceleration import runtime_enrollment as re


class EnrollmentEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.lease=self.root/'writer.lock'
        self.lease.write_bytes(b'')
        self.manifest=self.root/'enrollment.json'
        self.data={'schema':1,'producer_lock':str(self.lease),
            'writers':{
                role:{'unit':unit,'path':str(re.ORIGINAL_PATHS[role]),
                      'sha256':'a'*64}
                for role,unit in re.UNITS.items()
            }}
        self.manifest.write_text(json.dumps(self.data))
        self.manifest.chmod(0o640)
        self.lease.chmod(0o600)
        self.original_stat=Path.stat

    def fake_stat(self,p,*args,**kwargs):
        st=self.original_stat(p,*args,**kwargs)
        if str(p) in (str(self.manifest),str(self.lease)):
            return types.SimpleNamespace(st_uid=0,st_mode=st.st_mode,
                  st_size=st.st_size,st_mtime=st.st_mtime,st_nlink=st.st_nlink)
        return st

    def simulated_verify(self,*,active=True,timer=True,proc=True):
        def show(unit,key):
            if unit=='optolink-clock-sync.timer':
                return 'active' if timer else 'inactive'
            if key=='ExecStart':
                return str(re.ORIGINAL_PATHS['clock-sync'])
            return 'active' if active else 'inactive'
        with patch.object(re,'LEASE_PATH',self.lease), \
             patch.object(Path,'stat',lambda p,*a,**kw:self.fake_stat(p,*a,**kw)), \
             patch.object(re,'_pinned_file',return_value=True), \
             patch.object(re,'_show',side_effect=show), \
             patch.object(re,'_process_confirms',return_value=proc):
            return re.verify_enrollment(self.manifest)

    def test_full_source_attestation_can_pass_with_all_five_pinned(self):
        report=self.simulated_verify()
        self.assertTrue(report.accepted)
        self.assertEqual(set(report.checked_roles),set(re.UNITS))

    def test_missing_role_disables_p300(self):
        self.data['writers'].pop('maintenance')
        self.manifest.write_text(json.dumps(self.data))
        out=self.simulated_verify()
        self.assertFalse(out.accepted)
        self.assertIn('five writers',out.reason)

    def test_stale_process_proof_or_clock_timer_disables_p300(self):
        self.assertFalse(self.simulated_verify(proc=False).accepted)
        self.assertFalse(self.simulated_verify(timer=False).accepted)

    def test_persistent_failed_writer_marker_denies_auto(self):
        self.lease.write_bytes(b'ACTIVE:party')
        report=self.simulated_verify()
        self.assertFalse(report.accepted)
        self.assertIn('failure latched',report.reason)

    def test_manifest_permissions_and_symlink_fail_closed(self):
        # A non-root manifest is intentionally rejected without mocking.
        with patch.object(re,'LEASE_PATH',self.lease):
            self.assertFalse(re.verify_enrollment(self.manifest).accepted)
        link=self.root/'manifest-link'
        link.symlink_to(self.manifest)
        with patch.object(re,'LEASE_PATH',self.lease):
            self.assertFalse(re.verify_enrollment(link).accepted)

    def test_pinned_binary_requires_real_wrapper_and_exact_raw_hash(self):
        source=self.root/'program.py'
        source.write_text('print(1)\n')
        sha=hashlib.sha256(source.read_bytes()).hexdigest()
        self.assertFalse(re._pinned_file(source,sha,marker=True))
        source.write_text(re.TOKEN+'\nprint(1)\n')
        sha2=hashlib.sha256(source.read_bytes()).hexdigest()
        # Owner policy is root-only; this synthetic file is deliberately not.
        self.assertFalse(re._pinned_file(source,sha2,marker=True))
        self.assertFalse(re._pinned_file(source,'broken',marker=False))

    def test_invalid_writer_release_path_rejected(self):
        for name in ('/tmp/unsafe.py','../relative','/etc/passwd'):
            with self.subTest(path=name),self.assertRaises(re.EnrollmentRejected):
                re._approved_path('party',name)


if __name__=='__main__':
    unittest.main()
