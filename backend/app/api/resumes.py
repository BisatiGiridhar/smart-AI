from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from ..config import get_settings
from ..core.resume_parser import parse_resume
from ..core.sanitize import detect_injection
from ..core.text_extract import ExtractionError, extract_text
from ..models import GENUINE, Resume
from ..security.deps import Ctx, require
from ..services.audit import audit_ctx
from ..services.storage import delete_file, save_bytes
from .common import owned, page_params, row
from .jobs import corpus_clause

router = APIRouter(prefix="/api/resumes", tags=["resumes"])
L_FIELDS = ["id", "display_ref", "source_kind", "dataset_version_id", "source_record_id", "original_filename",
            "extraction_method", "split", "created_at"]


def _check_genuine_access(ctx: Ctx, kind: str) -> None:
    if kind == GENUINE and not ctx.can("resume.read_genuine"):
        raise HTTPException(403, "Your role cannot open genuine candidate records.")


@router.get("")
def list_resumes(corpus: str = "genuine", q: str = "", page: int = 1, size: int = 25, ctx: Ctx = Depends(require("resume.read"))):
    _check_genuine_access(ctx, GENUINE if corpus == "genuine" else "synthetic")
    off, lim = page_params(page, size)
    stmt = select(Resume).where(Resume.workspace_id == ctx.workspace_id, corpus_clause(Resume, corpus))
    if q:
        like = f"%{q[:100]}%"
        stmt = stmt.where(or_(Resume.display_ref.ilike(like), Resume.text.ilike(like)))
    total = ctx.db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = ctx.db.scalars(stmt.order_by(Resume.created_at.desc(), Resume.id).offset(off).limit(lim)).all()
    out = []
    for r in items:
        d = row(r, L_FIELDS)
        ex = r.extraction or {}
        d["skills"] = [s["value"] for s in ex.get("skills", [])][:12]
        d["missing_fields"] = ex.get("missing_fields", [])
        d["injection_flagged"] = bool(r.injection_flags)
        d["consent_recorded"] = r.consent is not None
        out.append(d)
    return {"total": total, "items": out}


@router.post("/upload")
async def upload(files: list[UploadFile] = File(...), lawful_basis: str = Form(..., min_length=3, max_length=200),
                 consent_reference: str = Form(..., min_length=1, max_length=200),
                 retention_until: date = Form(...), source_note: str = Form("", max_length=500),
                 ctx: Ctx = Depends(require("resume.write"))):
    s = get_settings()
    if retention_until <= date.today():
        raise HTTPException(422, "Retention date must be in the future.")
    if len(files) > 50:
        raise HTTPException(422, "Upload at most 50 files per batch.")
    created, errors = [], []
    for f in files:
        name = Path(f.filename or "resume").name
        data = await f.read()
        try:
            doc = extract_text(data, name, s.max_upload_mb * 1024 * 1024, s.enable_ocr)
        except ExtractionError as exc:
            errors.append({"file": name, "error": str(exc)})
            continue
        if len(doc.text.strip()) < 30:
            errors.append({"file": name, "error": "No usable text was extracted. " + " ".join(doc.warnings)})
            continue
        path, sha = save_bytes(data, name, ctx.workspace_id)
        dup = ctx.db.scalars(select(Resume.id).where(Resume.workspace_id == ctx.workspace_id, Resume.file_sha256 == sha)).first()
        if dup:
            delete_file(path)
            errors.append({"file": name, "error": f"Duplicate of an existing resume ({dup[:8]})."})
            continue
        count = ctx.db.scalar(select(func.count()).select_from(Resume).where(Resume.workspace_id == ctx.workspace_id,
                                                                             Resume.source_kind == GENUINE)) or 0
        r = Resume(workspace_id=ctx.workspace_id, source_kind=GENUINE, display_ref=f"C-{count + 1:05d}",
                   original_filename=name, stored_path=path, file_sha256=sha, text=doc.text, pages=doc.pages,
                   extraction=parse_resume(doc.text, doc.pages), extraction_method=f"{doc.method}+deterministic-v1",
                   extraction_warnings=doc.warnings, injection_flags=detect_injection(doc.text), created_by=ctx.user.id,
                   consent={"lawful_basis": lawful_basis, "consent_reference": consent_reference,
                            "retention_until": retention_until.isoformat(), "source_note": source_note,
                            "recorded_by": ctx.user.id, "recorded_at": datetime.now(timezone.utc).isoformat()})
        ctx.db.add(r)
        ctx.db.commit()
        created.append({"id": r.id, "display_ref": r.display_ref, "warnings": doc.warnings,
                        "injection_flagged": bool(r.injection_flags)})
    audit_ctx(ctx, "resume.upload_batch", "resume", None, {"created": len(created), "errors": len(errors)})
    return {"created": created, "errors": errors}


