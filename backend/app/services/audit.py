from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import AuditLog


def audit(db: Session, action: str, *, workspace_id: str | None, user_id: str | None, target_type: str | None = None,
          target_id: str | None = None, details: dict | None = None, ip: str | None = None, commit: bool = True) -> None:
    db.add(AuditLog(workspace_id=workspace_id, user_id=user_id, action=action, target_type=target_type,
                    target_id=target_id, details=details or {}, ip=ip))
    if commit:
        db.commit()


def audit_ctx(ctx, action: str, target_type: str | None = None, target_id: str | None = None,
              details: dict | None = None, commit: bool = True) -> None:
    audit(ctx.db, action, workspace_id=ctx.workspace_id, user_id=ctx.user.id, target_type=target_type,
          target_id=target_id, details=details, ip=ctx.ip, commit=commit)
