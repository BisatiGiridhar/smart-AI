from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text

from ..config import get_settings
from ..core.agents import AGENTS
from ..core.text_extract import ocr_available
from ..db import engine
from ..models import (GENUINE, SYNTHETIC, AuditLog, BackgroundTask, CalibrationRun, CandidateResult, DatasetVersion,
                      EvaluationRun, ExperimentRun, FairnessAudit, Job, MatchRecord, Resume, SecurityRun)
from ..security.deps import Ctx, require
from ..services import llm, model_runtime
from .common import owned, page_params, row

router = APIRouter(prefix="/api", tags=["system"])


def _langgraph() -> str | None:
    try:
        import langgraph  # noqa: F401
        from importlib.metadata import version
        return version("langgraph")
    except Exception:  # noqa: BLE001
        return None


@router.get("/health")
def health():
    db_ok = True
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "database": db_ok, "app": get_settings().app_name}


@router.get("/system/status")
def system_status(ctx: Ctx = Depends(require("analytics.read"))):
    s = get_settings()
    return {"database": engine.dialect.name, "orchestrator": "langgraph " + v if (v := _langgraph()) else "sequential executor",
            "ocr_available": ocr_available() and s.enable_ocr, "llm": llm.status(), "models": model_runtime.status(),
            "coverage_threshold": s.coverage_threshold, "max_upload_mb": s.max_upload_mb, "environment": s.environment}


@router.get("/system/agents")
def agents(ctx: Ctx = Depends(require("analytics.read"))):
    ms = model_runtime.status()
    llm_ok = llm.status()["configured"]
    avail = {
        "resume_extraction": ("available", "deterministic parser" + (" + OCR" if ocr_available() else "; OCR not installed")),
        "job_requirement_analysis": ("available", "deterministic analyzer"),
        "hybrid_retrieval": ("available" if not ms["embedder_error"] else "partial",
                             "BM25 ready; dense " + ("loads on first use" if not ms["embedder_error"] else f"unavailable: {ms['embedder_error']}")),
        "candidate_reranking": ("available" if not ms["reranker_error"] else "unavailable",
                                ms["reranker_error"] or "cross-encoder loads on first use"),
        "evidence_verification": ("available", "deterministic"),
        "candidate_evaluation": ("available", "deterministic" + (" and LLM" if llm_ok else "; LLM not configured")),
        "candidate_ranking": ("available", "deterministic"), "feedback": ("available", "deterministic"),
        "skill_gap": ("available", "deterministic"), "fairness_audit": ("available", "deterministic"),
        "security_robustness": ("available", "deterministic suite v1"), "calibration": ("available", "needs labelled experiment runs"),
    }
    last = ctx.db.scalars(select(EvaluationRun).where(EvaluationRun.workspace_id == ctx.workspace_id)
                          .order_by(EvaluationRun.created_at.desc())).first()
    return {"agents": [{**a, "availability": avail[a["id"]][0], "availability_detail": avail[a["id"]][1]} for a in AGENTS],
            "orchestrator": _langgraph() and "langgraph" or "sequential",
            "pipeline_order": ["job_requirement_analysis", "hybrid_retrieval", "candidate_reranking", "resume_extraction",
                               "candidate_evaluation", "evidence_verification", "candidate_ranking", "feedback_and_skill_gaps"],
            "latest_run": row(last, ["id", "status", "trace_id", "orchestrator", "created_at"]) if last else None}


@router.get("/dashboard")
def dashboard(ctx: Ctx = Depends(require("analytics.read"))):
    db, ws = ctx.db, ctx.workspace_id

    def count(model, *conds):
        return db.scalar(select(func.count()).select_from(model).where(*conds)) or 0

    versions = db.scalars(select(DatasetVersion).where(DatasetVersion.workspace_id == ws).order_by(DatasetVersion.created_at.desc())).all()
    v_ids = [v.id for v in versions]
    return {
        "counts": {
            "synthetic_resumes": count(Resume, Resume.workspace_id == ws, Resume.source_kind == SYNTHETIC),
            "genuine_resumes": count(Resume, Resume.workspace_id == ws, Resume.source_kind == GENUINE),
            "synthetic_jobs": count(Job, Job.workspace_id == ws, Job.source_kind == SYNTHETIC),
            "genuine_jobs": count(Job, Job.workspace_id == ws, Job.source_kind == GENUINE),
            "matching_records": count(MatchRecord, MatchRecord.dataset_version_id.in_(v_ids)) if v_ids else 0,
            "completed_evaluations": count(EvaluationRun, EvaluationRun.workspace_id == ws, EvaluationRun.status == "completed"),
            "pending_reviews": db.scalar(select(func.count()).select_from(CandidateResult).join(EvaluationRun, EvaluationRun.id == CandidateResult.run_id)
                                         .where(EvaluationRun.workspace_id == ws, CandidateResult.review_status == "pending")) or 0,
            "failed_tasks": count(BackgroundTask, BackgroundTask.workspace_id == ws, BackgroundTask.status == "failed"),
        },
        "datasets": [row(v, ["id", "name", "status", "validation", "revision", "imported_at", "split_config"]) for v in versions[:5]],
        "latest_experiments": [row(e, ["id", "experiment_id", "split", "status", "metrics", "created_at"]) for e in db.scalars(
            select(ExperimentRun).where(ExperimentRun.workspace_id == ws).order_by(ExperimentRun.created_at.desc()).limit(6))],
        "latest_audits": [row(a, ["id", "status", "summary", "created_at"]) for a in db.scalars(
            select(FairnessAudit).where(FairnessAudit.workspace_id == ws).order_by(FairnessAudit.created_at.desc()).limit(3))]
        + [{**row(s, ["id", "status", "summary", "created_at"]), "kind": "security"} for s in db.scalars(
            select(SecurityRun).where(SecurityRun.workspace_id == ws).order_by(SecurityRun.created_at.desc()).limit(3))],
        "recent_tasks": [row(t, ["id", "kind", "status", "progress", "message", "error", "created_at"]) for t in db.scalars(
            select(BackgroundTask).where(BackgroundTask.workspace_id == ws).order_by(BackgroundTask.created_at.desc()).limit(8))],
        "config": {"llm": llm.status(), "models": model_runtime.status(), "orchestrator": _langgraph() and "langgraph" or "sequential"},
    }


