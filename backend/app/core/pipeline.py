"""Screening pipeline nodes and orchestration.

Each node is a plain function ``(state) -> partial_state``. The same nodes run either inside a
LangGraph ``StateGraph`` (when LangGraph is installed) or in an explicit sequential executor.
The trace records which orchestrator ran and, for every node, whether it ran, was skipped
(and why) or failed. Nothing is reported as executed unless it executed.
"""
from __future__ import annotations

import time
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, TypedDict

from .bm25 import BM25Index
from .evaluator import evaluate_resume, feedback_perspectives, skill_gaps, verify_assessments
from .resume_parser import parse_resume
from .rrf import reciprocal_rank_fusion
from .sanitize import detect_injection
from .scoring import Assessment, compute_score, criterion_from_dict, validate_criteria


@dataclass
class PipelineConfig:
    use_bm25: bool = True
    use_dense: bool = True
    use_rrf: bool = True
    use_rerank: bool = True
    use_retrieval: bool = True       # False = evaluate the whole candidate pool (experiment B)
    use_extraction: bool = True      # False = ablation H
    use_verification: bool = True    # False = ablation I
    evaluate: bool = True            # False = retrieval-only experiments (C-F)
    top_k_bm25: int = 200
    top_k_dense: int = 200
    rrf_k: int = 60
    shortlist_size: int = 50
    rerank_top_n: int = 30
    coverage_threshold: float = 0.5
    ranking_policy: str = "normalized_verified_score"  # or "lower_bound"
    evaluator: str = "deterministic"  # or "llm"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Providers:
    """Injected model capabilities. ``None`` means unavailable; the node reports it as skipped."""
    dense_search: Callable[[str, set[str] | None, int], list[tuple[str, float]]] | None = None
    rerank: Callable[[str, list[str]], list[float]] | None = None
    llm_evaluate: Callable[[list[dict], str, str], tuple[list[Assessment], dict]] | None = None
    info: dict = field(default_factory=dict)


class ScreeningState(TypedDict, total=False):
    job: dict
    criteria: list[dict]
    corpus: dict
    pool: list[str]
    query: str
    bm25: list[list]
    dense: list[list]
    fused: list[dict]
    shortlist: list[str]
    rerank: dict
    extractions: dict
    assessments: dict
    verification: dict
    scores: dict
    ranking: list[str]
    feedback: dict
    gaps: dict
    injection: dict
    llm_meta: dict


class TraceRecorder:
    def __init__(self, trace_id: str | None = None) -> None:
        self.trace_id = trace_id or uuid.uuid4().hex
        self.events: list[dict] = []
        self.orchestrator = "sequential"

    def record(self, agent: str, status: str, started: float, detail: str = "", error: str | None = None,
               output_summary: dict | None = None) -> None:
        self.events.append({"trace_id": self.trace_id, "agent": agent, "status": status,
                            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                            "detail": detail, "error": error, "output_summary": output_summary or {}})


def build_query(job: dict, criteria: list[dict]) -> str:
    terms = []
    for c in criteria:
        if c.get("kind") == "skill":
            terms.append(c.get("label", ""))
            terms.extend((c.get("terms") or [])[:3])
    title = job.get("title") or ""
    base = " ".join(dict.fromkeys(t for t in terms if t))
    return f"{title} {base}".strip() or (job.get("text") or "")[:2000]


