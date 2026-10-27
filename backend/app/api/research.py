from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..models import (CalibrationRun, CandidateResult, DatasetVersion, EvaluationRun, ExperimentRun,
                      FairnessAudit, SecurityRun)
from ..security.deps import Ctx, require
from ..services import calibration_service, experiments, fairness, security_suite
from ..services.audit import audit_ctx
from ..services.tasks import submit
from .common import owned, row

router = APIRouter(prefix="/api", tags=["research"])


# ---------- fairness ----------
class CFTest(BaseModel):
    resume_id: str
    original: str = Field(min_length=1, max_length=120)
    replacement: str = Field(min_length=1, max_length=120)
    group: str | None = Field(default=None, max_length=60)


class FairnessIn(BaseModel):
    run_id: str
    tests: list[CFTest] = Field(min_length=1, max_length=200)
    tolerance: float = Field(0.0, ge=0, le=1)
    authorized: bool = False
    min_group_n: int = Field(5, ge=2, le=1000)


@router.post("/fairness/audits")
def start_audit(body: FairnessIn, ctx: Ctx = Depends(require("fairness.run"))):
    run = owned(ctx.db, EvaluationRun, body.run_id, ctx.workspace_id, "Evaluation run")
    if run.status != "completed":
        raise HTTPException(409, "The evaluation run has not completed.")
    if run.corpus == "genuine" and not body.authorized:
        raise HTTPException(422, "Confirm that counterfactual testing of genuine records is authorized.")
    members = set(ctx.db.scalars(select(CandidateResult.resume_id).where(CandidateResult.run_id == run.id)))
    for t in body.tests:
        if t.resume_id not in members:
            raise HTTPException(422, f"Resume {t.resume_id} is not part of this run.")
    a = FairnessAudit(workspace_id=ctx.workspace_id, run_id=run.id, created_by=ctx.user.id,
                      config={"tests": [t.model_dump() for t in body.tests], "tolerance": body.tolerance,
                              "min_group_n": body.min_group_n, "authorized": body.authorized})
    ctx.db.add(a)
    ctx.db.commit()
    t = submit(ctx.db, kind="fairness.audit", workspace_id=ctx.workspace_id, user_id=ctx.user.id,
               params={"audit_id": a.id}, fn=fairness.execute)
    audit_ctx(ctx, "fairness.start", "fairness_audit", a.id, {"tests": len(body.tests)})
    return {"audit_id": a.id, "task_id": t.id}


F_FIELDS = ["id", "run_id", "config", "status", "results", "summary", "error", "created_at"]


@router.get("/fairness/audits")
def list_audits(ctx: Ctx = Depends(require("fairness.run"))):
    return [row(a, ["id", "run_id", "status", "summary", "error", "created_at"]) for a in ctx.db.scalars(
        select(FairnessAudit).where(FairnessAudit.workspace_id == ctx.workspace_id).order_by(FairnessAudit.created_at.desc()).limit(100))]


@router.get("/fairness/audits/{aid}")
def get_audit(aid: str, ctx: Ctx = Depends(require("fairness.run"))):
    return row(owned(ctx.db, FairnessAudit, aid, ctx.workspace_id, "Audit"), F_FIELDS)


@router.get("/fairness/audits/{aid}/export.csv")
def export_audit(aid: str, ctx: Ctx = Depends(require("fairness.run"))):
    a = owned(ctx.db, FairnessAudit, aid, ctx.workspace_id, "Audit")
    buf = io.StringIO()
    cols = ["resume_id", "original", "replacement", "group", "status", "score_original", "score_counterfactual", "abs_gap",
            "rank_original", "rank_counterfactual", "pairwise_flip_rate", "evidence_status_changed", "flagged", "error"]
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in a.results:
        w.writerow(r)
    audit_ctx(ctx, "fairness.export", "fairness_audit", a.id)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename=fairness-{a.id[:8]}.csv"})


# ---------- security ----------
class SecurityIn(BaseModel):
    run_id: str | None = None
    sample: int = Field(5, ge=1, le=50)


