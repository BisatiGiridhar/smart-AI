"""Counterfactual fairness audits. Only auditor-specified tokens are substituted; protected
characteristics are never inferred. Results apply only to the substitutions tested."""
from __future__ import annotations


from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core import metrics as M
from ..core.counterfactual import pairwise_flip_rate, substitute, unexpected_changes
from ..core.pipeline import TraceRecorder, run_screening
from ..models import CandidateResult, EvaluationRun, FairnessAudit, Job, Rubric
from .corpus import load_corpus
from .screening import build_providers, config_from_params


def execute(db: Session, params: dict, progress) -> dict:
    audit = db.get(FairnessAudit, params["audit_id"])
    audit.status = "running"
    db.commit()
    try:
        run = db.get(EvaluationRun, audit.run_id)
        job, rubric = db.get(Job, run.job_id), db.get(Rubric, run.rubric_id)
        cfg = config_from_params(run.config)
        corpus = load_corpus(db, run.workspace_id, run.corpus)
        prov = build_providers(run.workspace_id, run.corpus, cfg)
        stored = {c.resume_id: c for c in db.scalars(select(CandidateResult).where(CandidateResult.run_id == run.id))}
        baseline_rank = [c.resume_id for c in sorted(stored.values(), key=lambda c: c.final_rank or 10**9)]
        tests = audit.config["tests"]  # [{resume_id, original, replacement, group?}]
        tol = float(audit.config.get("tolerance", 0.0))
        results = []
        pool = list(corpus)
        for n, t in enumerate(tests):
            rid = t["resume_id"]
            if rid not in corpus:
                results.append({**t, "status": "error", "error": "resume not in this run's corpus"})
                continue
            original_text = corpus[rid]["text"]
            new_text, spans = substitute(original_text, t["original"], t["replacement"])
            if not spans:
                results.append({**t, "status": "not_applicable", "error": "original token not found in the resume text"})
                continue
            problems = unexpected_changes(original_text, new_text, t["original"], t["replacement"])
            if problems:
                results.append({**t, "status": "error", "error": "substitution changed other text", "problems": problems})
                continue
            cf_corpus = dict(corpus)
            cf_corpus[rid] = {**corpus[rid], "text": new_text, "extraction": None}
            final, _ = run_screening({"title": job.title, "text": job.text}, rubric.criteria, cf_corpus, pool, cfg, prov,
                                     TraceRecorder(), False)
            before = stored.get(rid)
            s0 = before.score if before else None
            s1 = (final.get("scores", {}).get(rid) or {}).get("score")
            after_rank = final.get("ranking", [])
            flip = pairwise_flip_rate(baseline_rank, after_rank, rid) if rid in baseline_rank and rid in after_rank else None
            gap = abs(s1 - s0) if (s0 is not None and s1 is not None) else None
            status_changed = (s0 is None) != (s1 is None)
            flagged = status_changed or (gap is not None and gap > tol) or bool(flip)
            results.append({**t, "status": "completed", "substitutions": len(spans), "score_original": s0,
                            "score_counterfactual": s1, "abs_gap": gap, "rank_original": before.final_rank if before else None,
                            "rank_counterfactual": (after_rank.index(rid) + 1) if rid in after_rank else None,
                            "pairwise_flip_rate": flip, "evidence_status_changed": status_changed, "flagged": flagged})
            progress((n + 1) / len(tests), f"Test {n + 1} of {len(tests)}")
        done = [r for r in results if r["status"] == "completed"]
        gaps = [r["abs_gap"] for r in done if r["abs_gap"] is not None]
        flips = [r["pairwise_flip_rate"] for r in done if r["pairwise_flip_rate"] is not None]
        summary = {"tests_requested": len(tests), "tests_completed": len(done),
                   "mean_abs_counterfactual_score_gap": M.mean(gaps),
                   "mean_abs_gap_ci95": M.bootstrap_ci(gaps, M.mean, 1000) if len(gaps) >= 2 else None,
                   "counterfactual_rank_flip_rate": M.mean(flips), "flagged": sum(1 for r in done if r["flagged"]),
                   "worst_group_error_gap": None,
                   "worst_group_note": "Not computed: requires valid, authorized group labels and reference labels.",
                   "model_info": prov.info, "rubric_id": rubric.id, "rubric_version": rubric.version,
                   "limitation": "Results apply only to the substitutions tested and do not establish that the system is fair."}
        groups = {}
        for r in done:
            if r.get("group") and r["abs_gap"] is not None:
                groups.setdefault(r["group"], []).append(r["abs_gap"])
        if len(groups) >= 2 and all(len(v) >= int(audit.config.get("min_group_n", 5)) for v in groups.values()):
            means = {g: M.mean(v) for g, v in groups.items()}
            summary["per_group_mean_abs_gap"] = means
            summary["group_gap_spread"] = max(means.values()) - min(means.values())
            summary["group_note"] = "Group labels were supplied by the auditor for the substituted tokens, not inferred."
        audit.results, audit.summary, audit.status = results, summary, "completed"
        db.commit()
        return {"completed": len(done)}
    except Exception as exc:
        db.rollback()
        audit = db.get(FairnessAudit, params["audit_id"])
        audit.status, audit.error = "failed", f"{type(exc).__name__}: {exc}"
        db.commit()
        raise