def make_nodes(cfg: PipelineConfig, prov: Providers, trace: TraceRecorder,
               bm25_cache: dict | None = None) -> list[tuple[str, Callable[[ScreeningState], dict]]]:
    def guarded(name: str, fn: Callable[[ScreeningState], tuple[dict, str, str, dict]]):
        def node(state: ScreeningState) -> dict:
            t0 = time.perf_counter()
            try:
                update, status, detail, summary = fn(state)
                trace.record(name, status, t0, detail, output_summary=summary)
                return update
            except Exception as exc:  # noqa: BLE001 - surfaced in the trace and re-raised
                trace.record(name, "failed", t0, "", error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=3)}")
                raise
        node.__name__ = name
        return node

    def job_requirement_analysis(state):
        criteria = state["criteria"]
        validate_criteria([criterion_from_dict(c) for c in criteria])
        q = build_query(state["job"], criteria)
        return {"query": q}, "completed", f"{len(criteria)} approved criteria loaded", {"criteria": len(criteria)}

    def hybrid_retrieval(state):
        pool = state["pool"]
        if not cfg.use_retrieval:
            return ({"shortlist": list(pool), "bm25": [], "dense": [], "fused": []}, "skipped",
                    "retrieval disabled by configuration; whole pool evaluated", {"pool": len(pool)})
        pool_set = set(pool)
        bm, dn, details = [], [], []
        if cfg.use_bm25:
            key = ("bm25", tuple(sorted(pool)))
            idx = bm25_cache.get(key) if bm25_cache is not None else None
            if idx is None:
                idx = BM25Index().build({d: state["corpus"][d]["text"] for d in pool})
                if bm25_cache is not None:
                    bm25_cache[key] = idx
            bm = [[d, s] for d, s in idx.search(state["query"], cfg.top_k_bm25)]
            details.append(f"BM25 {len(bm)} hits")
        dense_status = "not requested"
        if cfg.use_dense:
            if prov.dense_search is None:
                dense_status = "unavailable: " + prov.info.get("dense_unavailable_reason", "no embedding model configured")
            else:
                dn = [[d, s] for d, s in prov.dense_search(state["query"], pool_set, cfg.top_k_dense)]
                dense_status = f"{len(dn)} hits"
            details.append(f"dense {dense_status}")
        rankings = {}
        if bm:
            rankings["bm25"] = [d for d, _ in bm]
        if dn:
            rankings["dense"] = [d for d, _ in dn]
        fused = []
        if cfg.use_rrf and len(rankings) >= 1:
            fused = [{"doc_id": f.doc_id, "score": f.score, "ranks": f.ranks}
                     for f in reciprocal_rank_fusion(rankings, cfg.rrf_k)]
            order = [f["doc_id"] for f in fused]
        else:
            order = rankings.get("bm25") or rankings.get("dense") or []
        shortlist = order[: cfg.shortlist_size]
        status = "completed" if rankings else "completed_no_hits"
        if cfg.use_dense and prov.dense_search is None:
            status = "partial"
        return ({"bm25": bm, "dense": dn, "fused": fused, "shortlist": shortlist}, status, "; ".join(details),
                {"bm25_hits": len(bm), "dense_hits": len(dn), "shortlist": len(shortlist), "rrf_k": cfg.rrf_k})

    def candidate_reranking(state):
        sl = state.get("shortlist", [])
        if not cfg.use_rerank or not cfg.use_retrieval:
            return {"rerank": {}}, "skipped", "reranking disabled by configuration", {}
        if prov.rerank is None:
            return ({"rerank": {}}, "skipped",
                    "unavailable: " + prov.info.get("rerank_unavailable_reason", "no cross-encoder configured"), {})
        head = sl[: cfg.rerank_top_n]
        scores = prov.rerank(state["query"], [state["corpus"][d]["text"] for d in head])
        rr = {d: float(s) for d, s in zip(head, scores)}
        new_head = sorted(head, key=lambda d: (-rr[d], d))
        return ({"rerank": rr, "shortlist": new_head + sl[cfg.rerank_top_n:]}, "completed",
                f"cross-encoder scored {len(head)} pairs", {"pairs": len(head)})

    def resume_extraction(state):
        if not cfg.evaluate:
            return {"extractions": {}}, "skipped", "evaluation not requested", {}
        ex, parsed_now = {}, 0
        for d in state.get("shortlist", []):
            doc = state["corpus"][d]
            if not cfg.use_extraction:
                ex[d] = None
                continue
            if doc.get("extraction"):
                ex[d] = doc["extraction"]
            else:
                ex[d] = parse_resume(doc["text"], doc.get("pages"))
                parsed_now += 1
        status = "completed" if cfg.use_extraction else "skipped"
        detail = (f"{len(ex) - parsed_now} stored extraction(s) reused, {parsed_now} parsed" if cfg.use_extraction
                  else "extraction agent disabled (ablation)")
        return {"extractions": ex}, status, detail, {"documents": len(ex)}

    def candidate_evaluation(state):
        if not cfg.evaluate:
            return {"assessments": {}, "injection": {}}, "skipped", "evaluation not requested", {}
        crit = [criterion_from_dict(c) for c in state["criteria"]]
        out, inj, meta = {}, {}, {}
        for d in state.get("shortlist", []):
            doc = state["corpus"][d]
            inj[d] = detect_injection(doc["text"])
            if cfg.evaluator == "llm":
                if prov.llm_evaluate is None:
                    raise RuntimeError("LLM evaluator requested but no LLM provider is available")
                a, m = prov.llm_evaluate(state["criteria"], doc["text"], d)
                meta[d] = m
            else:
                a = evaluate_resume(crit, doc["text"], state["extractions"].get(d), doc.get("pages"), cfg.use_extraction)
            out[d] = [x.to_dict() for x in a]
        return ({"assessments": out, "injection": inj, "llm_meta": meta}, "completed",
                f"{cfg.evaluator} evaluator over {len(out)} candidate(s)", {"candidates": len(out)})

    def evidence_verification(state):
        if not cfg.evaluate:
            return {"verification": {}}, "skipped", "evaluation not requested", {}
        if not cfg.use_verification:
            return {"verification": {}}, "skipped", "evidence verification disabled (ablation)", {}
        new, stats = {}, {}
        total_rej = 0
        for d, alist in state["assessments"].items():
            verified, st = verify_assessments([Assessment(**a) for a in alist], state["corpus"][d]["text"])
            new[d] = [x.to_dict() for x in verified]
            stats[d] = st
            total_rej += st["citations_rejected"]
        return ({"assessments": new, "verification": stats}, "completed",
                f"{total_rej} citation(s) rejected", {"citations_rejected": total_rej})

    def candidate_ranking(state):
        if not cfg.evaluate:
            order = state.get("shortlist", [])
            return {"scores": {}, "ranking": order}, "skipped", "ranking by retrieval order only", {}
        crit = [criterion_from_dict(c) for c in state["criteria"]]
        scores = {}
        for d, alist in state["assessments"].items():
            r = compute_score(crit, [Assessment(**a) for a in alist], cfg.coverage_threshold).to_dict()
            if state.get("injection", {}).get(d):
                r["needs_review"] = True
                r["review_reasons"].append("Instruction-like text detected in the document")
            scores[d] = r

        def key(d):
            s = scores[d]
            primary = s["s_low"] if cfg.ranking_policy == "lower_bound" else s["score"]
            return (primary is None, -(primary or 0.0), -s["coverage"], d)

        ranking = sorted(scores, key=key)
        return ({"scores": scores, "ranking": ranking}, "completed",
                f"policy={cfg.ranking_policy}", {"ranked": len(ranking)})

    def feedback_and_gaps(state):
        if not cfg.evaluate:
            return {"feedback": {}, "gaps": {}}, "skipped", "evaluation not requested", {}
        crit = [criterion_from_dict(c) for c in state["criteria"]]
        fb, gp = {}, {}
        for d in state["ranking"]:
            a = [Assessment(**x) for x in state["assessments"][d]]
            fb[d] = feedback_perspectives(crit, a, state["extractions"].get(d), state["scores"][d])
            gp[d] = skill_gaps(crit, a)
        return {"feedback": fb, "gaps": gp}, "completed", f"{len(fb)} candidate(s)", {}

    return [
        ("job_requirement_analysis", guarded("job_requirement_analysis", job_requirement_analysis)),
        ("hybrid_retrieval", guarded("hybrid_retrieval", hybrid_retrieval)),
        ("candidate_reranking", guarded("candidate_reranking", candidate_reranking)),
        ("resume_extraction", guarded("resume_extraction", resume_extraction)),
        ("candidate_evaluation", guarded("candidate_evaluation", candidate_evaluation)),
        ("evidence_verification", guarded("evidence_verification", evidence_verification)),
        ("candidate_ranking", guarded("candidate_ranking", candidate_ranking)),
        ("feedback_and_skill_gaps", guarded("feedback_and_skill_gaps", feedback_and_gaps)),
    ]


