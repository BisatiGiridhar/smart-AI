"""Unit tests for BM25 and RRF. Texts below are minimal unit-test fixtures, never loaded into the app."""
import unittest

from app.core.bm25 import BM25Index
from app.core.rrf import reciprocal_rank_fusion


class TestBM25(unittest.TestCase):
    def setUp(self):
        self.idx = BM25Index().build({
            "a": "Python developer with Django and PostgreSQL",
            "b": "Java engineer, Spring Boot",
            "c": "Python Python data scientist pandas",
        })

    def test_ranks_term_matches(self):
        res = self.idx.search("python pandas")
        self.assertEqual(res[0][0], "c")
        self.assertIn("a", [d for d, _ in res])
        self.assertNotIn("b", [d for d, _ in res])

    def test_restrict_and_empty(self):
        self.assertEqual([d for d, _ in self.idx.search("python", restrict_to={"a"})], ["a"])
        self.assertEqual(self.idx.search(""), [])

    def test_deterministic(self):
        self.assertEqual(self.idx.search("python"), self.idx.search("python"))


class TestRRF(unittest.TestCase):
    def test_formula(self):
        fused = reciprocal_rank_fusion({"bm25": ["a", "b"], "dense": ["b", "c"]}, k=60)
        scores = {f.doc_id: f.score for f in fused}
        self.assertAlmostEqual(scores["b"], 1 / 62 + 1 / 61)
        self.assertAlmostEqual(scores["a"], 1 / 61)
        self.assertEqual(fused[0].doc_id, "b")
        self.assertEqual(fused[0].ranks, {"bm25": 2, "dense": 1})

    def test_duplicates_ignored(self):
        fused = reciprocal_rank_fusion({"x": ["a", "a", "b"]}, k=0)
        self.assertAlmostEqual({f.doc_id: f.score for f in fused}["b"], 1 / 2)

    def test_negative_k(self):
        with self.assertRaises(ValueError):
            reciprocal_rank_fusion({"x": ["a"]}, k=-1)
