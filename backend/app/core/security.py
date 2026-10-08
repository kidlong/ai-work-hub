from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import get_settings

ALGORITHM = "HS256"


class TokenError(Exception):
    pass


def _encode(sub: str, typ: str, ttl: timedelta) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {"sub": sub, "typ": typ, "iat": now, "exp": now + ttl, "jti": uuid.uuid4().hex}
    return jwt.encode(payload, s.jwt_secret, algorithm=ALGORITHM)


def create_token_pair(username: str) -> dict:
    s = get_settings()
    return {
        "access_token": _encode(username, "access", timedelta(minutes=s.access_token_minutes)),
        "refresh_token": _encode(username, "refresh", timedelta(hours=s.refresh_token_hours)),
        "token_type": "bearer",
        "expires_in": s.access_token_minutes * 60,
    }


def decode_token(token: str, expected_type: str) -> str:
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise TokenError("Token không hợp lệ hoặc đã hết hạn") from exc
    if payload.get("typ") != expected_type:
        raise TokenError("Sai loại token")
    return payload["sub"]
