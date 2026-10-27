import unittest

from app.core.scoring import Assessment, Criterion, compute_score


class TestScoring(unittest.TestCase):
    def crit(self):
        return [Criterion("a", "A", 0.5, 4), Criterion("b", "B", 0.3, 4), Criterion("c", "C", 0.2, 4)]

    def test_formulas(self):
        r = compute_score(self.crit(), [Assessment("a", "supported", 4), Assessment("b", "supported", 2),
                                        Assessment("c", "not_found")])
        # S = (0.5*1 + 0.3*0.5) / 0.8
        self.assertAlmostEqual(r.score, 0.65 / 0.8)
        self.assertAlmostEqual(r.coverage, 0.8)
        self.assertAlmostEqual(r.s_low, 0.65)
        self.assertAlmostEqual(r.s_high, 0.85)
        self.assertEqual(r.unverified, ["c"])

    def test_insufficient_evidence_no_division(self):
        r = compute_score(self.crit(), [Assessment("a", "not_found")])
        self.assertIsNone(r.score)
        self.assertTrue(r.insufficient_evidence)
        self.assertTrue(r.needs_review)
        self.assertAlmostEqual(r.s_high, 1.0)

    def test_missing_not_zero(self):
        # a missing criterion does not drag S down; it lowers coverage instead
        r = compute_score(self.crit(), [Assessment("a", "supported", 4)])
        self.assertAlmostEqual(r.score, 1.0)
        self.assertAlmostEqual(r.coverage, 0.5)

    def test_weights_normalised(self):
        crit = [Criterion("a", "A", 2, 4), Criterion("b", "B", 2, 4)]
        r = compute_score(crit, [Assessment("a", "supported", 4), Assessment("b", "not_found")])
        self.assertAlmostEqual(r.coverage, 0.5)
        self.assertAlmostEqual(r.s_low, 0.5)

    def test_validation(self):
        with self.assertRaises(ValueError):
            compute_score([Criterion("a", "A", -1)], [])
        with self.assertRaises(ValueError):
            compute_score([Criterion("a", "A", 1, 4)], [Assessment("a", "supported", 5)])
        with self.assertRaises(ValueError):
            Assessment("a", "maybe")

    def test_contradicted_flags_review(self):
        r = compute_score([Criterion("a", "A", 1, 4)], [Assessment("a", "contradicted", 2)], coverage_threshold=0)
        self.assertTrue(r.needs_review)
        self.assertAlmostEqual(r.score, 0.5)