@router.get("/analytics")
def analytics(ctx: Ctx = Depends(require("analytics.read"))):
    db, ws = ctx.db, ctx.workspace_id
    runs = db.scalars(select(EvaluationRun).where(EvaluationRun.workspace_id == ws, EvaluationRun.status == "completed")).all()
    run_ids = [r.id for r in runs]
    status_counts, coverage_hist, review_counts = {}, [0] * 10, {}
    if run_ids:
        for c in db.scalars(select(CandidateResult).where(CandidateResult.run_id.in_(run_ids))):
            for p in c.score_detail.get("per_criterion", []):
                status_counts[p["status"]] = status_counts.get(p["status"], 0) + 1
            if c.coverage is not None:
                coverage_hist[min(int(c.coverage * 10), 9)] += 1
            review_counts[c.review_status] = review_counts.get(c.review_status, 0) + 1
    exps = db.scalars(select(ExperimentRun).where(ExperimentRun.workspace_id == ws, ExperimentRun.status == "completed")
                      .order_by(ExperimentRun.experiment_id, ExperimentRun.created_at.desc())).all()
    latest_by_exp = {}
    for e in exps:
        latest_by_exp.setdefault((e.experiment_id, e.split), e)
    cals = db.scalars(select(CalibrationRun).where(CalibrationRun.workspace_id == ws, CalibrationRun.status == "completed")
                      .order_by(CalibrationRun.created_at.desc()).limit(1)).all()
    return {"evaluation_runs": len(runs), "criterion_status_counts": status_counts,
            "coverage_histogram": [{"bucket": f"{i * 10}-{i * 10 + 10}%", "count": n} for i, n in enumerate(coverage_hist)],
            "review_status_counts": review_counts,
            "experiments": [{"experiment_id": k[0], "split": k[1], "run_id": e.id, "metrics": e.metrics,
                             "test_conditions": e.test_conditions} for k, e in sorted(latest_by_exp.items())],
            "latest_calibration": row(cals[0], ["id", "metrics", "created_at"]) if cals else None}


@router.get("/tasks/{task_id}")
def task(task_id: str, ctx: Ctx = Depends(require("analytics.read"))):
    t = owned(ctx.db, BackgroundTask, task_id, ctx.workspace_id, "Task")
    return row(t, ["id", "kind", "status", "progress", "message", "result", "error", "created_at", "started_at", "finished_at"])


@router.get("/tasks")
def tasks(ctx: Ctx = Depends(require("analytics.read"))):
    return [row(t, ["id", "kind", "status", "progress", "message", "error", "created_at", "finished_at"]) for t in ctx.db.scalars(
        select(BackgroundTask).where(BackgroundTask.workspace_id == ctx.workspace_id).order_by(BackgroundTask.created_at.desc()).limit(100))]


@router.get("/audit-logs")
def audit_logs(page: int = 1, size: int = 50, action: str = "", ctx: Ctx = Depends(require("audit.read"))):
    off, lim = page_params(page, size)
    q = select(AuditLog).where(AuditLog.workspace_id == ctx.workspace_id)
    if action:
        q = q.where(AuditLog.action.ilike(f"{action[:60]}%"))
    total = ctx.db.scalar(select(func.count()).select_from(q.subquery()))
    items = ctx.db.scalars(q.order_by(AuditLog.created_at.desc()).offset(off).limit(lim)).all()
    return {"total": total, "items": [row(a, ["id", "user_id", "action", "target_type", "target_id", "details", "ip", "created_at"])
                                      for a in items]}
