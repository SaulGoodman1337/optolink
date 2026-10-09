"""Comprehensive OFFLINE protocol campaign: no systemd, USB, broker or heater.

Covers seven-round wire scripts, alternate early-VS1 reads, tamper/mismatch,
independent recovery, mandatory health gates, stage ordering and bounded
model/trace analysis. Deterministic sweep and randomized synthetic variants.
"""
from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import test_handover_live_probe  # fixtures and legacy-helper stub if unavailable
from handover_acceleration import live_probe as live
from handover_acceleration import campaign
from handover_acceleration.coordinator import (
    ACK, EOT, STX, VS1_ID, VS1_SOFTWARE, GFA, DEVICE_ID, SOFTWARE,
    HandoverCoordinator, PortLease, Mode, ProtocolError, P300_ID,
)
from test_handover_acceleration import (
    FakeClock, FakePort, expect_vs1, expect_p300, p300_reply,
)


class FakeWireFixtures(unittest.TestCase):
    def setUp(self):
        td=tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root=Path(td.name)
        self.clock=FakeClock()

    def manager(self, script):
        peer=FakePort(script)
        manager=HandoverCoordinator(lambda: peer,PortLease(self.root/'lease'),
                    clock=self.clock.monotonic,sleep=self.clock.sleep)
        return manager,peer

    @staticmethod
    def full_round(p80=b'\x20',p06=b'\x00',p09=b'\x05',p87=b'\x00'):
        return expect_p300() + expect_vs1(1,p80=p80,p06=p06) + [
            (GFA['P09'],p09),(GFA['P87'],p87)]

    @staticmethod
    def novel_return(*,identity=DEVICE_ID, software=SOFTWARE,
                     p80=b'\x20',p06=b'\x00'):
        return [(EOT,b''),(STX+VS1_ID,identity),
                (VS1_SOFTWARE,software),
                (GFA['P80'],p80),(GFA['P06'],p06)]


