"""Live-archive-derived regression: no serial, MQTT or service operations."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'tools'))
from handover_acceleration.campaign_forensics import (
    EvidenceError, load_campaign, summarize_campaign, summarize_sweep,
    trace_early_attempt,
)


class ArchivedRealCampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        records=json.loads((HERE/'fixtures/real_campaign_20261009.json').read_text())
        cls.archived=records['summaries']

    def setUp(self):
        self.sweep=copy.deepcopy(self.archived['phase_sweep'])
        self.vs1=copy.deepcopy(self.archived['early_vs1_identity'])
        self.p300=copy.deepcopy(self.archived['early_p300_start'])

    def test_all_seven_real_sweep_rounds_parsed(self):
        x=summarize_sweep(self.sweep)
        self.assertEqual(x['sample_count'],7)
        self.assertEqual([r['label'] for r in x['trials']], list((
            'control_a','vs1_idle_400','vs1_idle_1100','p300_idle_400',
            'p300_idle_1100','both_idle_700','control_b')))

    def test_mean_and_median_are_from_real_not_fake_timing(self):
        x=summarize_sweep(self.sweep)
        self.assertAlmostEqual(x['core_mean_ms'],4645.183,places=3)
        self.assertAlmostEqual(x['core_median_ms'],4669.045,places=3)
        self.assertAlmostEqual(x['core_min_ms'],4499.808,places=3)
        self.assertAlmostEqual(x['core_max_ms'],4730.588,places=3)

    def test_earliest_core_run_is_not_the_fastest_actual_run(self):
        x=summarize_sweep(self.sweep)
        self.assertEqual(x['best_core_label'],'vs1_idle_1100')
        self.assertEqual(x['best_inclusive_label'],'control_a')
        self.assertAlmostEqual(x['trials'][2]['total_including_both_idle_ms'],5599.808,places=3)
        self.assertAlmostEqual(x['inclusive_mean_ms'],5273.754,places=3)

    def test_all_seven_p300_entry_waits_and_return_waits_preserved(self):
        x=summarize_sweep(self.sweep)
        entry=[r['p300_eot_enq_ms'] for r in x['trials']]
        ret=[r['vs1_eot_enq_ms'] for r in x['trials']]
        self.assertEqual(min(entry),1873.021)
        self.assertEqual(max(entry),1998.187)
        self.assertEqual(min(ret),1996.430)
        self.assertEqual(max(ret),1998.104)
        self.assertGreater(x['mean_two_enq_waits_ms'],3900)
        self.assertGreater(x['mean_non_enq_budget_ms'],500)

    def test_old_early_p300_eot_did_not_reset_observed_2s_clock(self):
        x=trace_early_attempt(self.p300,'early_p300_start')
        self.assertAlmostEqual(x['first_eot_to_recovery_eot_ms'],376.323,places=3)
        self.assertAlmostEqual(x['first_eot_to_first_observed_enq_ms'],1997.777,places=3)

    def test_new_early_vs1_eot_did_not_reset_observed_2s_clock(self):
        x=trace_early_attempt(self.vs1,'early_vs1_identity')
        self.assertAlmostEqual(x['first_eot_to_recovery_eot_ms'],375.789,places=3)
        self.assertAlmostEqual(x['first_eot_to_first_observed_enq_ms'],1998.684,places=3)

    def test_negative_hypotheses_not_relabelled_as_success(self):
        result=summarize_campaign(self.sweep,self.vs1,self.p300)
        self.assertEqual(result['verdict'],'NO_VALIDATED_SUB_4_SECOND_HANDOVER')
        self.assertEqual(len(result['early_eot_observations']),2)

    def test_unverified_sweep_rejected(self):
        self.sweep['trials'][3]['verified']=False
        with self.assertRaises(EvidenceError): summarize_sweep(self.sweep)

    def test_missing_trial_does_not_silently_change_averages(self):
        self.sweep['trials'].pop()
        with self.assertRaises(EvidenceError): summarize_sweep(self.sweep)

    def test_reordered_stages_rejected(self):
        self.sweep['trials'][1],self.sweep['trials'][2]=self.sweep['trials'][2],self.sweep['trials'][1]
        with self.assertRaises(EvidenceError): summarize_sweep(self.sweep)

    def test_false_healthy_p06_ff_rejected(self):
        self.sweep['trials'][0]['gfa']['P06']='ff'
        with self.assertRaises(EvidenceError): summarize_sweep(self.sweep)

    def test_non_hex_p06_rejected(self):
        self.sweep['trials'][0]['gfa']['P06']='zz'
        with self.assertRaises(EvidenceError): summarize_sweep(self.sweep)

    def test_wrong_p80_rejected(self):
        self.sweep['trials'][0]['gfa']['P80']='21'
        with self.assertRaises(EvidenceError): summarize_sweep(self.sweep)

    def test_idle_accounting_discrepancy_rejected(self):
        self.sweep['trials'][4]['full_elapsed_after_vs1_idle_ms']-=1000
        with self.assertRaises(EvidenceError): summarize_sweep(self.sweep)

    def test_wrong_early_failure_is_not_good_negative(self):
        self.vs1['measurement_errors']=['KeyboardInterrupt']
        with self.assertRaises(EvidenceError): trace_early_attempt(self.vs1,'early_vs1_identity')

    def test_missing_recovery_proof_rejected(self):
        self.vs1['independent_recovery']['verified']=False
        with self.assertRaises(EvidenceError): trace_early_attempt(self.vs1,'early_vs1_identity')

    def test_two_eot_timestamps_must_be_monotonic(self):
        self.p300['enq_trace'][2]['eot_t_monotonic']-=1
        with self.assertRaises(EvidenceError): trace_early_attempt(self.p300,'early_p300_start')

    def test_multiple_eot_candidate_pairs_rejected(self):
        self.p300['enq_trace'].extend(self.p300['enq_trace'][1:3])
        with self.assertRaises(EvidenceError): trace_early_attempt(self.p300,'early_p300_start')

    def test_malformed_enq_wait_rejected(self):
        self.vs1['enq_trace'][3]['enq_wait_ms'][0]=float('inf')
        with self.assertRaises(EvidenceError): trace_early_attempt(self.vs1,'early_vs1_identity')

    def test_read_only_archived_campaign_loader(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            campaign=root/'campaign-abc'
            campaign.mkdir()
            a=root/'run-sweep'
            b=root/'run-early'
            a.mkdir();b.mkdir()
            (a/'summary.json').write_text(json.dumps(self.sweep))
            (b/'summary.json').write_text(json.dumps(self.vs1))
            proof={'overall_verified':True,'services_restored':True,'errors':[],
                   'independent_link_restore':{'verified':True}}
            (a/'recovery.json').write_text(json.dumps(proof))
            (b/'recovery.json').write_text(json.dumps(proof))
            stages=[dict(stage='phase_sweep',session=str(a),classification='VERIFIED_SUCCESS',
                         production_health_pass=True),
                    dict(stage='early_vs1_identity',session=str(b),
                         classification='HYPOTHESIS_NEGATIVE_RESTORED',
                         production_health_pass=True)]
            (campaign/'campaign.json').write_text(json.dumps(dict(result='EARLY_VS1_NEGATIVE_BUT_RESTORED',stages=stages)))
            x,y=load_campaign(campaign)
            self.assertEqual(x['experiment'],'phase_sweep')
            self.assertEqual(y['experiment'],'early_vs1_identity')

    def test_fail_closed_when_health_gate_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'campaign-test'
            root.mkdir()
            (root/'campaign.json').write_text(json.dumps(dict(result='EARLY_VS1_NEGATIVE_BUT_RESTORED',
                stages=[dict(stage='phase_sweep',production_health_pass=False),
                        dict(stage='early_vs1_identity',production_health_pass=True)])))
            with self.assertRaises(EvidenceError): load_campaign(root)

    def test_no_serial_io_codepath_imported(self):
        import handover_acceleration.campaign_forensics as m
        source=Path(m.__file__).read_text()
        for unsafe in ('import serial','systemctl','Popen(','.write(','.unlink('):
            with self.subTest(token=unsafe):self.assertNotIn(unsafe,source)

if __name__=='__main__':
    unittest.main()
