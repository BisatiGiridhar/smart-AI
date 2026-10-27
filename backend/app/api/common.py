from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session


def iso(v):
    return v.isoformat() if isinstance(v, datetime) else v


def row(obj, fields: list[str]) -> dict:
    return {f: iso(getattr(obj, f)) for f in fields}


def owned(db: Session, model, obj_id: str, workspace_id: str, label: str = "Item"):
    """Fetch an object only if it belongs to the caller's workspace (404 otherwise, to avoid leaking existence)."""
    obj = db.get(model, obj_id)
    ws = getattr(obj, "workspace_id", None) if obj is not None else None
    if obj is None or ws != workspace_id:
        raise HTTPException(404, f"{label} not found in this workspace.")
    return obj


def page_params(page: int, size: int) -> tuple[int, int]:
    page = max(1, page)
    size = max(1, min(200, size))
    return (page - 1) * size, size
