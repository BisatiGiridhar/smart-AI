"""Builds the dense vector index for one corpus in ChromaDB."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import GENUINE, SYNTHETIC, Resume
from . import model_runtime


def corpus_filter(workspace_id: str, corpus: str):
    q = select(Resume.id, Resume.text).where(Resume.workspace_id == workspace_id)
    if corpus == "genuine":
        return q.where(Resume.source_kind == GENUINE)
    if corpus.startswith("dataset:"):
        return q.where(Resume.source_kind == SYNTHETIC, Resume.dataset_version_id == corpus.split(":", 1)[1])
    raise ValueError("corpus must be 'genuine' or 'dataset:<version id>'")


def build_index(db: Session, params: dict, progress) -> dict:
    ws, corpus = params["workspace_id"], params["corpus"]
    emb = model_runtime.embedder()
    if emb is None:
        raise RuntimeError(f"Embedding model unavailable: {model_runtime.status()['embedder_error']}")
    col = model_runtime.get_collection(ws, corpus, create=True)
    if col is None:
        raise RuntimeError(f"Vector store unavailable: {model_runtime.status()['vector_store_error']}")
    rows = db.execute(corpus_filter(ws, corpus)).all()
    if not rows:
        raise RuntimeError("The corpus has no resumes to index.")
    existing = set()
    try:
        existing = set(col.get(include=[])["ids"])
    except Exception:  # noqa: BLE001
        pass
    todo = [r for r in rows if r.id not in existing]
    batch = 64
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        vecs = emb.encode([r.text[:6000] for r in chunk], normalize_embeddings=True, show_progress_bar=False)
        col.upsert(ids=[r.id for r in chunk], embeddings=[v.tolist() for v in vecs],
                   metadatas=[{"corpus": corpus} for _ in chunk])
        progress((i + len(chunk)) / max(1, len(todo)), f"Embedded {i + len(chunk)} of {len(todo)} new resumes")
    return {"corpus": corpus, "embedding_model": get_settings().embedding_model, "indexed_total": col.count(),
            "newly_indexed": len(todo), "already_indexed": len(existing)}
