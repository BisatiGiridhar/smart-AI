"""Authentication and server-side authorization dependencies."""
from __future__ import annotations

from dataclasses import dataclass

import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Membership, RevokedToken, User
from .tokens import decode_token

bearer = HTTPBearer(auto_error=False)

PERMISSIONS: dict[str, set[str]] = {
    "dataset.read": {"admin", "researcher", "recruiter", "reviewer"},
    "dataset.import": {"admin"},
    "job.read": {"admin", "recruiter", "researcher", "reviewer"},
    "job.write": {"admin", "recruiter"},
    "rubric.approve": {"admin", "recruiter"},
    "resume.read": {"admin", "recruiter", "researcher", "reviewer"},
    "resume.read_genuine": {"admin", "recruiter", "reviewer"},
    "resume.write": {"admin", "recruiter"},
    "resume.correct": {"admin", "recruiter", "reviewer"},
    "search.run": {"admin", "recruiter", "researcher"},
    "evaluation.run": {"admin", "recruiter", "researcher"},
    "evaluation.read": {"admin", "recruiter", "researcher", "reviewer"},
    "review.write": {"admin", "recruiter", "reviewer"},
    "fairness.run": {"admin", "researcher"},
    "security.run": {"admin", "researcher"},
    "experiment.run": {"admin", "researcher"},
    "analytics.read": {"admin", "recruiter", "researcher", "reviewer"},
    "audit.read": {"admin"},
    "workspace.admin": {"admin"},
}


@dataclass
class Ctx:
    user: User
    workspace_id: str
    role: str
    db: Session
    ip: str | None
    token_jti: str

    def can(self, perm: str) -> bool:
        return self.role in PERMISSIONS.get(perm, set())


def get_ctx(request: Request, creds: HTTPAuthorizationCredentials | None = Depends(bearer),
            x_workspace_id: str | None = Header(default=None), db: Session = Depends(get_db)) -> Ctx:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue.")
    try:
        payload = decode_token(creds.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session has expired. Sign in again.")
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session token.")
    if db.get(RevokedToken, payload["jti"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "This session was signed out.")
    user = db.get(User, payload["sub"])
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account not available.")
    q = select(Membership).where(Membership.user_id == user.id)
    if x_workspace_id:
        q = q.where(Membership.workspace_id == x_workspace_id)
    m = db.scalars(q.order_by(Membership.workspace_id)).first()
    if m is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not a member of this workspace.")
    return Ctx(user=user, workspace_id=m.workspace_id, role=m.role, db=db,
               ip=request.client.host if request.client else None, token_jti=payload["jti"])


def require(perm: str):
    def dep(ctx: Ctx = Depends(get_ctx)) -> Ctx:
        if not ctx.can(perm):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Your role ({ctx.role}) does not allow this action.")
        return ctx
    return dep
