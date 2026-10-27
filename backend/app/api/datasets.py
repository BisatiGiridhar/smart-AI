from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from ..config import get_settings
from ..core.dataset_inspect import SUPPORTED
from ..models import DatasetVersion, Job, MatchRecord, RejectedRecord, Resume
from ..security.deps import Ctx, require
from ..services import dataset_importer as imp
from ..services.audit import audit_ctx
from ..services.tasks import submit
from .common import owned, page_params, row

router = APIRouter(prefix="/api/datasets", tags=["datasets"])
V_FIELDS = ["id", "name", "source_url", "source_method", "revision", "license", "is_synthetic", "status", "files",
            "mapping", "validation", "summary", "split_config", "created_at", "imported_at", "card_excerpt"]


@router.get("")
def list_versions(ctx: Ctx = Depends(require("dataset.read"))):
    vs = ctx.db.scalars(select(DatasetVersion).where(DatasetVersion.workspace_id == ctx.workspace_id)
                        .order_by(DatasetVersion.created_at.desc())).all()
    out = []
    for v in vs:
        d = row(v, V_FIELDS)
        d["card_excerpt"] = (v.card_excerpt or "")[:600]
        out.append(d)
    return {"versions": out, "synthetic_label": imp.SYNTHETIC_LABEL, "default_repo": get_settings().hf_dataset_repo}


@router.get("/{version_id}")
def get_version(version_id: str, ctx: Ctx = Depends(require("dataset.read"))):
    v = owned(ctx.db, DatasetVersion, version_id, ctx.workspace_id, "Dataset version")
    counts = {
        "resumes": ctx.db.scalar(select(func.count()).select_from(Resume).where(Resume.dataset_version_id == v.id)),
        "jobs": ctx.db.scalar(select(func.count()).select_from(Job).where(Job.dataset_version_id == v.id)),
        "matches": ctx.db.scalar(select(func.count()).select_from(MatchRecord).where(MatchRecord.dataset_version_id == v.id)),
        "rejected": ctx.db.scalar(select(func.count()).select_from(RejectedRecord).where(RejectedRecord.dataset_version_id == v.id)),
    }
    split_counts = {}
    for model, name in ((Job, "jobs"), (Resume, "resumes")):
        for s, n in ctx.db.execute(select(model.split, func.count()).where(model.dataset_version_id == v.id).group_by(model.split)):
            split_counts.setdefault(name, {})[s or "unassigned"] = n
    return {**row(v, V_FIELDS), "database_counts": counts, "split_counts": split_counts,
            "synthetic_label": imp.SYNTHETIC_LABEL}


class HFIn(BaseModel):
    repo_id: str = Field(min_length=3, max_length=200, pattern=r"^[\w.\-]+/[\w.\-]+$")
    revision: str | None = Field(default=None, max_length=100)


@router.post("/huggingface")
def from_hf(body: HFIn, ctx: Ctx = Depends(require("dataset.import"))):
    v = DatasetVersion(workspace_id=ctx.workspace_id, name=body.repo_id, source_method="huggingface",
                       source_url=f"https://huggingface.co/datasets/{body.repo_id}", storage_path="", created_by=ctx.user.id,
                       status="downloading")
    ctx.db.add(v)
    ctx.db.flush()
    v.storage_path = str(imp.staging_dir(ctx.workspace_id, v.id))
    ctx.db.commit()
    t = submit(ctx.db, kind="dataset.download", workspace_id=ctx.workspace_id, user_id=ctx.user.id,
               params={"version_id": v.id, "repo_id": body.repo_id, "revision": body.revision}, fn=_download_wrapper)
    audit_ctx(ctx, "dataset.download_requested", "dataset_version", v.id, {"repo": body.repo_id})
    return {"version_id": v.id, "task_id": t.id}


def _download_wrapper(db, params, progress):
    try:
        return imp.download_from_hf(db, params, progress)
    except Exception:
        v = db.get(DatasetVersion, params["version_id"])
        if v:
            v.status = "failed"
            v.validation = {"errors": ["Download failed. Check network access or upload the files instead."]}
            db.commit()
        raise


