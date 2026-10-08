from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import TokenError, decode_token
from app.db.models import User, UserSettings
from app.db.session import get_db

bearer = HTTPBearer(auto_error=False)


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Chưa đăng nhập")
    try:
        username = decode_token(creds.credentials, "access")
    except TokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    user = db.get(User, username)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Tài khoản không tồn tại")
    return user


def get_user_settings(db: Session, username: str) -> UserSettings:
    st = db.get(UserSettings, username)
    if st is None:
        st = UserSettings(username=username)
        db.add(st)
        db.commit()
        db.refresh(st)
    return st
