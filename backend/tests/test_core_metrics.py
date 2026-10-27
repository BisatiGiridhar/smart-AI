import math
import unittest

from app.core import metrics as m
from app.core.calibration import PlattScaler


class TestMetrics(unittest.TestCase):
    def test_agreement(self):
        self.assertAlmostEqual(m.pearson([1, 2, 3], [2, 4, 6]), 1.0)
        self.assertIsNone(m.pearson([1, 1, 1], [1, 2, 3]))
        self.assertAlmostEqual(m.spearman([1, 2, 3, 4], [10, 20, 30, 100]), 1.0)
        self.assertAlmostEqual(m.mae([1, 2], [2, 4]), 1.5)
        self.assertAlmostEqual(m.rmse([0, 0], [3, 4]), math.sqrt(12.5))
        self.assertAlmostEqual(m.kendall_tau_b([1, 2, 3], [3, 2, 1]), -1.0)

    def test_retrieval(self):
        ranked = ["a", "b", "c", "d"]
        rel = {"b", "d"}
        self.assertAlmostEqual(m.precision_at_k(ranked, rel, 2), 0.5)
        self.assertAlmostEqual(m.recall_at_k(ranked, rel, 2), 0.5)
        self.assertAlmostEqual(m.reciprocal_rank(ranked, rel), 0.5)
        self.assertIsNone(m.recall_at_k(ranked, set(), 2))

    def test_ndcg(self):
        self.assertAlmostEqual(m.ndcg_at_k(["a", "b"], {"a": 1, "b": 0}, 2), 1.0)
        v = m.ndcg_at_k(["b", "a"], {"a": 1}, 2)
        self.assertAlmostEqual(v, (1 / math.log2(3)) / 1.0)
        self.assertIsNone(m.ndcg_at_k(["a"], {"a": 0}, 1))

    def test_calibration_metrics(self):
        self.assertAlmostEqual(m.brier([1, 0], [1, 0]), 0.0)
        self.assertAlmostEqual(m.ece([0.9, 0.9], [1, 0]), 0.4)
        bins = m.reliability_bins([0.05, 0.95], [0, 1], 10)
        self.assertEqual(bins[0]["count"], 1)
        self.assertEqual(bins[9]["accuracy"], 1.0)

    def test_bootstrap(self):
        ci = m.bootstrap_ci([1, 2, 3, 4, 5], lambda xs: sum(xs) / len(xs), 500, seed=1)
        self.assertTrue(1 <= ci[0] <= 3 <= ci[1] <= 5)
        self.assertIsNone(m.bootstrap_ci([1], lambda xs: 1.0))

    def test_platt(self):
        scores = [i / 20 for i in range(20)]
        labels = [1 if s > 0.5 else 0 for s in scores]
        cal = PlattScaler().fit(scores, labels)
        p = cal.predict([0.1, 0.9])
        self.assertLess(p[0], 0.5)
        self.assertGreater(p[1], 0.5)
        with self.assertRaises(ValueError):
            PlattScaler().fit([0.1] * 12, [1] * 12)
