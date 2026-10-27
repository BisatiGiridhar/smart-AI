"""Persists and executes experiment runs A-J against an imported, split dataset version."""
from __future__ import annotations

import platform
from datetime import datetime, timezone

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.experiment_runner import EXPERIMENTS, build_pools, run_experiment
from ..core.sanitize import UNTRUSTED_POLICY, wrap_untrusted
from ..models import DatasetVersion, ExperimentRun, Job, MatchRecord, Resume, Rubric
from . import llm
from .corpus import load_corpus
from .screening import build_providers, config_from_params


class _PairScore(BaseModel):
    score: float = Field(ge=0, le=1)
    rationale: str = ""


def llm_pair_scorer(job: dict, text: str):
    block, _ = wrap_untrusted(text[:15000])
    system = ("Rate how well the resume fits the job on a 0-1 scale using only the resume text. " + UNTRUSTED_POLICY +
              ' Respond with JSON only: {"score": number, "rationale": string}')
    res = llm.complete(system, f"Job: {job.get('title')}\n{job['text'][:6000]}\n\nResume:\n{block}")
    meta = {"cost_usd": res.cost_usd, "ok": res.ok}
    if not res.ok:
        raise RuntimeError(f"LLM unavailable: {res.error}")
    try:
        return _PairScore.model_validate(llm.parse_json_object(res.text)).score, meta
    except (ValueError, ValidationError):
        meta["schema_valid"] = False
        return None, meta


def execute(db: Session, params: dict, progress) -> dict:
    run = db.get(ExperimentRun, params["run_id"])
    run.status = "running"
    db.commit()
    try:
        v = db.get(DatasetVersion, run.dataset_version_id)
        if not v.split_config:
            raise RuntimeError("Create a reproducible split for this dataset version first.")
        conf = run.config
        split = run.split
        jobs_q = (select(Job).where(Job.dataset_version_id == v.id, Job.split == split).order_by(Job.source_record_id))
        jobs_rows = list(db.scalars(jobs_q))[: int(conf.get("max_jobs", 100))]
        labels: dict[str, dict[str, float]] = {}
        for m in db.scalars(select(MatchRecord).where(MatchRecord.dataset_version_id == v.id, MatchRecord.split == split,
                                                      MatchRecord.label_value.is_not(None))):
            labels.setdefault(m.job_id, {})[m.resume_id] = m.label_value
        if not labels:
            raise RuntimeError("No labelled matching records in this split; metrics cannot be computed.")
        all_labels = [x for d in labels.values() for x in d.values()]
        lo, hi = float(conf.get("label_min", min(all_labels))), float(conf.get("label_max", max(all_labels)))
        resume_ids = list(db.scalars(select(Resume.id).where(Resume.dataset_version_id == v.id, Resume.split == split)))
        jobs = []
        for j in jobs_rows:
            approved = db.scalars(select(Rubric).where(Rubric.job_id == j.id, Rubric.status == "approved")
                                  .order_by(Rubric.version.desc())).first()
            jobs.append({"id": j.id, "title": j.title, "text": j.text,
                         "criteria": approved.criteria if approved else None,
                         "rubric_source": f"approved v{approved.version}" if approved else "auto-draft (not recruiter-approved)"})
        seed = int(conf.get("seed", 42))
        pools = build_pools(jobs, labels, resume_ids, int(conf.get("negatives_per_job", 30)), seed,
                            bool(conf.get("treat_unjudged_as_irrelevant", True)))
        needed = sorted({d for p in pools.values() for d in p})
        corpus = load_corpus(db, run.workspace_id, f"dataset:{v.id}", ids=needed)
        cfg = config_from_params(conf.get("pipeline", {}))
        prov = build_providers(run.workspace_id, f"dataset:{v.id}", cfg)
        scorer = llm_pair_scorer if llm.status()["configured"] else None
        res = run_experiment(run.experiment_id, jobs, corpus, labels, pools, cfg, prov, (lo, hi),
                             float(conf.get("relevance_threshold", 0.5)), int(conf.get("k", 10)), scorer, seed, progress)
        run.metrics = res["metrics"]
        run.per_job = res["per_job"]
        run.predictions = res["predictions"]
        rubric_sources = {}
        for j in jobs:
            rubric_sources[j["rubric_source"].split(" ")[0]] = rubric_sources.get(j["rubric_source"].split(" ")[0], 0) + 1
        run.test_conditions = {
            "dataset": v.name, "dataset_version_id": v.id, "revision": v.revision, "split": split,
            "split_config": v.split_config, "seed": seed, "label_range": [lo, hi], "pipeline": res.get("config"),
            "providers": prov.info, "llm": llm.status(), "python": platform.python_version(),
            "platform": platform.platform(), "machine": platform.machine(), "processor": platform.processor(),
            "rubrics": rubric_sources, "unjudged_treated_as_irrelevant": bool(conf.get("treat_unjudged_as_irrelevant", True)),
            "synthetic_data": v.is_synthetic,
        }
        run.status = res["status"] if res["status"] != "completed" else "completed"
        if res["status"] == "not_run":
            run.error = res["reason"]
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        return {"status": run.status, "jobs": len(jobs)}
    except Exception as exc:
        db.rollback()
        run = db.get(ExperimentRun, params["run_id"])
        run.status, run.error, run.finished_at = "failed", f"{type(exc).__name__}: {exc}", datetime.now(timezone.utc)
        db.commit()
        raise


def definitions() -> list[dict]:
    return [{"id": k, **{x: y for x, y in v.items() if x != "overrides"}, "overrides": v.get("overrides", {})}
            for k, v in EXPERIMENTS.items()]
