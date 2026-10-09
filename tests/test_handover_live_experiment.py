"""Opt-in early P300 START supervised worker tests. All inputs are mocks."""
from pathlib import Path
import contextlib
import json
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
# The pinned recovery helper is provided on GitHub. Local developer source
# trees may instead use the stub established by test_handover_live_probe.
import test_handover_live_probe  # noqa: F401
from handover_acceleration import live_probe as m
from handover_acceleration.coordinator import GFA
from test_handover_acceleration import FakePort, expect_vs1
from test_handover_early_start import speculative_early_start


class EarlyStartLiveAdapterTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.session=Path(tmp.name)
        self.state={'port':'/dev/NOT_A_DEVICE', 'services':{m.base.MAIN:True},
                    'restore':[],'source_sha256':{'dummy':'none'},
                    'experiment':'early_p300_start'}
        self.fake_port=None
        stack=contextlib.ExitStack()
        self.addCleanup(stack.close)
        def replace(target,name,value):
            stack.enter_context(patch.object(target,name,value,create=True))
        replace(m,'verify_session',lambda session:self.state)
        replace(m,'guard_other_research',lambda *args,**kwargs:None)
        replace(m.base,'read_settings',lambda _:{'port_optolink':self.state['port']})
        replace(m.base,'SETTINGS',types.SimpleNamespace(read_text=lambda:'safe-settings'))
        replace(m.base,'unit_state',lambda unit:{'WorkingDirectory':'/opt/optolink',
                            'ActiveState':'active' if unit==m.base.MAIN else 'inactive'})
        replace(m.base,'pause_services',lambda *a,**kw:None)
        replace(m.base,'assert_no_owner',lambda _:None)
        replace(m.base,'open_serial',lambda _:self.fake_port)
        replace(m.base,'atomic_json',lambda p,v:p.write_text(json.dumps(v)))
        replace(m.base,'locks',lambda:contextlib.nullcontext())

    def test_synthetic_early_worker_ack_identity_then_verified_vs1(self):
        self.fake_port=FakePort(expect_vs1(2)+speculative_early_start()+
                                expect_vs1(1)+[(GFA['P09'],b'\x00'),
                                               (GFA['P87'],b'\x00')])
        with patch.object(m,'PortLease'):
            self.assertEqual(m.worker(self.session),0)
        data=json.loads((self.session/'measurement.json').read_text())
        self.assertTrue(data['experiment_pass'])
        self.assertIn(['p300_early_start','verified'],data['history'])
        self.assertEqual(data['gfa']['P06'],'00')
        self.assertEqual(len(data['enq_trace']),3)
        self.assertEqual(data['enq_trace'][1]['enq_wait_ms'],[])
        self.assertTrue(self.fake_port.closed)
        self.assertEqual(self.fake_port.script,[])

    def test_synthetic_early_worker_nack_fails_then_restores_vs1(self):
        self.fake_port=FakePort(expect_vs1(2)+[(b'\x04',b''),
                                    (b'\x16\x00\x00',b'\x15')]+expect_vs1(2))
        with patch.object(m,'PortLease'):
            self.assertEqual(m.worker(self.session),1)
        data=json.loads((self.session/'measurement.json').read_text())
        self.assertFalse(data['experiment_pass'])
        self.assertIn(['p300_early_start','failed'],data['history'])
        self.assertTrue(self.fake_port.closed)
        self.assertFalse(self.fake_port.script)

    def test_unknown_experiment_denied_before_pause(self):
        self.state['experiment']='freeform_writer'
        with patch.object(m.base,'pause_services',
                          side_effect=AssertionError('MUST_NOT_STOP')):
            with self.assertRaisesRegex(m.base.ProbeError,'unknown experiment'):
                m.worker(self.session)

    def test_cli_requires_explicit_opt_in_both_flags(self):
        with patch.object(sys,'argv',['live_probe.py','--experiment-early-p300-start']):
            with patch.object(m,'execute',side_effect=AssertionError('MUST_NOT_EXECUTE')):
                with self.assertRaisesRegex(m.base.ProbeError,'requires --execute'):
                    m.main()
        with patch.object(sys,'argv',['live_probe.py','--execute',
                                      '--experiment-early-p300-start',
                                      '--accept-telemetry-pause']):
            with patch.object(m,'execute',return_value=0) as ex:
                self.assertEqual(m.main(),0)
                ex.assert_called_once_with(experiment='early_p300_start')

if __name__=='__main__':
    unittest.main()
