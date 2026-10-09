"""Recalculate timing claims from the 2026-10-08 archived console samples.

Source: docs/p300-goals-and-single-enq-result-2026-10-08.md and
        docs/evidence/p300-handover-baseline-2026-10-08.json
from optolink-p300-migration; no original measurement.json was available.
"""
import statistics
import unittest

BASELINE_MS = [6922.805932001211, 6823.113730060868, 6843.019502935931]
BASELINE_EXTRA_ENQ_MS = [2237.470232998021, 2237.6668649958447, 2237.8985040122643]
SINGLE_MS = [4624.6111950604245, 4568.931228015572, 4636.729417019524]
SINGLE_P300_ENQ_MS = [1996.9262860249728, 1998.9537069341168, 1996.82713591028]
SINGLE_VS1_ENQ_MS = [1997.6557079935446, 1998.1562299653888, 1997.8605279466137]
IDLE_MS = [5611.36752506718, 5637.235827045515, 5636.1030109692365]


class MeasuredBudgetTests(unittest.TestCase):
    def test_baseline_and_single_means(self):
        self.assertAlmostEqual(statistics.mean(BASELINE_MS), 6862.980, delta=.001)
        self.assertAlmostEqual(statistics.mean(SINGLE_MS), 4610.091, delta=.001)
        self.assertAlmostEqual(statistics.mean(BASELINE_EXTRA_ENQ_MS), 2237.679, delta=.001)

    def test_measured_saving_not_exactly_removed_enq(self):
        observed = statistics.mean(BASELINE_MS) - statistics.mean(SINGLE_MS)
        self.assertAlmostEqual(observed, 2252.889, delta=.001)
        self.assertGreater(observed, statistics.mean(BASELINE_EXTRA_ENQ_MS))
        self.assertAlmostEqual(observed / statistics.mean(BASELINE_MS), .32827, delta=.00001)

    def test_enq_waits_dominate_and_sub_four_needs_causal_change(self):
        total = statistics.mean(SINGLE_MS)
        waits = statistics.mean(SINGLE_P300_ENQ_MS) + statistics.mean(SINGLE_VS1_ENQ_MS)
        self.assertAlmostEqual(waits, 3995.46, delta=.01)
        self.assertGreater(waits/total, .86)
        self.assertGreater(total - 4000, 610)
        self.assertGreater(total - 2000, 2610)
        self.assertGreater(total - 1000, 3610)

    def test_idle_enq_negative(self):
        self.assertAlmostEqual(statistics.mean(IDLE_MS) - statistics.mean(SINGLE_MS),
                               1018.145, delta=.001)


if __name__ == "__main__":
    unittest.main()
