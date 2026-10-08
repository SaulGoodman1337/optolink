"""Fully simulated, operator-stopped UART1 overnight P300 research tests.

No serial port, MQTT broker, or heater hardware is accessed.
"""
import importlib.util
import io
import json
import contextlib
import subprocess
import sys
import tempfile
import tarfile
from pathlib import Path
from unittest import TestCase,main
from unittest.mock import patch

from test_handover_probe import Clock
from test_uart1_dma0_cycle import UART1DMAPeer

FILE=Path(__file__).resolve().parents[1]/'tools'/'wb2a-uart1-overnight.py'
spec=importlib.util.spec_from_file_location('wb2a_overnight_test',FILE)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class OvernightTests(TestCase):
    def setUp(self):
        self.clock=Clock()
        self.peer=UART1DMAPeer(self.clock)
        self.wire=m.UART1Wire(self.peer,self.clock.now,self.clock.sleep)

    def test_inert_plan(self):
        p=subprocess.run([sys.executable,str(FILE)],text=True,capture_output=True)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('NO TIME',p.stdout.upper() if 'NO TIME' in p.stdout.upper() else 'NO TIME') if False else self.assertIn('no duration cap',p.stdout)
        self.assertNotIn('SESSION=',p.stdout)

    def test_supervisor_has_no_runtime_expiry_and_runs_detached(self):
        args=m.supervisor_command(Path('/tmp/example/run-a'))
        self.assertIn('--no-block',args)
        self.assertNotIn('--wait',args)
        self.assertFalse(any('RuntimeMaxSec' in x for x in args))
        self.assertTrue(any('ExecStopPost=' in x and '--recover' in x for x in args))
        self.assertIn('--property=Restart=no',args)

    def test_streamed_trace_stays_bounded(self):
        sink=io.StringIO()
        self.wire.trace_sink=sink
        for i in range(250):
            self.wire.record('RX',b'\x30')
        self.wire.record('TX',b'\x06')
        self.wire.flush_trace()
        self.assertLess(len(self.wire.trace),25)
        lines=[json.loads(s) for s in sink.getvalue().splitlines()]
        self.assertEqual(lines[0]['direction'],'RX')
        self.assertEqual(bytes.fromhex(lines[0]['hex']),b'\x30'*250)
        self.assertEqual(lines[1]['direction'],'TX')

    def test_all_four_fixed_p300_reads_work(self):
        self.assertEqual(self.wire.reference()['P80'],'20')
        rows=[]
        def finish_after_eight(row):
            rows.append(row)
            if len(rows)==8:
                raise m.Error('OPERATOR_STOP_SIGNAL_15')
        with self.assertRaisesRegex(m.Error,'OPERATOR_STOP_SIGNAL_15'):
            self.wire.observe(finish_after_eight,lambda:None,lambda:None)
        self.assertEqual(len(rows),8)
        self.assertIn(m.DMA0,self.peer.sent)
        self.assertIn(m.RAM0,self.peer.sent)
        self.assertIn(m.RAM1,self.peer.sent)
        self.assertEqual(self.peer.sent.count(m.STATUS),8)
        self.assertEqual(self.peer.sent.count(m.DMA0),8)
        self.assertEqual(self.wire.restore_link()['P80'],'20')

    def test_flame_cycle_does_not_terminate_observation(self):
        self.assertEqual(self.wire.reference()['P80'],'20')
        rows=[]
        def stop_only_after_much_more_than_one_flame(row):
            rows.append(row)
            if len(rows)>=40:
                raise m.Error('OPERATOR_STOP_SIGNAL_15')
        with self.assertRaisesRegex(m.Error,'OPERATOR_STOP_SIGNAL_15'):
            self.wire.observe(stop_only_after_much_more_than_one_flame,
                              lambda:None,lambda:None)
        self.assertEqual(len(rows),40)
        self.assertGreater(max(r['complete_flame_cycles'] for r in rows),0)
        self.assertEqual(rows[-1]['flame_bit'],False)

    def test_no_other_ram_or_uart_receive_register_read(self):
        self.wire.phase='observation'
        for req in (bytes.fromhex('4105000303ae0216'),
                    bytes.fromhex('410500031640201e'),b'\x04',m.h.GFA['P06']):
            with self.subTest(req=req.hex()):
                with self.assertRaisesRegex(m.Error,'TX_FORBIDDEN'):
                    self.wire.send(req)
        self.assertEqual(self.peer.sent,[])

    def test_summary_of_many_samples_from_disk(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'samples.jsonl'
            with path.open('w') as out:
                for i in range(5000):
                    ram=bytearray(64)
                    ram[0x1b]=i%256
                    dma=bytearray(16)
                    dma[:3]=(0x161b+(i%8)).to_bytes(3,'little')
                    dma[4:7]=(0x3aa).to_bytes(3,'little')
                    status=bytearray(11)
                    status[5]=0x20 if 5<=i%200<70 else 0
                    out.write(json.dumps(dict(
                      index=i+1,elapsed_s=i*2,utc='2026-10-08T20:00:00Z',
                      native_block=status.hex(),native_b7='00',
                      flame_bit=bool(status[5]&0x20),
                      ram_1600=ram[:32].hex(),ram_1620=ram[32:].hex(),
                      dma0_0020=dma.hex(),
                      dma0_source=f'0x{0x161b+(i%8):05x}',dma0_target='0x003aa',
                      complete_flame_cycles=(i//200),
                    ))+'\n')
            result=m.summarize_file(path)
            self.assertEqual(result['sample_count'],5000)
            self.assertGreater(result['completed_natural_flame_cycles'],10)
            self.assertEqual(result['changed_ram_byte_count'],1)
            self.assertFalse(result['p06_rpm_alias_verified'])
            self.assertTrue(result['no_time_limit'])

    def test_disk_pressure_stops_safely(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'out.txt'
            with f.open('w') as stream:
                with patch.object(m.shutil,'disk_usage',return_value=(1000,970,30)):
                    with self.assertRaisesRegex(m.Error,'LOW_DISK_SPACE'):
                        m.resource_guard(Path(d),stream,stream)

    def test_log_size_guard_safely(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'out.txt'
            with f.open('w') as stream:
                with patch.object(m.shutil,'disk_usage',return_value=(10**12,0,10**12)), \
                     patch.object(m,'MAX_LOG_BYTES',3):
                    stream.write('1234')
                    with self.assertRaisesRegex(m.Error,'LOG_SIZE'):
                        m.resource_guard(Path(d),stream,stream)

    def test_atomic_private_bundle_and_idempotent_reuse(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);session=root/'run-20261008T200000Z-12'
            session.mkdir(mode=0o700)
            for name in ('state.json','progress.json','trace.jsonl',
                         'samples.jsonl','measurement.json','recovery.json','health.json'):
                p=session/name;p.write_text('{}\n');p.chmod(0o600)
            with patch.object(m,'ROOT',root),patch.object(m,'BUNDLES',root/'bundles'):
                first=m.upload_bundle(session,{'production_main_verified':True})
                second=m.upload_bundle(session,{})
                self.assertEqual(first,second)
                self.assertEqual(first.stat().st_mode&0o077,0)
                with tarfile.open(first) as archive:
                    names=archive.getnames()
                    self.assertIn('uart1-overnight/trace.jsonl',names)
                    manifest=json.load(archive.extractfile('uart1-overnight/bundle-manifest.json'))
                    self.assertEqual(len(manifest['files']),7)
                    self.assertFalse(manifest['p06_measured_rpm_alias_proven'])

    def test_private_file_symlink_denied(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);session=root/'run-fixture';session.mkdir(mode=0o700)
            (session/'state.json').symlink_to('/etc/passwd')
            with patch.object(m,'ROOT',root),patch.object(m,'BUNDLES',root/'bundles'):
                with self.assertRaisesRegex(m.Error,'UNSAFE_SESSION_FILE'):
                    m.upload_bundle(session,{})

    def test_start_requires_no_previous_unresolved_recovery(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);session=root/'run-old';session.mkdir(mode=0o700)
            (session/'state.json').write_text(json.dumps({'restore':[m.h.MAIN]}))
            with patch.object(m,'ROOT',root), \
                 patch.object(m,'locks',return_value=contextlib.nullcontext()), \
                 patch.object(m.h,'preflight',return_value=({'port_optolink':'/dev/fake'},
                    {u:u==m.h.MAIN for u in m.h.SERVICES})), \
                 patch.object(m.h,'unit_state',return_value={'ActiveState':'inactive'}), \
                 patch.object(m.subprocess,'run') as spawn:
                with self.assertRaisesRegex(m.Error,'UNRESOLVED_VS1_RECOVERY'):
                    m.launch()
                spawn.assert_not_called()

    def test_legacy_duration_is_not_accepted(self):
        p=subprocess.run([sys.executable,str(FILE),'--seconds','600'],
                         capture_output=True,text=True)
        self.assertNotEqual(p.returncode,0)

    def test_status_is_read_only(self):
        with tempfile.TemporaryDirectory() as d, \
             patch.object(m,'ROOT',Path(d)), \
             patch.object(m.h,'unit_state',return_value={'ActiveState':'active'}) as state:
            session=Path(d)/'run-20261008T200000Z-77'
            session.mkdir(mode=0o700)
            m.h.atomic_json(session/'progress.json',{'sample_count':40})
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(m.status(),0)
            self.assertIn('"sample_count": 40',out.getvalue())
            state.assert_called_once_with(m.UNIT)


if __name__=='__main__':
    main()
