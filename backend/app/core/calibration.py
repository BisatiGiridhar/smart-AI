"""Platt scaling fitted on a validation split; evaluation must use a separate test split."""
from __future__ import annotations

import math
from dataclasses import dataclass


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1 / (1 + math.exp(-z))
    e = math.exp(z)
    return e / (1 + e)


@dataclass
class PlattScaler:
    a: float = 1.0
    b: float = 0.0
    fitted: bool = False

    def fit(self, scores: list[float], labels: list[int], iters: int = 200, l2: float = 1e-3) -> "PlattScaler":
        if len(scores) != len(labels) or len(scores) < 10:
            raise ValueError("need at least 10 validation examples to fit calibration")
        if len(set(labels)) < 2:
            raise ValueError("validation labels contain a single class; calibration is not identifiable")
        # Platt's target smoothing
        n_pos = sum(labels)
        n_neg = len(labels) - n_pos
        t_pos, t_neg = (n_pos + 1) / (n_pos + 2), 1 / (n_neg + 2)
        t = [t_pos if y else t_neg for y in labels]
        a, b = 0.0, math.log((n_neg + 1) / (n_pos + 1)) * -1
        for _ in range(iters):  # Newton-Raphson on the regularised log loss
            ga = gb = 0.0
            haa = hab = hbb = l2
            for x, ti in zip(scores, t):
                p = _sigmoid(a * x + b)
                d = p - ti
                ga += d * x
                gb += d
                w = p * (1 - p)
                haa += w * x * x
                hab += w * x
                hbb += w
            ga += l2 * a
            det = haa * hbb - hab * hab
            if abs(det) < 1e-12:
                break
            da = (hbb * ga - hab * gb) / det
            db = (haa * gb - hab * ga) / det
            a -= da
            b -= db
            if abs(da) < 1e-9 and abs(db) < 1e-9:
                break
        self.a, self.b, self.fitted = a, b, True
        return self

    def predict(self, scores: list[float]) -> list[float]:
        if not self.fitted:
            raise RuntimeError("calibrator not fitted")
        return [_sigmoid(self.a * x + self.b) for x in scores]
