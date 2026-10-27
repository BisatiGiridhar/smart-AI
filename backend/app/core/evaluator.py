"""Deterministic criterion evaluation, feedback perspectives and skill-gap analysis.

Deterministic mode evaluates only what can be checked mechanically: direct skill mentions and
explicit statements of years of experience. Everything else is routed to human review. Absence
of a mention is recorded as ``not_found``, never as proof that the candidate lacks the skill.
"""
from __future__ import annotations

from .evidence import find_term_evidence, verify_citation
from .scoring import Assessment, Criterion


def assess_criterion(c: Criterion, text: str, extraction: dict | None, pages: list[dict] | None,
                     use_extraction: bool = True) -> Assessment:
    if c.kind == "skill":
        terms = c.terms if (use_extraction and c.terms) else (c.label,)
        hits = find_term_evidence(text, terms, pages)
        if hits:
            return Assessment(c.id, "supported", c.max_rating, hits,
                              f"Direct mention of {c.label} found in {len(hits)} passage(s).")
        return Assessment(c.id, "not_found", None, [],
                          f"No mention of {c.label} was found in the resume text. This is not evidence that the "
                          f"candidate lacks the skill.")
    if c.kind == "experience_years":
        stmts = (extraction or {}).get("years_of_experience_statements") or []
        if stmts and c.min_years:
            best = max(stmts, key=lambda s: s["years"])
            check = verify_citation(text, best["quote"], best["start"], best["end"])
            ev = [{"quote": best["quote"], "start": best["start"], "end": best["end"], "page": best.get("page"),
                   "verification": check.reason, "kind": "direct"}]
            if not check.valid:
                return Assessment(c.id, "unsupported", None, ev, "The years-of-experience citation could not be verified.")
            ratio = min(best["years"] / c.min_years, 1.0)
            rating = round(ratio * c.max_rating, 4)
            if best["years"] >= c.min_years:
                return Assessment(c.id, "supported", rating, ev,
                                  f"The resume states {best['years']:g} years; the requirement is {c.min_years:g}.")
            return Assessment(c.id, "contradicted", rating, ev,
                              f"The resume states {best['years']:g} years, below the {c.min_years:g} required. "
                              f"Check whether other experience applies.")
        if (extraction or {}).get("employment_history"):
            return Assessment(c.id, "needs_review", None, [],
                              "Employment date ranges are present but no explicit years-of-experience statement; "
                              "a reviewer should confirm the total.")
        return Assessment(c.id, "not_found", None, [], "No statement of years of experience was found.")
    return Assessment(c.id, "needs_review", None, [],
                      "This criterion needs judgement that the deterministic evaluator does not make.")


def evaluate_resume(criteria: list[Criterion], text: str, extraction: dict | None, pages: list[dict] | None,
                    use_extraction: bool = True) -> list[Assessment]:
    return [assess_criterion(c, text, extraction, pages, use_extraction) for c in criteria]


def verify_assessments(assessments: list[Assessment], text: str) -> tuple[list[Assessment], dict]:
    """Re-check every citation against the stored text. Assessments whose citations all fail are
    downgraded to ``unsupported``; individual failed citations are removed and counted."""
    stats = {"citations_checked": 0, "citations_rejected": 0, "assessments_downgraded": 0}
    out = []
    for a in assessments:
        kept = []
        for ev in a.evidence:
            stats["citations_checked"] += 1
            r = verify_citation(text, ev.get("quote", ""), ev.get("start"), ev.get("end"))
            if r.valid:
                kept.append({**ev, "verification": r.reason})
            else:
                stats["citations_rejected"] += 1
        if a.status in {"supported", "contradicted"} and a.evidence and not kept:
            stats["assessments_downgraded"] += 1
            out.append(Assessment(a.criterion_id, "unsupported", None, [], "All cited evidence failed verification.",
                                  a.method))
        else:
            out.append(Assessment(a.criterion_id, a.status, a.rating, kept, a.explanation, a.method))
    return out, stats


def feedback_perspectives(criteria: list[Criterion], assessments: list[Assessment], extraction: dict | None,
                          score: dict) -> dict:
    by = {a.criterion_id: a for a in assessments}
    skill_c = [c for c in criteria if c.kind == "skill"]
    req_found = [c.label for c in skill_c if c.required and by[c.id].status == "supported"]
    req_missing = [c.label for c in skill_c if c.required and by[c.id].status == "not_found"]
    pref_found = [c.label for c in skill_c if not c.required and by[c.id].status == "supported"]
    ex = extraction or {}
    exp_c = [c for c in criteria if c.kind == "experience_years"]
    technical = []
    if req_found:
        technical.append(f"Evidence found for required skills: {', '.join(req_found)}.")
    if req_missing:
        technical.append(f"No mention found for required skills: {', '.join(req_missing)}.")
    if pref_found:
        technical.append(f"Preferred skills with evidence: {', '.join(pref_found)}.")
    if not technical:
        technical.append("The rubric has no skill criteria to comment on.")
    experience = []
    for c in exp_c:
        experience.append(f"{c.label}: {by[c.id].explanation}")
    n_emp = len(ex.get("employment_history") or [])
    experience.append(f"{n_emp} dated employment or education line(s) were detected." if n_emp
                      else "No dated employment lines were detected.")
    recruiter = [f"Evidence coverage is {score['coverage']:.0%} of the rubric weight."]
    if score.get("insufficient_evidence"):
        recruiter.append("Insufficient evidence to produce a score; this candidate needs manual review.")
    recruiter.extend(score.get("review_reasons") or [])
    recruiter.append("This is decision support. A qualified reviewer makes the decision.")
    return {"technical": technical, "experience": experience, "recruiter": recruiter,
            "note": "Analytical views generated from the same evidence; they are not independent human opinions."}


def skill_gaps(criteria: list[Criterion], assessments: list[Assessment]) -> list[dict]:
    by = {a.criterion_id: a for a in assessments}
    gaps = []
    for c in criteria:
        a = by[c.id]
        if a.status == "not_found":
            gaps.append({"criterion_id": c.id, "label": c.label, "type": "no_evidence", "required": c.required,
                         "detail": "Not found in the resume. This is not proof of absence.",
                         "suggested_next_step": f"Ask the candidate about {c.label} during screening."})
        elif a.status == "contradicted":
            gaps.append({"criterion_id": c.id, "label": c.label, "type": "potential_gap", "required": c.required,
                         "detail": a.explanation, "suggested_next_step": "Confirm with the candidate."})
        elif a.status in {"unsupported", "needs_review"}:
            gaps.append({"criterion_id": c.id, "label": c.label, "type": "needs_review", "required": c.required,
                         "detail": a.explanation, "suggested_next_step": "Reviewer to assess this criterion."})
    return gaps
