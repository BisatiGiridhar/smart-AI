from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import ROLES, Membership, RevokedToken, User, Workspace
from ..security.deps import Ctx, get_ctx, require
from ..security.passwords import hash_password, verify_password
from ..security.ratelimit import limiter
from ..security.tokens import create_token, decode_token
from ..services.audit import audit, audit_ctx

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class BootstrapIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=200)
    full_name: str = Field(default="", max_length=200)
    workspace_name: str = Field(min_length=1, max_length=200)


class MemberIn(BaseModel):
    email: EmailStr
    full_name: str = Field(default="", max_length=200)
    password: str | None = Field(default=None, min_length=12, max_length=200)
    role: str


def _me(db: Session, user: User) -> dict:
    ms = db.scalars(select(Membership).where(Membership.user_id == user.id)).all()
    return {"id": user.id, "email": user.email, "full_name": user.full_name,
            "memberships": [{"workspace_id": m.workspace_id, "workspace_name": m.workspace.name, "role": m.role} for m in ms]}


@router.get("/bootstrap-status")
def bootstrap_status(db: Session = Depends(get_db)):
    return {"needs_bootstrap": (db.scalar(select(func.count()).select_from(User)) or 0) == 0}


@router.post("/bootstrap")
def bootstrap(body: BootstrapIn, request: Request, db: Session = Depends(get_db)):
    if db.scalar(select(func.count()).select_from(User)):
        raise HTTPException(409, "Setup is already complete. Sign in instead.")
    ws = Workspace(name=body.workspace_name)
    u = User(email=body.email.lower(), full_name=body.full_name, password_hash=hash_password(body.password))
    db.add_all([ws, u])
    db.flush()
    db.add(Membership(user_id=u.id, workspace_id=ws.id, role="admin"))
    db.commit()
    audit(db, "auth.bootstrap", workspace_id=ws.id, user_id=u.id, ip=request.client.host if request.client else None)
    return {"ok": True}


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "unknown"
    if not limiter.allow(f"login:{ip}", get_settings().login_rate_limit_per_minute):
        raise HTTPException(429, "Too many sign-in attempts. Wait a minute and try again.")
    u = db.scalars(select(User).where(User.email == body.email.lower())).first()
    if u is None or not u.is_active or not verify_password(body.password, u.password_hash):
        audit(db, "auth.login_failed", workspace_id=None, user_id=u.id if u else None, details={"email": body.email}, ip=ip)
        raise HTTPException(401, "Email or password is incorrect.")
    token, _, exp = create_token(u.id)
    audit(db, "auth.login", workspace_id=None, user_id=u.id, ip=ip)
    return {"access_token": token, "token_type": "bearer", "expires_at": exp.isoformat(), "user": _me(db, u)}


@router.post("/logout")
def logout(request: Request, ctx: Ctx = Depends(get_ctx)):
    token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    exp = datetime.fromtimestamp(decode_token(token)["exp"], tz=timezone.utc)
    ctx.db.merge(RevokedToken(jti=ctx.token_jti, expires_at=exp))
    audit_ctx(ctx, "auth.logout")
    return {"ok": True}


@router.get("/me")
def me(ctx: Ctx = Depends(get_ctx)):
    return {**_me(ctx.db, ctx.user), "active_workspace_id": ctx.workspace_id, "role": ctx.role}


@router.get("/members")
def members(ctx: Ctx = Depends(require("workspace.admin"))):
    ms = ctx.db.scalars(select(Membership).where(Membership.workspace_id == ctx.workspace_id)).all()
    return [{"user_id": m.user_id, "email": m.user.email, "full_name": m.user.full_name, "role": m.role,
             "active": m.user.is_active} for m in ms]


@router.post("/members")
def add_member(body: MemberIn, ctx: Ctx = Depends(require("workspace.admin"))):
    if body.role not in ROLES:
        raise HTTPException(422, f"Role must be one of {', '.join(ROLES)}.")
    db = ctx.db
    u = db.scalars(select(User).where(User.email == body.email.lower())).first()
    if u is None:
        if not body.password:
            raise HTTPException(422, "A password of at least 12 characters is needed for a new user.")
        u = User(email=body.email.lower(), full_name=body.full_name, password_hash=hash_password(body.password))
        db.add(u)
        db.flush()
    m = db.scalars(select(Membership).where(Membership.user_id == u.id, Membership.workspace_id == ctx.workspace_id)).first()
    if m:
        m.role = body.role
    else:
        db.add(Membership(user_id=u.id, workspace_id=ctx.workspace_id, role=body.role))
    db.commit()
    audit_ctx(ctx, "workspace.member_set", "user", u.id, {"role": body.role})
    return {"ok": True}


class WorkspaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


@router.post("/workspaces")
def create_workspace(body: WorkspaceIn, ctx: Ctx = Depends(require("workspace.admin"))):
    ws = Workspace(name=body.name)
    ctx.db.add(ws)
    ctx.db.flush()
    ctx.db.add(Membership(user_id=ctx.user.id, workspace_id=ws.id, role="admin"))
    ctx.db.commit()
    audit_ctx(ctx, "workspace.create", "workspace", ws.id)
    return {"id": ws.id, "name": ws.name}
