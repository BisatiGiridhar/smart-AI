"""Dataset staging, inspection, validated import and reproducible splitting.

The importer never creates records that are not in the source files, never fills missing
values, and reports counts from the database after import.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from ..config import get_settings
from ..core import dataset_inspect as di
from ..core.resume_parser import parse_resume
from ..core.sanitize import detect_injection
from ..core.splits import component_split
from ..models import SYNTHETIC, DatasetVersion, Job, MatchRecord, RejectedRecord, Resume

SYNTHETIC_LABEL = "Public synthetic research dataset — not genuine candidate records."


def staging_dir(workspace_id: str, version_id: str) -> Path:
    p = Path(get_settings().dataset_dir) / workspace_id / version_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def profile_files(folder: Path) -> list[dict]:
    files = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in di.SUPPORTED:
            continue
        entry = {"name": str(path.relative_to(folder)), "bytes": path.stat().st_size, "sha256": di.sha256_file(path)}
        try:
            df = di.load_frame(path)
            entry["profile"] = di.profile_frame(df)
            entry["suggestion"] = di.suggest_role_and_mapping([c["name"] for c in entry["profile"]["columns"]], entry["name"])
        except Exception as exc:  # noqa: BLE001
            entry["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
        files.append(entry)
    return files


def read_card(folder: Path) -> tuple[str, str]:
    """Return (license, excerpt) from a dataset card README if present."""
    readme = next((p for p in folder.rglob("README.md")), None)
    if not readme:
        return "", ""
    text = readme.read_text(encoding="utf-8", errors="replace")
    license_ = ""
    for line in text.splitlines():
        if line.strip().lower().startswith("license:"):
            license_ = line.split(":", 1)[1].strip()
            break
    return license_, text[:4000]


def download_from_hf(db: Session, params: dict, progress) -> dict:
    s = get_settings()
    v = db.get(DatasetVersion, params["version_id"])
    folder = Path(v.storage_path)
    progress(0.05, "Contacting Hugging Face")
    try:
        from huggingface_hub import HfApi, snapshot_download
    except ImportError as exc:
        raise RuntimeError("huggingface_hub is not installed; upload the files instead.") from exc
    info = HfApi().dataset_info(params["repo_id"], revision=params.get("revision") or None, token=s.hf_token or None)
    snapshot_download(repo_id=params["repo_id"], repo_type="dataset", revision=info.sha, local_dir=str(folder),
                      token=s.hf_token or None)
    progress(0.7, "Inspecting downloaded files")
    files = profile_files(folder)
    license_, card = read_card(folder)
    card_license = getattr(getattr(info, "card_data", None), "license", None)
    v.files, v.revision = files, info.sha
    v.license = str(card_license or license_ or "")
    v.card_excerpt = card
    v.status = "staged" if files else "failed"
    v.validation = None if files else {"errors": ["No CSV/JSON/JSONL/Parquet/TSV files found in the repository."]}
    db.commit()
    return {"files": len(files), "revision": info.sha}


def _bulk(db: Session, objs: list) -> None:
    db.add_all(objs)
    db.flush()


def import_version(db: Session, params: dict, progress) -> dict:
    """mapping = {"resumes": {"file":..., "fields": {...}}, "jobs": {...}, "matches": {..., "label_type": ...}}"""
    v = db.get(DatasetVersion, params["version_id"])
    mapping = params["mapping"]
    folder = Path(v.storage_path)
    v.status, v.mapping = "importing", mapping
    db.commit()
    ws = v.workspace_id
    summary: dict = {"files": {}, "label": SYNTHETIC_LABEL}
    # idempotency: rejected-record log is rebuilt for each attempt; valid rows already present are skipped
    db.execute(delete(RejectedRecord).where(RejectedRecord.dataset_version_id == v.id))
    db.commit()

    def run_role(role: str, model, make, known_r=None, known_j=None, step=0.0):
        spec = mapping.get(role)
        if not spec:
            return {}
        fpath = folder / spec["file"]
        if not fpath.resolve().is_relative_to(folder.resolve()):
            raise ValueError("file path escapes the dataset folder")
        df = di.load_frame(fpath)
        valid, rejected = di.validate_rows(df, role, spec["fields"], known_r, known_j, spec.get("label_type", "numeric"))
        existing = set(db.scalars(select(model.source_record_id).where(model.dataset_version_id == v.id)))
        new = [r for r in valid if r["source_record_id"] not in existing]
        for i in range(0, len(new), 500):
            _bulk(db, [make(r) for r in new[i:i + 500]])
            db.commit()
            progress(step + 0.3 * (i + 500) / max(1, len(new)), f"{role}: {min(i + 500, len(new))} of {len(new)} new rows")
        for i in range(0, len(rejected), 1000):
            _bulk(db, [RejectedRecord(dataset_version_id=v.id, file_name=spec["file"], role=role, row_index=r["row_index"],
                                      source_record_id=r["source_record_id"], reason=r["reason"]) for r in rejected[i:i + 1000]])
        db.commit()
        summary["files"][role] = {"file": spec["file"], "rows_in_file": int(len(df)), "valid": len(valid),
                                  "inserted": len(new), "already_present": len(valid) - len(new), "rejected": len(rejected)}

    def make_resume(r):
        parsed = parse_resume(r["text"])
        return Resume(workspace_id=ws, source_kind=SYNTHETIC, dataset_version_id=v.id, source_record_id=r["source_record_id"],
                      display_ref=f"R-{r['source_record_id']}"[:200], display_name=r.get("name"), text=r["text"],
                      pages=[{"page": 1, "start": 0, "end": len(r["text"])}], extraction=parsed,
                      extraction_method="dataset-text+deterministic-v1", injection_flags=detect_injection(r["text"]))

    def make_job(r):
        return Job(workspace_id=ws, source_kind=SYNTHETIC, dataset_version_id=v.id, source_record_id=r["source_record_id"],
                   title=(r.get("title") or r["text"].strip().split("\n")[0])[:300], text=r["text"])

    run_role("resumes", Resume, make_resume, step=0.0)
    run_role("jobs", Job, make_job, step=0.3)
    if mapping.get("matches"):
        rmap = dict(db.execute(select(Resume.source_record_id, Resume.id).where(Resume.dataset_version_id == v.id)).all())
        jmap = dict(db.execute(select(Job.source_record_id, Job.id).where(Job.dataset_version_id == v.id)).all())

        def make_match(r):
            return MatchRecord(dataset_version_id=v.id, source_record_id=r["source_record_id"], resume_id=rmap[r["resume_id"]],
                               job_id=jmap[r["job_id"]], label_raw=r["label_raw"], label_value=r["label_value"], extra=r["extra"])

        run_role("matches", MatchRecord, make_match, set(rmap), set(jmap), step=0.6)

    counts = {
        "resumes": db.scalar(select(func.count()).select_from(Resume).where(Resume.dataset_version_id == v.id)),
        "jobs": db.scalar(select(func.count()).select_from(Job).where(Job.dataset_version_id == v.id)),
        "matches": db.scalar(select(func.count()).select_from(MatchRecord).where(MatchRecord.dataset_version_id == v.id)),
        "rejected": db.scalar(select(func.count()).select_from(RejectedRecord).where(RejectedRecord.dataset_version_id == v.id)),
    }
    labels = db.execute(select(MatchRecord.label_value).where(MatchRecord.dataset_version_id == v.id,
                                                              MatchRecord.label_value.is_not(None))).scalars().all()
    if labels:
        counts["label_stats"] = {"n": len(labels), "min": min(labels), "max": max(labels),
                                 "distinct": len(set(labels))}
    summary["database_counts"] = counts
    v.summary = summary
    v.validation = {"rejected": counts["rejected"], "ok": True}
    v.status, v.imported_at = "imported", datetime.now(timezone.utc)
    db.commit()
    progress(1.0, "Import complete")
    return summary


def make_split(db: Session, version_id: str, seed: int, ratios: tuple[float, float, float]) -> dict:
    v = db.get(DatasetVersion, version_id)
    pairs = db.execute(select(MatchRecord.resume_id, MatchRecord.job_id).where(MatchRecord.dataset_version_id == version_id)).all()
    job_ids = list(db.scalars(select(Job.id).where(Job.dataset_version_id == version_id)))
    resume_ids = list(db.scalars(select(Resume.id).where(Resume.dataset_version_id == version_id)))
    res = component_split([(r, j) for r, j in pairs], job_ids, resume_ids, ratios, seed)
    for split in ("train", "validation", "test"):
        js = [j for j, s in res["job_split"].items() if s == split]
        rs = [r for r, s in res["resume_split"].items() if s == split]
        for i in range(0, len(js), 900):
            db.execute(update(Job).where(Job.id.in_(js[i:i + 900])).values(split=split))
        for i in range(0, len(rs), 900):
            db.execute(update(Resume).where(Resume.id.in_(rs[i:i + 900])).values(split=split))
    db.flush()
    for split in ("train", "validation", "test"):
        db.execute(update(MatchRecord).where(MatchRecord.dataset_version_id == version_id,
                                             MatchRecord.job_id.in_(select(Job.id).where(Job.split == split,
                                                                                         Job.dataset_version_id == version_id)))
                   .values(split=split))
    cfg = {**res["config"], "dataset_version_id": version_id, "revision": v.revision,
           "created_at": datetime.now(timezone.utc).isoformat(), "pair_counts": res["pair_counts"]}
    v.split_config = cfg
    db.commit()
    return cfg


def remove_staging(path: str) -> None:
    shutil.rmtree(path, ignore_errors=True)


def card_json(v: DatasetVersion) -> str:
    return json.dumps({"name": v.name, "source": v.source_url, "revision": v.revision, "license": v.license})