@router.post("/upload")
async def upload(name: str = Form(..., max_length=200), source_url: str = Form("", max_length=500),
                 license: str = Form("", max_length=200), is_synthetic: bool = Form(True),
                 files: list[UploadFile] = File(...), ctx: Ctx = Depends(require("dataset.import"))):
    v = DatasetVersion(workspace_id=ctx.workspace_id, name=name, source_method="upload", source_url=source_url,
                       license=license, is_synthetic=is_synthetic, storage_path="", created_by=ctx.user.id)
    ctx.db.add(v)
    ctx.db.flush()
    folder = imp.staging_dir(ctx.workspace_id, v.id)
    v.storage_path = str(folder)
    limit = 2 * 1024 * 1024 * 1024
    for f in files:
        safe = Path(f.filename or "file").name
        if Path(safe).suffix.lower() not in SUPPORTED | {".md"}:
            raise HTTPException(422, f"{safe}: only CSV, TSV, JSON, JSONL, Parquet and README.md files are accepted.")
        data = await f.read()
        if len(data) > limit:
            raise HTTPException(413, f"{safe} is larger than 2 GB.")
        (folder / safe).write_bytes(data)
    v.files = imp.profile_files(folder)
    lic, card = imp.read_card(folder)
    v.license = v.license or lic
    v.card_excerpt = card
    ctx.db.commit()
    audit_ctx(ctx, "dataset.uploaded", "dataset_version", v.id, {"files": [x["name"] for x in v.files]})
    return {"version_id": v.id, "files": v.files}


class FileMap(BaseModel):
    file: str
    fields: dict[str, str]
    label_type: str = Field(default="numeric", pattern="^(numeric|binary)$")


class ImportIn(BaseModel):
    resumes: FileMap
    jobs: FileMap
    matches: FileMap | None = None


@router.post("/{version_id}/import")
def start_import(version_id: str, body: ImportIn, ctx: Ctx = Depends(require("dataset.import"))):
    v = owned(ctx.db, DatasetVersion, version_id, ctx.workspace_id, "Dataset version")
    if v.status in ("importing", "downloading"):
        raise HTTPException(409, "This version is busy. Wait for the current task to finish.")
    names = {f["name"] for f in v.files or []}
    for fm in (body.resumes, body.jobs, body.matches):
        if fm and fm.file not in names:
            raise HTTPException(422, f"{fm.file} is not one of this version's files.")
    mapping = body.model_dump(exclude_none=True)
    t = submit(ctx.db, kind="dataset.import", workspace_id=ctx.workspace_id, user_id=ctx.user.id,
               params={"version_id": v.id, "mapping": mapping}, fn=_import_wrapper)
    audit_ctx(ctx, "dataset.import_started", "dataset_version", v.id, {"mapping": mapping})
    return {"task_id": t.id}


def _import_wrapper(db, params, progress):
    try:
        return imp.import_version(db, params, progress)
    except Exception as exc:
        db.rollback()
        v = db.get(DatasetVersion, params["version_id"])
        v.status = "failed"
        v.validation = {"errors": [f"{type(exc).__name__}: {exc}"]}
        db.commit()
        raise


class SplitIn(BaseModel):
    seed: int = 42
    train: float = Field(0.7, ge=0, le=1)
    validation: float = Field(0.15, ge=0, le=1)
    test: float = Field(0.15, ge=0, le=1)


@router.post("/{version_id}/split")
def split(version_id: str, body: SplitIn, ctx: Ctx = Depends(require("dataset.import"))):
    v = owned(ctx.db, DatasetVersion, version_id, ctx.workspace_id, "Dataset version")
    if v.status != "imported":
        raise HTTPException(409, "Import the dataset before creating a split.")
    try:
        cfg = imp.make_split(ctx.db, v.id, body.seed, (body.train, body.validation, body.test))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    audit_ctx(ctx, "dataset.split_created", "dataset_version", v.id, cfg)
    return cfg


@router.get("/{version_id}/rejected")
def rejected(version_id: str, page: int = 1, size: int = 50, ctx: Ctx = Depends(require("dataset.read"))):
    owned(ctx.db, DatasetVersion, version_id, ctx.workspace_id, "Dataset version")
    off, lim = page_params(page, size)
    q = select(RejectedRecord).where(RejectedRecord.dataset_version_id == version_id)
    total = ctx.db.scalar(select(func.count()).select_from(q.subquery()))
    items = ctx.db.scalars(q.order_by(RejectedRecord.role, RejectedRecord.row_index).offset(off).limit(lim)).all()
    reasons = ctx.db.execute(select(RejectedRecord.reason, func.count()).where(RejectedRecord.dataset_version_id == version_id)
                             .group_by(RejectedRecord.reason).order_by(func.count().desc()).limit(20)).all()
    return {"total": total, "items": [row(r, ["file_name", "role", "row_index", "source_record_id", "reason"]) for r in items],
            "top_reasons": [{"reason": r, "count": c} for r, c in reasons]}
