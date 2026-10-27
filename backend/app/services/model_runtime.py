"""Embedding model, cross-encoder and vector store, loaded lazily with honest availability."""
from __future__ import annotations

import logging
import threading

from ..config import get_settings

log = logging.getLogger("saiha.models")
_lock = threading.Lock()
_state: dict = {"embedder": None, "embedder_error": None, "reranker": None, "reranker_error": None,
                "chroma": None, "chroma_error": None}


def embedder():
    s = get_settings()
    if not s.enable_dense:
        _state["embedder_error"] = "dense retrieval disabled (ENABLE_DENSE=false)"
        return None
    with _lock:
        if _state["embedder"] is None and _state["embedder_error"] is None:
            try:
                from sentence_transformers import SentenceTransformer
                _state["embedder"] = SentenceTransformer(s.embedding_model)
            except Exception as exc:  # noqa: BLE001
                _state["embedder_error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
                log.warning("embedding model unavailable: %s", _state["embedder_error"])
    return _state["embedder"]


def reranker():
    s = get_settings()
    if not s.enable_rerank:
        _state["reranker_error"] = "reranking disabled (ENABLE_RERANK=false)"
        return None
    with _lock:
        if _state["reranker"] is None and _state["reranker_error"] is None:
            try:
                from sentence_transformers import CrossEncoder
                _state["reranker"] = CrossEncoder(s.cross_encoder_model, max_length=512)
            except Exception as exc:  # noqa: BLE001
                _state["reranker_error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
                log.warning("cross-encoder unavailable: %s", _state["reranker_error"])
    return _state["reranker"]


def chroma():
    s = get_settings()
    with _lock:
        if _state["chroma"] is None and _state["chroma_error"] is None:
            try:
                import chromadb
                _state["chroma"] = (chromadb.HttpClient(host=s.chroma_host, port=s.chroma_port) if s.chroma_host
                                    else chromadb.PersistentClient(path=s.chroma_dir))
            except Exception as exc:  # noqa: BLE001
                _state["chroma_error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
    return _state["chroma"]


def collection_name(workspace_id: str, corpus: str) -> str:
    model = get_settings().embedding_model.split("/")[-1].lower()
    safe = "".join(ch if ch.isalnum() else "-" for ch in f"{workspace_id[:8]}-{corpus}-{model}")
    return safe[:60].strip("-")


def get_collection(workspace_id: str, corpus: str, create: bool = False):
    c = chroma()
    if c is None:
        return None
    name = collection_name(workspace_id, corpus)
    try:
        if create:
            return c.get_or_create_collection(name, metadata={"hnsw:space": "cosine",
                                                              "embedding_model": get_settings().embedding_model})
        return c.get_collection(name)
    except Exception:  # noqa: BLE001 - collection missing
        return None


def status(workspace_id: str | None = None, corpus: str | None = None) -> dict:
    s = get_settings()
    out = {"embedding_model": s.embedding_model, "cross_encoder_model": s.cross_encoder_model,
           "embedder_loaded": _state["embedder"] is not None, "embedder_error": _state["embedder_error"],
           "reranker_loaded": _state["reranker"] is not None, "reranker_error": _state["reranker_error"],
           "vector_store": "chromadb", "vector_store_error": _state["chroma_error"]}
    if workspace_id and corpus:
        col = get_collection(workspace_id, corpus)
        out["index_count"] = col.count() if col is not None else 0
    return out


def make_dense_search(workspace_id: str, corpus: str):
    """Return (callable, reason). The callable is None when dense retrieval cannot run."""
    emb = embedder()
    if emb is None:
        return None, _state["embedder_error"] or "embedding model unavailable"
    col = get_collection(workspace_id, corpus)
    if col is None or col.count() == 0:
        return None, "vector index not built for this corpus (build it on the Hybrid Candidate Search page)"

    def search(query: str, pool: set[str] | None, k: int):
        import numpy as np
        q = np.asarray(emb.encode([query], normalize_embeddings=True)[0], dtype=float)
        if pool is not None and len(pool) <= 20000:
            got = col.get(ids=sorted(pool), include=["embeddings"])
            ids, embs = got["ids"], got["embeddings"]
            if ids is None or len(ids) == 0:
                return []
            sims = np.asarray(embs, dtype=float) @ q  # embeddings are stored L2-normalised
            order = sorted(range(len(ids)), key=lambda i: (-sims[i], ids[i]))[:k]
            return [(ids[i], float(sims[i])) for i in order]
        res = col.query(query_embeddings=[q.tolist()], n_results=min(col.count(), k))
        return [(i, 1.0 - d) for i, d in zip(res["ids"][0], res["distances"][0])]

    return search, None


def make_rerank():
    ce = reranker()
    if ce is None:
        return None, _state["reranker_error"] or "cross-encoder unavailable"

    def rerank(query: str, texts: list[str]):
        return [float(x) for x in ce.predict([(query, t[:4000]) for t in texts])]

    return rerank, None
