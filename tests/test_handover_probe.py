"""Simulated wire, recovery and supervisor tests. Never open a real serial port."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

FILE = Path(__file__).resolve().parents[1] / 'tools' / 'wb2a-handover-probe.py'
spec = importlib.util.spec_from_file_location('handover', FILE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Clock:
    def __init__(self): self.t = 0.0
    def now(self): return self.t
    def sleep(self, dt): self.t += max(.00001, dt)


class Peer:
    def __init__(self, clock):
        self.clock = clock
        self.queue = []
        self.sent = []
        self.mode = 'vs1'
        self.fragment = 1
        self.fault = None
        self.gfa_ff = 0
        self.controller = m.IDENT
        self.software = m.SOFTWARE
        self.p80 = b'\x20'
        self.enqs = 0

    def schedule(self, delay, data):
        self.queue.append([self.clock.now() + delay, bytearray(data)])
        self.queue.sort(key=lambda row: row[0])

    def read(self, n):
        if not self.queue or self.queue[0][0] > self.clock.now(): return b''
        t, data = self.queue[0]
        count = min(n, self.fragment, len(data))
        out = bytes(data[:count])
        del data[:count]
        if not data: self.queue.pop(0)
        if self.mode == 'detect' and out == b'\x05': self.enqs += 1
        return out

    def reset_input_buffer(self):
        self.queue = [q for q in self.queue if q[0] > self.clock.now()]

    def write(self, data):
        assert data in m.TX_ALLOWLIST
        self.sent.append(bytes(data))
        if self.fault == 'short_write': return max(0, len(data)-1)
        if data == b'\x04':
            self.queue = []
            self.mode = 'detect'
            self.enqs = 0
            if self.fault == 'no_enq': return len(data)
            self.schedule(.120, b'\x05')
            if self.fault != 'one_enq_only': self.schedule(.500, b'\x05')
        elif data == b'\x16\x00\x00':
            self.queue = []
            self.mode = 'p300'
            self.schedule(.010, b'\x15' if self.fault == 'bad_start' else b'\x06')
        elif data == b'\x06': pass
        elif data[:1] == b'\x01':
            assert self.enqs == 2, 'baseline must receive TWO distinct ENQs'
            self.queue = []
            self.mode = 'vs1'
            self.schedule(.020, self.controller)
        elif data in (m.VS1_ID, m.VS1_SOFTWARE, *m.GFA.values()):
            assert self.mode == 'vs1'
            result = self.controller if data == m.VS1_ID else self.software
            if data in m.GFA.values():
                result = self.p80 if data == m.GFA['P80'] else b'\x00'
                if data != m.GFA['P80'] and self.gfa_ff:
                    self.gfa_ff -= 1
                    result = b'\xff'
            if self.fault == 'short_response': result = result[:1] if len(result)>1 else b''
            if self.fault == 'trailing': result += b'\xab'
            self.schedule(.020, result)
        elif data[:1] == b'\x41':
            assert self.mode == 'p300'
            assert data[3] == 1 and data[1] == 5 and (sum(data[1:-1]) & 255) == data[-1]
            addr = data[4:6]
            result = self.controller if addr == b'\x00\xf8' else self.software
            msg, fc, count = 1, 1, 2
            if self.fault == 'controller_error': msg, count, result = 3, 1, b'\x05'
            if self.fault == 'wrong_address': addr = b'\x00\x00'
            if self.fault == 'wrong_function': fc = 3
            if self.fault == 'wrong_message': msg = 2
            if self.fault == 'wrong_length': count = 3
            body = bytes([5+len(result), msg, fc]) + addr + bytes([count]) + result
            reply = b'\x06\x41' + body + bytes([sum(body) & 255])
            if self.fault == 'checksum': reply = reply[:-1] + bytes([reply[-1]^1])
            if self.fault == 'bad_ack': reply = b'\x15' + reply[1:]
            if self.fault == 'no_stx': reply = reply[:1] + b'\x00' + reply[2:]
            if self.fault == 'repeated_ack': reply = b'\x06\x06' + reply
            if self.fault == 'oversized': reply = b'\x06\x41\xff'
            if self.fault == 'timeout': reply = b''
            self.schedule(.020, reply)
        return len(data)


class WireTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.peer = Peer(self.clock)
        self.wire = m.Wire(self.peer, self.clock.now, self.clock.sleep)

    def test_full_three_rounds(self):
        rows = self.wire.experiment()
        self.assertEqual(len(rows), 3)
        for row in rows:
            self.assertEqual(row['gfa'], {'P80':'20','P06':'00','P09':'00','P87':'00'})
            self.assertAlmostEqual(row['vs1']['first_enq_ms'],120,delta=2)
            self.assertAlmostEqual(row['vs1']['additional_enq_ms'],380,delta=2)
            self.assertGreater(row['roundtrip_with_gfa_ms'], row['roundtrip_to_vs1_id_ms'])
        self.assertTrue(all(s in m.TX_ALLOWLIST for s in self.peer.sent))
        self.assertFalse(any(s[:1]==b'\x41' and s[3]!=1 for s in self.peer.sent))

    def test_warm_vs1_before_each_p300(self):
        self.wire.experiment()
        start = [i for i,x in enumerate(self.peer.sent) if x == b'\x16\x00\x00']
        self.assertEqual(len(start), 3)
        for i in start: self.assertEqual(self.peer.sent[i-2], m.VS1_ID)

    def test_no_second_enq_aborts(self):
        self.peer.fault='one_enq_only'
        with self.assertRaises(m.ProbeError): self.wire.enter_vs1()
        self.assertFalse(any(s[:1]==b'\x01' for s in self.peer.sent))

    def test_no_enq_aborts(self):
        self.peer.fault='no_enq'
        with self.assertRaises(m.ProbeError): self.wire.enter_vs1()

    def test_initial_wrong_identity_stops_before_p300(self):
        self.peer.controller=b'\x20\xcb'
        with self.assertRaises(m.ProbeError): self.wire.experiment()
        self.assertNotIn(b'\x16\x00\x00', self.peer.sent)

    def test_wrong_software_stops(self):
        self.peer.software=b'\x01\x04'
        with self.assertRaises(m.ProbeError): self.wire.experiment()
        self.assertNotIn(b'\x16\x00\x00', self.peer.sent)

    def test_wrong_p80_stops(self):
        self.peer.p80=b'\x21'
        with self.assertRaises(m.ProbeError): self.wire.experiment()
        self.assertNotIn(b'\x16\x00\x00', self.peer.sent)

    def test_ff_once_recovers(self):
        self.wire.enter_vs1()
        self.peer.gfa_ff=1
        self.assertEqual(self.wire.gfa_block()['P06'],'00')
        self.assertEqual(self.peer.sent.count(m.GFA['P06']),2)

    def test_ff_twice_aborts(self):
        self.wire.enter_vs1()
        self.peer.gfa_ff=2
        with self.assertRaises(m.ProbeError): self.wire.gfa_block()
        self.assertEqual(self.peer.sent.count(m.GFA['P06']),2)

    def test_trailing_bytes_rejected(self):
        self.wire.enter_vs1()
        self.peer.fault='trailing'
        with self.assertRaises(m.ProbeError): self.wire.vs1(m.VS1_ID,2,m.IDENT)

    def test_p300_repeated_ack(self):
        self.peer.fault='repeated_ack'
        self.assertIn('software_ms',self.wire.enter_p300())

    def test_p300_faults(self):
        for fault in ('controller_error','wrong_address','wrong_function','wrong_message',
                      'wrong_length','checksum','bad_ack','no_stx','oversized','timeout','bad_start'):
            with self.subTest(fault=fault):
                self.setUp(); self.peer.fault=fault
                with self.assertRaises(m.ProbeError): self.wire.enter_p300()

    def test_truncated_response_rejected(self):
        self.wire.enter_vs1(); self.peer.fault='short_response'
        with self.assertRaises(m.ProbeError): self.wire.vs1(m.VS1_ID,2,m.IDENT)

    def test_short_write_rejected(self):
        self.peer.fault='short_write'
        with self.assertRaises(m.ProbeError): self.wire.enter_p300()

    def test_allowlist_denies_c9_ram_and_writes(self):
        for frame in ('410500c94050015f','4105000320a501ce','f423060115','6840500120','03'):
            with self.assertRaises(m.ProbeError): self.wire.send(bytes.fromhex(frame))
        self.assertEqual(self.peer.sent,[])

    def test_all_p300_request_checksums(self):
        for frame in (m.P300_ID, m.P300_SOFTWARE):
            self.assertEqual(sum(frame[1:-1])&255,frame[-1])
            self.assertEqual(frame[3],1)

    def test_fixed_vs1_only_reads(self):
        for frame in m.TX_ALLOWLIST:
            if len(frame)>3 and frame[0]!=0x41:
                self.assertIn(frame[0],(1,0xF7,0x6B))


VALID="port_optolink='/dev/serial/by-id/example'\nport_vitoconnect=None\nvs1protocol=True\n"
class OrchestrationTests(unittest.TestCase):
    def test_literal_settings(self): self.assertIs(m.read_settings(VALID)['vs1protocol'],True)

    def test_ambiguous_settings_rejected(self):
        for extra in ("if True:\n vs1protocol=False\n", "vs1protocol=some_function()\n", "vs1protocol:bool=True\n"):
            with self.assertRaises(m.ProbeError): m.read_settings(VALID+extra)

    def test_wrong_baseline_rejected(self):
        for txt in (VALID.replace('True','False'),VALID.replace('None',"'/dev/ttyUSB1'"),
                    VALID.replace("'/dev/serial/by-id/example'","'http://example'")):
            with self.assertRaises(m.ProbeError): m.read_settings(txt)

    def test_missing_value_rejected(self):
        with self.assertRaises(m.ProbeError): m.read_settings("port_optolink='/dev/x'\nvs1protocol=True\n")

    def test_supervision_before_worker(self):
        s=Path('/root/p300-trial-work/handover-results/run-test')
        cmd=m.supervisor_command(s)
        self.assertEqual(cmd[0],'systemd-run')
        self.assertIn('--property=RuntimeMaxSec=90',cmd)
        self.assertIn('--property=KillMode=control-group',cmd)
        self.assertIn('--wait',cmd)
        self.assertTrue(any('ExecStopPost=' in x and '--recover' in x for x in cmd))
        self.assertEqual(cmd[-2:],['--worker',str(s)])

    def test_stop_intent_saved_before_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp); state={'services':{u:True for u in m.SERVICES},'restore':[]}
            calls=[]
            def action(args):
                calls.append(args[-1])
                saved=json.loads((path/'state.json').read_text())
                self.assertIn(args[-1],saved['restore'])
            m.pause_services(path,state,action,lambda _: {'ActiveState':'inactive'})
            self.assertEqual(calls,list(m.SERVICES))

    def test_stop_failure_preserves_intent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp); state={'services':{u:True for u in m.SERVICES},'restore':[]}
            def fail(args): raise m.ProbeError('stop timed out after acceptance')
            with self.assertRaises(m.ProbeError): m.pause_services(path,state,fail)
            self.assertEqual(json.loads((path/'state.json').read_text())['restore'],[m.SERVICES[0]])

    def test_still_active_after_stop_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            state={'services':{u:True for u in m.SERVICES},'restore':[]}
            with self.assertRaises(m.ProbeError):
                m.pause_services(Path(tmp),state,lambda _:None,lambda _: {'ActiveState':'active'})

    def test_restore_main_first_timer_last(self):
        with tempfile.TemporaryDirectory() as tmp:
            state={'services':{u:True for u in m.SERVICES},'restore':list(m.SERVICES)}
            calls=[]
            with patch.object(m,'validate_session',return_value=state):
                result=m.recover(Path(tmp),lambda a:calls.append(a[-1]),lambda _:{'ActiveState':'active'},lambda:None)
            self.assertEqual(result,0)
            self.assertEqual(calls[0],m.MAIN)
            self.assertEqual(calls[-1],m.SERVICES[0])

    def test_inactive_services_not_started(self):
        with tempfile.TemporaryDirectory() as tmp:
            state={'services':{u:u==m.MAIN for u in m.SERVICES},'restore':[m.MAIN]}
            calls=[]
            with patch.object(m,'validate_session',return_value=state):
                m.recover(Path(tmp),lambda a:calls.append(a[-1]),lambda _:{'ActiveState':'active'},lambda:None)
            self.assertEqual(calls,[m.MAIN])

    def test_restore_failure_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            state={'services':{u:True for u in m.SERVICES},'restore':list(m.SERVICES)}
            calls=[]
            def action(a):
                calls.append(a[-1])
                if a[-1]==m.MAIN: raise m.ProbeError('start failed')
            with patch.object(m,'validate_session',return_value=state):
                self.assertEqual(m.recover(Path(tmp),action,lambda _:{'ActiveState':'active'},lambda:None),1)
            self.assertEqual(calls,[m.MAIN])
            self.assertFalse(json.loads((Path(tmp)/'recovery.json').read_text())['services_restored'])

    def test_active_restart_loop_is_not_ready(self):
        state={'ActiveState':'active','WorkingDirectory':'/opt/optolink','InvocationID':'fake'}
        with patch.object(m,'unit_state',return_value=state), patch.object(m,'command',return_value='init_protocol VS1 failed'):
            with self.assertRaises(m.ProbeError): m.wait_main_ready()

    def test_mainloop_ready_in_current_invocation(self):
        state={'ActiveState':'active','WorkingDirectory':'/opt/optolink','InvocationID':'fake'}
        with patch.object(m,'unit_state',return_value=state), patch.object(m,'command',return_value='enter main loop'):
            m.wait_main_ready()

    def test_not_found_systemd_state(self):
        proc=subprocess.CompletedProcess([],1,'LoadState=not-found\nActiveState=inactive\n','')
        with patch.object(m.subprocess,'run',return_value=proc):
            self.assertEqual(m.unit_state('missing.service')['ActiveState'],'inactive')

    def test_plan_inert(self):
        result=subprocess.run([sys.executable,str(FILE)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('PLAN ONLY',result.stdout)


if __name__=='__main__': unittest.main()
