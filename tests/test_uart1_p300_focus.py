"""Read-only, simulated P300 UART1-DMA0 RAM focus observer regression tests.

All device, service and serial communication is faked. These tests must never
contact a physical heater, USB port or MQTT broker.
"""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_handover_probe import Clock, Peer

FILE = Path(__file__).resolve().parents[1] / 'tools' / 'wb2a-uart1-p300-focus.py'
spec = importlib.util.spec_from_file_location('uart1_p300_focus', FILE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class UART1Peer(Peer):
    def __init__(self, clock):
        super().__init__(clock)
        self.ram_fault = None
        self.nfocus = 0
        self.close_called = False
        self.physical_values = None

    def close(self):
        self.close_called = True

    def write(self, data):
        if data not in (m.STATUS, m.RAM0, m.RAM1):
            return super().write(data)
        self.sent.append(data)
        assert self.mode == 'p300'
        assert (sum(data[1:-1]) & 255) == data[-1]
        address = data[4:6]
        fc = 1 if data == m.STATUS else 3
        count = 11 if data == m.STATUS else 32
        if data == m.STATUS:
            payload = bytearray(11)
            payload[7] = 0x20 if self.clock.now() < 18 else 0x62
        elif data == m.RAM0:
            payload = bytearray(32)
            payload[27] = self.nfocus & 0xFF
            self.nfocus += 1
        else:
            payload = bytearray([0xA0] * 32)
        if self.physical_values is not None and data in (m.RAM0, m.RAM1):
            payload[:] = self.physical_values[data]
        fault = self.ram_fault
        msg=1
        if fault == 'wrong_address': address = b'\x16\x40'
        if fault == 'wrong_function': fc = (1 if fc == 3 else 3)
        if fault == 'controller_error': msg, count, payload = 3, 1, bytearray(b'\x05')
        if fault == 'wrong_count': count = 2
        if fault == 'short_payload': payload = payload[:-1]
        body=bytes([5+len(payload),msg,fc])+address+bytes([count])+bytes(payload)
        reply = b'\x06\x41'+body+bytes([sum(body) & 0xFF])
        if fault == 'checksum': reply=reply[:-1]+bytes([reply[-1]^1])
        if fault == 'no_ack': reply=b'\x15'+reply[1:]
        if fault == 'no_stx': reply=reply[:1]+b'\x00'+reply[2:]
        if fault == 'oversized': reply=b'\x06\x41\xff'
        if fault == 'truncated': reply=reply[:-1]
        if fault == 'extra': reply+=b'\xfe'
        if fault == 'timeout': reply=b''
        self.schedule(0.020,reply)
        return len(data)


class WireTests(unittest.TestCase):
    def setUp(self):
        self.clock=Clock()
        self.peer=UART1Peer(self.clock)
        self.wire=m.UART1Wire(self.peer,self.clock.now,self.clock.sleep)

    def to_observation(self):
        ref=self.wire.reference()
        self.assertEqual(ref['P80'],'20')
        self.wire.phase='entry'
        entry=self.wire.enter_p300()
        self.wire.phase='observation'
        return entry

    def test_bounded_frames_have_correct_checksum(self):
        self.assertEqual(m.RAM0.hex(),'410500031600203e')
        self.assertEqual(m.RAM1.hex(),'410500031620205e')
        for frame in (m.RAM0,m.RAM1,m.STATUS):
            self.assertEqual(sum(frame[1:-1]) & 255,frame[-1])
        self.assertEqual([addr for _,addr in m.RAM_READS],[0x1600,0x1620])

    def test_full_read_only_observation_and_restore(self):
        ref=self.wire.reference()
        self.assertEqual(ref['P80'],'20')
        self.wire.observe(30,lambda _:None,lambda:None)
        summary=m.summarize(self.wire.samples)
        self.assertGreaterEqual(summary['sample_count'],5)
        self.assertEqual(summary['observed_dma_source_changed'],len(self.wire.samples)-1)
        self.assertEqual(summary['changed_byte_count'],1)
        self.assertFalse(summary['uart1_gfa_link_verified'])
        self.assertFalse(summary['p06_rpm_alias_verified'])
        self.assertFalse(summary['production_approved'])
        self.assertEqual(self.wire.restore_link()['P80'],'20')
        sent=self.peer.sent
        self.assertIn(m.RAM0,sent)
        self.assertIn(m.RAM1,sent)
        self.assertIn(m.STATUS,sent)
        self.assertEqual(sent.count(m.RAM0),sent.count(m.RAM1))
        self.assertEqual(sent.count(m.STATUS),sent.count(m.RAM1))
        self.assertFalse(any(packet.startswith(b'\x41') and packet[3] not in (1,3)
                             for packet in sent))
        self.assertTrue(all(packet in (m.RAM0,m.RAM1,m.STATUS,m.h.P300_ID,
                       m.h.P300_SOFTWARE,b'\x04',b'\x16\x00\x00',b'\x06',
                       b'\x01'+m.h.VS1_ID,m.h.VS1_ID,m.h.VS1_SOFTWARE,
                       *m.h.GFA.values()) for packet in sent))

    def test_correct_ram_data_and_time(self):
        self.to_observation()
        a=self.wire.p300_read(m.RAM0,0x1600,None)
        b=self.wire.p300_read(m.RAM1,0x1620,None)
        self.assertEqual(len(a),32)
        self.assertEqual(a[27],0)
        self.assertEqual(b,bytes([0xA0])*32)

    def test_all_ff_ram_is_valid_data_not_magic_ff(self):
        self.to_observation()
        self.peer.physical_values={m.RAM0:bytes([255])*32,m.RAM1:bytes([255])*32}
        self.assertEqual(self.wire.p300_read(m.RAM0,0x1600,None),bytes([255])*32)
        self.assertEqual(self.wire.p300_read(m.RAM1,0x1620,None),bytes([255])*32)

    def test_phase_allowlist_forbids_nonfocus_physical(self):
        self.wire.phase='observation'
        other=bytes.fromhex('410500031640201e')  # deliberately not allowlisted
        for packet in (other,b'\x04',m.h.P300_ID,m.h.GFA['P80'],
                       bytes.fromhex('f423060115'),bytes.fromhex('410500c94050015f')):
            with self.subTest(packet=packet.hex()):
                with self.assertRaisesRegex(m.Error,'TX_FORBIDDEN'):
                    self.wire.send(packet)
        self.assertEqual(self.peer.sent,[])

    def test_fixed_read_parameters_must_match_exactly(self):
        self.to_observation()
        for request,addr,expected in ((m.RAM0,0x1640,None),
                  (m.RAM0,0x1600,b'\0'*32), (m.RAM1,0x1601,None),
                  (m.STATUS,0x1600,None), (m.h.P300_ID,0x00F8,None)):
            with self.subTest(request=request,addr=addr):
                with self.assertRaisesRegex(m.Error,'NOT_A_FIXED_P300_READ'):
                    self.wire.p300_read(request,addr,expected)

    def test_own_write_never_accepts_new_protocol_phase(self):
        for phase in ('reference','entry','recovery','garbage'):
            self.wire.phase=phase
            with self.assertRaises(m.Error):
                self.wire.send(m.RAM0)
            with self.assertRaises(m.Error):
                self.wire.send(m.RAM1)
        self.assertEqual(self.peer.sent,[])

    def test_status_ff_rejected_but_ram_ff_allowed(self):
        self.to_observation()
        self.peer.physical_values={m.RAM0:bytes([255])*32,m.RAM1:bytes([255])*32}
        self.assertEqual(self.wire.p300_read(m.RAM1,0x1620,None),bytes([255])*32)
        self.assertEqual(self.wire.p300_read(m.STATUS,0x55D3,None)[7],0x20)

    def test_physical_reply_faults_fail_closed(self):
        for fault in ('wrong_address','wrong_function','wrong_count','short_payload',
                      'controller_error','checksum','no_ack','no_stx',
                      'oversized','truncated','extra','timeout'):
            with self.subTest(fault=fault):
                self.setUp()
                self.to_observation()
                self.peer.ram_fault=fault
                with self.assertRaises(m.Error):
                    self.wire.p300_read(m.RAM0,0x1600,None)

    def test_failed_ram_read_still_allows_vs1_restore(self):
        self.to_observation()
        self.peer.ram_fault='checksum'
        with self.assertRaisesRegex(m.Error,'P300_CHECKSUM_INVALID'):
            self.wire.p300_read(m.RAM0,0x1600,None)
        self.peer.ram_fault=None
        result=self.wire.restore_link()
        self.assertEqual(result['P80'],'20')

    def test_all_zero_ram_is_inconclusive(self):
        rows=[{'ram_1600':'00'*32,'ram_1620':'00'*32,
               'native_b7':'20','elapsed_s':i*2} for i in range(6)]
        result=m.summarize(rows)
        self.assertEqual(result['outcome'],'NO_CHANGES_IN_UART1_FOCUS')
        self.assertEqual(result['changed_byte_count'],0)
        self.assertFalse(result['production_approved'])

    def test_only_dma_pointer_byte_change(self):
        a='00'*32
        b=(bytes([0])*27+b'\x01'+bytes([0])*4).hex()
        rows=[{'ram_1600':a,'ram_1620':'00'*32,'native_b7':'20','elapsed_s':1},
              {'ram_1600':b,'ram_1620':'00'*32,'native_b7':'62','elapsed_s':2}]
        result=m.summarize(rows)
        self.assertEqual(result['changed_byte_count'],1)
        self.assertEqual(result['changed_address_counts'],{'0x161b':1})
        self.assertEqual(result['native_p87_changes'][0]['before'],'20')
        self.assertFalse(result['p06_rpm_alias_verified'])

    def test_nonmatching_sample_lengths_rejected(self):
        with self.assertRaisesRegex(m.Error,'SAMPLE_RAM_LENGTH_INVALID'):
            m.summarize([{'ram_1600':'ab','ram_1620':'00'*32,
                          'native_b7':'00','elapsed_s':1}])

    def test_invalid_duration_rejected(self):
        for duration in (0,1,29,181,600,True,None):
            with self.assertRaises(m.Error):
                m.seconds_ok(duration)
        self.assertEqual(m.seconds_ok(30),30)
        self.assertEqual(m.seconds_ok(180),180)

    def test_minimum_2s_interval_observed(self):
        self.wire.reference()
        self.wire.observe(30,lambda _:None,lambda:None)
        rows=self.wire.samples
        self.assertGreaterEqual(len(rows),4)
        for r0,r1 in zip(rows,rows[1:]):
            self.assertGreaterEqual(r1['elapsed_s']-r0['elapsed_s'],m.INTERVAL)


class OrchestrationTests(unittest.TestCase):
    def test_cli_default_is_inert_and_bounded(self):
        p=subprocess.run([sys.executable,str(FILE)],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('PLAN ONLY: 60s',p.stdout)
        self.assertIn('1600/32, 1620/32',p.stdout)
        self.assertNotIn('SESSION=',p.stdout)

    def test_bad_duration_fails_without_starting_worker(self):
        p=subprocess.run([sys.executable,str(FILE),'--seconds','600'],
                         capture_output=True,text=True)
        self.assertNotEqual(p.returncode,0)
        self.assertIn('REFUSED_OR_FAILED',p.stderr)
        self.assertNotIn('SESSION=',p.stdout)

    def test_systemd_supervision_and_exec_stop_post(self):
        session=m.ROOT/'run-test'
        cmd=m.supervisor_command(session,60)
        self.assertEqual(cmd[0],'systemd-run')
        self.assertIn('--property=RuntimeMaxSec=180',cmd)
        self.assertIn('--property=KillMode=control-group',cmd)
        self.assertTrue(any('ExecStopPost=' in p and '--recover' in p for p in cmd))
        self.assertTrue(cmd[-2:]==['--worker',str(session)])

    def test_worker_and_recovery_require_systemd(self):
        p=subprocess.run([sys.executable,str(FILE),'--worker','/tmp/not-ours'],
                         capture_output=True,text=True)
        self.assertNotEqual(p.returncode,0)

    def test_verified_helper_sha_is_pinned(self):
        self.assertEqual(m.HELPER_SHA256,
            'e419e0a32206a7398edadff2cb1f5f57ac1884df6532ee26c3b3e75e38cd1269')
        self.assertTrue(m.load_helper())

    def test_session_root_and_unit_do_not_clash(self):
        self.assertNotEqual(m.ROOT,Path('/root/p300-trial-work/p87-p300-results'))
        self.assertNotEqual(m.UNIT,'optolink-p87-p300-check.service')
        self.assertIn('uart1',m.UNIT)

    def test_invalid_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as d,patch.object(m,'ROOT',Path(d)):
            session=Path(d)/'run-test'
            session.mkdir(mode=0o700)
            state={'seconds':60,'services':{k:True for k in m.h.SERVICES},
                   'restore':[m.h.MAIN,'not-an-allowed-service']}
            m.h.atomic_json(session/'state.json',state)
            with self.assertRaises(m.Error):
                m.session_state(session)

    def test_launch_refuses_concurrent_status_observer(self):
        # All production and heater I/O mocked; test only preflight.
        with patch.object(m,'locks',return_value=contextlib.nullcontext()), \
             patch.object(m.h,'preflight',return_value=({'port_optolink':'/dev/test'},
                    {k: k==m.h.MAIN for k in m.h.SERVICES})), \
             patch.object(m.h,'unit_state',side_effect=lambda u: {
                 'ActiveState':'active' if u=='optolink-p87-p300-check.service'
                     else 'inactive'}), \
             patch.object(m,'ROOT',Path('/a/nonexistent/test-parent')), \
             patch.object(m.subprocess,'run') as run:
            with self.assertRaisesRegex(m.Error,'COMPETING_PROBE_ACTIVE'):
                m.launch(60)
            run.assert_not_called()

    def test_existing_p87_status_summary_stays_independent(self):
        self.assertNotEqual(m.ROOT.name,'p87-p300-results')
        self.assertEqual(m.summarize([])['outcome'],'NO_CHANGES_IN_UART1_FOCUS')



class LifecycleTests(unittest.TestCase):
    """Exercise the actual worker report and ExecStopPost ordering with fakes."""
    def unit_state(self,unit):
        return {'ActiveState':'active','SubState':'running','WorkingDirectory':'/opt/optolink'}

    def trial(self, ram_fault=None):
        clock=Clock()
        peer=UART1Peer(clock)
        peer.ram_fault=ram_fault
        real_class=m.UART1Wire
        state={'seconds':30,'port':'/dev/fake',
               'services':{unit:True for unit in m.h.SERVICES},
               'restore':list(m.h.SERVICES)}
        with tempfile.TemporaryDirectory() as d, \
             patch.object(Path,'read_text',return_value=
                  "port_optolink='/dev/fake'\nport_vitoconnect=None\nvs1protocol=True\n"), \
             patch.object(m.h,'unit_state',side_effect=self.unit_state), \
             patch.object(m.h,'pause_services'), \
             patch.object(m.h,'open_serial',return_value=peer), \
             patch.object(m,'UART1Wire',side_effect=
                  lambda serial:real_class(serial,clock.now,clock.sleep)), \
             patch.object(m,'isolation'), patch.object(m.signal,'signal'):
            # Patch Path.read_text only during guarded settings validation;
            # worker writes measurement.json directly via atomic_json.
            result=m.run_worker(Path(d),state)
            report=json.loads((Path(d)/'measurement.json').read_bytes())
        return result,report,peer

    def test_worker_success_restores_vs1_and_gfa(self):
        code,report,peer=self.trial()
        self.assertEqual(code,0)
        self.assertTrue(report['observation_complete'])
        self.assertTrue(report['vs1_link_restored'])
        self.assertFalse(report['errors'])
        self.assertEqual(report['recovery_gfa']['P80'],'20')
        self.assertGreater(report['comparison']['sample_count'],3)
        self.assertFalse(report['comparison']['p06_rpm_alias_verified'])
        self.assertTrue(peer.close_called)

    def test_worker_physical_crc_error_attempts_vs1_recovery(self):
        code,report,peer=self.trial('checksum')
        self.assertEqual(code,1)
        self.assertFalse(report['observation_complete'])
        self.assertTrue(report['vs1_link_restored'])
        self.assertEqual(report['recovery_gfa']['P80'],'20')
        self.assertTrue(any('P300_CHECKSUM_INVALID' in s for s in report['errors']))
        self.assertTrue(peer.close_called)

    def test_execstoppost_main_first_on_success(self):
        state={'services':{u:True for u in m.h.SERVICES},
               'restore':list(m.h.SERVICES)}
        calls=[]
        with tempfile.TemporaryDirectory() as d, \
             patch.object(m,'session_state',return_value=state), \
             patch.object(m,'locks',return_value=contextlib.nullcontext()), \
             patch.object(m.h,'command',side_effect=lambda c:calls.append(c[-1])), \
             patch.object(m.h,'unit_state',side_effect=self.unit_state), \
             patch.object(m.h,'wait_main_ready'):
            code=m.recover(Path(d))
            saved=json.loads((Path(d)/'recovery.json').read_text())
        self.assertEqual(code,0)
        self.assertTrue(saved['services_restored'])
        self.assertEqual(calls[0],m.h.MAIN)
        self.assertEqual(calls[-1],m.h.SERVICES[0])

    def test_execstoppost_defers_writers_on_main_failure(self):
        state={'services':{u:True for u in m.h.SERVICES},
               'restore':list(m.h.SERVICES)}
        calls=[]
        def fail_main(argv):
            calls.append(argv[-1])
            if argv[-1]==m.h.MAIN:
                raise m.Error('main start rejected')
        with tempfile.TemporaryDirectory() as d, \
             patch.object(m,'session_state',return_value=state), \
             patch.object(m,'locks',return_value=contextlib.nullcontext()), \
             patch.object(m.h,'command',side_effect=fail_main), \
             patch.object(m.h,'wait_main_ready'):
            code=m.recover(Path(d))
            saved=json.loads((Path(d)/'recovery.json').read_text())
        self.assertEqual(code,1)
        self.assertFalse(saved['services_restored'])
        self.assertEqual(calls,[m.h.MAIN])
        self.assertTrue(any('VS1_NOT_READY_WRITERS_DEFERRED' in s for s in saved['errors']))

    def test_unfinished_previous_session_fails_closed(self):
        fake={k:k==m.h.MAIN for k in m.h.SERVICES}
        with tempfile.TemporaryDirectory() as d, \
             patch.object(m,'ROOT',Path(d)), \
             patch.object(m,'locks',return_value=contextlib.nullcontext()), \
             patch.object(m.h,'preflight',return_value=({'port_optolink':'/dev/fake'},fake)), \
             patch.object(m.h,'unit_state',return_value={'ActiveState':'inactive'}), \
             patch.object(m.subprocess,'run') as run:
            p=Path(d)/'run-old';p.mkdir(mode=0o700)
            (p/'state.json').write_text(json.dumps({'restore':[m.h.MAIN]}))
            with self.assertRaisesRegex(m.Error,'PREVIOUS_RECOVERY_UNRESOLVED'):
                m.launch(30)
            run.assert_not_called()

if __name__=='__main__':
    unittest.main()
