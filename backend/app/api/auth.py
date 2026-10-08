from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.config import get_settings
from app.core.deps import current_user, get_user_settings
from app.core.ldap_auth import AuthError, authenticate
from app.core.security import TokenError, create_token_pair, decode_token
from app.db.models import User
from app.db.session import get_db
from app.schemas import LoginIn, RefreshIn, TokenOut, UserOut
from app.services.sync_service import sync_user

router = APIRouter(prefix="/auth", tags=["auth"])

DEMO_VIP = {"lan.pham": ["saoviet.example"]}


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)) -> dict:
    try:
        p = authenticate(body.username, body.password)
    except AuthError as exc:
        audit(db, body.username.strip().lower()[:64], "login_failed")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    user = db.get(User, p.username)
    first_login = user is None
    if user is None:
        user = User(username=p.username, email=p.email, display_name=p.display_name)
        db.add(user)
    user.email, user.display_name, user.title = p.email, p.display_name, p.title
    user.department, user.manager_email = p.department, p.manager_email
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    st = get_user_settings(db, user.username)
    if first_login and get_settings().auth_mode == "mock" and user.username in DEMO_VIP:
        st.vip_senders = DEMO_VIP[user.username]
        db.commit()
    if first_login or user.last_sync_at is None:
        sync_user(db, user)  # lần đầu: đồng bộ ngay để app có dữ liệu
    audit(db, user.username, "login")
    return create_token_pair(user.username)


@router.post("/refresh", response_model=TokenOut)
def refresh(body: RefreshIn, db: Session = Depends(get_db)) -> dict:
    try:
        username = decode_token(body.refresh_token, "refresh")
    except TokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    if db.get(User, username) is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Tài khoản không tồn tại")
    return create_token_pair(username)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> User:
    return user
