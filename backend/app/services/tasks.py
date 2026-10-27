"""Background tasks persisted in the database so progress and failures are visible in the UI.

Runs in a thread pool inside the API process. Tasks left 'running' after a restart are marked
failed on startup rather than reported as complete.
"""
from __future__ import annotations

import logging
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import update
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import BackgroundTask

log = logging.getLogger("saiha.tasks")
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="saiha-task")


class Progress:
    def __init__(self, task_id: str) -> None:
        self.task_id = task_id

    def __call__(self, fraction: float, message: str = "") -> None:
        with SessionLocal() as db:
            db.execute(update(BackgroundTask).where(BackgroundTask.id == self.task_id)
                       .values(progress=max(0.0, min(1.0, fraction)), message=message[:2000]))
            db.commit()


def submit(db: Session, *, kind: str, workspace_id: str, user_id: str | None, params: dict,
           fn: Callable[[Session, dict, Progress], dict]) -> BackgroundTask:
    task = BackgroundTask(kind=kind, workspace_id=workspace_id, created_by=user_id, params=params)
    db.add(task)
    db.commit()
    task_id = task.id

    def runner() -> None:
        with SessionLocal() as s:
            t = s.get(BackgroundTask, task_id)
            t.status, t.started_at = "running", datetime.now(timezone.utc)
            s.commit()
        try:
            with SessionLocal() as s:
                result = fn(s, params, Progress(task_id))
            with SessionLocal() as s:
                t = s.get(BackgroundTask, task_id)
                t.status, t.progress, t.result = "succeeded", 1.0, result
                t.finished_at = datetime.now(timezone.utc)
                s.commit()
        except Exception as exc:  # noqa: BLE001
            log.exception("task failed", extra={"task_id": task_id})
            with SessionLocal() as s:
                t = s.get(BackgroundTask, task_id)
                t.status, t.error = "failed", f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=5)}"
                t.finished_at = datetime.now(timezone.utc)
                s.commit()

    _pool.submit(runner)
    return task


def mark_orphaned_tasks() -> int:
    with SessionLocal() as s:
        res = s.execute(update(BackgroundTask).where(BackgroundTask.status.in_(["queued", "running"]))
                        .values(status="failed", error="Interrupted by a server restart; run it again.",
                                finished_at=datetime.now(timezone.utc)))
        s.commit()
        return res.rowcount or 0
