"""Đồng bộ dữ liệu từ các connector -> WorkItem, chấm điểm lại và sinh nhắc việc."""
from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.connectors.base import ConnectorError, UserContext
from app.connectors.registry import get_connectors
from app.core.config import get_settings
from app.core.deps import get_user_settings
from app.db.models import Alert, User, WorkItem
from app.services.alert_engine import AlertRules, generate_alerts
from app.services.calendar_insights import DayInsights, analyze_day
from app.services.priority_engine import score_item

log = logging.getLogger(__name__)

UPDATABLE_FIELDS = [
    "kind", "title", "preview", "url", "start_at", "end_at", "due_at", "sla_due_at", "status",
    "priority_raw", "requester", "requester_role", "participants", "location", "is_unread",
    "is_organizer", "tags", "source_updated_at",
]


def user_context(db: Session, user: User) -> UserContext:
    st = get_user_settings(db, user.username)
    domain = user.email.split("@", 1)[1] if "@" in user.email else "bank.local"
    return UserContext(
        username=user.username, email=user.email, display_name=user.display_name,
        manager_email=user.manager_email, vip_senders=list(st.vip_senders or []), internal_domain=domain,
    )


def user_items(db: Session, username: str, fresh: bool = True) -> list[WorkItem]:
    items = list(db.scalars(select(WorkItem).where(WorkItem.username == username)))
    return fresh_scores(items) if fresh else items


def fresh_scores(items: list[WorkItem], now: datetime | None = None) -> list[WorkItem]:
    """Chấm lại điểm tại thời điểm đọc để lý do (\"quá hạn 13 phút\"...) luôn khớp thời gian thực.
    Chỉ cập nhật trên object trong phiên đọc; worker sẽ lưu khi đồng bộ."""
    now = now or datetime.now(timezone.utc)
    for it in items:
        r = score_item(it, now)
        it.score, it.bucket, it.score_reasons = r.score, r.bucket, r.reasons
    return items


def insights_for(items: list[WorkItem], now: datetime, days: int = 2) -> list[DayInsights]:
    tz = get_settings().tz
    meetings = [i for i in items if i.kind == "meeting"]
    today = now.astimezone(tz).date()
    return [analyze_day(meetings, today + timedelta(days=d), tz) for d in range(days)]


def recompute(db: Session, user: User, now: datetime | None = None) -> None:
    """Chấm điểm lại + sinh lại nhắc việc từ dữ liệu đang có (không gọi hệ thống nguồn)."""
    now = now or datetime.now(timezone.utc)
    s = get_settings()
    st = get_user_settings(db, user.username)
    items = fresh_scores(user_items(db, user.username, fresh=False), now)
    db.flush()

    rules = AlertRules(meeting_lead_minutes=st.meeting_lead_minutes, quiet_start=st.quiet_start, quiet_end=st.quiet_end)
    drafts = generate_alerts(items, insights_for(items, now), rules, now, s.tz)

    existing = {a.group_key: a for a in db.scalars(select(Alert).where(Alert.username == user.username))}
    seen: set[str] = set()
    for d in drafts:
        seen.add(d.group_key)
        a = existing.get(d.group_key)
        if a is None:
            db.add(Alert(username=user.username, **asdict(d)))
        elif a.status == "pending":
            a.kind, a.severity, a.title, a.body, a.fire_at, a.work_item_id = (
                d.kind, d.severity, d.title, d.body, d.fire_at, d.work_item_id
            )
    for key, a in existing.items():
        if key not in seen and a.status == "pending":
            db.delete(a)
    db.commit()


def sync_user(db: Session, user: User, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    st = get_user_settings(db, user.username)
    ctx = user_context(db, user)
    enabled = set(st.enabled_sources or [])
    result: dict[str, str | int] = {}

    for source, conn in get_connectors().items():
        if source not in enabled:
            continue
        try:
            fetched = conn.fetch(ctx, now)
        except ConnectorError as exc:
            result[source] = f"error: {exc}"
            continue

        rows = {
            r.external_id: r
            for r in db.scalars(select(WorkItem).where(WorkItem.username == user.username, WorkItem.source == source))
        }
        returned: set[str] = set()
        for it in fetched:
            returned.add(it.external_id)
            row = rows.get(it.external_id)
            if row is None:
                row = WorkItem(username=user.username, source=source, external_id=it.external_id)
                db.add(row)
            for f in UPDATABLE_FIELDS:
                setattr(row, f, getattr(it, f))
            row.synced_at = now
        stale_ids = [r.id for k, r in rows.items() if k not in returned]
        if stale_ids:
            db.execute(delete(Alert).where(Alert.work_item_id.in_(stale_ids)))
            db.execute(delete(WorkItem).where(WorkItem.id.in_(stale_ids)))
        result[source] = len(fetched)
        db.flush()

    user.last_sync_at = now
    db.commit()
    recompute(db, user, now)
    log.info("sync user=%s result=%s", user.username, result)
    return result
