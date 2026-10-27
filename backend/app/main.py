"""FastAPI application entry point for the Smart AI Hiring Assistant (SAIHA)."""
from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import auth, datasets, evaluations, jobs, research, resumes, system
from .config import get_settings
from .logging_conf import configure_logging
from .security.ratelimit import limiter

configure_logging()
log = logging.getLogger("saiha")
settings = get_settings()

app = FastAPI(title=settings.full_title, version="1.0.0",
              description="Decision-support API. Rankings are not hiring decisions; human reviewers decide.")
app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=False,
                   allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type", "X-Workspace-Id"])


@app.middleware("http")
async def guard(request: Request, call_next):
    t0 = time.perf_counter()
    key = request.client.host if request.client else "unknown"
    if request.url.path.startswith("/api/") and not limiter.allow(f"api:{key}", settings.rate_limit_per_minute):
        return JSONResponse({"detail": "Rate limit exceeded. Try again shortly."}, status_code=429)
    try:
        response = await call_next(request)
    except Exception:  # noqa: BLE001 - never leak stack traces to clients
        log.exception("unhandled error", extra={"path": request.url.path})
        return JSONResponse({"detail": "Internal error. The event was logged."}, status_code=500)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    log.info("request", extra={"path": request.url.path, "status": response.status_code,
                               "duration_ms": round((time.perf_counter() - t0) * 1000, 1)})
    return response


for r in (auth.router, datasets.router, jobs.router, jobs.rubric_router, resumes.router, evaluations.router,
          research.router, system.router):
    app.include_router(r)


@app.on_event("startup")
def startup() -> None:
    problems = settings.validate()
    if problems:
        for p in problems:
            log.error(p)
        raise RuntimeError("Configuration invalid: " + " ".join(problems))
    from .services.tasks import mark_orphaned_tasks
    n = mark_orphaned_tasks()
    if n:
        log.warning("marked %s interrupted task(s) as failed", n)
    _bootstrap_admin()


def _bootstrap_admin() -> None:
    """Optional: create the first admin from environment variables if no user exists."""
    if not (settings.bootstrap_admin_email and settings.bootstrap_admin_password):
        return
    from sqlalchemy import func, select

    from .db import SessionLocal
    from .models import Membership, User, Workspace
    from .security.passwords import hash_password
    with SessionLocal() as db:
        if db.scalar(select(func.count()).select_from(User)):
            return
        ws = Workspace(name="Default workspace")
        u = User(email=settings.bootstrap_admin_email.lower(), full_name="Administrator",
                 password_hash=hash_password(settings.bootstrap_admin_password))
        db.add_all([ws, u])
        db.flush()
        db.add(Membership(user_id=u.id, workspace_id=ws.id, role="admin"))
        db.commit()
        log.info("bootstrap administrator created")
