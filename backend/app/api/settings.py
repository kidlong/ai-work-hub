from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.connectors.registry import ALL_SOURCES, get_connectors
from app.core.deps import current_user, get_user_settings
from app.db.models import Device, User
from app.db.session import get_db
from app.schemas import DeviceIn, SettingsIO
from app.services.sync_service import recompute

router = APIRouter(tags=["settings"])

SOURCE_NAMES = {
    "exchange_calendar": "Lịch Outlook (Exchange)",
    "exchange_mail": "Email (Exchange)",
    "jira": "Jira",
    "confluence": "Confluence",
    "sdp": "ServiceDesk Plus",
    "teams": "Microsoft Teams",
}


@router.get("/settings", response_model=SettingsIO)
def get_settings_(user: User = Depends(current_user), db: Session = Depends(get_db)):  # noqa: ANN201
    return get_user_settings(db, user.username)


@router.put("/settings", response_model=SettingsIO)
def put_settings(body: SettingsIO, user: User = Depends(current_user), db: Session = Depends(get_db)):  # noqa: ANN201
    bad = [s for s in body.enabled_sources if s not in ALL_SOURCES]
    if bad:
        raise HTTPException(422, f"Nguồn không hợp lệ: {bad}")
    st = get_user_settings(db, user.username)
    for k, v in body.model_dump().items():
        setattr(st, k, v)
    db.commit()
    recompute(db, user)
    return st


@router.get("/sources")
def sources(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    st = get_user_settings(db, user.username)
    available = get_connectors()
    return [
        {
            "id": s,
            "name": SOURCE_NAMES[s],
            "available": s in available,
            "enabled": s in (st.enabled_sources or []),
        }
        for s in ALL_SOURCES
    ]


@router.post("/devices", status_code=204)
def register_device(body: DeviceIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> None:
    d = db.get(Device, body.token)
    if d is None:
        db.add(Device(token=body.token, username=user.username, platform=body.platform))
    else:
        d.username, d.platform = user.username, body.platform
    db.commit()


@router.delete("/devices/{token}", status_code=204)
def unregister_device(token: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> None:
    d = db.get(Device, token)
    if d is not None and d.username == user.username:
        db.delete(d)
        db.commit()
