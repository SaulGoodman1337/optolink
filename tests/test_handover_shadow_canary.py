"""Offline simulated systemd canary execution, SIGKILL and restore."""
from __future__ import annotations
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from handover_acceleration import shadow_canary as canary


class FakeRollbackTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.session=self.root/"run-20261010T110000Z-555"
        self.session.mkdir()
        self.release=self.root/"release"
        self.release.mkdir()
        self.source={
            canary.MAIN:"[Service]\nMain=patched\n",
            canary.WRITERS[0]:"[Service]\nParty=patched\n",
            canary.WRITERS[1]:"[Service]\nSchedule=patched\n",
        }
        self.state={"release":str(self.release),
                    "installed":{},"phase":"PREPARED",
                    "before":{name:"active" for name in canary.ALL}}
        self.events=[]
        self.contexts=[
            patch.object(canary,"load",side_effect=lambda _:self.state),
            patch.object(canary,"unit_dropins",return_value=self.source),
            patch.object(canary,"dropin",side_effect=self.dropin),
            patch.object(canary,"call",side_effect=self.fake_call),
            patch.object(canary,"status",return_value="active"),
            patch.object(canary,"gfa",return_value={"P80":"20","P06":"00"}),
            patch.object(canary,"clear_p300_after_gfa",return_value=False),
            patch.object(canary,"provision_lock",return_value=self.root/"dummy.lock"),
            patch.object(canary,"provision_serial_lease",return_value=self.root/"serial.lease"),
            patch.object(canary.os,"geteuid",return_value=0),
            patch.object(canary.os,"chown",return_value=None),
            patch.object(canary.time,"sleep",return_value=None),
            patch.dict(os.environ,{"INVOCATION_ID":"fake-supervised"}),
        ]
        for ctx in self.contexts:
            ctx.start()
            self.addCleanup(ctx.stop)

    def dropin(self,unit):
        return self.root/"systemd"/(unit+".d")/canary.DROPIN

    def fake_call(self,args,*a,**kw):
        self.events.append(args)
        return ""

    def test_worker_and_independent_restore_are_symmetric(self):
        self.assertEqual(canary.worker(self.session),0)
        self.assertTrue((self.session/"measurement.json").is_file())
        self.assertEqual(self.state["phase"],"RUNNING_SHADOW_NO_AUTO")
        for unit in self.source:
            self.assertEqual(self.dropin(unit).read_text(),self.source[unit])
        result=canary.recover(self.session)
        self.assertEqual(result,0)
        for unit in self.source:
            self.assertFalse(self.dropin(unit).exists())
        proof=json.loads((self.session/"recovery.json").read_text())
        self.assertEqual(proof["result"],"PASS_ORIGINAL_SERVICES_RESTORED")
        starts=[cmd[-1] for cmd in self.events if cmd[:2]==["systemctl","start"]]
        self.assertGreater(starts.count(canary.MAIN),1)

    def test_crash_before_intent_persistence_still_removes_own_dropins(self):
        target=self.dropin(canary.MAIN)
        target.parent.mkdir(parents=True)
        target.write_text(self.source[canary.MAIN])
        self.assertEqual(self.state["installed"],{})
        self.assertEqual(canary.recover(self.session),0)
        self.assertFalse(target.exists())

    def test_modified_override_refuses_unsafe_writer_restart(self):
        target=self.dropin(canary.MAIN)
        target.parent.mkdir(parents=True)
        target.write_text("DIFFERENT_UNREVIEWED_OVERRIDE")
        self.assertEqual(canary.recover(self.session),1)
        self.assertEqual(target.read_text(),"DIFFERENT_UNREVIEWED_OVERRIDE")
        proof=json.loads((self.session/"recovery.json").read_text())
        self.assertEqual(proof["result"],"FAIL_OR_NOT_VERIFIED")
        self.assertFalse(any(
            args[:2]==["systemctl","start"]
            and args[-1] in canary.WRITERS
            for args in self.events))

    def test_attested_stuck_shadow_requires_exact_pid_executable_and_uid(self):
        from types import SimpleNamespace
        p_root=self.root/'proc'
        target=p_root/'777'
        target.mkdir(parents=True)
        correct=b'\x00'.join((canary.PYTHON.encode(),b'-u',
             str(self.release/'main/optolinkvs2_switch.py').encode()))+b'\x00'
        (target/'cmdline').write_bytes(correct)
        with patch.object(canary,'RELEASES',self.root),\
             patch.object(canary,'PROC_ROOT',p_root),\
             patch.object(canary,'call',return_value='777'),\
             patch.object(canary,'status',return_value='deactivating'),\
             patch.object(canary.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=os.getuid())):
            self.assertEqual(canary._attest_stuck_shadow_main(self.release),777)
            (target/'cmdline').write_bytes(b'/opt/optolink/venv/bin/python\x00-u\x00/opt/optolink/optolinkvs2_switch.py\x00')
            with self.assertRaisesRegex(canary.CanaryRejected,'exact pinned'):
                canary._attest_stuck_shadow_main(self.release)
            (target/'cmdline').write_bytes(correct)
            with patch.object(canary.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=os.getuid()+1)):
                with self.assertRaisesRegex(canary.CanaryRejected,'exact pinned'):
                    canary._attest_stuck_shadow_main(self.release)

    def test_timeout_for_exact_shadow_kills_only_attested_main_then_restores_but_never_passes_canary(self):
        state={'killed':False,'original_started':False}
        def result(cmd,*a,**kw):
            if cmd[:2]==['systemctl','stop'] and cmd[-1]==canary.MAIN:
                raise subprocess.TimeoutExpired(cmd,15)
            if cmd[:2]==['systemctl','kill']:
                self.assertEqual(cmd,['systemctl','kill','--kill-whom=main',
                                      '--signal=SIGKILL',canary.MAIN])
                state['killed']=True
            if cmd[:2]==['systemctl','start'] and cmd[-1]==canary.MAIN:
                state['original_started']=True
            return self.fake_call(cmd,*a,**kw)
        def unit_state(name):
            if name==canary.MAIN and not state['original_started']:
                return 'inactive' if state['killed'] else 'deactivating'
            return 'active'
        with patch.object(canary,'call',side_effect=result),\
             patch.object(canary,'status',side_effect=unit_state),\
             patch.object(canary,'_attest_stuck_shadow_main',return_value=777):
            rc=canary.recover(self.session)
        self.assertEqual(rc,1)
        self.assertTrue(state['killed'])
        self.assertTrue(state['original_started'])
        report=json.loads((self.session/'recovery.json').read_text())
        self.assertEqual(report['errors'],[])
        self.assertTrue(report['warnings'])
        self.assertEqual(report['result'],'RESTORED_WITH_VERIFIED_FORCE_STOP_NOT_CANARY_PASS')
        self.assertIn('original_gfa_confirmed',report['actions'])
        self.assertIn('cleared_failed_main_state_before_original_restart',report['actions'])
        self.assertTrue(any(x[:2]==['systemctl','reset-failed'] and x[-1]==canary.MAIN
                            for x in self.events))
        self.assertTrue(any(x.startswith('exact_shadow_main_force_stopped_after_timeout:')
                            for x in report['actions']))

    def test_unknown_main_pid_stop_timeout_must_never_kill_or_restart(self):
        def result(cmd,*a,**kw):
            if cmd[:2]==['systemctl','stop'] and cmd[-1]==canary.MAIN:
                raise subprocess.TimeoutExpired(cmd,15)
            return self.fake_call(cmd,*a,**kw)
        with patch.object(canary,'call',side_effect=result),\
             patch.object(canary,'status',return_value='deactivating'),\
             patch.object(canary,'_attest_stuck_shadow_main',
                          side_effect=canary.CanaryRejected('not exact pinned shadow')):
            self.assertEqual(canary.recover(self.session),1)
        report=json.loads((self.session/'recovery.json').read_text())
        self.assertEqual(report['result'],'FAIL_OR_NOT_VERIFIED')
        self.assertTrue(any('not exact pinned shadow' in x for x in report['errors']))
        self.assertFalse(any(x[:2] in (['systemctl','kill'],['systemctl','start'])
                             for x in self.events))

    def test_timeout_and_already_stopped_unit_does_not_force_kill(self):
        state={'started':False}
        def result(cmd,*a,**kw):
            if cmd[:2]==['systemctl','stop'] and cmd[-1]==canary.MAIN:
                raise subprocess.TimeoutExpired(cmd,15)
            if cmd[:2]==['systemctl','start'] and cmd[-1]==canary.MAIN:
                state['started']=True
            return self.fake_call(cmd,*a,**kw)
        with patch.object(canary,'call',side_effect=result),\
             patch.object(canary,'status',side_effect=lambda name:
                          'active' if state['started'] else 'inactive'):
            self.assertEqual(canary.recover(self.session),1)
        report=json.loads((self.session/'recovery.json').read_text())
        self.assertEqual(report['result'],'RESTORED_WITH_VERIFIED_FORCE_STOP_NOT_CANARY_PASS')
        self.assertFalse(any(x[:2]==['systemctl','kill'] for x in self.events))
        self.assertTrue(state['started'])

    def test_no_worker_outside_root_owned_systemd(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaisesRegex(canary.CanaryRejected,"supervised"):
                canary.worker(self.session)

    def test_real_canary_never_auto_switches_during_diagnostic_phase(self):
        canary.worker(self.session)
        for content in self.source.values():
            self.assertNotIn("fenced-readonly",content)
        self.assertEqual(json.loads((self.session/"measurement.json").read_text())
                         ["status"],"SHADOW_DIAGNOSTIC_PASS_NO_P300")


class SerialLeaseProvisionTests(unittest.TestCase):
    def setUp(self):
        from types import SimpleNamespace
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"serial.lease"
        self.mocks=[
            patch.object(canary,"SERIAL_LEASE",self.path),
            patch("pwd.getpwnam",return_value=SimpleNamespace(pw_uid=os.getuid())),
            patch("grp.getgrnam",return_value=SimpleNamespace(gr_gid=os.getgid())),
            patch.object(canary.os,"fchown",return_value=None),
        ]
        for handle in self.mocks:
            handle.start()
            self.addCleanup(handle.stop)

    def test_creates_owner_only_serial_lease_then_idempotently_checks(self):
        import stat
        self.assertEqual(canary.provision_serial_lease(),self.path)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode),0o600)
        self.assertEqual(self.path.stat().st_size,0)
        self.assertEqual(canary.provision_serial_lease(),self.path)

    def test_refuses_symlink_loose_permissions_and_nonempty_lock(self):
        outside=Path(self.tmp.name)/"outside"
        outside.write_bytes(b"unchanged")
        self.path.symlink_to(outside)
        with self.assertRaises(canary.CanaryRejected):
            canary.provision_serial_lease()
        self.path.unlink()
        self.path.write_bytes(b"")
        self.path.chmod(0o666)
        with self.assertRaisesRegex(canary.CanaryRejected,"unsafe"):
            canary.provision_serial_lease()
        self.path.chmod(0o600)
        self.path.write_bytes(b"foreign")
        with self.assertRaisesRegex(canary.CanaryRejected,"unsafe"):
            canary.provision_serial_lease()


if __name__=="__main__":
    unittest.main()
