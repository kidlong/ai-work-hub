from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.connectors.base import ItemIn, UserContext
from app.connectors.live import item_from_row, item_to_payload, payload_to_item
from app.connectors.mock import MockConnector
from app.db import models  # noqa: F401  (đăng ký model)
from app.db.models import LiveEvent
from app.db.session import Base

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
CTX = UserContext("an.nguyen", "an.nguyen@bank.local", "Nguyễn Văn An", manager_email="minh.tran@bank.local")


def test_payload_roundtrip_keeps_times_anchored_to_created_at():
    anchor = datetime(2026, 10, 8, 3, 0, tzinfo=timezone.utc)
    item = ItemIn("jira", "X-1", "task", "t", due_at=anchor + timedelta(hours=2), tags=["a"], participants=["p"])
    payload = item_to_payload(item, anchor)
    assert payload["offsets"] == {"due_at": 7200}
    ev = SimpleNamespace(source="jira", external_id="X-1", created_at=anchor, payload=payload)
    back = payload_to_item(ev)
    assert back.due_at == item.due_at and back.start_at is None
    assert back.tags == ["a"] and back.participants == ["p"] and back.title == "t"


def test_item_from_row_copies_lists():
    row = SimpleNamespace(
        source="sdp", external_id="1", kind="ticket", title="t", preview="", url="", status="Open", priority_raw="High",
        requester="r", requester_role="peer", participants=["a"], location="", is_unread=False, is_organizer=False,
        tags=["incident"], start_at=None, end_at=None, due_at=None, sla_due_at=None, source_updated_at=None,
    )
    item = item_from_row(row)
    item.tags.append("escalated")
    assert row.tags == ["incident"]


def _factory(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng, expire_on_commit=False)


def _event(username, source, item, now, kind="new_item"):
    return LiveEvent(
        username=username, type=kind, scenario="x", source=source, severity="info", title="t",
        external_id=item.external_id, payload=item_to_payload(item, now), created_at=now,
    )


def test_mock_connector_appends_new_and_overrides_same_id(tmp_path):
    sf = _factory(tmp_path)
    now = datetime.now(timezone.utc)
    base = MockConnector("sdp", TZ).fetch(CTX, now)
    target = base[0]
    new_item = ItemIn("sdp", "sim-new", "ticket", "[SDP#1] mới", sla_due_at=now + timedelta(minutes=60))
    upd = ItemIn("sdp", target.external_id, "ticket", target.title, sla_due_at=now + timedelta(minutes=10))
    with sf() as db:
        db.add(_event("an.nguyen", "sdp", new_item, now))
        db.add(_event("an.nguyen", "sdp", upd, now, "update_item"))
        db.commit()

    # 3 phút sau: mốc của sự kiện vẫn neo theo created_at, không trôi theo "bây giờ"
    out = MockConnector("sdp", TZ, sf).fetch(CTX, now + timedelta(minutes=3))
    ids = [i.external_id for i in out]
    assert ids.count(target.external_id) == 1 and "sim-new" in ids
    got = next(i for i in out if i.external_id == target.external_id)
    assert abs((got.sla_due_at - (now + timedelta(minutes=10))).total_seconds()) < 1


def test_mock_connector_isolates_users_and_sources(tmp_path):
    sf = _factory(tmp_path)
    now = datetime.now(timezone.utc)
    with sf() as db:
        db.add(_event("an.nguyen", "sdp", ItemIn("sdp", "sim-new", "ticket", "x"), now))
        db.commit()
    other = UserContext("lan.pham", "lan.pham@bank.local", "Lan")
    assert "sim-new" not in [i.external_id for i in MockConnector("sdp", TZ, sf).fetch(other, now)]
    assert "sim-new" not in [i.external_id for i in MockConnector("jira", TZ, sf).fetch(CTX, now)]


def test_mock_connector_without_session_factory_is_unchanged():
    now = datetime.now(timezone.utc)
    assert [i.external_id for i in MockConnector("jira", TZ).fetch(CTX, now)] == [
        "CORE-2481", "CORE-2455", "OPB-118", "CORE-2502"
    ]
