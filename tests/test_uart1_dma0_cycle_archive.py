"""No device I/O: automatic archive and post-restore checks are mocked."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import tarfile
import json
import unittest
from unittest.mock import patch

target=Path(__file__).resolve().parents[1]/'tools'/'wb2a-uart1-dma0-cycle.py'
spec=importlib.util.spec_from_file_location('dma_cycle_extra',target)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class ArchiveSmoke(unittest.TestCase):
    def test_private_bundle(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            session=root/'run-fixture'
            session.mkdir(mode=0o700)
            for name in ('state.json','samples.jsonl','measurement.json','recovery.json'):
                (session/name).write_text('{}\n')
            with patch.object(m,'ROOT',root),patch.object(m,'BUNDLES',root/'bundles'):
                out=m.upload_bundle(session,{'production_main_verified':True})
                self.assertEqual(out.stat().st_mode & 0o077,0)
                with tarfile.open(out,'r:gz') as archive:
                    data=json.load(archive.extractfile('uart1-dma0/bundle-manifest.json'))
                    self.assertEqual(len(data['source_sha256']),4)
                    self.assertFalse(data['p06_rpm_alias_verified'])
                with self.assertRaises(m.Error):
                    m.upload_bundle(session,{})

    def test_gfa_readback_validation(self):
        state={'ActiveState':'active','SubState':'running','WorkingDirectory':'/opt/optolink'}
        p80=subprocess.CompletedProcess([],0,stdout='1;0x4050;20\n',stderr='')
        p06=subprocess.CompletedProcess([],0,stdout='1;0x4006;53\n',stderr='')
        with patch.object(m.h,'unit_state',return_value=state),patch.object(m.subprocess,'run',side_effect=[p80,p06]):
            actual=m.post_restore_health()
        self.assertTrue(actual['gfa_reads']['P80']['format_and_identity_verified'])
        self.assertTrue(actual['gfa_reads']['P06']['format_and_identity_verified'])
        self.assertFalse(actual['ha_entity_freshness_verified'])

    def test_wrong_gfa_identity_refused(self):
        state={'ActiveState':'active','SubState':'running','WorkingDirectory':'/opt/optolink'}
        p80=subprocess.CompletedProcess([],0,stdout='1;0x4050;22\n',stderr='')
        p06=subprocess.CompletedProcess([],0,stdout='1;0x4006;00\n',stderr='')
        with patch.object(m.h,'unit_state',return_value=state),patch.object(m.subprocess,'run',side_effect=[p80,p06]):
            actual=m.post_restore_health()
        self.assertFalse(actual['gfa_reads']['P80']['format_and_identity_verified'])
        self.assertTrue(actual['gfa_reads']['P06']['format_and_identity_verified'])

if __name__=='__main__':
    unittest.main()
