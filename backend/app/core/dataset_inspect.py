"""Dataset file inspection, mapping suggestion and record validation (pandas based).

Nothing here generates records. Rows that fail validation are returned with a reason so the
importer can log them; missing values are never filled in.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

SUPPORTED = {".csv", ".json", ".jsonl", ".parquet", ".tsv"}

ROLE_FIELDS = {
    "resumes": {"required": ["id", "text"], "optional": ["name", "title"]},
    "jobs": {"required": ["id", "text"], "optional": ["title"]},
    "matches": {"required": ["resume_id", "job_id"], "optional": ["id", "label"]},
}

HINTS = {
    "resumes": {"id": ["resume_id", "candidate_id", "cv_id", "id"], "text": ["resume_text", "resume", "cv_text", "cv", "text", "content"],
                "name": ["name", "candidate_name", "full_name"], "title": ["title", "headline", "current_title"]},
    "jobs": {"id": ["job_id", "jd_id", "posting_id", "id"], "text": ["job_description", "description", "jd_text", "jd", "text", "content"],
             "title": ["job_title", "title", "position"]},
    "matches": {"id": ["match_id", "pair_id", "id"], "resume_id": ["resume_id", "candidate_id", "cv_id"],
                "job_id": ["job_id", "jd_id", "posting_id"],
                "label": ["label", "match_score", "score", "relevance", "match", "is_match", "fit", "matched"]},
}


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_frame(path: str | Path, max_rows: int | None = None) -> pd.DataFrame:
    p = Path(path)
    ext = p.suffix.lower()
    if ext not in SUPPORTED:
        raise ValueError(f"unsupported file format {ext}")
    if ext == ".csv":
        return pd.read_csv(p, nrows=max_rows, dtype=str, keep_default_na=False, na_values=[""])
    if ext == ".tsv":
        return pd.read_csv(p, sep="\t", nrows=max_rows, dtype=str, keep_default_na=False, na_values=[""])
    if ext == ".jsonl":
        return pd.read_json(p, lines=True, nrows=max_rows, dtype=False)
    if ext == ".json":
        raw = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            for key in ("data", "rows", "records", "train"):
                if isinstance(raw.get(key), list):
                    raw = raw[key]
                    break
        df = pd.DataFrame(raw)
        return df.head(max_rows) if max_rows else df
    df = pd.read_parquet(p)
    return df.head(max_rows) if max_rows else df


def profile_frame(df: pd.DataFrame) -> dict:
    cols = []
    for c in df.columns:
        s = df[c]
        non_null = s.dropna()
        sample = non_null.astype(str).head(3).map(lambda v: v[:160]).tolist()
        avg_len = float(non_null.astype(str).str.len().mean()) if len(non_null) else 0.0
        cols.append({"name": str(c), "dtype": str(s.dtype), "null_count": int(s.isna().sum()),
                     "unique_count": int(non_null.astype(str).nunique()), "avg_length": round(avg_len, 1),
                     "sample": sample})
    return {"rows": int(len(df)), "columns": cols}


def suggest_role_and_mapping(columns: list[str], filename: str = "") -> dict:
    lower = {c.lower(): c for c in columns}
    fname = filename.lower()
    best = None
    for role, hints in HINTS.items():
        mapping = {}
        for field, cands in hints.items():
            for cand in cands:
                if cand in lower:
                    mapping[field] = lower[cand]
                    break
        req = ROLE_FIELDS[role]["required"]
        score = sum(1 for f in req if f in mapping) * 2 + len(mapping)
        if role.rstrip("s") in fname or role in fname:
            score += 3
        if role == "matches" and not ({"resume_id", "job_id"} <= mapping.keys()):
            score -= 10
        if best is None or score > best["score"]:
            best = {"role": role, "mapping": mapping, "score": score}
    complete = all(f in best["mapping"] for f in ROLE_FIELDS[best["role"]]["required"])
    return {"role": best["role"], "mapping": best["mapping"], "complete": complete,
            "note": "Suggestion from column names only. Confirm before importing."}


def validate_rows(df: pd.DataFrame, role: str, mapping: dict, known_resume_ids: set[str] | None = None,
                  known_job_ids: set[str] | None = None, label_type: str = "numeric") -> tuple[list[dict], list[dict]]:
    if role not in ROLE_FIELDS:
        raise ValueError(f"unknown role {role}")
    missing_map = [f for f in ROLE_FIELDS[role]["required"] if f not in mapping]
    if missing_map:
        raise ValueError(f"mapping for {role} is missing required fields: {missing_map}")
    for f, col in mapping.items():
        if col not in df.columns:
            raise ValueError(f"mapped column {col!r} for field {f!r} not found in file")
    valid, rejected = [], []
    seen: set[str] = set()
    for idx, row in enumerate(df.to_dict(orient="records")):
        def get(field):
            col = mapping.get(field)
            if col is None:
                return None
            v = row.get(col)
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return None
            return v

        rec = {f: get(f) for f in mapping}
        if role == "matches":
            rid, jid = rec.get("resume_id"), rec.get("job_id")
            if rid is None or str(rid).strip() == "" or jid is None or str(jid).strip() == "":
                rejected.append({"row_index": idx, "source_record_id": _sid(rec.get("id")), "reason": "missing resume_id or job_id"})
                continue
            rid, jid = str(rid).strip(), str(jid).strip()
            if known_resume_ids is not None and rid not in known_resume_ids:
                rejected.append({"row_index": idx, "source_record_id": _sid(rec.get("id")), "reason": f"broken reference: resume {rid} not imported"})
                continue
            if known_job_ids is not None and jid not in known_job_ids:
                rejected.append({"row_index": idx, "source_record_id": _sid(rec.get("id")), "reason": f"broken reference: job {jid} not imported"})
                continue
            sid = str(rec["id"]).strip() if rec.get("id") is not None else f"{rid}::{jid}"
            if sid in seen:
                rejected.append({"row_index": idx, "source_record_id": sid, "reason": "duplicate match id"})
                continue
            label_raw = rec.get("label")
            label_value = None
            if label_raw is not None and str(label_raw).strip() != "":
                label_value = _parse_label(label_raw, label_type)
                if label_value is None:
                    rejected.append({"row_index": idx, "source_record_id": sid, "reason": f"label {str(label_raw)[:40]!r} is not {label_type}"})
                    continue
            seen.add(sid)
            extra = {k: (v if _jsonable(v) else str(v)) for k, v in row.items() if k not in mapping.values()}
            valid.append({"source_record_id": sid, "resume_id": rid, "job_id": jid,
                          "label_raw": None if label_raw is None else str(label_raw), "label_value": label_value,
                          "extra": extra})
            continue
        sid = rec.get("id")
        text = rec.get("text")
        if sid is None or str(sid).strip() == "":
            rejected.append({"row_index": idx, "source_record_id": None, "reason": "missing id"})
            continue
        sid = str(sid).strip()
        if text is None or not isinstance(text, str) and not str(text).strip():
            rejected.append({"row_index": idx, "source_record_id": sid, "reason": "missing text"})
            continue
        text = text if isinstance(text, str) else _as_text(text)
        if not text.strip():
            rejected.append({"row_index": idx, "source_record_id": sid, "reason": "empty text"})
            continue
        if sid in seen:
            rejected.append({"row_index": idx, "source_record_id": sid, "reason": "duplicate id"})
            continue
        seen.add(sid)
        valid.append({"source_record_id": sid, "text": text, "name": _opt(rec.get("name")), "title": _opt(rec.get("title"))})
    return valid, rejected


def _sid(v):
    return None if v is None else str(v)


def _opt(v):
    return None if v is None else str(v)[:300]


def _as_text(v) -> str:
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False, indent=1)
    return str(v)


def _jsonable(v) -> bool:
    try:
        json.dumps(v)
        return True
    except (TypeError, ValueError):
        return False


def _parse_label(v, label_type: str) -> float | None:
    s = str(v).strip().lower()
    if label_type == "binary":
        if s in {"1", "true", "yes", "match", "matched", "relevant", "1.0"}:
            return 1.0
        if s in {"0", "false", "no", "no_match", "not_match", "irrelevant", "0.0", "mismatch"}:
            return 0.0
        return None
    try:
        f = float(s)
    except ValueError:
        return None
    return f if f == f else None
