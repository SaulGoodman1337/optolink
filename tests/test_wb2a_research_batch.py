"""Research batch: synthetic-only proof of offline data collection and no reruns."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

FILE=Path(__file__).resolve().parents[1]/'tools'/'wb2a-research-batch.py'
spec=importlib.util.spec_from_file_location('wb2a_research_batch',FILE)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def fixture(root):
    parent=Path(root);parent.chmod(0o700)
    session=parent/'run-20261008T194615Z-123456'
    session.mkdir(mode=0o700)
    raw1=bytes([0]*64)
    raw2=bytearray(raw1);raw2[0x1b]=2
    samples=[]
    for index,buf in ((1,raw1),(2,bytes(raw2))):
        samples.append(dict(index=index,elapsed_s=index*2.0,
            native_b7='00',native_block='00'*11,
            ram_1600=buf[:32].hex(),ram_1620=buf[32:].hex(),
            p06_rpm_alias_verified=False,uart1_gfa_link_verified=False))
    sends=['160000','4105000100f80200','41050001778c020b']
    for _ in range(2):
        sends+=list(m.P300_OBSERVE)
    specs={
        '4105000100f80200':(1,0x00f8,bytes.fromhex('20c2')),
        '41050001778c020b':(1,0x778c,bytes.fromhex('0103')),
        '4105000155d30b39':(1,0x55d3,None),
        '410500031600203e':(3,0x1600,None),
        '410500031620205e':(3,0x1620,None)
    }
    trace=[]
    counts={}
    for frame in sends:
        trace.append({'direction':'TX','hex':frame})
        if frame in specs:
            fc,addr,payload=specs[frame]
            if payload is None:
                idx=counts.get(frame,0)
                field={'4105000155d30b39':'native_block',
                       '410500031600203e':'ram_1600',
                       '410500031620205e':'ram_1620'}[frame]
                payload=bytes.fromhex(samples[idx][field])
            size=5+len(payload)
            body=bytes([1,fc,addr>>8,addr&255,len(payload)])+payload
            response=bytes([6,0x41,size])+body+bytes([(size+sum(body))&255])
            trace.append({'direction':'RX','hex':response.hex()})
            trace.append({'direction':'TX','hex':'06'})
            counts[frame]=counts.get(frame,0)+1
    measurement={
        'samples':samples,'errors':[],'observation_complete':True,
        'vs1_link_restored':True,
        'reference_gfa':{'P80':'20','P06':'00','P09':'00','P87':'00'},
        'recovery_gfa':{'P80':'20','P06':'00','P09':'00','P87':'00'},
        'trace':trace,
        'p300_phase_start_monotonic':100.0,
        'p300_phase_end_monotonic':104.0,
        'comparison':{
            'sample_count':2,'changed_byte_count':1,
            'changed_address_counts':{'0x161b':1},
            'observed_dma_source_changed':1,
            'uart1_gfa_link_verified':False,
            'p06_rpm_alias_verified':False,
            'production_approved':False,'ram_write_approved':False}}
    recovery={'services_restored':True,'errors':[],
              'systemd_service_result':'success'}
    state={'services':{str(i):True for i in range(7)},
           'restore':list(str(i) for i in range(7))}
    (session/'measurement.json').write_text(json.dumps(measurement))
    (session/'samples.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in samples))
    (session/'recovery.json').write_text(json.dumps(recovery))
    (session/'state.json').write_text(json.dumps(state))
    return session


class SyntheticCollectionTests(unittest.TestCase):
    def test_full_valid_fixture(self):
        with tempfile.TemporaryDirectory() as d:
            session=fixture(d)
            report,source=m.validate(session)
            self.assertEqual(report['samples_verified'],2)
            self.assertEqual(report['ram_unique_64byte_states'],2)
            self.assertEqual(report['ram_change_events'][0]['changed_addresses'],['0x161b'])
            self.assertEqual(report['native_b7_states'],['00'])
            self.assertFalse(report['sensor_alias_verified'])
            self.assertTrue(report['trace_frames_allowlisted'])
            self.assertEqual(report['p300_wire_responses_verified']['responses_verified'],8)
            self.assertTrue(report['p300_wire_responses_verified']['response_checksum_address_and_payload_verified'])
            self.assertEqual(len(source),4)

    def modify(self,fn):
        with tempfile.TemporaryDirectory() as d:
            session=fixture(d)
            fn(session)
            with self.assertRaises(m.BatchError):
                m.validate(session)

    def edit(self,session,file,operation):
        target=session/file
        if file.endswith('.jsonl'):
            rows=[json.loads(s) for s in target.read_text().splitlines()]
            operation(rows)
            target.write_text(''.join(json.dumps(x)+'\n' for x in rows))
        else:
            data=json.loads(target.read_text())
            operation(data)
            target.write_text(json.dumps(data))

    def test_missing_gfa_restore(self):
        self.modify(lambda p:self.edit(p,'measurement.json',lambda x:x.update(vs1_link_restored=False)))

    def test_reported_main_failure(self):
        self.modify(lambda p:self.edit(p,'recovery.json',lambda x:x.update(services_restored=False)))

    def test_wrong_model_p80(self):
        self.modify(lambda p:self.edit(p,'measurement.json',lambda x:x['reference_gfa'].update(P80='21')))

    def test_mismatch_jsonl_measured(self):
        self.modify(lambda p:self.edit(p,'samples.jsonl',lambda x:x.pop()))

    def test_unreviewed_tx_denied(self):
        self.modify(lambda p:self.edit(p,'measurement.json',
            lambda x:x['trace'].append({'direction':'TX','hex':'410500c94050015f'})))

    def test_alias_promoted_denied(self):
        self.modify(lambda p:self.edit(p,'measurement.json',
            lambda x:x['comparison'].update(p06_rpm_alias_verified=True)))

    def test_bad_sample_length_denied(self):
        self.modify(lambda p:self.edit(p,'measurement.json',
            lambda x:x['samples'][1].update(ram_1620='ff')))

    def test_inconsistent_changed_counts(self):
        self.modify(lambda p:self.edit(p,'measurement.json',
            lambda x:x['comparison'].update(changed_byte_count=3)))

    def test_checksum_frame_count_mismatch(self):
        self.modify(lambda p:self.edit(p,'measurement.json',
            lambda x:x['trace'].pop()))

    def test_corrupted_wire_checksum_denied(self):
        def patch_wire(session):
            def edit_trace(obj):
                for item in obj['trace']:
                    if item['direction']=='RX':
                        frame=bytearray.fromhex(item['hex'])
                        frame[-1] ^= 0x10
                        item['hex']=frame.hex()
                        break
            self.edit(session,'measurement.json',edit_trace)
        self.modify(patch_wire)

    def test_corrupted_wire_payload_denied(self):
        def patch_wire(session):
            def edit_trace(obj):
                items=[x for x in obj['trace'] if x['direction']=='RX']
                frame=bytearray.fromhex(items[-1]['hex'])
                frame[-2]^=0x1
                frame[-1]=(sum(frame[2:-1]) & 255)
                items[-1]['hex']=frame.hex()
            self.edit(session,'measurement.json',edit_trace)
        self.modify(patch_wire)

    def test_incorrect_wire_address_denied(self):
        def patch_wire(session):
            def edit_trace(obj):
                items=[x for x in obj['trace'] if x['direction']=='RX']
                frame=bytearray.fromhex(items[-1]['hex'])
                frame[5]^=0x1
                frame[-1]=(sum(frame[2:-1]) & 255)
                items[-1]['hex']=frame.hex()
            self.edit(session,'measurement.json',edit_trace)
        self.modify(patch_wire)

    def test_truncated_wire_response_denied(self):
        def patch_wire(session):
            def edit_trace(obj):
                items=[x for x in obj['trace'] if x['direction']=='RX']
                frame=bytearray.fromhex(items[-1]['hex'])
                items[-1]['hex']=frame[:-1].hex()
            self.edit(session,'measurement.json',edit_trace)
        self.modify(patch_wire)

    def test_incorrect_controller_identity_denied(self):
        def patch_wire(session):
            def edit_trace(obj):
                items=[x for x in obj['trace'] if x['direction']=='RX']
                frame=bytearray.fromhex(items[0]['hex'])
                frame[-2]^=0x01
                frame[-1]=(sum(frame[2:-1]) & 255)
                items[0]['hex']=frame.hex()
            self.edit(session,'measurement.json',edit_trace)
        self.modify(patch_wire)

    def test_unexpected_rx(self):
        self.modify(lambda p:self.edit(p,'measurement.json',
            lambda x:x['trace'].append({'direction':'RX_UNEXPECTED','hex':'ff'})))

    def test_only_most_recent_session_collected(self):
        with tempfile.TemporaryDirectory() as d,patch.object(m,'ROOT',Path(d)):
            p=fixture(d)
            self.assertEqual(m.latest(),p)

    def test_collect_writes_private_single_archive(self):
        with tempfile.TemporaryDirectory() as d,patch.object(m,'OUTPUT',Path(d)/'bundle'):
            session=fixture(d)
            report,source=m.validate(session)
            out=m.archive(session,source,report,'tests passed',
                          {'service':'PASS','ha_freshness_verified':False})
            self.assertTrue(out.is_file())
            self.assertEqual(out.stat().st_mode & 0o077,0)
            with tarfile.open(out) as arc:
                names=arc.getnames()
                self.assertIn('uart1/batch-analysis.json',names)
                self.assertIn('uart1/batch-health.json',names)
                self.assertIn('uart1/measurement.json',names)
                self.assertIn('uart1/samples.jsonl',names)
                self.assertIn('uart1/offline-tests.txt',names)
                self.assertEqual(json.load(arc.extractfile('uart1/batch-analysis.json'))['samples_verified'],2)

    def test_archive_repeat_reuses_identical_source(self):
        with tempfile.TemporaryDirectory() as d,patch.object(m,'OUTPUT',Path(d)/'bundle'):
            session=fixture(d);report,source=m.validate(session)
            first=m.archive(session,source,report,'pass',{})
            second=m.archive(session,source,report,'pass',{})
            self.assertEqual(first,second)
            self.assertTrue(second.is_file())

    def test_read_symlink_refused(self):
        with tempfile.TemporaryDirectory() as d:
            s=fixture(d)
            (s/'samples.jsonl').unlink()
            (s/'samples.jsonl').symlink_to(s/'measurement.json')
            with self.assertRaisesRegex(m.BatchError,'symlinked'):
                m.validate(s)

    def test_prevent_duplicate_hardware_run(self):
        with tempfile.TemporaryDirectory() as d,patch.object(m,'ROOT',Path(d)),\
             patch.object(m.subprocess,'run') as runner:
            fixture(d)
            with self.assertRaisesRegex(m.BatchError,'ALREADY_COMPLETED'):
                m.execute_uart1('offline tests passed')
            runner.assert_not_called()

    def test_service_probe_not_running_avoids_gfa_reads(self):
        fake=subprocess.CompletedProcess([],0,stdout=
             'ActiveState=inactive\nSubState=dead\nWorkingDirectory=/opt/optolink\n',stderr='')
        with patch.object(m.subprocess,'run',return_value=fake) as runner:
            result=m.health()
            self.assertEqual(result['service'],'NOT_VERIFIED')
            self.assertEqual(runner.call_count,1)

    def test_service_healthy_reads_p80_and_p06(self):
        fake=subprocess.CompletedProcess([],0,stdout=
             'ActiveState=active\nSubState=running\nWorkingDirectory=/opt/optolink\n',stderr='')
        data=subprocess.CompletedProcess([],0,stdout='RESULT=20',stderr='')
        with patch.object(m.subprocess,'run',side_effect=[fake,data,data]) as runner:
            result=m.health()
            self.assertEqual(result['service'],'PASS')
            self.assertEqual(set(result['mqtt_readbacks']),{'P80','P06'})
            self.assertEqual(runner.call_count,3)
            self.assertFalse(result['ha_freshness_verified'])

    def test_cli_default_plan_no_research_io(self):
        completed=subprocess.run([sys.executable,str(FILE)],capture_output=True,text=True)
        self.assertEqual(completed.returncode,0)
        self.assertIn('PLAN ONLY',completed.stdout)
        self.assertNotIn('UPLOAD_ONE_FILE',completed.stdout)

    def test_known_write_frames_disallowed(self):
        for x in ('410500c94050015f','f423060115','4105000320a501ce'):
            self.assertNotIn(x,m.TX_FRAMES)


if __name__=='__main__':
    unittest.main()
