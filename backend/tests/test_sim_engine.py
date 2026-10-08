import random
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.core.deps import get_user_settings
from app.db.models import Alert, LiveEvent, User, WorkItem
from app.db.session import SessionLocal
from app.services import simulator
from app.services.sync_service import sync_user


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture
def env(client, login):
    login("an.nguyen")
    login("lan.pham")
    with SessionLocal() as db:
        yield db
    with SessionLocal() as db2:
        for name in ("an.nguyen", "lan.pham"):  # khôi phục cài đặt TRƯỚC, để reset() sync đủ mọi nguồn
            st = get_user_settings(db2, name)
            st.live_sim_enabled = True
            st.enabled_sources = ["exchange_mail", "exchange_calendar", "jira", "confluence", "sdp", "teams"]
        db2.commit()
        for name in ("an.nguyen", "lan.pham"):
            simulator.reset(db2, db2.get(User, name))


def _row(db, ext_id, username="an.nguyen"):
    db.expire_all()
    return db.scalar(select(WorkItem).where(WorkItem.username == username, WorkItem.external_id == ext_id))


def test_emit_manager_mail_creates_event_item_and_alert(env):
    user = env.get(User, "an.nguyen")
    ev = simulator.emit(env, user, "mail_manager_deadline", rng=random.Random(1))
    assert ev.type == "new_item" and ev.scenario == "mail_manager_deadline" and ev.severity == "warning"
    item = _row(env, ev.external_id)
    assert item and item.is_unread and item.requester_role == "manager" and item.kind == "email"
    kinds = {a.kind for a in env.scalars(select(Alert).where(Alert.work_item_id == item.id))}
    assert "important_message" in kinds


def test_sim_item_survives_sync(env):
    user = env.get(User, "an.nguyen")
    ev = simulator.emit(env, user, "teams_mention", rng=random.Random(1))
    sync_user(env, user)
    assert _row(env, ev.external_id) is not None


def test_update_event_overrides_and_stays_anchored_after_sync(env):
    user = env.get(User, "an.nguyen")
    ev = simulator.emit(env, user, "sdp_sla_escalation", rng=random.Random(2))
    assert ev.type == "update_item"
    sync_user(env, user, now=ev.created_at + timedelta(minutes=3))
    row = _row(env, ev.external_id)
    assert abs((row.sla_due_at - (ev.created_at + timedelta(minutes=10))).total_seconds()) < 1
    count = env.scalar(select(func.count()).select_from(WorkItem).where(
        WorkItem.username == "an.nguyen", WorkItem.external_id == ev.external_id))
    assert count == 1


def test_update_falls_back_to_new_item_when_no_target(env):
    user = env.get(User, "an.nguyen")
    first = simulator.emit(env, user, "jira_unblocked", rng=random.Random(1))  # CORE-2455 đang Blocked
    assert first.scenario == "jira_unblocked" and first.type == "update_item"
    second = simulator.emit(env, user, "jira_unblocked", rng=random.Random(1))  # hết đối tượng
    assert second.scenario == "jira_assigned_highest" and second.type == "new_item"


def test_meeting_conflict_raises_conflict_alert(env):
    user = env.get(User, "an.nguyen")
    now = _now()
    env.add(WorkItem(username="an.nguyen", source="exchange_calendar", external_id="test-target-meeting",
                     kind="meeting", title="Họp mục tiêu (test)", start_at=now + timedelta(hours=2),
                     end_at=now + timedelta(hours=3)))
    env.commit()
    ev = simulator.emit(env, user, "meeting_conflict", now=now, rng=random.Random(1))
    assert ev.scenario == "meeting_conflict"
    bodies = [a.body for a in env.scalars(select(Alert).where(Alert.username == "an.nguyen", Alert.kind == "conflict"))]
    # đối tượng bị trùng do rng chọn trong mọi cuộc họp còn tương lai (kể cả họp demo), nên lấy tên từ banner
    target = ev.title.split('"')[1]
    assert any(target in b and "Họp khẩn" in b for b in bodies)


def test_done_local_survives_update_and_sync(env):
    user = env.get(User, "an.nguyen")
    ev = simulator.emit(env, user, "sdp_sla_escalation", rng=random.Random(2))
    row = _row(env, ev.external_id)
    row.done_local = True
    env.commit()
    sync_user(env, user)
    assert _row(env, ev.external_id).done_local is True


