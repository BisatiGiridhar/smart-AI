from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from ..core.job_parser import analyze_job, draft_rubric
from ..core.pipeline import PipelineConfig, TraceRecorder, run_screening
from ..models import (GENUINE, AgentExecution, CandidateResult, EvaluationRun, Job, Resume, Review, Rubric)
from ..security.deps import Ctx, require
from ..services import model_runtime
from ..services.audit import audit_ctx
from ..services.corpus import load_corpus, parse_corpus_key
from ..services.indexing import build_index
from ..services.screening import _BM25_CACHE, build_providers, config_from_params, execute_run
from ..services.tasks import submit
from .common import owned, row

router = APIRouter(prefix="/api", tags=["screening"])
RUN_FIELDS = ["id", "job_id", "rubric_id", "corpus", "config", "model_info", "status", "trace_id", "orchestrator",
              "retrieval", "error", "created_at", "finished_at"]
CR_FIELDS = ["id", "resume_id", "final_rank", "bm25_rank", "dense_rank", "rrf_rank", "rrf_score", "rerank_score", "score",
             "coverage", "s_low", "s_high", "review_status", "created_at"]


def _corpus_guard(ctx: Ctx, corpus: str) -> None:
    try:
        kind, _ = parse_corpus_key(corpus)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    if kind == GENUINE and not ctx.can("resume.read_genuine"):
        raise HTTPException(403, "Your role cannot process genuine candidate records.")


class SearchIn(BaseModel):
    job_id: str
    corpus: str
    shortlist_size: int = Field(25, ge=1, le=200)
    rrf_k: int = Field(60, ge=0, le=1000)
    use_dense: bool = True
    use_rerank: bool = True
    rerank_top_n: int = Field(20, ge=1, le=100)


@router.post("/search")
def search(body: SearchIn, ctx: Ctx = Depends(require("search.run"))):
    _corpus_guard(ctx, body.corpus)
    job = owned(ctx.db, Job, body.job_id, ctx.workspace_id, "Job")
    rub = ctx.db.scalars(select(Rubric).where(Rubric.job_id == job.id, Rubric.status == "approved").order_by(Rubric.version.desc())).first()
    criteria = rub.criteria if rub else draft_rubric(job.analysis or analyze_job(job.text, job.title))
    if not criteria:
        raise HTTPException(422, "No criteria could be derived from this job. Add an approved rubric.")
    corpus = load_corpus(ctx.db, ctx.workspace_id, body.corpus)
    if not corpus:
        return {"results": [], "message": "The selected corpus has no resumes yet."}
    cfg = PipelineConfig(evaluate=False, shortlist_size=body.shortlist_size, rrf_k=body.rrf_k, use_dense=body.use_dense,
                         use_rerank=body.use_rerank, rerank_top_n=body.rerank_top_n)
    prov = build_providers(ctx.workspace_id, body.corpus, cfg)
    final, trace = run_screening({"title": job.title, "text": job.text}, criteria, corpus, list(corpus), cfg, prov,
                                 TraceRecorder(), False, _BM25_CACHE)
    bm = {d: (i + 1, s) for i, (d, s) in enumerate(final.get("bm25", []))}
    dn = {d: (i + 1, s) for i, (d, s) in enumerate(final.get("dense", []))}
    fz = {f["doc_id"]: (i + 1, f["score"]) for i, f in enumerate(final.get("fused", []))}
    rr = final.get("rerank", {})
    results = []
    for pos, d in enumerate(final.get("shortlist", []), start=1):
        results.append({"resume_id": d, "display_ref": corpus[d]["display_ref"], "final_position": pos,
                        "bm25_rank": bm.get(d, (None,))[0], "bm25_score": bm.get(d, (None, None))[1],
                        "dense_rank": dn.get(d, (None,))[0], "dense_similarity": dn.get(d, (None, None))[1],
                        "rrf_rank": fz.get(d, (None,))[0], "rrf_score": fz.get(d, (None, None))[1],
                        "cross_encoder_score": rr.get(d), "snippet": corpus[d]["text"][:280]})
    return {"query": final.get("query"), "criteria_source": f"approved rubric v{rub.version}" if rub else "auto-draft from job text",
            "results": results, "trace": trace.events, "providers": prov.info, "pool_size": len(corpus),
            "score_note": "BM25, cosine similarity, RRF and cross-encoder values are retrieval scores, not probabilities "
                          "and not measures of candidate merit."}


