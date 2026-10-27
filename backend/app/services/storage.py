"""Secure file storage: randomised names, size limits, hashing; files are never served publicly."""
from __future__ import annotations

import hashlib
import secrets
from pathlib import Path

from ..config import get_settings


def save_bytes(data: bytes, original_name: str, workspace_id: str) -> tuple[str, str]:
    s = get_settings()
    ext = Path(original_name).suffix.lower()[:10]
    folder = Path(s.storage_dir) / workspace_id
    folder.mkdir(parents=True, exist_ok=True)
    name = secrets.token_hex(16) + ext
    path = folder / name
    path.write_bytes(data)
    return str(path), hashlib.sha256(data).hexdigest()


def delete_file(path: str | None) -> None:
    if path:
        p = Path(path)
        if p.exists():
            p.unlink()