@router.post("/security/runs")
def start_security(body: SecurityIn, ctx: Ctx = Depends(require("security.run"))):
    if body.run_id:
        owned(ctx.db, EvaluationRun, body.run_id, ctx.workspace_id, "Evaluation run")
    sr = SecurityRun(workspace_id=ctx.workspace_id, suite_version=security_suite.SUITE_VERSION, created_by=ctx.user.id,
                     config=body.model_dump())
    ctx.db.add(sr)
    ctx.db.commit()
    t = submit(ctx.db, kind="security.run", workspace_id=ctx.workspace_id, user_id=ctx.user.id,
               params={"security_run_id": sr.id}, fn=security_suite.execute)
    audit_ctx(ctx, "security.start", "security_run", sr.id)
    return {"security_run_id": sr.id, "task_id": t.id}


@router.get("/security/runs")
def list_security(ctx: Ctx = Depends(require("security.run"))):
    return [row(s, ["id", "suite_version", "status", "summary", "error", "created_at"]) for s in ctx.db.scalars(
        select(SecurityRun).where(SecurityRun.workspace_id == ctx.workspace_id).order_by(SecurityRun.created_at.desc()).limit(50))]


@router.get("/security/runs/{sid}")
def get_security(sid: str, ctx: Ctx = Depends(require("security.run"))):
    return row(owned(ctx.db, SecurityRun, sid, ctx.workspace_id, "Security run"),
               ["id", "suite_version", "config", "status", "results", "summary", "error", "created_at"])


# ---------- experiments ----------
@router.get("/experiments/definitions")
def exp_defs(ctx: Ctx = Depends(require("analytics.read"))):
    return experiments.definitions()


class ExperimentIn(BaseModel):
    experiment_id: str = Field(pattern="^[A-J]$")
    dataset_version_id: str
    split: str = Field("test", pattern="^(validation|test)$")
    max_jobs: int = Field(100, ge=1, le=5000)
    negatives_per_job: int = Field(30, ge=0, le=500)
    treat_unjudged_as_irrelevant: bool = True
    relevance_threshold: float = Field(0.5, ge=0, le=1)
    k: int = Field(10, ge=1, le=100)
    seed: int = 42
    pipeline: dict = Field(default_factory=lambda: {"shortlist_size": 10})


@router.post("/experiments/runs")
def start_experiment(body: ExperimentIn, ctx: Ctx = Depends(require("experiment.run"))):
    v = owned(ctx.db, DatasetVersion, body.dataset_version_id, ctx.workspace_id, "Dataset version")
    if v.status != "imported" or not v.split_config:
        raise HTTPException(409, "Import the dataset and create a split first.")
    er = ExperimentRun(workspace_id=ctx.workspace_id, dataset_version_id=v.id, experiment_id=body.experiment_id,
                       split=body.split, config=body.model_dump(), created_by=ctx.user.id)
    ctx.db.add(er)
    ctx.db.commit()
    t = submit(ctx.db, kind="experiment.run", workspace_id=ctx.workspace_id, user_id=ctx.user.id,
               params={"run_id": er.id}, fn=experiments.execute)
    audit_ctx(ctx, "experiment.start", "experiment_run", er.id, {"experiment": body.experiment_id, "split": body.split})
    return {"experiment_run_id": er.id, "task_id": t.id}


E_FIELDS = ["id", "dataset_version_id", "experiment_id", "split", "config", "status", "metrics", "test_conditions", "error",
            "created_at", "finished_at"]


@router.get("/experiments/runs")
def list_experiments(ctx: Ctx = Depends(require("analytics.read"))):
    return [row(e, E_FIELDS) for e in ctx.db.scalars(select(ExperimentRun).where(ExperimentRun.workspace_id == ctx.workspace_id)
                                                     .order_by(ExperimentRun.created_at.desc()).limit(200))]


@router.get("/experiments/runs/{eid}")
def get_experiment(eid: str, ctx: Ctx = Depends(require("analytics.read"))):
    e = owned(ctx.db, ExperimentRun, eid, ctx.workspace_id, "Experiment run")
    return {**row(e, E_FIELDS), "per_job": e.per_job[:500]}