class PhaseSweepWireTests(FakeWireFixtures):
    def test_seven_realistic_verified_rounds(self):
        script=expect_vs1(2)+self.full_round()*7
        m,p=self.manager(script)
        with m:
            obs=live.perform_phase_sweep(m,lambda: None,monotonic=self.clock.monotonic,
                sleep=self.clock.sleep)
            self.assertIs(m.mode,Mode.VS1_VERIFIED)
            self.assertEqual(len(obs),7)
            self.assertTrue(all(o['verified'] for o in obs))
            self.assertTrue(all(o['gfa']['P80']=='20' for o in obs))
            self.assertTrue(all(o['gfa']['P06']=='00' for o in obs))
            self.assertEqual([o['label'] for o in obs],
                             [c[0] for c in live.PHASE_SWEEP])
            self.assertEqual(sum(o['vs1_idle_ms'] for o in obs),2200)
            self.assertEqual(sum(o['p300_idle_ms'] for o in obs),2200)
        self.assertEqual(p.writes.count(EOT),15)
        self.assertEqual(p.writes.count(b'\x16\x00\x00'),7)
        self.assertEqual(sum(w==P300_ID for w in p.writes),7)
        self.assertEqual(sum(w==GFA['P80'] for w in p.writes),8)
        self.assertTrue(p.closed)
        self.assertEqual(p.script,[])

    def test_sweep_only_permits_existing_allowlisted_frames(self):
        m,p=self.manager(expect_vs1(2)+self.full_round()*7)
        with m:
            live.perform_phase_sweep(m,lambda:None,monotonic=self.clock.monotonic,
                sleep=self.clock.sleep)
        self.assertTrue(set(p.writes).issubset({EOT,ACK,b'\x16\x00\x00',
                            STX+VS1_ID,VS1_SOFTWARE, GFA['P80'],GFA['P06'],
                            GFA['P09'],GFA['P87'],
                            P300_ID,bytes.fromhex('41050001778c020b')}))

    def test_sweep_no_eot_for_sleep_or_extra_reads(self):
        m,p=self.manager(expect_vs1(2)+self.full_round()*7)
        with m:
            live.perform_phase_sweep(m,lambda:None,monotonic=self.clock.monotonic,
                sleep=self.clock.sleep)
        self.assertEqual(p.writes.count(EOT),15)
        self.assertEqual(p.writes.count(GFA['P09']),7)
        self.assertEqual(p.writes.count(GFA['P87']),7)

    def test_sweep_never_switches_if_precondition_unverified(self):
        m,p=self.manager(expect_vs1(2))
        with self.assertRaisesRegex(live.base.ProbeError,'verified VS1'):
            live.perform_phase_sweep(m,lambda:None,
                monotonic=self.clock.monotonic,sleep=self.clock.sleep)
        self.assertEqual(p.writes,[])

    def test_sweep_refuses_before_first_p300_when_cancelled(self):
        m,p=self.manager(expect_vs1(2))
        with m:
            with self.assertRaisesRegex(RuntimeError,'operator stop'):
                live.perform_phase_sweep(m,lambda: (_ for _ in ()).throw(
                    RuntimeError('operator stop')),
                    monotonic=self.clock.monotonic,sleep=self.clock.sleep)
        self.assertEqual(p.writes.count(EOT),1)

    def test_sweep_aborts_after_bad_second_p300_crc(self):
        script=(expect_vs1(2)+self.full_round()+
                expect_p300(bad_crc=True)[:3]+expect_vs1(2))
        m,p=self.manager(script)
        with m:
            with self.assertRaisesRegex(ProtocolError,'checksum'):
                live.perform_phase_sweep(m,lambda:None,
                    monotonic=self.clock.monotonic,sleep=self.clock.sleep)
        self.assertEqual(p.script,[])
        self.assertEqual(p.writes.count(EOT),5)
        self.assertIn(('vs1','verified:2'),m.history)

    def test_sweep_does_not_fake_valid_p06_after_ff(self):
        script=expect_vs1(2)+expect_p300()+expect_vs1(1,p06=b'\xff')+expect_vs1(2)
        m,p=self.manager(script)
        with m:
            with self.assertRaisesRegex(ProtocolError,'P06'):
                live.perform_phase_sweep(m,lambda:None,
                     monotonic=self.clock.monotonic,sleep=self.clock.sleep)
        self.assertEqual(p.script,[])
        self.assertFalse(any(x[0]=='vs1' and x[1]=='verified:1' for x in m.history))

    def test_sweep_with_wrong_p80_fails_closed(self):
        script=expect_vs1(2)+expect_p300()+expect_vs1(1,p80=b'\x21')[:4]+expect_vs1(2)
        m,p=self.manager(script)
        with m:
            with self.assertRaisesRegex(ProtocolError,'P80'):
                live.perform_phase_sweep(m,lambda:None,
                    monotonic=self.clock.monotonic,sleep=self.clock.sleep)
        self.assertFalse(p.script)

    def test_sweep_with_identity_corruption_fails_closed(self):
        script=expect_vs1(2)+expect_p300()+expect_vs1(1,device=b'\x00\x00')[:2]+expect_vs1(2)
        m,p=self.manager(script)
        with m:
            with self.assertRaisesRegex(ProtocolError,'identity'):
                live.perform_phase_sweep(m,lambda:None,
                    monotonic=self.clock.monotonic,sleep=self.clock.sleep)
        self.assertFalse(p.script)

    def test_each_trial_contains_fresh_vs1_gfa(self):
        script=expect_vs1(2)
        for i in range(7):
            script+=self.full_round(p06=bytes([i+1]))
        m,p=self.manager(script)
        with m:
            obs=live.perform_phase_sweep(m,lambda:None,
                monotonic=self.clock.monotonic,sleep=self.clock.sleep)
        self.assertEqual([o['gfa']['P06'] for o in obs],
                         ['01','02','03','04','05','06','07'])
        self.assertFalse(p.script)

    def test_sweep_has_bounded_fixed_trial_count(self):
        self.assertEqual(len(live.PHASE_SWEEP),7)
        self.assertEqual(live.PHASE_SWEEP[0][0],'control_a')
        self.assertEqual(live.PHASE_SWEEP[-1][0],'control_b')

    def test_idle_offsets_below_two_second_interval(self):
        self.assertTrue(all(0<=vs1<=1400 and 0<=p300<=1400
            for _,vs1,p300 in live.PHASE_SWEEP))

    def test_sweep_requires_current_protocol_to_start(self):
        m,p=self.manager(expect_vs1(2))
        self.assertEqual(m.mode,Mode.DETACHED)
        with self.assertRaises(live.base.ProbeError):
            live.perform_phase_sweep(m,lambda:None)

    def test_randomized_successful_frame_payloads_never_change_wire_shape(self):
        rand=random.Random(391816)
        for run in range(32):
            with self.subTest(run=run):
                clock=FakeClock()
                script=expect_vs1(2)
                pp=[]
                for j in range(7):
                    p06=bytes([rand.randint(0,254)])
                    p09=bytes([rand.randint(0,254)])
                    pp.append(p06.hex())
                    script+=self.full_round(p06=p06,p09=p09)
                peer=FakePort(script)
                with tempfile.TemporaryDirectory() as td:
                    m=HandoverCoordinator(lambda:peer,PortLease(Path(td)/'lease'),
                          clock=clock.monotonic,sleep=clock.sleep)
                    with m:
                        obs=live.perform_phase_sweep(m,lambda:None,
                              monotonic=clock.monotonic,sleep=clock.sleep)
                    self.assertEqual([o['gfa']['P06'] for o in obs],pp)
                    self.assertEqual(peer.writes.count(EOT),15)
                    self.assertFalse(peer.script)


