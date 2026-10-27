"""Evaluation metrics. Every function returns None when the metric is undefined for the input."""
from __future__ import annotations

import math
import random
from typing import Callable, Sequence


def _finite(xs: Sequence[float]) -> bool:
    return all(isinstance(x, (int, float)) and math.isfinite(x) for x in xs)


def mae(y: Sequence[float], h: Sequence[float]) -> float | None:
    if not y or len(y) != len(h):
        return None
    return sum(abs(a - b) for a, b in zip(y, h)) / len(y)


def rmse(y: Sequence[float], h: Sequence[float]) -> float | None:
    if not y or len(y) != len(h):
        return None
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(y, h)) / len(y))


def pearson(x: Sequence[float], y: Sequence[float]) -> float | None:
    n = len(x)
    if n < 2 or n != len(y) or not _finite(x) or not _finite(y):
        return None
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    if sxx == 0 or syy == 0:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / math.sqrt(sxx * syy)


def average_ranks(x: Sequence[float]) -> list[float]:
    order = sorted(range(len(x)), key=lambda i: x[i])
    ranks = [0.0] * len(x)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and x[order[j + 1]] == x[order[i]]:
            j += 1
        r = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = r
        i = j + 1
    return ranks


def spearman(x: Sequence[float], y: Sequence[float]) -> float | None:
    if len(x) < 2 or len(x) != len(y):
        return None
    return pearson(average_ranks(x), average_ranks(y))


def kendall_tau_b(x: Sequence[float], y: Sequence[float]) -> float | None:
    n = len(x)
    if n < 2 or n != len(y):
        return None
    conc = disc = tx = ty = 0
    for i in range(n):
        for j in range(i + 1, n):
            dx, dy = x[i] - x[j], y[i] - y[j]
            if dx == 0 and dy == 0:
                continue
            if dx == 0:
                tx += 1
            elif dy == 0:
                ty += 1
            elif (dx > 0) == (dy > 0):
                conc += 1
            else:
                disc += 1
    denom = math.sqrt((conc + disc + tx) * (conc + disc + ty))
    return None if denom == 0 else (conc - disc) / denom


def precision_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float | None:
    if k <= 0:
        return None
    top = list(ranked)[:k]
    return sum(1 for d in top if d in relevant) / k


def recall_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float | None:
    if not relevant:
        return None
    return sum(1 for d in list(ranked)[:k] if d in relevant) / len(relevant)


def reciprocal_rank(ranked: Sequence[str], relevant: set[str]) -> float | None:
    if not relevant:
        return None
    for i, d in enumerate(ranked, start=1):
        if d in relevant:
            return 1.0 / i
    return 0.0


def dcg(gains: Sequence[float]) -> float:
    return sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(gains))


def ndcg_at_k(ranked: Sequence[str], gains: dict[str, float], k: int) -> float | None:
    """Graded nDCG@k (Jarvelin and Kekalainen). ``gains`` maps doc id to relevance >= 0."""
    ideal = sorted((g for g in gains.values() if g > 0), reverse=True)[:k]
    idcg = dcg(ideal)
    if idcg == 0:
        return None
    return dcg([gains.get(d, 0.0) for d in list(ranked)[:k]]) / idcg


def brier(p: Sequence[float], o: Sequence[int]) -> float | None:
    if not p or len(p) != len(o):
        return None
    return sum((a - b) ** 2 for a, b in zip(p, o)) / len(p)


def reliability_bins(p: Sequence[float], o: Sequence[int], n_bins: int = 10) -> list[dict]:
    bins = [{"lower": i / n_bins, "upper": (i + 1) / n_bins, "count": 0, "sum_p": 0.0, "sum_o": 0}
            for i in range(n_bins)]
    for pi, oi in zip(p, o):
        idx = min(int(pi * n_bins), n_bins - 1)
        b = bins[idx]
        b["count"] += 1
        b["sum_p"] += pi
        b["sum_o"] += oi
    out = []
    for b in bins:
        c = b["count"]
        out.append({"lower": b["lower"], "upper": b["upper"], "count": c,
                    "confidence": (b["sum_p"] / c) if c else None,
                    "accuracy": (b["sum_o"] / c) if c else None})
    return out


def ece(p: Sequence[float], o: Sequence[int], n_bins: int = 10) -> float | None:
    n = len(p)
    if n == 0 or n != len(o):
        return None
    total = 0.0
    for b in reliability_bins(p, o, n_bins):
        if b["count"]:
            total += b["count"] / n * abs(b["accuracy"] - b["confidence"])
    return total


def percentile(xs: Sequence[float], q: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    pos = (len(s) - 1) * q / 100
    lo, hi = math.floor(pos), math.ceil(pos)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def bootstrap_ci(values: Sequence, statistic: Callable[[list], float | None], n_resamples: int = 1000,
                 alpha: float = 0.05, seed: int = 0) -> tuple[float, float] | None:
    """Percentile bootstrap CI over resampled units (e.g. jobs)."""
    vals = list(values)
    if len(vals) < 2:
        return None
    rng = random.Random(seed)
    stats = []
    for _ in range(n_resamples):
        sample = [vals[rng.randrange(len(vals))] for _ in vals]
        s = statistic(sample)
        if s is not None and math.isfinite(s):
            stats.append(s)
    if len(stats) < n_resamples * 0.5:
        return None
    lo, hi = percentile(stats, 100 * alpha / 2), percentile(stats, 100 * (1 - alpha / 2))
    return (lo, hi) if lo is not None and hi is not None else None


def mean(xs: Sequence[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def wilcoxon_signed_rank(a: Sequence[float], b: Sequence[float]) -> dict | None:
    """Paired Wilcoxon signed-rank test via SciPy when available."""
    if len(a) != len(b) or len(a) < 6:
        return None
    diffs = [x - y for x, y in zip(a, b)]
    if all(d == 0 for d in diffs):
        return {"statistic": 0.0, "p_value": 1.0, "n": len(a), "note": "all paired differences are zero"}
    try:
        from scipy.stats import wilcoxon
    except ImportError:  # pragma: no cover
        return None
    res = wilcoxon(a, b)
    return {"statistic": float(res.statistic), "p_value": float(res.pvalue), "n": len(a)}