def test_two_emits_at_same_instant_do_not_collide(env):
    user = env.get(User, "an.nguyen")
    now, rng = _now(), random.Random(5)
    a = simulator.emit(env, user, "teams_mention", now=now, rng=rng)
    b = simulator.emit(env, user, "teams_mention", now=now, rng=rng)
    assert a.external_id != b.external_id
    assert _row(env, a.external_id) and _row(env, b.external_id)


def test_random_pick_skips_disabled_sources(env):
    user = env.get(User, "an.nguyen")
    st = get_user_settings(env, "an.nguyen")
    st.enabled_sources = ["exchange_mail"]
    env.commit()
    rng, now = random.Random(7), _now()
    for i in range(25):
        ev = simulator.emit(env, user, now=now + timedelta(seconds=i), rng=rng)
        assert ev.source == "exchange_mail"


def test_no_enabled_sources_raises(env):
    user = env.get(User, "an.nguyen")
    get_user_settings(env, "an.nguyen").enabled_sources = []
    env.commit()
    with pytest.raises(ValueError):
        simulator.emit(env, user)


def test_invalid_or_wrong_persona_scenario_raises(env):
    user = env.get(User, "an.nguyen")
    with pytest.raises(ValueError):
        simulator.emit(env, user, "khong_ton_tai")
    with pytest.raises(ValueError):
        simulator.emit(env, user, "rm_meeting_new")  # kịch bản của persona RM


def test_failed_emit_leaves_no_orphan_event(env, monkeypatch):
    user = env.get(User, "an.nguyen")

    def boom(*a, **k):
        raise RuntimeError("recompute lỗi")

    monkeypatch.setattr(simulator, "recompute", boom)
    with pytest.raises(RuntimeError):
        simulator.emit(env, user, "teams_mention", rng=random.Random(1))
    assert simulator.latest_event_id(env, "an.nguyen") == 0


def test_trim_keeps_latest_events(env, monkeypatch):
    monkeypatch.setattr(simulator, "MAX_EVENTS", 3)
    user = env.get(User, "an.nguyen")
    rng, now = random.Random(3), _now()
    evs = [simulator.emit(env, user, "teams_mention", now=now + timedelta(seconds=i), rng=rng) for i in range(5)]
    ids = list(env.scalars(select(LiveEvent.id).where(LiveEvent.username == "an.nguyen").order_by(LiveEvent.id)))
    assert ids == [e.id for e in evs[-3:]]


def test_reset_removes_sim_items_and_events(env):
    user = env.get(User, "an.nguyen")
    ev = simulator.emit(env, user, "mail_manager_deadline", rng=random.Random(1))
    simulator.reset(env, user)
    assert simulator.latest_event_id(env, "an.nguyen") == 0
    assert _row(env, ev.external_id) is None


def test_events_since_and_latest_id(env):
    user = env.get(User, "an.nguyen")
    rng, now = random.Random(4), _now()
    evs = [simulator.emit(env, user, "teams_mention", now=now + timedelta(seconds=i), rng=rng) for i in range(3)]
    assert simulator.latest_event_id(env, "an.nguyen") == evs[-1].id
    assert simulator.latest_event_id(env, "lan.pham") == 0
    got = simulator.events_since(env, "an.nguyen", evs[0].id)
    assert [e.id for e in got] == [evs[1].id, evs[2].id]
    assert [e.id for e in simulator.events_since(env, "an.nguyen", 0, limit=2)] == [evs[0].id, evs[1].id]
    ids = simulator.work_item_ids(env, "an.nguyen", got)
    assert ids[(got[0].source, got[0].external_id)] == _row(env, got[0].external_id).id


def test_ticker_emits_only_for_active_enabled_users(env):
    get_user_settings(env, "lan.pham").live_sim_enabled = False
    env.commit()
    ticker = simulator.SimTicker(rng=random.Random(3))
    t0 = _now()
    assert ticker.tick(env, t0) == []  # lần đầu chỉ đặt lịch
    assert ticker.tick(env, t0 + timedelta(seconds=31)) == ["an.nguyen"]
    assert ticker.tick(env, t0 + timedelta(seconds=32)) == []  # chưa tới lượt kế (>= 30s)
    assert ticker.tick(env, t0 + timedelta(seconds=32 + 91)) == ["an.nguyen"]
