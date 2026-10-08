"""Synthetic P300/status and recovery tests. Never open real serial or systemd."""
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_handover_probe import Clock, Peer

FILE = Path(__file__).resolve().parents[1] / 'tools' / 'wb2a-p87-p300-check.py'
spec = importlib.util.spec_from_file_location('p87_p300', FILE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class StatusPeer(Peer):
    def __init__(self, clock):
        super().__init__(clock)
        self.status_fault = None
        self.values = lambda t: 0 if t < 18 else 0x20 if t < 23 else 0x62
        self.status_times = []
        self.closed = False

    def close(self):
        self.closed = True

    def write(self, data):
        if data != m.STATUS:
            return super().write(data)
        self.sent.append(data)
        assert self.mode == 'p300'
        assert data.hex() == '4105000155d30b39'
        self.status_times.append(self.clock.now())
        value = self.values(self.clock.now())
        payload = bytes(7) + bytes([value]) + bytes(3)
        address, fc, msg, count = b'\x55\xd3', 1, 1, 11
        fault = self.status_fault
        if fault == 'short_write': return 1
        if fault == 'controller_error': msg, count, payload = 3, 1, b'\x05'
        if fault == 'wrong_address': address = b'\x55\xda'
        if fault == 'wrong_function': fc = 3
        if fault == 'wrong_message': msg = 2
        if fault == 'wrong_count': count = 2
        if fault == 'short_payload': payload = payload[:-1]
        if fault == 'ff': payload = b'\xff' * 11
        body = bytes([5+len(payload), msg, fc]) + address + bytes([count]) + payload
        reply = b'\x06\x41' + body + bytes([sum(body) & 255])
        if fault == 'checksum': reply = reply[:-1] + bytes([reply[-1] ^ 1])
        if fault == 'no_ack': reply = b'\x15' + reply[1:]
        if fault == 'no_stx': reply = reply[:1] + b'\x00' + reply[2:]
        if fault == 'ack_flood': reply = b'\x06' * 20 + reply
        if fault == 'repeated_ack': reply = b'\x06\x06' + reply
        if fault == 'oversized': reply = b'\x06\x41\xff'
        if fault == 'trailing': reply += b'\xab'
        if fault == 'truncated': reply = reply[:-1]
        if fault == 'timeout': reply = b''
        self.schedule(.02, reply)
        return len(data)


class WireTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.peer = StatusPeer(self.clock)
        self.wire = m.StatusWire(self.peer, self.clock.now, self.clock.sleep)

    def test_complete_p300_only_and_recovery(self):
        self.assertEqual(self.wire.reference()['P80'], '20')
        start = len(self.peer.sent)
        checks = []
        self.wire.observe(30, lambda row: None, lambda: checks.append(True))
        end = len(self.peer.sent)
        self.assertEqual(len(self.wire.samples), 30)
        entry = self.peer.sent[start:end]
        self.assertEqual(entry.count(b'\x04'), 1)
        self.assertEqual(entry.count(b'\x16\x00\x00'), 1)
        first = entry.index(m.STATUS)
        self.assertTrue(all(x in (m.STATUS, b'\x06') for x in entry[first:]))
        self.assertFalse(any(x in m.h.GFA.values() for x in entry))
        self.assertEqual(m.summarize(self.wire.samples)['outcome'], 'CHANGES_OBSERVED_WITHOUT_EXTERNAL_GFA')
        self.assertGreater(len(checks), 1)
        self.assertEqual(self.wire.restore_link()['P80'], '20')
        self.assertEqual(self.peer.mode, 'vs1')
        self.assertFalse(m.summarize(self.wire.samples)['production_approved'])

    def test_reference_required_without_io(self):
        with self.assertRaises(m.Error):
            self.wire.observe(30, lambda row: None, lambda: None)
        self.assertEqual(self.peer.sent, [])

    def test_phase_tx_allowlists(self):
        forbidden = (bytes.fromhex('410500c94050015f'), b'\x03', b'\xf4',
                     bytes.fromhex('4105000355d30b3b'), b'\xf455d301', b'\x09')
        for phase in ('reference', 'entry', 'observation', 'recovery', 'nonsense'):
            self.wire.phase = phase
            for data in forbidden:
                with self.assertRaises(m.Error): self.wire.send(data)
        self.wire.phase = 'observation'
        for data in (b'\x04', b'\x16\x00\x00', m.h.P300_ID, *m.h.GFA.values()):
            with self.assertRaises(m.Error): self.wire.send(data)
        self.assertEqual(self.peer.sent, [])

    def test_p300_request_checksums(self):
        for request in (m.STATUS, m.h.P300_ID, m.h.P300_SOFTWARE):
            self.assertEqual(sum(request[1:-1]) & 255, request[-1])
            self.assertEqual(request[3], 1)

    def test_fixed_status_only_no_free_reads(self):
        for request, addr, expected in ((m.STATUS, 0x55DA, None), (m.STATUS, 0x55D3, b'\0'*11),
                                        (m.h.P300_ID, 0xF8, None)):
            with self.assertRaises(m.Error): self.wire.p300_read(request, addr, expected)
        self.assertEqual(self.peer.sent, [])

    def test_wrong_controller_or_software_before_p300(self):
        for field in ('controller', 'software', 'p80'):
            with self.subTest(field=field):
                c=Clock(); peer=StatusPeer(c); setattr(peer, field, b'\x7f')
                wire=m.StatusWire(peer, c.now, c.sleep)
                with self.assertRaises(m.Error): wire.reference()
                self.assertNotIn(b'\x16\x00\x00', peer.sent)

    def test_status_faults_abort_no_retry(self):
        faults = ('controller_error','wrong_address','wrong_function','wrong_message','wrong_count',
                  'short_payload','ff','checksum','no_ack','no_stx','ack_flood','oversized',
                  'trailing','truncated','timeout','short_write')
        for fault in faults:
            with self.subTest(fault=fault):
                c=Clock(); peer=StatusPeer(c); wire=m.StatusWire(peer,c.now,c.sleep)
                wire.reference(); peer.status_fault=fault
                with self.assertRaises(m.Error): wire.observe(30,lambda r:None,lambda:None)
                self.assertEqual(peer.sent.count(m.STATUS),1)
                self.assertEqual(wire.samples,[])
                self.assertEqual(wire.restore_link()['P80'],'20')

    def test_repeated_ack_and_fragmented_status(self):
        self.wire.reference(); self.peer.status_fault='repeated_ack'
        self.wire.observe(30,lambda r:None,lambda:None)
        self.assertEqual(len(self.wire.samples),30)
        self.assertTrue(all(len(r['native_block']) == 22 for r in self.wire.samples))

    def test_isolation_failure_before_next_tx(self):
        self.wire.reference()
        checks=[]
        def check():
            checks.append(True)
            if len(checks)>1: raise m.Error('COMPETING_READER')
        with self.assertRaisesRegex(m.Error,'COMPETING_READER'):
            self.wire.observe(30,lambda r:None,check)
        self.assertEqual(self.peer.sent.count(m.STATUS),5)
        self.assertEqual(len(self.wire.samples),5)

    def test_no_catchup_burst_after_slow_check(self):
        self.wire.reference()
        self.wire.observe(30,lambda r:None,lambda:self.clock.sleep(1.2))
        gaps=[b-a for a,b in zip(self.peer.status_times,self.peer.status_times[1:])]
        # A slow check does not produce a burst of overdue scheduled samples.
        self.assertTrue(all(gap >= .99 for gap in gaps),gaps)


class SummaryTests(unittest.TestCase):
    def rows(self, values):
        return [dict(elapsed_s=float(i),native_b7=f'{v:02x}') for i,v in enumerate(values)]

    def test_zero_static_inconclusive(self):
        self.assertEqual(m.summarize(self.rows([0]*40))['outcome'],'INCONCLUSIVE_NO_LATE_STATUS_CHANGE')

    def test_nonzero_static_inconclusive(self):
        self.assertEqual(m.summarize(self.rows([0x62]*40))['confirmed_late_changes'],[])

    def test_entry_only_change_not_counted(self):
        self.assertEqual(m.summarize(self.rows([0]*2+[0x62]*38))['late_changes'],[])

    def test_boundary_change_not_counted(self):
        self.assertEqual(m.summarize(self.rows([0]*10+[0x20]*30))['late_changes'],[])

    def test_late_sustained_change_supported_not_alias(self):
        s=m.summarize(self.rows([0]*20+[0x62]*20))
        self.assertEqual(len(s['confirmed_late_changes']),1)
        self.assertEqual(s['outcome'],'CHANGES_OBSERVED_WITHOUT_EXTERNAL_GFA')
        for key in ('p87_equivalence_verified','acquisition_latency_verified','p06_or_p09_replacement_verified','production_approved'):
            self.assertFalse(s[key])

    def test_last_sample_change_unconfirmed(self):
        s=m.summarize(self.rows([0]*29+[0x20]))
        self.assertEqual(s['outcome'],'INCONCLUSIVE_UNCONFIRMED_CHANGE')

    def test_transient_not_accepted_as_confirmed(self):
        s=m.summarize(self.rows([0]*20+[0x20,0x30]))
        self.assertEqual(s['confirmed_late_changes'],[])

    def test_empty_is_inconclusive(self):
        self.assertEqual(m.summarize([])['outcome'],'INCONCLUSIVE_NO_LATE_STATUS_CHANGE')

    def test_burst_does_not_confirm(self):
        rows=[dict(elapsed_s=t,native_b7=v) for t,v in ((15,'00'),(16,'20'),(16.1,'20'),(16.2,'20'))]
        self.assertEqual(m.summarize(rows)['confirmed_late_changes'],[])


class OrchestrationTests(unittest.TestCase):
    def state(self, seconds=30):
        return dict(seconds=seconds,port='/dev/fake',
                    services={u:True for u in m.h.SERVICES},restore=[])

    def unit_state(self, unit):
        return dict(WorkingDirectory='/opt/optolink',ActiveState='active',SubState='running')

    def test_launcher_stages_before_supervision_without_stopping_services(self):
        state=self.state(30)
        def supervised(args, check):
            session=Path(args[-1])
            saved=json.loads((session/'state.json').read_text())
            self.assertEqual(saved['restore'],[])
            self.assertEqual(saved['helper_sha256'],m.HELPER_SHA256)
            self.assertTrue((session/m.HELPER).is_file())
            m.h.atomic_json(session/'measurement.json',dict(observation_complete=True,
                vs1_link_restored=True,errors=[],comparison={'outcome':'INCONCLUSIVE_NO_LATE_STATUS_CHANGE'}))
            m.h.atomic_json(session/'recovery.json',dict(services_restored=True,errors=[]))
            return subprocess.CompletedProcess(args,0)
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'ROOT',Path(tmp)), \
             patch.object(m,'locks',return_value=contextlib.nullcontext()), \
             patch.object(m.h,'preflight',return_value=({'port_optolink':'/dev/fake'},state['services'])), \
             patch.object(m.h,'unit_state',return_value={'ActiveState':'inactive'}), \
             patch.object(m.subprocess,'run',side_effect=supervised),patch.object(m.h,'pause_services') as pause:
            self.assertEqual(m.launch(30),0);pause.assert_not_called()

    def test_failed_supervision_cannot_report_success(self):
        state=self.state()
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'ROOT',Path(tmp)), \
             patch.object(m,'locks',return_value=contextlib.nullcontext()), \
             patch.object(m.h,'preflight',return_value=({'port_optolink':'/dev/fake'},state['services'])), \
             patch.object(m.h,'unit_state',return_value={'ActiveState':'inactive'}), \
             patch.object(m.subprocess,'run',return_value=subprocess.CompletedProcess([],1)):
            self.assertEqual(m.launch(30),1)

    def test_unresolved_recovery_refuses_new_trial(self):
        state=self.state()
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'ROOT',Path(tmp)), \
             patch.object(m,'locks',return_value=contextlib.nullcontext()), \
             patch.object(m.h,'preflight',return_value=({'port_optolink':'/dev/fake'},state['services'])), \
             patch.object(m.h,'unit_state',return_value={'ActiveState':'inactive'}), \
             patch.object(m.subprocess,'run') as run:
            old=Path(tmp)/'run-old';old.mkdir()
            m.h.atomic_json(old/'state.json',{'restore':[m.h.MAIN]})
            with self.assertRaisesRegex(m.Error,'PREVIOUS_RECOVERY'):m.launch(30)
            run.assert_not_called()

    def test_plan_inert(self):
        p=subprocess.run([sys.executable,str(FILE),'--seconds','30'],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('PLAN ONLY',p.stdout)
        self.assertNotIn('SESSION=',p.stdout)

    def test_seconds_bounds(self):
        for value in (0,29,601,True,'300',1.5):
            with self.assertRaises(m.Error): m.seconds_ok(value)

    def test_internal_modes_refuse_duration_override(self):
        env=dict(os.environ,INVOCATION_ID='test')
        p=subprocess.run([sys.executable,str(FILE),'--worker','/tmp/nope','--seconds','30'],
                         capture_output=True,text=True,env=env)
        self.assertNotEqual(p.returncode,0)

    def test_helper_hash_required(self):
        with patch.object(Path,'read_bytes',return_value=b'fake'):
            with self.assertRaisesRegex(RuntimeError,'PINNED'):m.load_helper()

    def test_supervised_before_worker(self):
        args=m.supervisor_command(Path('/root/p300-trial-work/p87-p300-results/run-test'),300)
        self.assertIn('--property=RuntimeMaxSec=420',args)
        self.assertTrue(any(a.startswith('--property=ExecStopPost=') for a in args))
        self.assertIn('--property=KillMode=control-group',args)
        self.assertIn('--property=TimeoutStopSec=180',args)

    def test_isolation_rejects_active_production(self):
        with patch.object(m.h,'unit_state',side_effect=self.unit_state),patch.object(m.h,'assert_no_owner') as owner:
            with self.assertRaisesRegex(m.Error,'RESTARTED'):m.isolation('/dev/fake')
            owner.assert_not_called()

    def test_isolation_checks_other_owners(self):
        with patch.object(m.h,'unit_state',return_value={'ActiveState':'inactive'}),patch.object(m.h,'assert_no_owner') as owner:
            m.isolation('/dev/fake');owner.assert_called_once()

    def test_worker_status_error_recovers_and_keeps_failure(self):
        c=Clock(); peer=StatusPeer(c); wire=m.StatusWire(peer,c.now,c.sleep)
        peer.status_fault='controller_error'; state=self.state()
        with tempfile.TemporaryDirectory() as tmp, patch.object(m.h.SETTINGS.__class__,'read_text',return_value="vs1protocol=True\nport_vitoconnect=None\nport_optolink='/dev/fake'"), \
             patch.object(m.h,'unit_state',side_effect=self.unit_state),patch.object(m.h,'pause_services') as pause, \
             patch.object(m,'isolation'),patch.object(m.h,'open_serial',return_value=peer), \
             patch.object(m,'StatusWire',return_value=wire),patch.object(m.signal,'signal'):
            rc=m.run_worker(Path(tmp),state)
            report=json.loads((Path(tmp)/'measurement.json').read_bytes())
            self.assertEqual(rc,1);self.assertFalse(report['observation_complete'])
            self.assertTrue(report['vs1_link_restored']);self.assertTrue(peer.closed)
            self.assertIn('55d3',report['errors'][0]);pause.assert_called_once()

    def test_worker_success_records_reference_and_trace(self):
        c=Clock(); peer=StatusPeer(c); wire=m.StatusWire(peer,c.now,c.sleep)
        with tempfile.TemporaryDirectory() as tmp, patch.object(Path,'read_text',return_value="vs1protocol=True\nport_vitoconnect=None\nport_optolink='/dev/fake'"), \
             patch.object(m.h,'unit_state',side_effect=self.unit_state),patch.object(m.h,'pause_services'), \
             patch.object(m,'isolation'),patch.object(m.h,'open_serial',return_value=peer), \
             patch.object(m,'StatusWire',return_value=wire),patch.object(m.signal,'signal'):
            rc=m.run_worker(Path(tmp),self.state())
            report=json.loads((Path(tmp)/'measurement.json').read_bytes())
            self.assertEqual(rc,0);self.assertEqual(report['reference_gfa']['P80'],'20')
            self.assertEqual(report['recovery_gfa']['P80'],'20');self.assertTrue(report['trace'])
            self.assertEqual(len(report['samples']),30)

    def test_worker_changed_settings_before_any_stop(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(Path,'read_text',return_value="vs1protocol=True\nport_vitoconnect=None\nport_optolink='/dev/other'"), \
             patch.object(m.h,'pause_services') as pause, patch.object(m.h,'open_serial') as opened,patch.object(m.signal,'signal'):
            self.assertEqual(m.run_worker(Path(tmp),self.state()),1)
            pause.assert_not_called();opened.assert_not_called()

    def test_worker_signal_recovers(self):
        c=Clock(); peer=StatusPeer(c); wire=m.StatusWire(peer,c.now,c.sleep)
        with tempfile.TemporaryDirectory() as tmp, patch.object(Path,'read_text',return_value="vs1protocol=True\nport_vitoconnect=None\nport_optolink='/dev/fake'"), \
             patch.object(m.h,'unit_state',side_effect=self.unit_state),patch.object(m.h,'pause_services'), \
             patch.object(m,'isolation'),patch.object(m.h,'open_serial',return_value=peer),patch.object(m,'StatusWire',return_value=wire), \
             patch.object(wire,'observe',side_effect=KeyboardInterrupt),patch.object(m.signal,'signal'):
            self.assertEqual(m.run_worker(Path(tmp),self.state()),1)
            report=json.loads((Path(tmp)/'measurement.json').read_bytes())
            self.assertTrue(report['vs1_link_restored']);self.assertTrue(peer.closed)

    def test_restore_main_first_timer_last(self):
        state=self.state();state['restore']=list(m.h.SERVICES)
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'session_state',return_value=state), \
             patch.object(m,'locks',return_value=contextlib.nullcontext()),patch.object(m.h,'command') as cmd, \
             patch.object(m.h,'unit_state',side_effect=self.unit_state),patch.object(m.h,'wait_main_ready'):
            self.assertEqual(m.recover(Path(tmp)),0)
            self.assertEqual(cmd.call_args_list[0].args[0],['systemctl','start',m.h.MAIN])
            self.assertEqual(cmd.call_args_list[-1].args[0],['systemctl','start','optolink-clock-sync.timer'])

    def test_failed_main_defers_all_writers(self):
        state=self.state();state['restore']=list(m.h.SERVICES)
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'session_state',return_value=state), \
             patch.object(m,'locks',return_value=contextlib.nullcontext()),patch.object(m.h,'command') as cmd, \
             patch.object(m.h,'wait_main_ready',side_effect=m.Error('restart loop')):
            self.assertEqual(m.recover(Path(tmp)),1);self.assertEqual(cmd.call_count,1)
            result=json.loads((Path(tmp)/'recovery.json').read_text())
            self.assertFalse(result['services_restored'])

    def test_partial_stop_checks_main_before_writers(self):
        state=self.state();state['restore']=[m.h.SERVICES[0]]
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'session_state',return_value=state), \
             patch.object(m,'locks',return_value=contextlib.nullcontext()),patch.object(m.h,'command') as cmd, \
             patch.object(m.h,'wait_main_ready',side_effect=m.Error('not ready')):
            self.assertEqual(m.recover(Path(tmp)),1);cmd.assert_not_called()

    def test_inactive_services_not_started(self):
        state=self.state();state['restore']=[m.h.MAIN]
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'session_state',return_value=state), \
             patch.object(m,'locks',return_value=contextlib.nullcontext()),patch.object(m.h,'command') as cmd, \
             patch.object(m.h,'unit_state',side_effect=self.unit_state),patch.object(m.h,'wait_main_ready'):
            self.assertEqual(m.recover(Path(tmp)),0);self.assertEqual(cmd.call_count,1)


if __name__ == '__main__': unittest.main()
