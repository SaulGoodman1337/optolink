"""Offline deterministic tests of multi-hour VS1/P300 logger safety and wire framing."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

PATH=Path(__file__).resolve().parents[1]/'tools'/'wb2a-p300-deep-logger.py'
spec=importlib.util.spec_from_file_location('p300_deep_logger',PATH)
app=importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class Port:
    def __init__(self):
        self.tx=[]
    def write(self,data):
        self.tx.append(data)
        return len(data)


class Fake:
    def __init__(self,read_sequence=()):
        self.port=Port()
        self.rx=list(read_sequence)
        self.t=0.
        self.trace=[]
        self.gaps=0
    def record(self,direction,bytes_):
        self.trace.append((direction,bytes_.hex()))
    def clock(self):
        self.t+=0.010
        return self.t
    def gap(self):
        self.gaps+=1
    def exact(self,n,deadline):
        if not self.rx:
            raise RuntimeError('unexpected read')
        ans=self.rx.pop(0)
        if len(ans)!=n:
            raise RuntimeError('bad fixture RX length')
        return ans
    def quiet(self):
        pass


def make_response(fc,address,data):
    n=len(data)
    body=bytes([1,fc,address>>8,address&255,n])+data
    size=5+n
    return [b'\x06',b'\x41',bytes([size]),body+bytes([(size+sum(body))&255])]


class DeepLoggerTests(unittest.TestCase):
    def setUp(self):
        app.BASE=None

    def test_guard_fixed_known_shapes(self):
        self.assertEqual(len(app.ALL_READS),8)
        self.assertEqual(len(set(app.ALL_READS)),8)
        assert app.FAST_READS[0]==(1,0x55d3,11,'native_55d3')
        self.assertEqual(app.frame(1,0x55D3,11).hex(),'4105000155d30b39')
        self.assertEqual(app.frame(3,0x0020,16).hex(),'4105000300201038')
        self.assertEqual(app.frame(3,0x1600,32).hex(),'410500031600203e')
        self.assertEqual(app.frame(3,0x1620,32).hex(),'410500031620205e')

    def test_no_sfr_receive_register_read(self):
        for addr in (0x03ae,0x03af,0x03b0,0x196c,0x19ae,0x1a00,0x0400):
            with self.subTest(addr=hex(addr)),self.assertRaisesRegex(ValueError,'UNREVIEWED'):
                app.frame(3,addr,32)

    def test_reject_write_function_and_p06_alias(self):
        with self.assertRaisesRegex(ValueError,'UNREVIEWED'):
            app.frame(2,0x1600,32)
        config=app.entry_config()
        self.assertFalse(config['live_raw_p06_p300_alias_verified'])
        self.assertTrue(config['no_write'])
        self.assertFalse(config['uart1_u1rb_read'])

    def test_phase_guards_allow_only_historical_vs1(self):
        base=app.load_local_base(PATH.parent)
        self.assertTrue(app.DeepWire.permitted('vs1',base.h.GFA['P06'],base))
        self.assertTrue(app.DeepWire.permitted('vs1',app.EXTRA_GFA['P84'],base))
        self.assertFalse(app.DeepWire.permitted('p300',base.h.GFA['P06'],base))
        self.assertFalse(app.DeepWire.permitted('p300',app.EXTRA_GFA['P84'],base))
        self.assertFalse(app.DeepWire.permitted('vs1',app.frame(3,0x1600,32),base))
        self.assertTrue(app.DeepWire.permitted('p300',app.frame(3,0x1600,32),base))
        self.assertFalse(app.DeepWire.permitted('p300',b'\x41\x05\x00\x02\x16\x00\x20\x3d',base))

    def test_no_unknown_p300_memory_or_telegram(self):
        base=app.load_local_base(PATH.parent)
        for raw in (bytes.fromhex('4105000303ae1030'),bytes.fromhex('41050003196c206b'),
                    bytes.fromhex('410500021600203d')):
            self.assertFalse(app.DeepWire.permitted('p300',raw,base))

    def test_p300_native_ack_crc_payload(self):
        data=bytes.fromhex('0102030405210708000001')
        fake=Fake(make_response(1,0x55d3,data))
        wire=app.DeepWire(fake)
        wire.set_phase('p300')
        out=wire.read_native(app.FAST_READS[0])
        self.assertEqual(bytes.fromhex(out['hex']),data)
        self.assertEqual(fake.port.tx,[app.frame(1,0x55d3,11),b'\x06'])
        self.assertEqual(len(fake.rx),0)

    def test_p300_physical_32bytes(self):
        data=bytes(range(32))
        fake=Fake(make_response(3,0x18f8,data))
        wire=app.DeepWire(fake)
        wire.set_phase('p300')
        out=wire.read_native(app.SLOW_READS[2])
        self.assertEqual(out['address'],'0x18f8')
        self.assertEqual(out['hex'],data.hex())
        self.assertEqual(fake.port.tx[0],app.frame(3,0x18f8,32))

    def test_p300_invalid_checksum_fails_closed(self):
        sequence=make_response(1,0x55d3,bytes(11))
        last=bytearray(sequence[-1])
        last[-1]^=1
        sequence[-1]=bytes(last)
        wire=app.DeepWire(Fake(sequence))
        wire.set_phase('p300')
        with self.assertRaisesRegex(Exception,'CHECKSUM'):
            wire.read_native(app.FAST_READS[0])

    def test_p300_wrong_address_fails_closed(self):
        sequence=make_response(3,0x1601,bytes(32))
        wire=app.DeepWire(Fake(sequence))
        wire.set_phase('p300')
        with self.assertRaisesRegex(Exception,'ADDRESS'):
            wire.read_native(app.FAST_READS[2])

    def test_p300_wrong_length_fails_closed(self):
        sequence=make_response(3,0x1600,bytes(16))
        wire=app.DeepWire(Fake(sequence))
        wire.set_phase('p300')
        with self.assertRaisesRegex(Exception,'SIZE'):
            wire.read_native(app.FAST_READS[2])

    def test_p300_rejects_gfa_from_wrong_phase(self):
        wire=app.DeepWire(Fake())
        wire.set_phase('p300')
        with self.assertRaisesRegex(Exception,'FORBIDDEN'):
            wire.vs1_read('P06')

    def test_vs1_p06_raw_rpm_and_ff(self):
        for raw,expected in ((0x53,2490),(0x00,0),(0xff,None)):
            wire=app.DeepWire(Fake([bytes([raw])]))
            r=wire.vs1_read('P06')
            self.assertEqual(r['rpm'],expected)
            self.assertEqual(r['valid'],raw!=0xff)

    def test_p09_never_actual_rpm(self):
        wire=app.DeepWire(Fake([b'\x93']))
        r=wire.vs1_read('P09')
        self.assertIsNone(r['rpm'])
        self.assertTrue(r['not_an_actual_rpm'])
        self.assertAlmostEqual(r['percentage'],57.653,places=3)

    def test_p80_variant_fail_closed(self):
        wire=app.DeepWire(Fake([b'\x24']))
        with self.assertRaisesRegex(Exception,'WRONG_GFA_TYPE'):
            wire.vs1_read('P80')

    def test_p80_single_transient_ff_retries_and_recovers(self):
        fake=Fake([b'\xff',b'\x20'])
        fake.sleep=lambda seconds:None
        wire=app.DeepWire(fake)
        answer=wire.vs1_read('P80')
        self.assertEqual(answer['hex'],'20')
        self.assertEqual(answer['attempts'],2)
        self.assertEqual(fake.port.tx,[app.load_local_base(PATH.parent).h.GFA['P80']]*2)

    def test_p80_two_ff_returns_error(self):
        fake=Fake([b'\xff',b'\xff'])
        fake.sleep=lambda seconds:None
        wire=app.DeepWire(fake)
        with self.assertRaisesRegex(Exception,'WRONG_GFA_TYPE'):
            wire.vs1_read('P80')

    def test_recovery_main_before_any_helpers(self):
        import contextlib
        from types import SimpleNamespace
        from unittest.mock import Mock
        log=[]
        def action(args):
            log.append(tuple(args))
        def state(unit):
            return {'ActiveState':'active'}
        fakeh=SimpleNamespace(
            MAIN='optolink-splitter.service',
            command=action,
            wait_main_ready=lambda:log.append(('ready',)),
            unit_state=state,
            atomic_json=lambda path,data:log.append(('json',path.name,data.get('services_restored')))
        )
        fakebase=SimpleNamespace(h=fakeh,locks=contextlib.nullcontext)
        state={'restore':['optolink-party-emulator.service','optolink-splitter.service']}
        with patch.object(app,'load_local_base',return_value=fakebase), \
             patch.object(app,'validate_state',return_value=state), \
             patch.object(app,'post_restore_health',return_value={'production_main_verified':True}), \
             patch.object(app,'bundle',return_value=Path('/tmp/fake-bundle.tar.gz')):
            self.assertEqual(app.recover(Path('/tmp/fake-session')),0)
        self.assertEqual(log[0],('systemctl','start','optolink-splitter.service'))
        self.assertEqual(log[1],('ready',))
        self.assertEqual(log[2],('systemctl','start','optolink-party-emulator.service'))

    def test_recovery_defers_writers_on_main_failure(self):
        import contextlib
        from types import SimpleNamespace
        log=[]
        def bad_ready():
            raise RuntimeError('splitter unready')
        fakeh=SimpleNamespace(
            MAIN='optolink-splitter.service',
            command=lambda args:log.append(tuple(args)),
            wait_main_ready=bad_ready,
            unit_state=lambda unit:{'ActiveState':'active'},
            atomic_json=lambda path,data:log.append(('json',data.get('services_restored')))
        )
        fakebase=SimpleNamespace(h=fakeh,locks=contextlib.nullcontext)
        state={'restore':['optolink-party-emulator.service','optolink-splitter.service']}
        with patch.object(app,'load_local_base',return_value=fakebase), \
             patch.object(app,'validate_state',return_value=state), \
             patch.object(app,'post_restore_health',return_value={'production_main_verified':False}), \
             patch.object(app,'bundle',return_value=Path('/tmp/fake-bundle.tar.gz')):
            self.assertEqual(app.recover(Path('/tmp/fake-session')),1)
        self.assertEqual([v for v in log if v[:2]==('systemctl','start')],
                         [('systemctl','start','optolink-splitter.service')])
        self.assertIn(('json',False),log)

    def test_extra_gfa_uses_only_vs1(self):
        wire=app.DeepWire(Fake([b'\x03']))
        v=wire.vs1_read('P10')
        self.assertEqual(v['hex'],'03')
        self.assertEqual(wire.w.port.tx,[app.EXTRA_GFA['P10']])

    def test_writer_does_not_contact_hardware(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'test.jsonl'
            with p.open('x') as f:
                app.write_line(f,{'unsafe':False,'a':3})
            self.assertEqual(json.loads(p.read_text()),{'unsafe':False,'a':3})

    def test_summary_keeps_reference_and_p300_separate(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            p06={'key':'P06','valid':True,'rpm':2490,'hex':'53'}
            vs1={'reads':[p06,{'key':'P09','hex':'61','valid':True},
                            {'key':'P80','hex':'20','valid':True}]}
            status=bytearray(11)
            status[5]=0x20
            native={'reads':{'native_55d3':{'hex':status.hex()},
                             'dma0':{'hex':'00'*16}},'native_flame':True}
            (folder/'vs1.jsonl').write_text(json.dumps(vs1)+'\n')
            (folder/'p300.jsonl').write_text(json.dumps(native)+'\n')
            (folder/'switches.jsonl').write_text(json.dumps({'duration_s':4.6})+'\n')
            report=app.summarize_files(folder)
            self.assertEqual(report['vs1_rounds'],1)
            self.assertEqual(report['p300_rounds'],1)
            self.assertEqual(report['p06_valid_nonzero'],1)
            self.assertEqual(report['native_flame_samples'],1)
            self.assertEqual(report['phase_switch_seconds']['mean'],4.6)
            self.assertFalse(report['p06_rpm_alias_verified'])

    def test_resources_refuse_low_disk(self):
        with patch.object(app.shutil,'disk_usage') as disk:
            disk.return_value=type('Disk',(),{'free':100})()
            with self.assertRaisesRegex(RuntimeError,'DISK'):
                app.resource_guard(Path('/tmp'),())

    def test_stop_and_status_never_fetch_source(self):
        self.assertEqual(app.DEFAULT_HOURS,4)
        self.assertEqual(app.MAX_HOURS,8)
        self.assertEqual(app.UNIT,'optolink-p300-deep-logger.service')
        self.assertLess(app.VS1_WINDOW_S,app.P300_WINDOW_S)

    def test_post_restore_p06_zero_is_valid(self):
        from types import SimpleNamespace
        obj={'production_main_verified':True,
             'gfa_reads':{'P80':{'format_and_identity_verified':True},
                          'P06':{'returncode':0,'stdout':'1;0x4006;00',
                                 'format_and_identity_verified':True}}}
        fake=SimpleNamespace(post_restore_health=lambda:obj)
        with patch.object(app.subprocess,'run') as called:
            result=app.post_restore_health(fake)
            called.assert_not_called()
        self.assertTrue(result['gfa_p06_actual_rpm_quality_verified'])
        self.assertTrue(result['gfa_reads']['P06']['p06_non_ff_verified'])

    def test_post_restore_p06_ff_bounded_retry_passes(self):
        from types import SimpleNamespace
        obj={'production_main_verified':True,
             'gfa_reads':{'P80':{'format_and_identity_verified':True},
                          'P06':{'returncode':0,'stdout':'1;0x4006;ff',
                                 'format_and_identity_verified':True}}}
        fake=SimpleNamespace(post_restore_health=lambda:obj)
        response=SimpleNamespace(returncode=0,stdout='1;0x4006;53\n',stderr='')
        with patch.object(app.time,'sleep') as sleeper, \
             patch.object(app.subprocess,'run',return_value=response) as called:
            result=app.post_restore_health(fake)
            self.assertEqual(called.call_count,1)
            self.assertEqual(sleeper.call_count,1)
        self.assertTrue(result['gfa_reads']['P06']['p06_non_ff_verified'])

    def test_post_restore_p06_double_ff_is_not_health_pass(self):
        from types import SimpleNamespace
        obj={'production_main_verified':True,
             'gfa_reads':{'P80':{'format_and_identity_verified':True},
                          'P06':{'returncode':0,'stdout':'1;0x4006;ff',
                                 'format_and_identity_verified':True}}}
        fake=SimpleNamespace(post_restore_health=lambda:obj)
        response=SimpleNamespace(returncode=0,stdout='1;0x4006;FF\n',stderr='')
        with patch.object(app.time,'sleep'), \
             patch.object(app.subprocess,'run',return_value=response):
            result=app.post_restore_health(fake)
        self.assertFalse(result['gfa_p06_actual_rpm_quality_verified'])
        self.assertFalse(result['gfa_reads']['P06']['format_and_identity_verified'])

    def test_sigterm_is_deferred_until_gfa_read_completes(self):
        import signal
        latch=app.DeferredStop()
        fake=Fake([b'\x53'])
        original=fake.exact
        def read_after_signal(n,deadline):
            latch.on_signal(signal.SIGTERM,None)
            return original(n,deadline)
        fake.exact=read_after_signal
        wire=app.DeepWire(fake)
        # This must complete the pending GFA response despite SIGTERM.
        sample=wire.vs1_read('P06')
        self.assertEqual(sample['rpm'],2490)
        self.assertEqual(fake.port.tx,[app.load_local_base(PATH.parent).h.GFA['P06']])
        with self.assertRaisesRegex(RuntimeError,'OPERATOR_STOP_SIGNAL_15'):
            latch.check()

    def test_sigterm_not_raised_inside_p300_frame(self):
        import signal
        latch=app.DeferredStop()
        data=bytes(range(32))
        fake=Fake(make_response(3,0x1600,data))
        original=fake.exact
        def read_after_signal(n,deadline):
            latch.on_signal(signal.SIGTERM,None)
            return original(n,deadline)
        fake.exact=read_after_signal
        wire=app.DeepWire(fake)
        wire.set_phase('p300')
        sample=wire.read_native(app.FAST_READS[2])
        self.assertEqual(sample['hex'],data.hex())
        self.assertEqual(fake.port.tx[-1],b'\x06')
        with self.assertRaisesRegex(RuntimeError,'OPERATOR_STOP_SIGNAL_15'):
            latch.check()

    def test_verified_vs1_stop_has_no_new_eot(self):
        wire=app.DeepWire(Fake())
        wire.set_phase('vs1')
        with patch.object(wire,'identify_vs1') as reenter, \
             patch.object(wire,'vs1_read',side_effect=[
                {'hex':'20','key':'P80'}, {'hex':'53','key':'P06'},
                {'hex':'53','key':'P09'}, {'hex':'62','key':'P87'}]) as read:
            final=wire.restore_final_gfa()
        reenter.assert_not_called()
        self.assertEqual([x['key'] for x in final],['P80','P06','P09','P87'])
        self.assertEqual(wire.phase,'recovery')
        self.assertEqual(read.call_count,4)

    def test_p300_stop_switches_to_vs1_before_final_gfa(self):
        wire=app.DeepWire(Fake())
        wire.set_phase('p300')
        with patch.object(wire,'identify_vs1') as reenter, \
             patch.object(wire,'vs1_read',side_effect=[
                {'hex':'20','key':'P80'}, {'hex':'00','key':'P06'},
                {'hex':'00','key':'P09'}, {'hex':'00','key':'P87'}]):
            final=wire.restore_final_gfa()
        reenter.assert_called_once_with()
        self.assertEqual(final[0]['hex'],'20')

    def test_p300_stop_wrong_gfa_type_is_not_success(self):
        wire=app.DeepWire(Fake())
        wire.set_phase('vs1')
        with patch.object(wire,'vs1_read',side_effect=[
             {'hex':'21','key':'P80'},{'hex':'00','key':'P06'},
             {'hex':'00','key':'P09'},{'hex':'00','key':'P87'}]):
            with self.assertRaisesRegex(Exception,'FINAL_GFA_P80'):
                wire.restore_final_gfa()

    def test_competing_services_include_old_overnight(self):
        self.assertIn('optolink-uart1-overnight.service',app.SELF_NAMED_SERVICE_UNITS)
        self.assertIn('optolink-handover-probe.service',app.SELF_NAMED_SERVICE_UNITS)


if __name__=='__main__':
    unittest.main()