@router.get("/{resume_id}")
def get_resume(resume_id: str, ctx: Ctx = Depends(require("resume.read"))):
    r = owned(ctx.db, Resume, resume_id, ctx.workspace_id, "Resume")
    _check_genuine_access(ctx, r.source_kind)
    if r.source_kind == GENUINE:
        audit_ctx(ctx, "resume.view", "resume", r.id)
    return {**row(r, L_FIELDS), "text": r.text, "pages": r.pages, "extraction": r.extraction,
            "extraction_warnings": r.extraction_warnings, "corrections": r.corrections, "injection_flags": r.injection_flags,
            "consent": r.consent, "has_file": bool(r.stored_path)}


@router.get("/{resume_id}/file")
def get_file(resume_id: str, ctx: Ctx = Depends(require("resume.read_genuine"))):
    r = owned(ctx.db, Resume, resume_id, ctx.workspace_id, "Resume")
    if not r.stored_path or not Path(r.stored_path).exists():
        raise HTTPException(404, "No stored source file for this record.")
    audit_ctx(ctx, "resume.file_download", "resume", r.id)
    return FileResponse(r.stored_path, filename=r.original_filename or "resume", headers={"Cache-Control": "no-store"})


class CorrectionIn(BaseModel):
    field: str = Field(pattern="^(skills|education|experience|employment_history|projects|certifications|achievements)$")
    action: str = Field(pattern="^(remove|add|edit)$")
    index: int | None = Field(default=None, ge=0)
    value: str | None = Field(default=None, max_length=500)
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=0)
    reason: str = Field(min_length=3, max_length=500)


@router.post("/{resume_id}/corrections")
def correct(resume_id: str, body: CorrectionIn, ctx: Ctx = Depends(require("resume.correct"))):
    r = owned(ctx.db, Resume, resume_id, ctx.workspace_id, "Resume")
    _check_genuine_access(ctx, r.source_kind)
    ex = dict(r.extraction or {})
    items = list(ex.get(body.field, []))
    before = None
    if body.action in ("remove", "edit"):
        if body.index is None or body.index >= len(items):
            raise HTTPException(422, "index is out of range")
        before = items[body.index]
    if body.action in ("add", "edit"):
        if not body.value or body.start is None or body.end is None or not (body.start < body.end <= len(r.text)):
            raise HTTPException(422, "add/edit needs a value and a valid source span (start < end within the text)")
        new_item = {"value": body.value, "start": body.start, "end": body.end, "corrected_by": ctx.user.id}
    if body.action == "remove":
        items.pop(body.index)
    elif body.action == "edit":
        items[body.index] = new_item
    else:
        items.append(new_item)
    ex[body.field] = items
    r.extraction = ex
    r.corrections = [*(r.corrections or []), {"field": body.field, "action": body.action, "before": before,
                                              "after": None if body.action == "remove" else new_item, "reason": body.reason,
                                              "by": ctx.user.id, "at": datetime.now(timezone.utc).isoformat()}]
    ctx.db.commit()
    audit_ctx(ctx, "resume.correction", "resume", r.id, {"field": body.field, "action": body.action, "reason": body.reason})
    return {"extraction": r.extraction, "corrections": r.corrections}


@router.delete("/{resume_id}")
def delete(resume_id: str, ctx: Ctx = Depends(require("resume.write"))):
    r = owned(ctx.db, Resume, resume_id, ctx.workspace_id, "Resume")
    if r.source_kind != GENUINE:
        raise HTTPException(409, "Dataset records are removed by deleting the dataset version.")
    delete_file(r.stored_path)
    ctx.db.delete(r)
    ctx.db.commit()
    audit_ctx(ctx, "resume.delete", "resume", resume_id)
    return {"ok": True}