class EarlyVs1WireTests(FakeWireFixtures):
    def test_early_vs1_success_requires_full_identity_gfa(self):
        m,p=self.manager(expect_vs1(2)+expect_p300()+self.novel_return())
        with m:
            m.to_p300()
            m.to_vs1_early_identity_experiment()
            self.assertEqual(m.verified_gfa_snapshot(),{'P80':b'\x20','P06':b'\x00'})
            self.assertIs(m.mode,Mode.VS1_VERIFIED)
        self.assertFalse(p.script)
        self.assertIn(('vs1_early_identity','verified'),m.history)
        self.assertNotIn(('vs1','verified:1'),m.history)
        self.assertEqual(p.writes.count(EOT),3)

    def test_early_vs1_empty_identity_times_out_and_recovers(self):
        m,p=self.manager(expect_vs1(2)+expect_p300()+
                    [(EOT,b''),(STX+VS1_ID,b'')]+expect_vs1(2))
        with m:
            m.to_p300()
            with self.assertRaisesRegex(ProtocolError,'EARLY_VS1_NO_IDENTITY'):
                m.to_vs1_early_identity_experiment()
            self.assertEqual(m.mode,Mode.FAILED_CLOSED)
        self.assertEqual(p.script,[])
        self.assertIn(('vs1','verified:2'),m.history)
        self.assertNotIn(('vs1_early_identity','verified'),m.history)
        self.assertGreaterEqual(self.clock.now,.35)

    def test_early_vs1_wrong_identity_does_not_get_pass(self):
        m,p=self.manager(expect_vs1(2)+expect_p300()+
              self.novel_return(identity=b'\x12\x34')[:2]+expect_vs1(2))
        with m:
            m.to_p300()
            with self.assertRaisesRegex(ProtocolError,'WRONG_IDENTITY'):
                m.to_vs1_early_identity_experiment()
        self.assertFalse(p.script)
        self.assertIn(('vs1_early_identity','failed'),m.history)

    def test_early_vs1_ff_p06_is_invalid(self):
        m,p=self.manager(expect_vs1(2)+expect_p300()+
                           self.novel_return(p06=b'\xff')+expect_vs1(2))
        with m:
            m.to_p300()
            with self.assertRaisesRegex(ProtocolError,'P06_FF'):
                m.to_vs1_early_identity_experiment()
        self.assertFalse(p.script)

    def test_early_vs1_wrong_p80_rejected(self):
        m,p=self.manager(expect_vs1(2)+expect_p300()+
                           self.novel_return(p80=b'\x21')[:4]+expect_vs1(2))
        with m:
            m.to_p300()
            with self.assertRaisesRegex(ProtocolError,'P80_MISMATCH'):
                m.to_vs1_early_identity_experiment()
        self.assertFalse(p.script)

    def test_early_vs1_bad_software_rejected(self):
        m,p=self.manager(expect_vs1(2)+expect_p300()+
                           self.novel_return(software=b'\xff\xff')[:3]+expect_vs1(2))
        with m:
            m.to_p300()
            with self.assertRaisesRegex(ProtocolError,'WRONG_SOFTWARE'):
                m.to_vs1_early_identity_experiment()
        self.assertFalse(p.script)

    def test_early_vs1_requires_verified_p300(self):
        m,p=self.manager(expect_vs1(2))
        with self.assertRaisesRegex(ProtocolError,'requires a freshly verified P300'):
            m.to_vs1_early_identity_experiment()
        with m:
            with self.assertRaisesRegex(ProtocolError,'requires a freshly verified P300'):
                m.to_vs1_early_identity_experiment()
        self.assertEqual(p.script,[])

    def test_early_vs1_does_not_accept_stale_enq_as_identity(self):
        m,p=self.manager(expect_vs1(2)+expect_p300()+
                   [(EOT,b''),(STX+VS1_ID,b'\x05\x05')]+expect_vs1(2))
        with m:
            m.to_p300()
            with self.assertRaisesRegex(ProtocolError,'WRONG_IDENTITY'):
                m.to_vs1_early_identity_experiment()
        self.assertFalse(p.script)

    def test_early_vs1_exact_wire_has_no_extra_enq_wait(self):
        m,p=self.manager(expect_vs1(2)+expect_p300()+self.novel_return())
        with m:
            m.to_p300()
            m.to_vs1_early_identity_experiment()
        self.assertEqual(p.writes.count(EOT),3)
        self.assertEqual(sum(w==STX+VS1_ID for w in p.writes),2)
        # 2 ENQs from cold, one from known P300, zero during early return.
        self.assertFalse(p.script)

    def test_early_vs1_does_not_publish_stale_gfa_after_failure(self):
        m,p=self.manager(expect_vs1(2)+expect_p300()+
                   [(EOT,b''),(STX+VS1_ID,b'\x12\x34')]+expect_vs1(2))
        with m:
            m.to_p300()
            with self.assertRaises(ProtocolError):
                m.to_vs1_early_identity_experiment()
            with self.assertRaises(ProtocolError):
                m.verified_gfa_snapshot()
        self.assertFalse(p.script)

    def test_early_vs1_only_known_read_bytes(self):
        m,p=self.manager(expect_vs1(2)+expect_p300()+self.novel_return())
        with m:
            m.to_p300()
            m.to_vs1_early_identity_experiment()
        self.assertNotIn(bytes.fromhex('c9'),p.writes)
        self.assertNotIn(bytes.fromhex('6b400602'),p.writes)
        self.assertEqual(p.writes[-1],GFA['P06'])


