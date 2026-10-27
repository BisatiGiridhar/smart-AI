"""Reciprocal Rank Fusion: RRF(d) = sum_r 1 / (k + rank_r(d)), with 1-based ranks."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FusedItem:
    doc_id: str
    score: float
    ranks: dict[str, int]


def reciprocal_rank_fusion(rankings: dict[str, list[str]], k: int = 60) -> list[FusedItem]:
    if k < 0:
        raise ValueError("k must be non-negative")
    scores: dict[str, float] = {}
    ranks: dict[str, dict[str, int]] = {}
    for name, ranked in rankings.items():
        seen: set[str] = set()
        rank = 0
        for doc_id in ranked:
            if doc_id in seen:
                continue
            seen.add(doc_id)
            rank += 1
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
            ranks.setdefault(doc_id, {})[name] = rank
    items = [FusedItem(d, s, ranks[d]) for d, s in scores.items()]
    items.sort(key=lambda it: (-it.score, min(it.ranks.values()), it.doc_id))
    return items
