from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select

from ..config import get_settings
from ..core.job_parser import analyze_job, draft_rubric
from ..core.scoring import criterion_from_dict, validate_criteria
from ..core.text_extract import ExtractionError, extract_text
from ..models import GENUINE, Job, Rubric
from ..security.deps import Ctx, require
from ..services.audit import audit_ctx
from .common import owned, page_params, row

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
J_FIELDS = ["id", "title", "source_kind", "dataset_version_id", "source_record_id", "status", "split", "created_at", "updated_at"]
R_FIELDS = ["id", "job_id", "version", "status", "origin", "criteria", "notes", "created_by", "created_at", "approved_by", "approved_at"]


def corpus_clause(model, corpus: str):
    if corpus == "genuine":
        return model.source_kind == GENUINE
    if corpus.startswith("dataset:"):
        return model.dataset_version_id == corpus.split(":", 1)[1]
    raise HTTPException(422, "corpus must be 'genuine' or 'dataset:<version id>'")


@router.get("")
def list_jobs(corpus: str = "genuine", q: str = "", status: str = "active", page: int = 1, size: int = 25,
              ctx: Ctx = Depends(require("job.read"))):
    off, lim = page_params(page, size)
    stmt = select(Job).where(Job.workspace_id == ctx.workspace_id, corpus_clause(Job, corpus))
    if status != "all":
        stmt = stmt.where(Job.status == status)
    if q:
        like = f"%{q[:100]}%"
        stmt = stmt.where(or_(Job.title.ilike(like), Job.source_record_id.ilike(like)))
    total = ctx.db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = ctx.db.scalars(stmt.order_by(Job.created_at.desc(), Job.id).offset(off).limit(lim)).all()
    out = []
    for j in items:
        d = row(j, J_FIELDS)
        d["approved_rubric_version"] = ctx.db.scalar(select(func.max(Rubric.version)).where(Rubric.job_id == j.id, Rubric.status == "approved"))
        out.append(d)
    return {"total": total, "items": out}


class JobIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=20, max_length=100_000)


@router.post("")
def create_job(body: JobIn, ctx: Ctx = Depends(require("job.write"))):
    j = Job(workspace_id=ctx.workspace_id, source_kind=GENUINE, title=body.title, text=body.text, created_by=ctx.user.id,
            analysis=analyze_job(body.text, body.title))
    ctx.db.add(j)
    ctx.db.commit()
    audit_ctx(ctx, "job.create", "job", j.id)
    return row(j, J_FIELDS)


@router.post("/upload")
async def upload_job(title: str = Form(..., max_length=300), file: UploadFile = File(...),
                     ctx: Ctx = Depends(require("job.write"))):
    data = await file.read()
    try:
        doc = extract_text(data, file.filename or "job.txt", get_settings().max_upload_mb * 1024 * 1024, get_settings().enable_ocr)
    except ExtractionError as exc:
        raise HTTPException(422, str(exc))
    if len(doc.text.strip()) < 20:
        raise HTTPException(422, "No usable text was extracted from the document.")
    j = Job(workspace_id=ctx.workspace_id, source_kind=GENUINE, title=title, text=doc.text, created_by=ctx.user.id,
            analysis=analyze_job(doc.text, title))
    ctx.db.add(j)
    ctx.db.commit()
    audit_ctx(ctx, "job.upload", "job", j.id, {"method": doc.method, "warnings": doc.warnings})
    return {**row(j, J_FIELDS), "extraction_warnings": doc.warnings}


@router.get("/{job_id}")
def get_job(job_id: str, ctx: Ctx = Depends(require("job.read"))):
    j = owned(ctx.db, Job, job_id, ctx.workspace_id, "Job")
    rubrics = ctx.db.scalars(select(Rubric).where(Rubric.job_id == j.id).order_by(Rubric.version.desc())).all()
    return {**row(j, J_FIELDS), "text": j.text, "analysis": j.analysis, "rubrics": [row(r, R_FIELDS) for r in rubrics]}


class JobPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    text: str | None = Field(default=None, min_length=20, max_length=100_000)