class TraceAssociationTests(unittest.TestCase):
    def setUp(self):
        self.obs=[{'label':x[0], 'verified':True,
                   'to_p300_ms':2000.,'to_vs1_ms':2000.,
                   'gfa':{'P80':'20','P06':'00'}} for x in live.PHASE_SWEEP]
        self.groups=[{'enq_wait_ms':[1750.,3988.]}]
        for _ in self.obs:
            self.groups.extend([{'enq_wait_ms':[1999.0]},
                                {'enq_wait_ms':[2001.0]}])

    def test_assoc_successful_seven_pairs(self):
        v=live.associate_sweep_enqs(self.obs,self.groups)
        self.assertEqual(len(v),7)
        self.assertEqual(v[0]['p300_eot_enq_ms'],1999.)
        self.assertEqual(v[-1]['vs1_eot_enq_ms'],2001.)
        self.assertNotIn('p300_eot_enq_ms',self.obs[0])

    def test_assoc_rejects_missing_eot(self):
        with self.assertRaisesRegex(ValueError,'EOT count'):
            live.associate_sweep_enqs(self.obs,self.groups[:-1])

    def test_assoc_rejects_extra_eot(self):
        with self.assertRaisesRegex(ValueError,'EOT count'):
            live.associate_sweep_enqs(self.obs,self.groups+[{'enq_wait_ms':[5.0]}])

    def test_assoc_rejects_bad_cold_enq(self):
        self.groups[0]={'enq_wait_ms':[1998.]}
        with self.assertRaisesRegex(ValueError,'cold'):
            live.associate_sweep_enqs(self.obs,self.groups)

    def test_assoc_rejects_spurious_extra_p300_enq(self):
        self.groups[3]={'enq_wait_ms':[1999.,2237.]}
        with self.assertRaisesRegex(ValueError,'unexpected first ENQ'):
            live.associate_sweep_enqs(self.obs,self.groups)

    def test_assoc_rejects_missing_return_enq(self):
        self.groups[2]={'enq_wait_ms':[]}
        with self.assertRaisesRegex(ValueError,'unexpected first ENQ'):
            live.associate_sweep_enqs(self.obs,self.groups)

    def test_assoc_binds_correct_trial_not_aggregate(self):
        self.groups[5]={'enq_wait_ms':[123.456]}
        rows=live.associate_sweep_enqs(self.obs,self.groups)
        self.assertEqual(rows[2]['p300_eot_enq_ms'],123.456)
        self.assertEqual(rows[3]['p300_eot_enq_ms'],1999.)

    def test_phase_effect_mild_jitter_is_not_fast_handshake_proof(self):
        rows=live.associate_sweep_enqs(self.obs,self.groups)
        a=campaign.summarize_phase_effect(rows)
        self.assertFalse(a['potential_phase_dependency'])
        self.assertIn('NO_LARGE',a['interpretation'])

    def test_phase_effect_large_response_change_is_candidate_only(self):
        self.groups[9]['enq_wait_ms']=[888.]
        rows=live.associate_sweep_enqs(self.obs,self.groups)
        a=campaign.summarize_phase_effect(rows)
        self.assertTrue(a['potential_phase_dependency'])
        self.assertEqual(a['interpretation'],'PHASE_DEPENDENCE_CANDIDATE_ONLY')

    def test_phase_effect_rejects_wrong_number(self):
        with self.assertRaisesRegex(campaign.CampaignError,'number'):
            campaign.summarize_phase_effect([])

    def test_phase_effect_rejects_wrong_labels(self):
        rows=live.associate_sweep_enqs(self.obs,self.groups)
        rows[0]['label']='wrong'
        with self.assertRaisesRegex(campaign.CampaignError,'order'):
            campaign.summarize_phase_effect(rows)

    def test_phase_effect_rejects_nan(self):
        rows=live.associate_sweep_enqs(self.obs,self.groups)
        rows[2]['p300_eot_enq_ms']=float('nan')
        with self.assertRaises(campaign.CampaignError):
            campaign.summarize_phase_effect(rows)

    def test_phase_effect_rejects_negative(self):
        rows=live.associate_sweep_enqs(self.obs,self.groups)
        rows[3]['vs1_eot_enq_ms']=-1
        with self.assertRaises(campaign.CampaignError):
            campaign.summarize_phase_effect(rows)

    def test_phase_effect_rejects_missing(self):
        rows=live.associate_sweep_enqs(self.obs,self.groups)
        del rows[1]['to_p300_ms']
        with self.assertRaises(campaign.CampaignError):
            campaign.summarize_phase_effect(rows)


class CampaignClassificationTests(unittest.TestCase):
    @staticmethod
    def recovered():
        return {'services_restored':True,'overall_verified':True,
                'errors':[], 'independent_link_restore':{'verified':True}}

    @staticmethod
    def summary(*,success=True,stage='phase_sweep'):
        return {'experiment':stage,'result':
                'PASS_VERIFIED_READ_ONLY_PHASE_SWEEP' if success else
                'FAIL_OR_NOT_VERIFIED',
                'measurement_errors':[] if success else
                ['ProtocolError: EARLY_VS1_NO_IDENTITY_WITHIN_350MS'],
                'unit_rc':0 if success else 1,
                'services_restored':True, 'recovery_errors':[]}

    def test_known_good_success(self):
        self.assertEqual(campaign.interpret_stage(self.summary(),self.recovered(),0),
                         'VERIFIED_SUCCESS')

    def test_novel_success(self):
        s=self.summary(stage='early_vs1_identity')
        self.assertEqual(campaign.interpret_stage(s,self.recovered(),0,
                          speculative=True),'VERIFIED_SUCCESS')

    def test_negative_novel_with_restore_is_scientific_negative(self):
        s=self.summary(success=False,stage='early_vs1_identity')
        self.assertEqual(campaign.interpret_stage(s,self.recovered(),1,
                           speculative=True),'HYPOTHESIS_NEGATIVE_RESTORED')

    def test_negative_standard_cannot_be_interpreted_as_expected(self):
        s=self.summary(success=False)
        self.assertEqual(campaign.interpret_stage(s,self.recovered(),1),
                         'INCONCLUSIVE_STOP')

    def test_missing_recovery_is_hard_stop(self):
        self.assertEqual(campaign.interpret_stage(self.summary(),{},0),
                         'UNVERIFIED_RESTORE_STOP')

    def test_service_restore_false_is_hard_stop(self):
        r=self.recovered();r['services_restored']=False
        self.assertEqual(campaign.interpret_stage(self.summary(),r,0),
                         'UNVERIFIED_RESTORE_STOP')

    def test_independent_link_restore_false_is_hard_stop(self):
        r=self.recovered();r['independent_link_restore']['verified']=False
        self.assertEqual(campaign.interpret_stage(self.summary(),r,0),
                         'UNVERIFIED_RESTORE_STOP')

    def test_recovery_errors_hard_stop(self):
        r=self.recovered();r['errors']=['unit failed']
        self.assertEqual(campaign.interpret_stage(self.summary(),r,0),
                         'UNVERIFIED_RESTORE_STOP')

    def test_summary_recovery_errors_hard_stop(self):
        s=self.summary();s['recovery_errors']=['serial problem']
        self.assertEqual(campaign.interpret_stage(s,self.recovered(),0),
                         'UNVERIFIED_RESTORE_STOP')

    def test_unit_failure_with_pass_label_is_not_success(self):
        self.assertEqual(campaign.interpret_stage(self.summary(),self.recovered(),1),
                         'INCONCLUSIVE_STOP')

    def test_negative_novel_with_unknown_exception_is_not_expected(self):
        s=self.summary(success=False,stage='early_vs1_identity')
        s['measurement_errors']=['RuntimeError: strange device state']
        self.assertEqual(campaign.interpret_stage(s,self.recovered(),1,
                          speculative=True),'INCONCLUSIVE_STOP')

    def test_negative_novel_with_multiple_errors_is_not_expected(self):
        s=self.summary(success=False,stage='early_vs1_identity')
        s['measurement_errors'].append('RestoreError: recovery fault')
        self.assertEqual(campaign.interpret_stage(s,self.recovered(),1,
                          speculative=True),'INCONCLUSIVE_STOP')

    def test_negative_novel_p80_mismatch_is_not_pass(self):
        s=self.summary(success=False,stage='early_vs1_identity')
        s['measurement_errors']=['ProtocolError: EARLY_VS1_P80_MISMATCH']
        self.assertEqual(campaign.interpret_stage(s,self.recovered(),1,
                          speculative=True),'HYPOTHESIS_NEGATIVE_RESTORED')

    def test_negative_novel_wrong_software_is_not_pass(self):
        s=self.summary(success=False,stage='early_vs1_identity')
        s['measurement_errors']=['ProtocolError: EARLY_VS1_WRONG_SOFTWARE']
        self.assertEqual(campaign.interpret_stage(s,self.recovered(),1,
                          speculative=True),'HYPOTHESIS_NEGATIVE_RESTORED')

    def test_failed_standard_with_clean_recovery_not_counted_as_speed(self):
        s=self.summary(success=False)
        self.assertEqual(campaign.interpret_stage(s,self.recovered(),1,
                         speculative=False),'INCONCLUSIVE_STOP')