class IndexIn(BaseModel):
    corpus: str


@router.post("/index/build")
def index_build(body: IndexIn, ctx: Ctx = Depends(require("search.run"))):
    _corpus_guard(ctx, body.corpus)
    t = submit(ctx.db, kind="index.build", workspace_id=ctx.workspace_id, user_id=ctx.user.id,
               params={"workspace_id": ctx.workspace_id, "corpus": body.corpus}, fn=build_index)
    audit_ctx(ctx, "index.build", "corpus", body.corpus)
    return {"task_id": t.id}


@router.get("/index/status")
def index_status(corpus: str, ctx: Ctx = Depends(require("search.run"))):
    _corpus_guard(ctx, corpus)
    return model_runtime.status(ctx.workspace_id, corpus)


class RunIn(BaseModel):
    job_id: str
    rubric_id: str
    corpus: str
    config: dict = Field(default_factory=dict)


@router.post("/evaluations")
def start_run(body: RunIn, ctx: Ctx = Depends(require("evaluation.run"))):
    _corpus_guard(ctx, body.corpus)
    job = owned(ctx.db, Job, body.job_id, ctx.workspace_id, "Job")
    rub = ctx.db.get(Rubric, body.rubric_id)
    if rub is None or rub.job_id != job.id:
        raise HTTPException(404, "Rubric not found for this job.")
    if rub.status != "approved":
        raise HTTPException(409, "Approve the rubric before running an evaluation.")
    try:
        cfg = config_from_params(body.config)
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc))
    run = EvaluationRun(workspace_id=ctx.workspace_id, job_id=job.id, rubric_id=rub.id, corpus=body.corpus,
                        config=cfg.to_dict(), created_by=ctx.user.id)
    ctx.db.add(run)
    ctx.db.commit()
    t = submit(ctx.db, kind="evaluation.run", workspace_id=ctx.workspace_id, user_id=ctx.user.id,
               params={"run_id": run.id}, fn=execute_run)
    audit_ctx(ctx, "evaluation.start", "evaluation_run", run.id, {"job": job.id, "rubric_version": rub.version})
    return {"run_id": run.id, "task_id": t.id}


@router.get("/evaluations")
def list_runs(job_id: str | None = None, ctx: Ctx = Depends(require("evaluation.read"))):
    q = select(EvaluationRun).where(EvaluationRun.workspace_id == ctx.workspace_id)
    if job_id:
        q = q.where(EvaluationRun.job_id == job_id)
    runs = ctx.db.scalars(q.order_by(EvaluationRun.created_at.desc()).limit(100)).all()
    out = []
    for r in runs:
        d = row(r, RUN_FIELDS)
        j = ctx.db.get(Job, r.job_id)
        d["job_title"] = j.title if j else None
        d["rubric_version"] = ctx.db.get(Rubric, r.rubric_id).version
        d["candidates"] = ctx.db.scalar(select(func.count()).select_from(CandidateResult).where(CandidateResult.run_id == r.id))
        out.append(d)
    return out


@router.get("/evaluations/{run_id}")
def get_run(run_id: str, ctx: Ctx = Depends(require("evaluation.read"))):
    r = owned(ctx.db, EvaluationRun, run_id, ctx.workspace_id, "Evaluation run")
    if r.corpus == "genuine" and not ctx.can("resume.read_genuine"):
        raise HTTPException(403, "Your role cannot view results for genuine candidate records.")
    rub = ctx.db.get(Rubric, r.rubric_id)
    results = ctx.db.scalars(select(CandidateResult).where(CandidateResult.run_id == r.id)
                             .order_by(CandidateResult.final_rank)).all()
    items = []
    for c in results:
        d = row(c, CR_FIELDS)
        res = ctx.db.get(Resume, c.resume_id)
        d["display_ref"] = res.display_ref if res else None
        d["verified"] = c.score_detail.get("verified", [])
        d["unverified"] = c.score_detail.get("unverified", [])
        d["insufficient_evidence"] = c.score_detail.get("insufficient_evidence", False)
        d["review_reasons"] = c.score_detail.get("review_reasons", [])
        d["skills_matched"] = [p["label"] for p in c.score_detail.get("per_criterion", []) if p["status"] == "supported"]
        d["gaps"] = [g["label"] for g in c.skill_gaps]
        items.append(d)
    job = ctx.db.get(Job, r.job_id)
    return {**row(r, RUN_FIELDS), "job_title": job.title, "rubric": {"id": rub.id, "version": rub.version, "criteria": rub.criteria,
            "origin": rub.origin}, "results": items,
            "notice": "Decision support for qualified human reviewers. The ranking is not a hiring decision."}


