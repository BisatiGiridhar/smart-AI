"""Deterministic, recomputable candidate scoring.

For criterion i: s_i = r_i / R_i.  Verified set V, unverified set U.
  S      = sum_{i in V} w_i s_i / sum_{i in V} w_i      normalized verified score
  C      = sum_{i in V} w_i / sum_i w_i                   evidence coverage
With weights normalised to sum to 1:
  S_low  = sum_{i in V} w_i s_i
  S_high = S_low + sum_{i in U} w_i
S ignores unverified criteria. The bounds describe the range the weighted total could take
once the unverified criteria are resolved. They are different quantities.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

VERIFIED_STATUSES = frozenset({"supported", "contradicted"})
ALL_STATUSES = frozenset({"supported", "contradicted", "not_found", "unsupported", "needs_review"})


@dataclass(frozen=True)
class Criterion:
    id: str
    label: str
    weight: float
    max_rating: float = 4.0
    kind: str = "skill"  # skill | experience_years | free_text
    terms: tuple[str, ...] = ()
    required: bool = True
    min_years: float | None = None


@dataclass
class Assessment:
    criterion_id: str
    status: str
    rating: float | None = None
    evidence: list[dict] = field(default_factory=list)
    explanation: str = ""
    method: str = "deterministic"

    def __post_init__(self) -> None:
        if self.status not in ALL_STATUSES:
            raise ValueError(f"unknown status {self.status!r}")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScoreResult:
    score: float | None
    coverage: float
    s_low: float
    s_high: float
    verified: list[str]
    unverified: list[str]
    insufficient_evidence: bool
    needs_review: bool
    review_reasons: list[str]
    per_criterion: list[dict]
    normalized_weights: dict[str, float]

    def to_dict(self) -> dict:
        return asdict(self)


def validate_criteria(criteria: list[Criterion]) -> None:
    if not criteria:
        raise ValueError("rubric has no criteria")
    ids = [c.id for c in criteria]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate criterion ids")
    for c in criteria:
        if c.weight < 0:
            raise ValueError(f"criterion {c.id}: weight must be >= 0")
        if c.max_rating <= 0:
            raise ValueError(f"criterion {c.id}: max_rating must be > 0")
    if sum(c.weight for c in criteria) <= 0:
        raise ValueError("criterion weights must not all be zero")


def compute_score(criteria: list[Criterion], assessments: list[Assessment],
                  coverage_threshold: float = 0.5) -> ScoreResult:
    validate_criteria(criteria)
    by_id = {a.criterion_id: a for a in assessments}
    total_w = sum(c.weight for c in criteria)
    w = {c.id: c.weight / total_w for c in criteria}

    verified: list[str] = []
    unverified: list[str] = []
    per: list[dict] = []
    review: list[str] = []
    num = den = 0.0
    for c in criteria:
        a = by_id.get(c.id)
        status = a.status if a else "not_found"
        s_i = None
        if a is not None and status in VERIFIED_STATUSES and a.rating is not None:
            if not (0 <= a.rating <= c.max_rating):
                raise ValueError(f"criterion {c.id}: rating {a.rating} outside [0, {c.max_rating}]")
            s_i = a.rating / c.max_rating
            verified.append(c.id)
            num += w[c.id] * s_i
            den += w[c.id]
        else:
            unverified.append(c.id)
        if status == "contradicted":
            review.append(f"{c.label}: evidence contradicts the requirement")
        elif status in {"unsupported", "needs_review"}:
            review.append(f"{c.label}: {status.replace('_', ' ')}")
        per.append({"criterion_id": c.id, "label": c.label, "status": status,
                    "rating": a.rating if a else None, "max_rating": c.max_rating,
                    "normalized": s_i, "weight": c.weight, "normalized_weight": w[c.id]})

    coverage = den
    s_low = num
    s_high = s_low + sum(w[i] for i in unverified)
    insufficient = den == 0
    score = None if insufficient else num / den
    if insufficient:
        review.append("Insufficient evidence: no verified criteria")
    elif coverage < coverage_threshold:
        review.append(f"Evidence coverage {coverage:.2f} is below the review threshold {coverage_threshold:.2f}")
    return ScoreResult(score=score, coverage=coverage, s_low=s_low, s_high=min(1.0, s_high),
                       verified=verified, unverified=unverified, insufficient_evidence=insufficient,
                       needs_review=bool(review), review_reasons=review, per_criterion=per,
                       normalized_weights=w)


def criterion_from_dict(d: dict) -> Criterion:
    return Criterion(id=str(d["id"]), label=str(d.get("label", d["id"])), weight=float(d["weight"]),
                     max_rating=float(d.get("max_rating", 4.0)), kind=str(d.get("kind", "skill")),
                     terms=tuple(d.get("terms") or ()), required=bool(d.get("required", True)),
                     min_years=(float(d["min_years"]) if d.get("min_years") is not None else None))


def criterion_to_dict(c: Criterion) -> dict:
    d = asdict(c)
    d["terms"] = list(c.terms)
    return d