class CampaignRunnerTests(unittest.TestCase):
    def setUp(self):
        td=tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.base_dir=Path(td.name)
        self.stack=contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(campaign.live,'BASE_DIR',self.base_dir))
        self.stack.enter_context(patch.object(campaign.live,'preflight',lambda : ({},{})))
        self.stack.enter_context(patch.object(campaign.os,'geteuid',lambda :0))
        self.stack.enter_context(patch.object(campaign.live.base,'atomic_json',
                   lambda path,obj: Path(path).write_text(json.dumps(obj)),create=True))
        self.calls=[]
        self.stack.enter_context(patch.object(campaign,'verify_health',
                   lambda :self._health_check()))
        self.healthy=True

    def _health_check(self):
        self.calls.append('health')
        return self.healthy

    def fixture(self, stage):
        success=stage=='phase_sweep'
        record=CampaignClassificationTests.summary(success=success,stage=stage)
        if success:
            record['trials']=self.sweep_trials()
        recovery=CampaignClassificationTests.recovered()
        return record,recovery

    @staticmethod
    def sweep_trials():
        return [{'label':c[0], 'verified':True,
                 'to_p300_ms':2200.,'to_vs1_ms':2300.,
                 'p300_eot_enq_ms':2000.,'vs1_eot_enq_ms':2000.}
                for c in live.PHASE_SWEEP]

    def set_runner(self, result_cases):
        cases=list(result_cases)
        def run(command):
            stage='phase_sweep' if '--experiment-phase-sweep' in command else 'early_vs1_identity'
            self.calls.append(stage)
            if not cases:
                raise AssertionError('spurious repeated hardware stage')
            expected,rc=cases.pop(0)
            self.assertEqual(expected,stage)
            return rc, str(self.base_dir/('run-'+stage))
        def evidence(session):
            stage='phase_sweep' if session.endswith('phase_sweep') else 'early_vs1_identity'
            record,recovery=self.fixture(stage)
            return record,recovery
        self.stack.enter_context(patch.object(campaign,'run_and_capture',run))
        self.stack.enter_context(patch.object(campaign,'stage_evidence',evidence))

    def test_sweep_only_finishes_after_health(self):
        self.set_runner([('phase_sweep',0)])
        self.assertEqual(campaign.run_campaign(),0)
        self.assertEqual(self.calls,['phase_sweep','health'])

    def test_sweep_then_one_speculative_negative_and_health(self):
        self.set_runner([('phase_sweep',0),('early_vs1_identity',1)])
        self.assertEqual(campaign.run_campaign(include_early_vs1=True),0)
        self.assertEqual(self.calls,['phase_sweep','health','early_vs1_identity','health'])

    def test_sweep_good_but_health_failed_blocks_speculative(self):
        self.set_runner([('phase_sweep',0)])
        self.healthy=False
        self.assertEqual(campaign.run_campaign(include_early_vs1=True),1)
        self.assertEqual(self.calls,['phase_sweep','health'])

    def test_sweep_failure_blocks_speculative(self):
        self.set_runner([('phase_sweep',1)])
        self.assertEqual(campaign.run_campaign(include_early_vs1=True),1)
        self.assertEqual(self.calls,['phase_sweep'])

    def test_unverified_restore_blocks_everything(self):
        self.set_runner([('phase_sweep',0)])
        def evidence(_):
            s=CampaignClassificationTests.summary();r={}
            return s,r
        self.stack.enter_context(patch.object(campaign,'stage_evidence',evidence))
        self.assertEqual(campaign.run_campaign(include_early_vs1=True),1)
        self.assertEqual(self.calls,['phase_sweep'])

    def test_missing_evidence_blocks_next_stage(self):
        self.set_runner([('phase_sweep',0)])
        self.stack.enter_context(patch.object(campaign,'stage_evidence',
                         side_effect=campaign.CampaignError('missing')))
        self.assertEqual(campaign.run_campaign(include_early_vs1=True),1)
        self.assertEqual(self.calls,['phase_sweep'])

    def test_wrong_experiment_tag_blocks_next_stage(self):
        self.set_runner([('phase_sweep',0)])
        self.stack.enter_context(patch.object(campaign,'stage_evidence',
             return_value=(CampaignClassificationTests.summary(
                          stage='early_vs1_identity'),
                          CampaignClassificationTests.recovered())))
        self.assertEqual(campaign.run_campaign(include_early_vs1=True),1)
        self.assertEqual(self.calls,['phase_sweep'])

    def test_summary_written_before_and_after_each_step(self):
        self.set_runner([('phase_sweep',0)])
        self.assertEqual(campaign.run_campaign(),0)
        manifests=list(self.base_dir.glob('campaign-*/campaign.json'))
        self.assertEqual(len(manifests),1)
        record=json.loads(manifests[0].read_text())
        self.assertEqual(record['result'],'ALL_STAGES_VERIFIED_SUCCESS')
        self.assertEqual(record['stages'][0]['classification'],'VERIFIED_SUCCESS')

    def test_negative_result_persisted_without_false_pass(self):
        self.set_runner([('phase_sweep',0),('early_vs1_identity',1)])
        self.assertEqual(campaign.run_campaign(include_early_vs1=True),0)
        record=json.loads(next(self.base_dir.glob('campaign-*/campaign.json')).read_text())
        self.assertEqual(record['result'],'EARLY_VS1_NEGATIVE_BUT_RESTORED')
        self.assertEqual(record['stages'][-1]['classification'],
                         'HYPOTHESIS_NEGATIVE_RESTORED')

    def test_running_without_root_refuses_before_hardware(self):
        self.stack.enter_context(patch.object(campaign.os,'geteuid',lambda:1000))
        with self.assertRaisesRegex(campaign.CampaignError,'root'):
            campaign.run_campaign()
        self.assertEqual(self.calls,[])

    def test_preflight_refusal_before_hardware(self):
        self.stack.enter_context(patch.object(campaign.live,'preflight',
                  side_effect=campaign.live.base.ProbeError('rpm logger active')))
        with self.assertRaisesRegex(campaign.live.base.ProbeError,'rpm logger'):
            campaign.run_campaign(include_early_vs1=True)
        self.assertEqual(self.calls,[])

    def test_campaign_never_runs_same_unreviewed_stage_twice(self):
        self.set_runner([('phase_sweep',0),('early_vs1_identity',1)])
        self.assertEqual(campaign.run_campaign(include_early_vs1=True),0)
        self.assertEqual(self.calls.count('early_vs1_identity'),1)