@router.patch("/{job_id}")
def edit_job(job_id: str, body: JobPatch, ctx: Ctx = Depends(require("job.write"))):
    j = owned(ctx.db, Job, job_id, ctx.workspace_id, "Job")
    if j.source_kind != GENUINE:
        raise HTTPException(409, "Dataset jobs are read-only so experiments stay reproducible.")
    if body.title is not None:
        j.title = body.title
    if body.text is not None:
        j.text = body.text
        j.analysis = analyze_job(j.text, j.title)
    ctx.db.commit()
    audit_ctx(ctx, "job.edit", "job", j.id, {"fields": [k for k, v in body.model_dump().items() if v is not None]})
    return row(j, J_FIELDS)


@router.post("/{job_id}/archive")
def archive(job_id: str, ctx: Ctx = Depends(require("job.write"))):
    j = owned(ctx.db, Job, job_id, ctx.workspace_id, "Job")
    j.status = "archived" if j.status == "active" else "active"
    ctx.db.commit()
    audit_ctx(ctx, "job.archive_toggle", "job", j.id, {"status": j.status})
    return {"status": j.status}


@router.post("/{job_id}/analyze")
def analyze(job_id: str, ctx: Ctx = Depends(require("job.write"))):
    j = owned(ctx.db, Job, job_id, ctx.workspace_id, "Job")
    j.analysis = analyze_job(j.text, j.title)
    ctx.db.commit()
    return {"analysis": j.analysis, "draft_criteria": draft_rubric(j.analysis)}


class CriterionIn(BaseModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9:\-_.]+$")
    label: str = Field(min_length=1, max_length=200)
    kind: str = Field(pattern="^(skill|experience_years|free_text)$")
    weight: float = Field(ge=0, le=100)
    max_rating: float = Field(default=4, gt=0, le=100)
    terms: list[str] = Field(default_factory=list, max_length=20)
    required: bool = True
    min_years: float | None = Field(default=None, ge=0, le=60)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("terms")
    @classmethod
    def clean_terms(cls, v):
        return [t.strip().lower()[:80] for t in v if t.strip()]


class RubricIn(BaseModel):
    criteria: list[CriterionIn] = Field(min_length=1, max_length=50)
    notes: str = Field(default="", max_length=2000)
    origin: str = Field(default="recruiter", pattern="^(recruiter|auto_draft)$")


@router.post("/{job_id}/rubrics")
def new_rubric(job_id: str, body: RubricIn, ctx: Ctx = Depends(require("job.write"))):
    j = owned(ctx.db, Job, job_id, ctx.workspace_id, "Job")
    crit = [c.model_dump() for c in body.criteria]
    for c in crit:
        if c["kind"] == "skill" and not c["terms"]:
            c["terms"] = [c["label"].lower()]
        if c["kind"] == "experience_years" and c["min_years"] is None:
            raise HTTPException(422, f"{c['label']}: experience criteria need min_years.")
    try:
        validate_criteria([criterion_from_dict(c) for c in crit])
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    version = (ctx.db.scalar(select(func.max(Rubric.version)).where(Rubric.job_id == j.id)) or 0) + 1
    r = Rubric(job_id=j.id, version=version, status="draft", origin=body.origin, criteria=crit, notes=body.notes,
               created_by=ctx.user.id)
    ctx.db.add(r)
    ctx.db.commit()
    audit_ctx(ctx, "rubric.create", "rubric", r.id, {"job_id": j.id, "version": version})
    return row(r, R_FIELDS)


rubric_router = APIRouter(prefix="/api/rubrics", tags=["rubrics"])


@rubric_router.post("/{rubric_id}/approve")
def approve(rubric_id: str, ctx: Ctx = Depends(require("rubric.approve"))):
    r = ctx.db.get(Rubric, rubric_id)
    if r is None:
        raise HTTPException(404, "Rubric not found.")
    owned(ctx.db, Job, r.job_id, ctx.workspace_id, "Rubric")
    if r.status != "draft":
        raise HTTPException(409, "Only a draft can be approved. Create a new version to change an approved rubric.")
    for other in ctx.db.scalars(select(Rubric).where(Rubric.job_id == r.job_id, Rubric.status == "approved")):
        other.status = "superseded"
    r.status, r.approved_by, r.approved_at = "approved", ctx.user.id, datetime.now(timezone.utc)
    ctx.db.commit()
    audit_ctx(ctx, "rubric.approve", "rubric", r.id, {"version": r.version})
    return row(r, R_FIELDS)