@router.get("/experiments/compare")
def compare(a: str, b: str, metric: str = "ndcg@10", ctx: Ctx = Depends(require("analytics.read"))):
    from ..core.metrics import wilcoxon_signed_rank
    ea = owned(ctx.db, ExperimentRun, a, ctx.workspace_id, "Experiment run")
    eb = owned(ctx.db, ExperimentRun, b, ctx.workspace_id, "Experiment run")
    if ea.dataset_version_id != eb.dataset_version_id or ea.split != eb.split or ea.config.get("seed") != eb.config.get("seed"):
        raise HTTPException(422, "Paired comparison needs the same dataset version, split and seed.")
    va = {p["job_id"]: p.get(metric) for p in ea.per_job if p.get(metric) is not None}
    vb = {p["job_id"]: p.get(metric) for p in eb.per_job if p.get(metric) is not None}
    common = sorted(set(va) & set(vb))
    return {"metric": metric, "paired_jobs": len(common), "a": ea.experiment_id, "b": eb.experiment_id,
            "wilcoxon": wilcoxon_signed_rank([va[j] for j in common], [vb[j] for j in common])}


# ---------- calibration ----------
class CalibrationIn(BaseModel):
    validation_run_id: str
    test_run_id: str
    bins: int = Field(10, ge=5, le=30)


@router.post("/calibration/runs")
def start_calibration(body: CalibrationIn, ctx: Ctx = Depends(require("experiment.run"))):
    owned(ctx.db, ExperimentRun, body.validation_run_id, ctx.workspace_id, "Experiment run")
    owned(ctx.db, ExperimentRun, body.test_run_id, ctx.workspace_id, "Experiment run")
    c = CalibrationRun(workspace_id=ctx.workspace_id, validation_run_id=body.validation_run_id, test_run_id=body.test_run_id,
                       config={"bins": body.bins}, created_by=ctx.user.id)
    ctx.db.add(c)
    ctx.db.commit()
    t = submit(ctx.db, kind="calibration.run", workspace_id=ctx.workspace_id, user_id=ctx.user.id,
               params={"calibration_id": c.id}, fn=calibration_service.execute)
    audit_ctx(ctx, "calibration.start", "calibration_run", c.id)
    return {"calibration_id": c.id, "task_id": t.id}


@router.get("/calibration/runs")
def list_calibration(ctx: Ctx = Depends(require("analytics.read"))):
    return [row(c, ["id", "validation_run_id", "test_run_id", "method", "config", "params", "metrics", "bins", "status", "error",
                    "created_at"]) for c in ctx.db.scalars(select(CalibrationRun).where(CalibrationRun.workspace_id == ctx.workspace_id)
                                                           .order_by(CalibrationRun.created_at.desc()).limit(50))]


@router.get("/reports/experiments.csv")
def export_experiments(ctx: Ctx = Depends(require("analytics.read"))):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["experiment", "run_id", "split", "status", "jobs", "pearson", "spearman", "mae", "rmse", "ndcg@10", "ndcg@10_ci_low",
                "ndcg@10_ci_high", "mrr", "p95_seconds_per_job", "cost_per_resume_usd", "synthetic_data"])
    for e in ctx.db.scalars(select(ExperimentRun).where(ExperimentRun.workspace_id == ctx.workspace_id)
                            .order_by(ExperimentRun.experiment_id, ExperimentRun.created_at)):
        m = e.metrics or {}
        nd = m.get("ndcg@10") or {}
        ci = nd.get("ci95") or [None, None]
        w.writerow([e.experiment_id, e.id, e.split, e.status, m.get("jobs_evaluated"), m.get("pearson"), m.get("spearman"),
                    m.get("mae"), m.get("rmse"), nd.get("mean"), ci[0], ci[1], (m.get("mrr") or {}).get("mean"),
                    m.get("p95_seconds_per_job"), m.get("cost_per_resume_usd"), (e.test_conditions or {}).get("synthetic_data")])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=experiments.csv"})


