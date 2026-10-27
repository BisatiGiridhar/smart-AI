"""Leakage-aware reproducible splits.

Jobs and resumes connected through matching records form connected components. Whole
components are assigned to train/validation/test so the same resume or job never appears in
two splits. The seed, ratios and rule are returned for reproducibility.
"""
from __future__ import annotations

import random
from collections import defaultdict


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            if ra < rb:
                self.parent[rb] = ra
            else:
                self.parent[ra] = rb


def component_split(pairs: list[tuple[str, str]], job_ids: list[str], resume_ids: list[str],
                    ratios: tuple[float, float, float] = (0.7, 0.15, 0.15), seed: int = 42) -> dict:
    if abs(sum(ratios) - 1.0) > 1e-6 or any(r < 0 for r in ratios):
        raise ValueError("ratios must be non-negative and sum to 1")
    uf = _UnionFind()
    for j in job_ids:
        uf.find("J:" + j)
    for r in resume_ids:
        uf.find("R:" + r)
    for r, j in pairs:
        uf.union("R:" + r, "J:" + j)
    comps: dict[str, list[str]] = defaultdict(list)
    for node in list(uf.parent):
        comps[uf.find(node)].append(node)
    comp_list = sorted(comps.values(), key=lambda c: min(c))
    rng = random.Random(seed)
    rng.shuffle(comp_list)
    pair_count = defaultdict(int)
    for r, j in pairs:
        pair_count[uf.find("R:" + r)] += 1
    total_pairs = max(1, len(pairs))
    names = ("train", "validation", "test")
    targets = [r * total_pairs for r in ratios]
    filled = [0.0, 0.0, 0.0]
    job_split: dict[str, str] = {}
    resume_split: dict[str, str] = {}
    largest = max((pair_count[uf.find(c[0])] for c in comp_list), default=0)
    unpaired_idx = 0
    for comp in comp_list:
        weight = pair_count[uf.find(comp[0])]
        if weight == 0:
            # isolated record: distribute round-robin by ratio
            idx = _pick_by_ratio(unpaired_idx, ratios)
            unpaired_idx += 1
        else:
            deficits = [targets[i] - filled[i] for i in range(3)]
            idx = max(range(3), key=lambda i: (deficits[i], -i))
            filled[idx] += weight
        for node in comp:
            kind, rid = node.split(":", 1)
            (job_split if kind == "J" else resume_split)[rid] = names[idx]
    return {
        "job_split": job_split,
        "resume_split": resume_split,
        "config": {"seed": seed, "ratios": list(ratios), "rule": "connected-components over job-resume match graph",
                   "components": len(comp_list), "largest_component_pairs": largest,
                   "leakage_free": True},
        "pair_counts": {n: filled[i] for i, n in enumerate(names)},
    }


def _pick_by_ratio(i: int, ratios: tuple[float, float, float]) -> int:
    slot = (i * 0.6180339887) % 1.0  # low-discrepancy, deterministic
    acc = 0.0
    for k, r in enumerate(ratios):
        acc += r
        if slot < acc:
            return k
    return 2
