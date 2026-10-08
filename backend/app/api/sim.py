"""Endpoint giả lập realtime. Toàn bộ router chỉ hoạt động khi MOCK_CONNECTORS=true."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.deps import current_user, require_mock
from app.db.models import LiveEvent, User
from app.db.session import get_db
from app.schemas import EventsOut, LiveEventOut, ScenarioOut, SimEmitIn
from app.services import simulator
from app.services.sim_catalog import persona_of, scenarios_for

router = APIRouter(tags=["sim"], dependencies=[Depends(require_mock)])


def _out(ev: LiveEvent, ids: dict[tuple[str, str], int]) -> LiveEventOut:
    return LiveEventOut(
        id=ev.id, type=ev.type, scenario=ev.scenario, source=ev.source, severity=ev.severity, title=ev.title,
        work_item_id=ids.get((ev.source, ev.external_id)), created_at=ev.created_at,
    )


@router.get("/events", response_model=EventsOut)
def list_events(
    since: int | None = Query(default=None, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> EventsOut:
    latest = simulator.latest_event_id(db, user.username)
    if since is None:  # lần đầu: chỉ lấy con trỏ, không phát lại lịch sử
        return EventsOut(events=[], latest_id=latest)
    evs = simulator.events_since(db, user.username, since, limit)
    ids = simulator.work_item_ids(db, user.username, evs)
    return EventsOut(events=[_out(e, ids) for e in evs], latest_id=latest)


@router.post("/sim/emit", response_model=LiveEventOut)
def sim_emit(body: SimEmitIn | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)) -> LiveEventOut:
    try:
        ev = simulator.emit(db, user, body.scenario if body else None)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    audit(db, user.username, "sim_emit", scenario=ev.scenario)
    return _out(ev, simulator.work_item_ids(db, user.username, [ev]))


@router.get("/sim/scenarios", response_model=list[ScenarioOut])
def sim_scenarios(user: User = Depends(current_user)) -> list[ScenarioOut]:
    return [ScenarioOut(key=s.key, label=s.label) for s in scenarios_for(persona_of(user.username))]


@router.post("/sim/reset", status_code=204)
def sim_reset(user: User = Depends(current_user), db: Session = Depends(get_db)) -> None:
    simulator.reset(db, user)
    audit(db, user.username, "sim_reset")
