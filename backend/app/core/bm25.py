"""Okapi BM25 implemented directly so the ranking is transparent and reproducible."""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

from .text_utils import tokenize


@dataclass
class BM25Index:
    k1: float = 1.5
    b: float = 0.75
    doc_ids: list[str] = field(default_factory=list)
    _tf: list[Counter] = field(default_factory=list)
    _len: list[int] = field(default_factory=list)
    _df: Counter = field(default_factory=Counter)
    _avgdl: float = 0.0

    def build(self, docs: dict[str, str]) -> "BM25Index":
        self.doc_ids, self._tf, self._len, self._df = [], [], [], Counter()
        for doc_id in sorted(docs):
            toks = tokenize(docs[doc_id])
            tf = Counter(toks)
            self.doc_ids.append(doc_id)
            self._tf.append(tf)
            self._len.append(len(toks))
            self._df.update(tf.keys())
        self._avgdl = (sum(self._len) / len(self._len)) if self._len else 0.0
        return self

    @property
    def size(self) -> int:
        return len(self.doc_ids)

    def idf(self, term: str) -> float:
        n, df = self.size, self._df.get(term, 0)
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def scores(self, query: str, restrict_to: set[str] | None = None) -> dict[str, float]:
        q_terms = list(dict.fromkeys(tokenize(query)))
        out: dict[str, float] = {}
        if not q_terms or not self.size:
            return out
        idfs = {t: self.idf(t) for t in q_terms}
        avgdl = self._avgdl or 1.0
        for i, doc_id in enumerate(self.doc_ids):
            if restrict_to is not None and doc_id not in restrict_to:
                continue
            tf, dl = self._tf[i], self._len[i]
            s = 0.0
            for t in q_terms:
                f = tf.get(t, 0)
                if f:
                    s += idfs[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / avgdl))
            if s > 0:
                out[doc_id] = s
        return out

    def search(self, query: str, top_k: int = 100, restrict_to: set[str] | None = None) -> list[tuple[str, float]]:
        sc = self.scores(query, restrict_to)
        return sorted(sc.items(), key=lambda kv: (-kv[1], kv[0]))[:top_k]