class CampaignCliTests(unittest.TestCase):
    def test_no_flags_is_inert(self):
        with patch.object(sys,'argv',['campaign.py']), \
             patch.object(campaign,'run_campaign',
                          side_effect=AssertionError('no run')):
            self.assertEqual(campaign.main(),0)

    def test_execute_missing_acceptance_refused(self):
        with patch.object(sys,'argv',['campaign.py','--execute']), \
             patch.object(campaign,'run_campaign',
                          side_effect=AssertionError('no run')):
            with self.assertRaisesRegex(campaign.CampaignError,'requires'):
                campaign.main()

    def test_speculative_without_execute_refused(self):
        with patch.object(sys,'argv',['campaign.py','--include-early-vs1']):
            with self.assertRaisesRegex(campaign.CampaignError,'require'):
                campaign.main()

    def test_execute_acceptance_calls_sweep_only(self):
        with patch.object(sys,'argv',['campaign.py','--execute','--accept-telemetry-pause']), \
             patch.object(campaign,'run_campaign',return_value=0) as run:
            self.assertEqual(campaign.main(),0)
            run.assert_called_once_with(include_early_vs1=False)

    def test_execute_with_explicit_speculation(self):
        with patch.object(sys,'argv',['campaign.py','--execute','--accept-telemetry-pause',
                                       '--include-early-vs1']), \
             patch.object(campaign,'run_campaign',return_value=0) as run:
            self.assertEqual(campaign.main(),0)
            run.assert_called_once_with(include_early_vs1=True)


if __name__=='__main__':
    unittest.main()