@router.get("/evaluations/{run_id}/trace")
def trace(run_id: str, ctx: Ctx = Depends(require("evaluation.read"))):
    r = owned(ctx.db, EvaluationRun, run_id, ctx.workspace_id, "Evaluation run")
    ev = ctx.db.scalars(select(AgentExecution).where(AgentExecution.run_id == r.id).order_by(AgentExecution.seq)).all()
    return {"trace_id": r.trace_id, "orchestrator": r.orchestrator, "status": r.status, "error": r.error,
            "events": [row(e, ["seq", "agent", "status", "duration_ms", "detail", "error", "output_summary"]) for e in ev]}


@router.get("/candidate-results/{cid}")
def candidate(cid: str, ctx: Ctx = Depends(require("evaluation.read"))):
    c = ctx.db.get(CandidateResult, cid)
    if c is None:
        raise HTTPException(404, "Result not found.")
    run = owned(ctx.db, EvaluationRun, c.run_id, ctx.workspace_id, "Result")
    res = ctx.db.get(Resume, c.resume_id)
    if res.source_kind == GENUINE and not ctx.can("resume.read_genuine"):
        raise HTTPException(403, "Your role cannot view genuine candidate records.")
    reviews = ctx.db.scalars(select(Review).where(Review.candidate_result_id == c.id).order_by(Review.created_at)).all()
    return {**row(c, CR_FIELDS), "score_detail": c.score_detail, "assessments": c.assessments, "feedback": c.feedback,
            "skill_gaps": c.skill_gaps, "injection_flags": c.injection_flags, "run_id": run.id,
            "resume": {"id": res.id, "display_ref": res.display_ref, "source_kind": res.source_kind, "text": res.text,
                       "pages": res.pages},
            "reviews": [row(v, ["id", "reviewer_id", "decision", "override_score", "comment", "created_at"]) for v in reviews]}


class ReviewIn(BaseModel):
    decision: str = Field(pattern="^(agree|override|needs_information)$")
    override_score: float | None = Field(default=None, ge=0, le=1)
    comment: str = Field(min_length=3, max_length=4000)


@router.post("/candidate-results/{cid}/review")
def review(cid: str, body: ReviewIn, ctx: Ctx = Depends(require("review.write"))):
    c = ctx.db.get(CandidateResult, cid)
    if c is None:
        raise HTTPException(404, "Result not found.")
    owned(ctx.db, EvaluationRun, c.run_id, ctx.workspace_id, "Result")
    if body.decision == "override" and body.override_score is None:
        raise HTTPException(422, "An override needs a score between 0 and 1.")
    v = Review(candidate_result_id=c.id, reviewer_id=ctx.user.id, decision=body.decision,
               override_score=body.override_score, comment=body.comment)
    ctx.db.add(v)
    c.review_status = "reviewed" if body.decision != "needs_information" else "pending"
    ctx.db.commit()
    audit_ctx(ctx, "review.record", "candidate_result", c.id, {"decision": body.decision})
    return {"ok": True, "review_status": c.review_status}


@router.get("/reviews/pending")
def pending(ctx: Ctx = Depends(require("evaluation.read"))):
    q = (select(CandidateResult, EvaluationRun).join(EvaluationRun, EvaluationRun.id == CandidateResult.run_id)
         .where(EvaluationRun.workspace_id == ctx.workspace_id, CandidateResult.review_status == "pending")
         .order_by(EvaluationRun.created_at.desc(), CandidateResult.final_rank).limit(200))
    out = []
    for c, r in ctx.db.execute(q).all():
        if r.corpus == "genuine" and not ctx.can("resume.read_genuine"):
            continue
        res = ctx.db.get(Resume, c.resume_id)
        out.append({"id": c.id, "run_id": r.id, "display_ref": res.display_ref, "final_rank": c.final_rank, "score": c.score,
                    "coverage": c.coverage, "reasons": c.score_detail.get("review_reasons", [])})
    return out
