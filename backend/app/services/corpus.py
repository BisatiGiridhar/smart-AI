"""Loads one retrieval corpus. Synthetic and genuine records are never combined."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import GENUINE, SYNTHETIC, Resume


def parse_corpus_key(corpus: str) -> tuple[str, str | None]:
    if corpus == "genuine":
        return GENUINE, None
    if corpus.startswith("dataset:") and len(corpus) > 8:
        return SYNTHETIC, corpus.split(":", 1)[1]
    raise ValueError("corpus must be 'genuine' or 'dataset:<version id>'")


def load_corpus(db: Session, workspace_id: str, corpus: str, ids: list[str] | None = None,
                split: str | None = None) -> dict[str, dict]:
    kind, version = parse_corpus_key(corpus)
    q = select(Resume).where(Resume.workspace_id == workspace_id, Resume.source_kind == kind)
    if version:
        q = q.where(Resume.dataset_version_id == version)
    if kind == GENUINE:
        q = q.where(Resume.consent.is_not(None))
    if ids is not None:
        q = q.where(Resume.id.in_(ids))
    if split:
        q = q.where(Resume.split == split)
    out = {}
    for r in db.scalars(q):
        out[r.id] = {"text": r.text, "pages": r.pages, "extraction": r.extraction, "display_ref": r.display_ref}
    return out
