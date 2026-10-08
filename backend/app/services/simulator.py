"""Bộ phát sự kiện giả lập. Chỉ dùng khi MOCK_CONNECTORS=true."""
from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.connectors.base import ItemIn
from app.connectors.live import item_to_payload, payload_to_item
from app.core.config import get_settings
from app.core.deps import get_user_settings
from app.db.models import LiveEvent, User, WorkItem
from app.services.sim_catalog import SCENARIOS, ScenarioCtx, persona_of, scenarios_for
from app.services.sync_service import UPDATABLE_FIELDS, recompute, sync_user, user_context, user_items

log = logging.getLogger(__name__)

MAX_EVENTS = 200  # mỗi user giữ tối đa chừng này sự kiện gần nhất


def _upsert_item(db: Session, username: str, item: ItemIn, now: datetime) -> None:
    row = db.scalar(select(WorkItem).where(
        WorkItem.username == username, WorkItem.source == item.source, WorkItem.external_id == item.external_id))
    if row is None:
        row = WorkItem(username=username, source=item.source, external_id=item.external_id)
        db.add(row)
    for f in UPDATABLE_FIELDS:
        setattr(row, f, getattr(item, f))
    row.synced_at = now
    db.flush()  # SessionLocal đặt autoflush=False: phải flush để recompute() nhìn thấy item


def _trim(db: Session, username: str) -> None:
    old = list(db.scalars(
        select(LiveEvent.id).where(LiveEvent.username == username).order_by(LiveEvent.id.desc()).offset(MAX_EVENTS)))
    if old:  # nếu sự kiện bị cắt là nguồn của một item thì lần sync sau item đó sẽ biến mất: chấp nhận được
        db.execute(delete(LiveEvent).where(LiveEvent.id.in_(old)))


def emit(db: Session, user: User, scenario: str | None = None, now: datetime | None = None,
         rng: random.Random | None = None) -> LiveEvent:
    """Phát một sự kiện: ghi live_events, upsert WorkItem ngay, rồi chấm điểm lại + sinh nhắc việc."""
    now = now or datetime.now(timezone.utc)
    rng = rng or random.Random()
    persona = persona_of(user.username)
    if scenario is None:
        enabled = set(get_user_settings(db, user.username).enabled_sources or [])
        pool = [s for s in scenarios_for(persona) if s.source in enabled]
        if not pool:
            raise ValueError("Không có nguồn dữ liệu nào đang bật")
        sc = rng.choices(pool, weights=[s.weight for s in pool])[0]
    else:
        sc = SCENARIOS.get(scenario)
        if sc is None or sc.persona != persona:
            raise ValueError(f"Kịch bản không hợp lệ: {scenario}")

    rows = user_items(db, user.username, fresh=False)
    ctx = ScenarioCtx(user=user_context(db, user), now=now, rng=rng, tz=get_settings().tz,
                      rows=rows, taken_ids={r.external_id for r in rows})
    draft = sc.build(ctx)
    if draft is None and sc.fallback:
        sc = SCENARIOS[sc.fallback]
        draft = sc.build(ctx)
    if draft is None:
        raise ValueError(f"Kịch bản {sc.key} không tạo được sự kiện")

    try:
        ev = LiveEvent(
            username=user.username, type=draft.type, scenario=sc.key, source=draft.item.source,
            severity=sc.severity, title=draft.banner[:512], external_id=draft.item.external_id,
            payload=item_to_payload(draft.item, now), created_at=now,
        )
        db.add(ev)
        db.flush()
        _upsert_item(db, user.username, payload_to_item(ev), now)  # dựng lại từ payload = đúng thứ sync sẽ tạo
        _trim(db, user.username)
        db.flush()
        recompute(db, user, now)  # commit tại đây: event + item + alert cùng một transaction
    except Exception:
        db.rollback()
        raise
    return ev


def reset(db: Session, user: User) -> None:
    """Xoá mọi sự kiện của user rồi sync lại: item do sim tạo biến mất, item bị sửa trở về dữ liệu gốc."""
    db.execute(delete(LiveEvent).where(LiveEvent.username == user.username))
    db.commit()
    sync_user(db, user)


def latest_event_id(db: Session, username: str) -> int:
    return db.scalar(select(func.max(LiveEvent.id)).where(LiveEvent.username == username)) or 0


def events_since(db: Session, username: str, since: int, limit: int = 50) -> list[LiveEvent]:
    return list(db.scalars(
        select(LiveEvent).where(LiveEvent.username == username, LiveEvent.id > since)
        .order_by(LiveEvent.id).limit(limit)))


def work_item_ids(db: Session, username: str, events: list[LiveEvent]) -> dict[tuple[str, str], int]:
    if not events:
        return {}
    ext_ids = {e.external_id for e in events}
    rows = db.execute(select(WorkItem.source, WorkItem.external_id, WorkItem.id).where(
        WorkItem.username == username, WorkItem.external_id.in_(ext_ids)))
    return {(s, x): i for s, x, i in rows}


class SimTicker:
    """Quyết định khi nào phát sự kiện tự động. `next_due` giữ trong bộ nhớ (chỉ chạy 1 worker)."""

    FIRST_DELAY = (10, 30)
    INTERVAL = (30, 90)

    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()
        self.next_due: dict[str, datetime] = {}

    def tick(self, db: Session, now: datetime | None = None, active_days: int = 14) -> list[str]:
        now = now or datetime.now(timezone.utc)
        cutoff = now - timedelta(days=active_days)
        emitted: list[str] = []
        for user in db.scalars(select(User).where(User.last_login_at >= cutoff)):
            if not get_user_settings(db, user.username).live_sim_enabled:
                self.next_due.pop(user.username, None)
                continue
            due = self.next_due.get(user.username)
            if due is None:
                self.next_due[user.username] = now + timedelta(seconds=self.rng.uniform(*self.FIRST_DELAY))
                continue
            if now < due:
                continue
            try:
                emit(db, user, now=now, rng=self.rng)
                emitted.append(user.username)
            except Exception:
                log.exception("Phát sự kiện giả lập lỗi cho %s", user.username)
                db.rollback()
            self.next_due[user.username] = now + timedelta(seconds=self.rng.uniform(*self.INTERVAL))
        return emitted
