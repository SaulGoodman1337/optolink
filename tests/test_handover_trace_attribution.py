"""Deterministic validation that telemetry chunks are not wire-level timestamps."""
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from handover_acceleration.trace_attribution import trace_attribution,TraceRejected


class TraceAttributionTests(unittest.TestCase):
    def test_eot_waits_and_gap_distinguished(self):
        events=[
          {'direction':'TX','hex':'04','t_monotonic':0.0},
          {'direction':'RX','hex':'05','t_monotonic':2.010},
          {'direction':'TX','hex':'160000','t_monotonic':2.015},
          {'direction':'RX','hex':'06','t_monotonic':2.029},
          {'direction':'TX','hex':'4105000100f80200','t_monotonic':2.056},
          {'direction':'RX','hex':'064107010100f80220c2db','t_monotonic':2.089},
        ]
        x=trace_attribution(events)
        self.assertEqual(len(x['eot_to_enq_host_ms']),1)
        self.assertAlmostEqual(x['eot_to_enq_host_ms'][0]['wait_ms'],2010)
        self.assertEqual(x['inter_request_rx_to_tx_ms'],[5.0,27.0])
        self.assertEqual(len(x['batched_rx_without_per_byte_timestamps']),1)
        self.assertEqual(x['batched_rx_without_per_byte_timestamps'][0]['byte_count'],11)
        self.assertEqual(x['transactions'][0]['operation'],'EOT_RESET')
        self.assertEqual(x['transactions'][1]['operation'],'P300_START')

    def test_second_enq_is_individual_arrival(self):
        events=[{'direction':'TX','hex':'04','t_monotonic':0.0},
                {'direction':'RX','hex':'05','t_monotonic':1.9},
                {'direction':'RX','hex':'05','t_monotonic':4.1}]
        x=trace_attribution(events)
        self.assertEqual([a['wait_ms'] for a in x['eot_to_enq_host_ms']], [1900,4100])
        self.assertEqual(len(x['transactions'][0]['rx_chunks']),2)

    def test_coalesced_enq_bytes_not_counted_as_exact_event(self):
        events=[{'direction':'TX','hex':'04','t_monotonic':0.0},
                {'direction':'RX','hex':'060505','t_monotonic':2.0}]
        x=trace_attribution(events)
        self.assertEqual(len(x['eot_to_enq_host_ms']),0)
        self.assertEqual(len(x['batched_rx_without_per_byte_timestamps']),1)

    def test_early_start_without_enq_not_claimed_as_success(self):
        events=[{'direction':'TX','hex':'04','t_monotonic':0.0},
                {'direction':'TX','hex':'160000','t_monotonic':0.025},
                {'direction':'RX','hex':'15','t_monotonic':0.035}]
        x=trace_attribution(events)
        self.assertEqual(x['eot_to_enq_host_ms'],[])
        self.assertEqual(x['transactions'][1]['first_rx_wait_ms'],10.0)

    def test_non_monotonic_and_invalid_event_refused(self):
        for events in (
           [{'direction':'TX','hex':'04','t_monotonic':2},
            {'direction':'RX','hex':'05','t_monotonic':1}],
           [{'direction':'RX','hex':'foobar','t_monotonic':1}],
           [{'direction':'TX','hex':'04','t_monotonic':float('nan')}],
           []):
            with self.subTest(events=events),self.assertRaises(TraceRejected):
                trace_attribution(events)


if __name__=='__main__':
    unittest.main()
