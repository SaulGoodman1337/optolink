"""Supervisor lifecycle contract exercised with fake services, no hardware."""
import contextlib
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from handover_acceleration import hybrid_acceptance as h
from test_handover_hybrid_acceptance import HybridAcceptanceTests


class SupervisionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.session=Path(self.temp.name)
        self.work=Path('/opt/optolink')
        self.events=[]
        # Unit tests never take root-owned global locks or stop real services.
        lease_patch=patch.object(h,'pump_lease',lambda:contextlib.nullcontext())
        lease_patch.start()
        self.addCleanup(lease_patch.stop)
        self.state={'port':'/dev/fake_opto',
                    'services':{'optolink-splitter.service':True,'opto-maint.service':False},
                    'source_sha256':{}}
        self.base=types.SimpleNamespace(
            MAIN='optolink-splitter.service',
            SETTINGS=self.session/'settings.ini',
            PYTHON='/opt/optolink/venv/bin/python',
            locks=lambda:contextlib.nullcontext(),
            read_settings=lambda _: {'port_optolink':'/dev/fake_opto'},
            unit_state=lambda unit: {'WorkingDirectory':'/opt/optolink',
                                      'ActiveState':('active' if unit=='optolink-splitter.service' else 'inactive'),
                                      'SubState':('running' if unit=='optolink-splitter.service' else 'dead')},
            assert_no_owner=lambda port:self.events.append(('no_owner',port)),
            pause_services=lambda session,state:self.events.append(('paused',state['services'])),
            atomic_json=lambda path,record:path.write_text(json.dumps(record)),
        )
        self.base.SETTINGS.write_text('safe config fake')
        self.live=types.SimpleNamespace(
            base=self.base,verify_session=lambda _:self.state,
            guard_other_research=lambda:self.events.append(('guard',)),
            preflight=lambda:({'port_optolink':'/dev/fake_opto'},self.state['services']),
            snapshot=lambda path,values,services,experiment:path.mkdir(mode=0o700),
            read_health=lambda:{'P80':{'valid':True},'P06':{'valid':True}}
        )

    def good_worker_run(self,*args,**kwargs):
        self.events.append(('subprocess',tuple(args[0]),kwargs.get('cwd')))
        report=HybridAcceptanceTests.good_boot()
        (self.session/'hybrid-result.json').write_text(json.dumps(report))
        return types.SimpleNamespace(returncode=0)

    def test_worker_stops_services_only_after_static_verify_and_restarts_through_supervisor(self):
        with patch.object(h,'_live',return_value=self.live),\
             patch.object(h,'verify_stage',side_effect=lambda s,root:self.events.append(('stage_verified',))),\
             patch.object(h.subprocess,'run',side_effect=self.good_worker_run),\
             patch.object(h,'ROOT',self.work):
            self.assertEqual(h.worker(self.session),0)
        result=json.loads((self.session/'measurement.json').read_text())
        self.assertTrue(result['experiment_pass'])
        self.assertTrue(result['verified_boot_result'])
        self.assertFalse(result['vs1_link_restored'])
        self.assertEqual([x[0] for x in self.events[:4]],
                         ['stage_verified','guard','paused','guard'])
        worker_cmd=next(x[1] for x in self.events if x[0]=='subprocess')
        self.assertTrue(worker_cmd[2].endswith('optolinkvs2_switch.py'))
        self.assertIn(('no_owner','/dev/fake_opto'),self.events)

    def test_active_pump_daemon_refused_before_any_service_pause(self):
        original = self.base.unit_state
        self.base.unit_state = lambda unit: (
            {'ActiveState': 'active'} if unit == 'optolink-pump-override.service'
            else original(unit))
        with patch.object(h, '_live', return_value=self.live), \
             patch.object(h, 'verify_stage', return_value={}):
            self.assertEqual(h.worker(self.session), 1)
        report=json.loads((self.session/'measurement.json').read_text())
        self.assertIn('pump override must be stopped', report['errors'][0])
        self.assertFalse(any(row[0] == 'paused' for row in self.events))

    def test_active_pump_blocks_supervisor_before_staging_or_systemd(self):
        original = self.base.unit_state
        self.base.unit_state = lambda unit: (
            {'ActiveState': 'active'} if unit == 'optolink-pump-override.service'
            else original(unit))
        with patch.object(h, '_live', return_value=self.live), \
             patch.object(h, '_verify_original', return_value={}), \
             patch.object(h, 'stage', side_effect=AssertionError('no stage')), \
             patch.object(h.subprocess, 'run',
                          side_effect=AssertionError('no systemd')), \
             patch.object(h.os, 'geteuid', return_value=0), \
             patch.object(h, 'BASE', self.session):
            with self.assertRaisesRegex(Exception, 'pump override must be stopped'):
                h.execute()
        self.assertFalse(self.events)

    def test_worker_bad_result_exits_with_failure_and_writes_evidence(self):
        def invalid_run(*args,**kwargs):
            (self.session/'hybrid-result.json').write_text('{"status":"PASS"}')
            return types.SimpleNamespace(returncode=0)
        with patch.object(h,'_live',return_value=self.live),\
             patch.object(h,'verify_stage',return_value={}),\
             patch.object(h.subprocess,'run',side_effect=invalid_run):
            self.assertEqual(h.worker(self.session),1)
        result=json.loads((self.session/'measurement.json').read_text())
        self.assertFalse(result['experiment_pass'])
        self.assertFalse(result['verified_boot_result'])
        self.assertTrue(result['errors'])

    def test_worker_refuses_changed_source_before_any_service_pause(self):
        with patch.object(h,'_live',return_value=self.live),\
             patch.object(h,'verify_stage',side_effect=h.AcceptanceRejected('hash')):
            self.assertEqual(h.worker(self.session), 1)
        errors=json.loads((self.session/'measurement.json').read_text())['errors']
        self.assertIn('hash', errors[0])
        self.assertFalse(self.events)

    def test_worker_p300_subprocess_timeout_fails_closed_for_execstoppost(self):
        def timed_out(*args,**kwargs):
            import subprocess
            raise subprocess.TimeoutExpired(args[0],timeout=75)
        with patch.object(h,'_live',return_value=self.live),\
             patch.object(h,'verify_stage',return_value={}),\
             patch.object(h.subprocess,'run',side_effect=timed_out):
            self.assertEqual(h.worker(self.session),1)
        record=json.loads((self.session/'measurement.json').read_text())
        self.assertIn('TimeoutExpired',record['errors'][0])
        self.assertFalse(record['experiment_pass'])

    def test_worker_service_preflight_mismatch_never_pauses(self):
        self.base.unit_state=lambda _: {'WorkingDirectory':'/bad','ActiveState':'active'}
        with patch.object(h,'_live',return_value=self.live),\
             patch.object(h,'verify_stage',return_value={}):
            self.assertEqual(h.worker(self.session),1)
        self.assertFalse(any(x[0]=='paused' for x in self.events))

    def test_previous_unverified_production_state_blocks_any_new_hardware_run(self):
        # A previous test exited in 154ms without recovery proof. Do not
        # suspend the original services unless live P80 and P06 pass now.
        self.live.read_health = lambda: {
            'P80': {'valid': True, 'response': '1;0x4050;20'},
            'P06': {'valid': False, 'response': '1;0x4006;ff'}}
        with patch.object(h, '_live', return_value=self.live), \
             patch.object(h, '_verify_original', return_value={}), \
             patch.object(h, 'stage', side_effect=AssertionError('must not stage')), \
             patch.object(h.subprocess, 'run', side_effect=AssertionError('must not execute')), \
             patch.object(h.os, 'geteuid', return_value=0):
            with self.assertRaisesRegex(h.AcceptanceRejected, 'no services stopped'):
                h.execute()
        self.assertFalse(self.events)

    def test_staged_worker_smoke_failure_prevents_systemd_and_pause(self):
        # Systemd must never start if the independently launched staged
        # Python process would reject the session or its original source.
        with patch.object(h, '_live', return_value=self.live), \
             patch.object(h, '_verify_original', return_value={}), \
             patch.object(h, 'stage', return_value={}), \
             patch.object(h, 'run_staged_preflight',
                          side_effect=h.AcceptanceRejected('invalid session path')), \
             patch.object(h.subprocess, 'run', side_effect=AssertionError('must not start unit')), \
             patch.object(h, 'BASE', self.session), \
             patch.object(h.os, 'geteuid', return_value=0):
            with self.assertRaisesRegex(h.AcceptanceRejected, 'invalid session path'):
                h.execute()
        self.assertFalse(self.events)

    def test_execute_creates_only_supervised_systemd_and_independent_recovery(self):
        invocation={}
        def fake_stage(session, root):
            invocation['stage']=session
        def fake_systemd_run(argv,**kwargs):
            invocation['argv']=argv
            session=invocation['stage']
            (session/'measurement.json').write_text(json.dumps({
                'experiment_pass':True,'verified_boot_result':True}))
            (session/'recovery.json').write_text(json.dumps({
                'services_restored':True,'overall_verified':True,
                'independent_link_restore':{'verified':True}}))
            (session/'hybrid-result.json').write_text(json.dumps(HybridAcceptanceTests.good_boot()))
            return types.SimpleNamespace(returncode=0)
        with patch.object(h,'_live',return_value=self.live),\
             patch.object(h,'_verify_original',return_value={'shadow_source_copy_supported':True}),\
             patch.object(h,'stage',side_effect=fake_stage),\
             patch.object(h,'run_staged_preflight',return_value=None),\
             patch.object(h.subprocess,'run',side_effect=fake_systemd_run),\
             patch.object(h,'BASE',self.session),\
             patch.object(h.os,'geteuid',return_value=0):
            self.assertEqual(h.execute(),0)
        argv=' '.join(invocation['argv'])
        self.assertIn('systemd-run --unit='+h.UNIT,argv)
        self.assertIn('--property=ExecStopPost=',argv)
        self.assertIn('--recover',argv)
        self.assertIn('--worker',argv)
        self.assertNotIn('/dev/ttyUSB',argv)
        self.assertFalse(any(x[0]=='paused' for x in self.events))

    def test_supervisor_success_cannot_mask_missing_actual_boot_record(self):
        def fake_systemd_run(*args,**kwargs):
            session=next(self.session.glob('run-inprocess-*'))
            (session/'measurement.json').write_text(json.dumps({
                'experiment_pass':True,'verified_boot_result':True}))
            (session/'recovery.json').write_text(json.dumps({
                'services_restored':True,'overall_verified':True}))
            return types.SimpleNamespace(returncode=0)
        with patch.object(h,'_live',return_value=self.live),\
             patch.object(h,'_verify_original',return_value={}),\
             patch.object(h,'stage',return_value={}),\
             patch.object(h,'run_staged_preflight',return_value=None),\
             patch.object(h.subprocess,'run',side_effect=fake_systemd_run),\
             patch.object(h,'BASE',self.session),\
             patch.object(h.os,'geteuid',return_value=0):
            self.assertEqual(h.execute(),1)
        summary=json.loads(next(self.session.glob('run-inprocess-*/hybrid-summary.json')).read_text())
        self.assertFalse(summary['boot_record_verified'])
        self.assertEqual(summary['phase_ms'],{})

    def test_post_restore_gfa_health_failure_rejects_success(self):
        def fake_systemd_run(*args,**kwargs):
            session=next(self.session.glob('run-inprocess-*'))
            (session/'measurement.json').write_text(json.dumps({
                'experiment_pass':True,'verified_boot_result':True}))
            (session/'recovery.json').write_text(json.dumps({
                'services_restored':True,'overall_verified':True}))
            (session/'hybrid-result.json').write_text(json.dumps(HybridAcceptanceTests.good_boot()))
            # Only the post-run health fails; pre-run production check succeeds.
            self.live.read_health=lambda:{'P80':{'valid':True},'P06':{'valid':False}}
            return types.SimpleNamespace(returncode=0)
        with patch.object(h,'_live',return_value=self.live),\
             patch.object(h,'_verify_original',return_value={}),\
             patch.object(h,'stage',return_value={}),\
             patch.object(h,'run_staged_preflight',return_value=None),\
             patch.object(h.subprocess,'run',side_effect=fake_systemd_run),\
             patch.object(h,'BASE',self.session),\
             patch.object(h.os,'geteuid',return_value=0):
            self.assertEqual(h.execute(),1)
        summary=json.loads(next(self.session.glob('run-inprocess-*/hybrid-summary.json')).read_text())
        self.assertEqual(summary['result'],'FAIL_OR_NOT_VERIFIED')


if __name__=='__main__':unittest.main()