def run_screening(job: dict, criteria: list[dict], corpus: dict[str, dict], pool: list[str],
                  cfg: PipelineConfig | None = None, prov: Providers | None = None,
                  trace: TraceRecorder | None = None, prefer_langgraph: bool = True,
                  bm25_cache: dict | None = None) -> tuple[dict, TraceRecorder]:
    cfg = cfg or PipelineConfig()
    prov = prov or Providers()
    trace = trace or TraceRecorder()
    nodes = make_nodes(cfg, prov, trace, bm25_cache)
    state: dict[str, Any] = {"job": job, "criteria": criteria, "corpus": corpus, "pool": list(pool)}
    graph = None
    if prefer_langgraph:
        try:
            from langgraph.graph import END, StateGraph  # type: ignore

            g = StateGraph(ScreeningState)
            for name, fn in nodes:
                g.add_node(name, fn)
            g.set_entry_point(nodes[0][0])
            for (a, _), (b, _) in zip(nodes, nodes[1:]):
                g.add_edge(a, b)
            g.add_edge(nodes[-1][0], END)
            graph = g.compile()
        except ImportError:
            graph = None
    if graph is not None:
        trace.orchestrator = "langgraph"
        final = graph.invoke(state)
    else:
        trace.orchestrator = "sequential"
        final = dict(state)
        for _, fn in nodes:
            final.update(fn(final))
    final.pop("corpus", None)
    return final, trace
