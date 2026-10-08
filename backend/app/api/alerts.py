from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import current_user
from app.db.models import Alert, User
from app.db.session import get_db
from app.schemas import AlertOut, SnoozeIn

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _own(db: Session, user: User, alert_id: int) -> Alert:
    a = db.get(Alert, alert_id)
    if a is None or a.username != user.username:
        raise HTTPException(404, "Không tìm thấy nhắc việc")
    return a


@router.get("", response_model=list[AlertOut])
def list_alerts(
    scope: str = "active",  # active = đã tới giờ & chưa xử lý | upcoming = sắp tới | all
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[Alert]:
    now = datetime.now(timezone.utc)
    stmt = select(Alert).where(Alert.username == user.username)
    if scope == "active":
        stmt = stmt.where(Alert.status.in_(["pending", "sent", "snoozed"]), Alert.fire_at <= now).order_by(Alert.fire_at.desc())
    elif scope == "upcoming":
        stmt = stmt.where(Alert.status.in_(["pending", "snoozed"]), Alert.fire_at > now).order_by(Alert.fire_at)
    else:
        stmt = stmt.where(Alert.fire_at >= now - timedelta(days=2)).order_by(Alert.fire_at.desc())
    return list(db.scalars(stmt.limit(200)))


@router.post("/{alert_id}/ack", response_model=AlertOut)
def ack(alert_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Alert:
    a = _own(db, user, alert_id)
    a.status = "acked"
    db.commit()
    return a


@router.post("/ack-all")
def ack_all(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    now = datetime.now(timezone.utc)
    rows = list(db.scalars(select(Alert).where(
        Alert.username == user.username, Alert.status.in_(["pending", "sent", "snoozed"]), Alert.fire_at <= now
    )))
    for a in rows:
        a.status = "acked"
    db.commit()
    return {"acked": len(rows)}


@router.post("/{alert_id}/snooze", response_model=AlertOut)
def snooze(alert_id: int, body: SnoozeIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Alert:
    a = _own(db, user, alert_id)
    a.fire_at = datetime.now(timezone.utc) + timedelta(minutes=body.minutes)
    a.status = "snoozed"  # recompute() không ghi đè trạng thái này
    db.commit()
    return a