class CampaignLiveWorkerTests(unittest.TestCase):
    """Worker integration with virtual USB; fully mocks systemd and serial."""
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.session=Path(tmp.name)
        self.fake_port=None
        self.state={'port':'/dev/NO_REAL_SERIAL',
                    'services':{live.base.MAIN:True},'restore':[],
                    'source_sha256':{'mock':'mock'},'experiment':'phase_sweep'}
        st=contextlib.ExitStack();self.addCleanup(st.close)
        def fake(obj,name,value):
            st.enter_context(patch.object(obj,name,value,create=True))
        fake(live,'verify_session',lambda _:self.state)
        fake(live,'guard_other_research',lambda *a,**kw:None)
        fake(live.base,'read_settings',lambda s:{'port_optolink':self.state['port']})
        fake(live.base,'SETTINGS',types.SimpleNamespace(read_text=lambda :'settings'))
        fake(live.base,'unit_state',lambda unit: {'WorkingDirectory':'/opt/optolink',
            'ActiveState':'active' if unit==live.base.MAIN else 'inactive'})
        fake(live.base,'pause_services',lambda *a,**k:None)
        fake(live.base,'assert_no_owner',lambda _:None)
        fake(live.base,'open_serial',lambda _:self.fake_port)
        fake(live.base,'atomic_json',lambda p,value:Path(p).write_text(json.dumps(value)))
        fake(live.base,'locks',lambda : contextlib.nullcontext())
        fake(live,'PortLease',lambda *_args:types.SimpleNamespace(acquire=lambda:None,
                                                                 release=lambda:None))

    @staticmethod
    def full_round():
        return FakeWireFixtures.full_round()

    def test_worker_phase_sweep_performs_every_frame_and_trace(self):
        self.fake_port=FakePort(expect_vs1(2)+self.full_round()*7)
        self.assertEqual(live.worker(self.session),0)
        result=json.loads((self.session/'measurement.json').read_text())
        self.assertTrue(result['experiment_pass'])
        self.assertTrue(result['vs1_link_restored'])
        self.assertEqual(len(result['trials']),7)
        self.assertEqual(len(result['enq_trace']),15)
        self.assertEqual(len(result['events'])>120,True)
        self.assertTrue(all(t['verified'] for t in result['trials']))
        self.assertTrue(all('p300_eot_enq_ms' in t for t in result['trials']))
        self.assertTrue(self.fake_port.closed)
        self.assertFalse(self.fake_port.script)

    def test_worker_phase_sweep_crc_error_restores_but_does_not_pass(self):
        self.fake_port=FakePort(expect_vs1(2)+self.full_round()+
                         expect_p300(bad_crc=True)[:3]+expect_vs1(2))
        self.assertEqual(live.worker(self.session),1)
        data=json.loads((self.session/'measurement.json').read_text())
        self.assertFalse(data['experiment_pass'])
        self.assertTrue(data['vs1_link_restored'])
        self.assertIn('checksum',data['errors'][0])
        self.assertEqual(data['history'][-1],['vs1','verified:2'])
        self.assertTrue(self.fake_port.closed)

    def test_worker_speculative_early_vs1_success_with_full_checks(self):
        self.state['experiment']='early_vs1_identity'
        self.fake_port=FakePort(expect_vs1(2)+expect_p300()+
               FakeWireFixtures.novel_return()+[(GFA['P09'],b'\x00'),
                                                 (GFA['P87'],b'\x00')])
        self.assertEqual(live.worker(self.session),0)
        data=json.loads((self.session/'measurement.json').read_text())
        self.assertTrue(data['experiment_pass'])
        self.assertTrue(data['vs1_link_restored'])
        self.assertEqual(data['history'][-1],['vs1_early_identity','verified'])
        self.assertEqual(len(data['enq_trace']),3)
        self.assertEqual(data['enq_trace'][2]['enq_wait_ms'],[])
        self.assertTrue(self.fake_port.closed)

    def test_worker_speculative_early_vs1_negative_restores_and_reports(self):
        self.state['experiment']='early_vs1_identity'
        self.fake_port=FakePort(expect_vs1(2)+expect_p300()+
                    [(EOT,b''),(STX+VS1_ID,b'')]+expect_vs1(2))
        self.assertEqual(live.worker(self.session),1)
        data=json.loads((self.session/'measurement.json').read_text())
        self.assertFalse(data['experiment_pass'])
        self.assertTrue(data['vs1_link_restored'])
        self.assertIn('EARLY_VS1_NO_IDENTITY',data['errors'][0])
        self.assertEqual(data['history'][-1],['vs1','verified:2'])
        self.assertTrue(self.fake_port.closed)

    def test_worker_unknown_experiment_refuses_before_service_stop(self):
        self.state['experiment']='unbounded_script'
        with patch.object(live.base,'pause_services',
                          side_effect=AssertionError('NO SERVICE STOP')):
            with self.assertRaisesRegex(live.base.ProbeError,'unknown experiment'):
                live.worker(self.session)

    def test_worker_speculative_wrong_id_reports_failed_not_verified(self):
        self.state['experiment']='early_vs1_identity'
        self.fake_port=FakePort(expect_vs1(2)+expect_p300()+
                    [(EOT,b''),(STX+VS1_ID,b'\x12\x34')]+expect_vs1(2))
        self.assertEqual(live.worker(self.session),1)
        data=json.loads((self.session/'measurement.json').read_text())
        self.assertFalse(data['experiment_pass'])
        self.assertIn('WRONG_IDENTITY',data['errors'][0])
        self.assertEqual(data['history'][-1],['vs1','verified:2'])

    def test_worker_phase_sweep_refuses_if_research_logger_appears(self):
        with patch.object(live,'guard_other_research',
                     side_effect=live.base.ProbeError('rpm logger active')),\
             patch.object(live.base,'pause_services',
                          side_effect=AssertionError('NO SERVICE STOP')):
            self.assertEqual(live.worker(self.session),1)
        data=json.loads((self.session/'measurement.json').read_text())
        self.assertIn('rpm logger active',data['errors'][0])


