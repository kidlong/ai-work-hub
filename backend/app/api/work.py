from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.brief_generator import _greeting
from app.core.audit import audit
from app.core.config import get_settings
from app.core.deps import current_user
from app.db.models import Alert, DailyBrief, User, WorkItem
from app.db.session import get_db
from app.schemas import InsightOut, SnoozeIn, TodayOut, UserOut, WorkItemOut
from app.services.calendar_insights import DayInsights, analyze_day
from app.services.sync_service import fresh_scores, recompute, sync_user, user_items

router = APIRouter(tags=["work"])


def _insight_out(ins: DayInsights) -> InsightOut:
    return InsightOut(
        day=ins.day.isoformat(),
        meeting_count=ins.meeting_count,
        meeting_minutes=ins.meeting_minutes,
        load_ratio=ins.load_ratio,
        overloaded=ins.overloaded,
        conflicts=[asdict(c) for c in ins.conflicts],
        back_to_back=ins.back_to_back,
        focus_slots=[{"start": f.start, "end": f.end, "minutes": f.minutes} for f in ins.focus_slots],
    )


def _own_item(db: Session, user: User, item_id: int) -> WorkItem:
    it = db.get(WorkItem, item_id)
    if it is None or it.username != user.username:
        raise HTTPException(404, "Không tìm thấy mục công việc")
    return it


@router.get("/today", response_model=TodayOut)
def today(user: User = Depends(current_user), db: Session = Depends(get_db)) -> TodayOut:
    now = datetime.now(timezone.utc)
    tz = get_settings().tz
    local_day = now.astimezone(tz).date()
    eod = datetime.combine(local_day, datetime.max.time(), tzinfo=tz)
    items = [i for i in user_items(db, user.username) if not i.done_local]
    active = [i for i in items if not (i.snoozed_until and i.snoozed_until > now)]

    meetings = sorted(
        [i for i in items if i.kind == "meeting" and i.end_at and i.end_at >= now and i.start_at <= eod],
        key=lambda i: i.start_at,
    )
    deadlines = sorted(
        [i for i in items if i.kind != "meeting" and ((i.due_at and i.due_at <= eod) or (i.sla_due_at and i.sla_due_at <= eod))],
        key=lambda i: i.due_at or i.sla_due_at,
    )
    top = sorted([i for i in active if i.score > 0 and i.kind != "meeting"], key=lambda i: -i.score)[:3]
    ins = analyze_day([i for i in items if i.kind == "meeting"], local_day, tz, now=now)
    pending = db.scalar(
        select(func.count()).select_from(Alert).where(Alert.username == user.username, Alert.status.in_(["pending", "sent", "snoozed"]), Alert.fire_at <= now)
    )
    brief_ready = db.scalar(
        select(func.count()).select_from(DailyBrief).where(DailyBrief.username == user.username, DailyBrief.brief_date == local_day.isoformat())
    )
    stats = {
        "meetings_today": ins.meeting_count,
        "meeting_minutes": ins.meeting_minutes,
        "due_today": sum(1 for i in items if i.due_at and now <= i.due_at <= eod and i.kind != "meeting"),
        "overdue": sum(1 for i in items if i.due_at and i.due_at < now and i.kind != "meeting"),
        "sla_breached": sum(1 for i in items if i.sla_due_at and i.sla_due_at < now),
        "sla_risk": sum(1 for i in items if i.sla_due_at and now <= i.sla_due_at <= now + timedelta(hours=4)),
        "unread_important": sum(1 for i in items if i.is_unread and i.requester_role in ("manager", "vip_customer", "audit")),
        "critical": sum(1 for i in items if i.bucket == "critical"),
    }
    return TodayOut(
        greeting=_greeting(user.display_name, now, tz),
        user=UserOut.model_validate(user),
        stats=stats,
        top_priorities=top,
        next_meetings=meetings[:5],
        deadlines=deadlines[:8],
        insights=_insight_out(ins),
        pending_alerts=pending or 0,
        brief_ready=bool(brief_ready),
    )


@router.get("/work-items", response_model=list[WorkItemOut])
def list_items(
    source: str | None = None,
    kind: str | None = None,
    bucket: str | None = None,
    q: str | None = Query(default=None, max_length=100),
    include_done: bool = False,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[WorkItem]:
    stmt = select(WorkItem).where(WorkItem.username == user.username)
    if source:
        stmt = stmt.where(WorkItem.source == source)
    if kind:
        stmt = stmt.where(WorkItem.kind == kind)
    if bucket:
        stmt = stmt.where(WorkItem.bucket == bucket)
    if not include_done:
        stmt = stmt.where(WorkItem.done_local.is_(False))
    if q:
        stmt = stmt.where(WorkItem.title.ilike(f"%{q}%"))
    rows = fresh_scores(list(db.scalars(stmt.limit(500))))
    rows.sort(key=lambda i: -i.score)
    return rows[:300]


@router.get("/work-items/{item_id}", response_model=WorkItemOut)
def get_item(item_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> WorkItem:
    return fresh_scores([_own_item(db, user, item_id)])[0]


@router.post("/work-items/{item_id}/done", response_model=WorkItemOut)
def mark_done(item_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> WorkItem:
    it = _own_item(db, user, item_id)
    it.done_local = True
    db.commit()
    recompute(db, user)
    audit(db, user.username, "item_done", item_id=item_id)
    return it


@router.post("/work-items/{item_id}/undone", response_model=WorkItemOut)
def mark_undone(item_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> WorkItem:
    it = _own_item(db, user, item_id)
    it.done_local = False
    db.commit()
    recompute(db, user)
    return it


@router.post("/work-items/{item_id}/snooze", response_model=WorkItemOut)
def snooze_item(item_id: int, body: SnoozeIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> WorkItem:
    it = _own_item(db, user, item_id)
    it.snoozed_until = datetime.now(timezone.utc) + timedelta(minutes=body.minutes)
    db.commit()
    recompute(db, user)
    return it


@router.get("/insights/calendar", response_model=InsightOut)
def calendar_insights(
    day: date | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> InsightOut:
    tz = get_settings().tz
    d = day or datetime.now(timezone.utc).astimezone(tz).date()
    meetings = [i for i in user_items(db, user.username) if i.kind == "meeting"]
    now = datetime.now(timezone.utc)
    return _insight_out(analyze_day(meetings, d, tz, now=now if d == now.astimezone(tz).date() else None))


@router.post("/sync")
def manual_sync(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    result = sync_user(db, user)
    audit(db, user.username, "manual_sync", result={k: (v if isinstance(v, int) else "error") for k, v in result.items()})
    return {"result": result, "synced_at": user.last_sync_at}
