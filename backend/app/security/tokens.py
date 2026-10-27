from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt

from ..config import get_settings


def create_token(user_id: str) -> tuple[str, str, datetime]:
    s = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(minutes=s.jwt_ttl_minutes)
    jti = uuid.uuid4().hex
    token = jwt.encode({"sub": user_id, "jti": jti, "exp": exp, "iat": datetime.now(timezone.utc)},
                       s.jwt_secret, algorithm="HS256")
    return token, jti, exp


def decode_token(token: str) -> dict:
    return jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"], options={"require": ["exp", "sub", "jti"]})
