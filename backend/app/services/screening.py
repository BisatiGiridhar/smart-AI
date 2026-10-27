"""Runs a persisted evaluation (screening) run through the multi-agent pipeline."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..config import get_settings
from ..core.pipeline import PipelineConfig, Providers, TraceRecorder, run_screening
from ..models import AgentExecution, CandidateResult, EvaluationRun, Job, Rubric
from . import llm, model_runtime
from .corpus import load_corpus
from .llm_evaluator import evaluate as llm_evaluate

_BM25_CACHE: dict = {}


def build_providers(workspace_id: str, corpus: str, cfg: PipelineConfig) -> Providers:
    info: dict = {}
    dense = rerank = None
    if cfg.use_dense:
        dense, reason = model_runtime.make_dense_search(workspace_id, corpus)
        if reason:
            info["dense_unavailable_reason"] = reason
    if cfg.use_rerank:
        rerank, reason = model_runtime.make_rerank()
        if reason:
            info["rerank_unavailable_reason"] = reason
    llm_fn = llm_evaluate if (cfg.evaluator == "llm" and llm.status()["configured"]) else None
    s = get_settings()
    info["models"] = {"embedding_model": s.embedding_model if dense else None,
                      "cross_encoder_model": s.cross_encoder_model if rerank else None,
                      "llm": llm.status() if cfg.evaluator == "llm" else None}
    return Providers(dense_search=dense, rerank=rerank, llm_evaluate=llm_fn, info=info)


def config_from_params(params: dict) -> PipelineConfig:
    allowed = PipelineConfig().__dict__.keys()
    cfg = PipelineConfig(**{k: v for k, v in (params or {}).items() if k in allowed})
    if cfg.rrf_k < 0 or cfg.shortlist_size < 1 or not (0 <= cfg.coverage_threshold <= 1):
        raise ValueError("invalid pipeline configuration")
    if cfg.ranking_policy not in {"normalized_verified_score", "lower_bound"}:
        raise ValueError("unknown ranking policy")
    return cfg


def execute_run(db: Session, params: dict, progress) -> dict:
    run = db.get(EvaluationRun, params["run_id"])
    run.status = "running"
    db.commit()
    trace = TraceRecorder(run.trace_id)
    try:
        job = db.get(Job, run.job_id)
        rubric = db.get(Rubric, run.rubric_id)
        if rubric.status != "approved":
            raise RuntimeError("Only an approved rubric can be used for screening.")
        cfg = config_from_params(run.config)
        progress(0.1, "Loading corpus")
        corpus = load_corpus(db, run.workspace_id, run.corpus)
        if not corpus:
            raise RuntimeError("The selected corpus has no resumes (genuine resumes need consent metadata).")
        prov = build_providers(run.workspace_id, run.corpus, cfg)
        progress(0.2, "Running pipeline")
        final, trace = run_screening({"title": job.title, "text": job.text}, rubric.criteria, corpus, list(corpus),
                                     cfg, prov, trace, bm25_cache=_BM25_CACHE)
        for i, e in enumerate(trace.events):
            db.add(AgentExecution(run_id=run.id, trace_id=trace.trace_id, seq=i, agent=e["agent"], status=e["status"],
                                  duration_ms=e["duration_ms"], detail=e["detail"], error=e["error"],
                                  output_summary=e["output_summary"]))
        bm = {d: i + 1 for i, (d, _) in enumerate(final.get("bm25", []))}
        dn = {d: i + 1 for i, (d, _) in enumerate(final.get("dense", []))}
        fused = {f["doc_id"]: (i + 1, f["score"]) for i, f in enumerate(final.get("fused", []))}
        rr = final.get("rerank", {})
        ranking = final.get("ranking", [])
        scores = final.get("scores", {})
        for pos, d in enumerate(ranking, start=1):
            sc = scores.get(d, {})
            needs = bool(sc.get("needs_review"))
            db.add(CandidateResult(run_id=run.id, resume_id=d, final_rank=pos, bm25_rank=bm.get(d), dense_rank=dn.get(d),
                                   rrf_rank=fused.get(d, (None, None))[0], rrf_score=fused.get(d, (None, None))[1],
                                   rerank_score=rr.get(d), score=sc.get("score"), coverage=sc.get("coverage"),
                                   s_low=sc.get("s_low"), s_high=sc.get("s_high"), score_detail=sc,
                                   assessments=final.get("assessments", {}).get(d, []),
                                   feedback=final.get("feedback", {}).get(d, {}), skill_gaps=final.get("gaps", {}).get(d, []),
                                   injection_flags=final.get("injection", {}).get(d, []),
                                   review_status="pending" if needs else "not_required"))
        run.orchestrator = trace.orchestrator
        run.model_info = {**prov.info, "llm_calls": final.get("llm_meta", {}) and len(final["llm_meta"])}
        run.retrieval = {"query": final.get("query"), "bm25_hits": len(bm), "dense_hits": len(dn),
                         "fused": len(fused), "reranked": len(rr), "pool": len(corpus)}
        run.status = "completed"
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        return {"run_id": run.id, "ranked": len(ranking), "orchestrator": trace.orchestrator}
    except Exception as exc:
        db.rollback()
        run = db.get(EvaluationRun, params["run_id"])
        run.status, run.error, run.finished_at = "failed", f"{type(exc).__name__}: {exc}", datetime.now(timezone.utc)
        run.orchestrator = trace.orchestrator
        for i, e in enumerate(trace.events):
            db.add(AgentExecution(run_id=run.id, trace_id=trace.trace_id, seq=i, agent=e["agent"], status=e["status"],
                                  duration_ms=e["duration_ms"], detail=e["detail"], error=e["error"],
                                  output_summary=e["output_summary"]))
        db.commit()
        raise