class CampaignIndependentRecoveryTests(unittest.TestCase):
    def setUp(self):
        td=tempfile.TemporaryDirectory();self.addCleanup(td.cleanup)
        self.root=Path(td.name)
        self.state={'port':'/dev/NO_DEVICE','services':{live.base.MAIN:True},
                    'restore':[live.base.MAIN],'source_sha256':{'dummy':'x'}}

    def test_negative_with_proven_vs1_restoration_avoids_second_eot(self):
        (self.root/'measurement.json').write_text(json.dumps({
            'experiment_pass':False,'vs1_link_restored':True,
            'history':[['vs1','verified:2']]}))
        with patch.object(live.base,'open_serial',
                          side_effect=AssertionError('NO SECOND PORT OPEN'),create=True):
            r=live.link_restore(self.root,self.state)
        self.assertTrue(r['verified']);self.assertFalse(r['attempted'])

    def test_proven_early_vs1_success_skips_redundant_eot(self):
        (self.root/'measurement.json').write_text(json.dumps({
            'experiment_pass':True,'vs1_link_restored':True,
            'history':[['vs1','verified:2'],['p300','verified'],
                       ['vs1_early_identity','verified']]}))
        with patch.object(live.base,'open_serial',
                          side_effect=AssertionError('NO SECOND PORT OPEN'),create=True):
            r=live.link_restore(self.root,self.state)
        self.assertTrue(r['verified']);self.assertFalse(r['attempted'])

    def test_false_restoration_claim_without_last_vs1_proof_causes_recovery(self):
        (self.root/'measurement.json').write_text(json.dumps({
            'experiment_pass':True,'vs1_link_restored':True,
            'history':[['vs1','verified:2'],['p300','verified']]}))
        with patch.object(live,'guard_other_research',lambda :None),\
             patch.object(live.base,'assert_no_owner',lambda _:None,create=True),\
             patch.object(live.base,'open_serial',
                          side_effect=RuntimeError('explicit mock port refused'),create=True):
            r=live.link_restore(self.root,self.state)
        self.assertFalse(r['verified']);self.assertTrue(r['attempted'])
        self.assertIn('mock port refused',r['error'])

    def test_crash_without_measurement_forces_independent_restore(self):
        with patch.object(live,'guard_other_research',lambda :None),\
             patch.object(live.base,'assert_no_owner',lambda _:None,create=True),\
             patch.object(live.base,'open_serial',
                          side_effect=RuntimeError('fake crash cleanup'),create=True):
            r=live.link_restore(self.root,self.state)
        self.assertTrue(r['attempted']);self.assertFalse(r['verified'])

    def test_corrupted_measurement_requires_recovery(self):
        (self.root/'measurement.json').write_text('{BAD-JSON')
        with patch.object(live,'guard_other_research',lambda :None),\
             patch.object(live.base,'assert_no_owner',lambda _:None,create=True),\
             patch.object(live.base,'open_serial',
                          side_effect=RuntimeError('must restore'),create=True):
            r=live.link_restore(self.root,self.state)
        self.assertTrue(r['attempted']);self.assertFalse(r['verified'])



class CampaignRealHealthValidationTests(unittest.TestCase):
    @staticmethod
    def fake_stdout(p80='1;0x4050;20',p06='1;0x4006;00',marker='PRODUCTION_HEALTH=PASS'):
        health={'P80':{'rc':0,'reason':'OK','response':p80,'valid':True},
                'P06':{'rc':0,'reason':'OK','response':p06,'valid':True}}
        return marker+'\nPRODUCTION_HEALTH_JSON='+json.dumps(health)+'\n'

    def run_case(self,stdout,rc=0):
        with patch.object(campaign.subprocess,'run',return_value=types.SimpleNamespace(
             stdout=stdout,returncode=rc)):
            return campaign.verify_health()

    def test_health_real_p80_p06_are_valid(self):
        self.assertTrue(self.run_case(self.fake_stdout()))

    def test_health_nonzero_exit_refused(self):
        self.assertFalse(self.run_case(self.fake_stdout(),rc=1))

    def test_health_only_fake_plan_text_refused(self):
        self.assertFalse(self.run_case('PLAN ONLY. No serial activity.\n'))

    def test_health_wrong_p80_refused(self):
        self.assertFalse(self.run_case(self.fake_stdout(p80='1;0x4050;21')))

    def test_health_ff_rpm_refused(self):
        self.assertFalse(self.run_case(self.fake_stdout(p06='1;0x4006;ff')))

    def test_health_p06_zero_valid_real(self):
        self.assertTrue(self.run_case(self.fake_stdout(p06='1;0x4006;00')))

    def test_health_p06_nonzero_valid_real(self):
        self.assertTrue(self.run_case(self.fake_stdout(p06='1;0x4006;7a')))

    def test_health_malformed_raw_value_refused(self):
        self.assertFalse(self.run_case(self.fake_stdout(p06='1;0x4006;zz')))

    def test_health_extra_marker_refused(self):
        self.assertFalse(self.run_case(self.fake_stdout()+'PRODUCTION_HEALTH=PASS\n'))

    def test_health_error_marker_refused(self):
        self.assertFalse(self.run_case(self.fake_stdout(marker='PRODUCTION_HEALTH=FAIL')))

    def test_health_missing_json_refused(self):
        self.assertFalse(self.run_case('PRODUCTION_HEALTH=PASS\n'))

    def test_health_malformed_json_refused(self):
        self.assertFalse(self.run_case('PRODUCTION_HEALTH=PASS\nPRODUCTION_HEALTH_JSON={BAD\n'))

    def test_health_wrong_p80_status_refused(self):
        raw=self.fake_stdout().replace('"reason": "OK"','"reason": "FAILED"',1)
        self.assertFalse(self.run_case(raw))

    def test_health_unavailable_debug_process_refused(self):
        with patch.object(campaign.subprocess,'run',side_effect=OSError('missing binary')):
            self.assertFalse(campaign.verify_health())

    def test_health_timeout_refused(self):
        with patch.object(campaign.subprocess,'run',side_effect=
                          subprocess.TimeoutExpired(cmd='python3',timeout=35)):
            self.assertFalse(campaign.verify_health())
