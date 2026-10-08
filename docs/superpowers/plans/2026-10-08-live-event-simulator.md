# Live Event Simulator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ở chế độ `MOCK_CONNECTORS=true`, dữ liệu mới (mail, ticket, mention, họp...) tự xuất hiện khi người dùng đang dùng app mobile và hiện banner ngay, qua đúng đường ống thật (upsert WorkItem → chấm điểm → Alert).

**Architecture:** Bảng `live_events` vừa là feed cho app vừa là trạng thái bền của mock (`MockConnector` dựng lại item từ bảng này nên sync 5 phút không xoá được). `services/simulator.py` phát sự kiện theo danh mục kịch bản theo persona; worker phát tự động, API phát thủ công. App Flutter poll `GET /events?since=` mỗi 8 giây, invalidate các provider và hiện banner.

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy 2 / APScheduler / pytest; Flutter 3.47 / Riverpod 3 / Dio / go_router.

**Spec:** [docs/superpowers/specs/2026-10-08-live-event-simulator-design.md](../specs/2026-10-08-live-event-simulator-design.md)

> **Lưu ý môi trường:** thư mục dự án **không phải git repo**, nên mỗi task kết thúc bằng bước **Checkpoint** (chạy test) thay cho bước commit. Nếu bạn `git init` sau này, hãy commit tại mỗi checkpoint.
> Lệnh backend chạy trong `backend/` với venv có sẵn: `cd backend && source .venv/bin/activate`. Lệnh mobile chạy trong `mobile/`.

## Global Constraints

- Mọi endpoint mới (`/events`, `/sim/emit`, `/sim/scenarios`, `/sim/reset`) trả **404** khi `mock_connectors=false`; job `sim` của worker **chỉ đăng ký khi** `mock_connectors=true`.
- Giữ tối đa **200** `live_events` gần nhất mỗi user.
- Worker: job `job_sim_tick` chạy mỗi **10 giây**; lần đầu của mỗi user phát sau **10–30 giây**, các lần sau cách nhau ngẫu nhiên **30–90 giây**.
- App poll mỗi **8 giây**; lỗi mạng giãn dần tối đa **30 giây**, thành công thì về 8 giây; gặp 404 thì tự dừng; dừng khi app `paused`.
- `LiveEventOut` **không** trả `payload`. Audit log chỉ ghi `scenario`, không ghi nội dung item.
- Mốc thời gian trong `payload` lưu dạng **offset giây so với `created_at`**.
- Dữ liệu hoàn toàn hư cấu (tên công ty, người, số TK, SĐT).
- Không thêm Alembic; cột mới `user_settings.live_sim_enabled` thêm bằng `ALTER TABLE` lúc khởi động, **chỉ khi `app_env == "dev"`**.
- Không thêm dependency mới (cả Python lẫn Dart).

## Review Focus

Những tình huống spec hàm ý nhưng không nói rõ, dễ làm hỏng trải nghiệm nhất (mỗi dòng có test ghim ở task ghi trong ngoặc):

1. Con trỏ `since` của app **lớn hơn** `latest_id` của server (sau `reset`, hoặc DB dựng lại): app phải tự hạ con trỏ, không đứng im mãi. (Task 5 API, Task 8 controller)
2. Hai lần `emit` trong **cùng một thời điểm** không được đè lên nhau (trùng `external_id`). (Task 4)
3. Người dùng đã **đánh dấu xong** một item rồi sự kiện `update_item` / lần sync sau tới: `done_local` phải được giữ. (Task 4)
4. Người dùng **tắt một nguồn** (ví dụ Teams): chọn ngẫu nhiên không được phát sự kiện của nguồn đó. (Task 4)
5. `since` âm / không phải số, `limit` ngoài `1..200` phải bị từ chối 422 chứ không trả 500. (Task 5)

---

## File Structure

**Backend (tạo mới)**
| File | Trách nhiệm |
|---|---|
| `backend/app/connectors/live.py` | Chuyển `ItemIn` ⇄ payload của `LiveEvent`; `item_from_row` (WorkItem → ItemIn) |
| `backend/app/services/sim_catalog.py` | `Scenario`, `ScenarioCtx`, `Draft`, 18 kịch bản (12 IT + 6 RM), `persona_of`, `scenarios_for` |
| `backend/app/services/simulator.py` | `emit`, `reset`, `latest_event_id`, `events_since`, `work_item_ids`, `SimTicker` |
| `backend/app/api/sim.py` | Router `/events`, `/sim/*` |
| `backend/tests/test_db_migrate.py` | Test `ensure_dev_columns` + cờ `live_sim_enabled` |
| `backend/tests/test_live_payload.py` | Test chuyển đổi payload + `MockConnector` hợp nhất sự kiện |
| `backend/tests/test_sim_catalog.py` | Test từng kịch bản |
| `backend/tests/test_sim_engine.py` | Test `emit`/`reset`/`SimTicker` |
| `backend/tests/test_sim_api.py` | Test endpoint |
| `backend/tests/test_worker_sim.py` | Test job & lịch worker |

**Backend (sửa)**
`db/models.py` (model `LiveEvent`, cột `live_sim_enabled`), `db/session.py` (`ensure_dev_columns`), `schemas.py`, `core/deps.py` (`require_mock`), `connectors/mock.py`, `connectors/registry.py`, `main.py`, `worker.py`, `tests/conftest.py`.

**Mobile (tạo mới)**
`lib/data/live_events.dart` (controller + `liveBannerText`), `test/live_events_test.dart`, `test/fixtures/events.json`, `test/fixtures/scenarios.json`.

**Mobile (sửa)**
`lib/domain/models.dart`, `lib/data/repository.dart`, `lib/app/app.dart`, `lib/features/settings/settings_screen.dart`, `test/models_test.dart`, `test/fixtures/settings.json`.

**Docs (sửa)**: `README.md`, `docs/architecture.md`.

---

### Task 1: Model `LiveEvent`, cờ `live_sim_enabled`, migration dev

**Files:**
- Modify: `backend/app/db/models.py` (thêm `LiveEvent`, cột `UserSettings.live_sim_enabled`)
- Modify: `backend/app/db/session.py` (thêm `ensure_dev_columns`, gọi trong `init_db`)
- Modify: `backend/app/schemas.py:137-145` (`SettingsIO`)
- Modify: `backend/tests/conftest.py` (fixture `client`, `login`; `source_updated_at` trong `make_item`)
- Create: `backend/tests/test_db_migrate.py`

**Interfaces:**
- Produces: `app.db.models.LiveEvent` (cột: `id, username, type, scenario, source, severity, title, external_id, payload, created_at`); `UserSettings.live_sim_enabled: bool`; `app.db.session.ensure_dev_columns(eng=None) -> None`; `SettingsIO.live_sim_enabled: bool = True`; fixtures pytest `client` (module-scope) và `login(user="an.nguyen") -> dict` (header Authorization).

- [ ] **Step 1: Sửa conftest — thêm fixture dùng chung**

Trong `backend/tests/conftest.py`, thêm `source_updated_at=None` vào dict `base` của `make_item` (sau `snoozed_until=None,`) và thêm cuối file:

```python
@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def login(client):
    def _login(user: str = "an.nguyen") -> dict:
        r = client.post("/api/v1/auth/login", json={"username": user, "password": "demo"})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    return _login
```

- [ ] **Step 2: Viết test thất bại**

Tạo `backend/tests/test_db_migrate.py`:

```python
from sqlalchemy import create_engine, inspect, text

from app.db.session import ensure_dev_columns


def test_adds_missing_column_with_default_true_and_is_idempotent(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE user_settings (username VARCHAR(128) PRIMARY KEY, brief_time VARCHAR(5))"))
        c.execute(text("INSERT INTO user_settings VALUES ('an.nguyen', '07:30')"))

    ensure_dev_columns(eng)
    ensure_dev_columns(eng)  # chạy lần 2 không lỗi

    assert "live_sim_enabled" in {c["name"] for c in inspect(eng).get_columns("user_settings")}
    with eng.connect() as c:
        assert c.execute(text("SELECT live_sim_enabled FROM user_settings")).scalar() == 1


def test_noop_when_table_missing(tmp_path):
    ensure_dev_columns(create_engine(f"sqlite:///{tmp_path / 'empty.db'}"))


def test_settings_roundtrip_live_sim_flag(client, login):
    h = login()
    st = client.get("/api/v1/settings", headers=h).json()
    assert st["live_sim_enabled"] is True
    st["live_sim_enabled"] = False
    assert client.put("/api/v1/settings", json=st, headers=h).json()["live_sim_enabled"] is False
    st["live_sim_enabled"] = True
    assert client.put("/api/v1/settings", json=st, headers=h).json()["live_sim_enabled"] is True
```

- [ ] **Step 3: Chạy test, xác nhận thất bại**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_db_migrate.py -v`
Expected: FAIL (`ImportError: cannot import name 'ensure_dev_columns'`).

- [ ] **Step 4: Thêm model và cột**

Trong `backend/app/db/models.py`, đổi dòng import đầu thành:

```python
from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, true
```

Thêm vào `UserSettings` (sau `focus_time_suggestions`):

```python
    live_sim_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
```

Thêm cuối file:

```python
class LiveEvent(Base):
    """Sự kiện giả lập (chỉ dùng ở chế độ MOCK): vừa là feed cho app, vừa là trạng thái bền của MockConnector."""

    __tablename__ = "live_events"
    __table_args__ = {"sqlite_autoincrement": True}  # không tái sử dụng id sau khi xoá

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(ForeignKey("users.username"), index=True)
    type: Mapped[str] = mapped_column(String(16))  # new_item | update_item
    scenario: Mapped[str] = mapped_column(String(48))
    source: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16), default="info")  # info | warning | critical
    title: Mapped[str] = mapped_column(String(512))  # nội dung banner
    external_id: Mapped[str] = mapped_column(String(512))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)  # trường ItemIn; thời gian dạng offset giây so với created_at
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
```

- [ ] **Step 5: Thêm `ensure_dev_columns`**

Trong `backend/app/db/session.py`, đổi import `from sqlalchemy import DateTime, create_engine` thành `from sqlalchemy import DateTime, create_engine, inspect, text`, rồi thay hàm `init_db` bằng:

```python
def ensure_dev_columns(eng=None) -> None:  # noqa: ANN001
    """Chỉ cho dev: DB cũ chưa có cột mới thì ALTER TABLE (dự án chưa dùng Alembic)."""
    eng = eng or engine
    insp = inspect(eng)
    if "user_settings" not in insp.get_table_names():
        return
    if "live_sim_enabled" in {c["name"] for c in insp.get_columns("user_settings")}:
        return
    default = "1" if eng.dialect.name == "sqlite" else "TRUE"
    with eng.begin() as conn:
        conn.execute(text(f"ALTER TABLE user_settings ADD COLUMN live_sim_enabled BOOLEAN NOT NULL DEFAULT {default}"))


def init_db() -> None:
    from app.db import models  # noqa: F401  (đăng ký model)

    Base.metadata.create_all(bind=engine)
    if get_settings().app_env == "dev":
        ensure_dev_columns()
```

- [ ] **Step 6: Thêm field vào `SettingsIO`**

Trong `backend/app/schemas.py`, thêm dòng sau `focus_time_suggestions: bool = True` của `SettingsIO`:

```python
    live_sim_enabled: bool = True
```

- [ ] **Step 7: Chạy test, xác nhận đạt**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_db_migrate.py -v`
Expected: 3 passed.

- [ ] **Step 8: Checkpoint — không làm hỏng test cũ**

Run: `cd backend && source .venv/bin/activate && pytest -q`
Expected: toàn bộ pass (35 test cũ + 3 test mới).

---

### Task 2: Payload `LiveEvent` ⇄ `ItemIn` và `MockConnector` hợp nhất sự kiện

**Files:**
- Create: `backend/app/connectors/live.py`
- Modify: `backend/app/connectors/mock.py:172-178` (`MockConnector`)
- Modify: `backend/app/connectors/registry.py:11-15`
- Create: `backend/tests/test_live_payload.py`

**Interfaces:**
- Consumes: `LiveEvent` (Task 1), `ItemIn`/`UserContext` (`connectors/base.py`).
- Produces:
  - `TIME_FIELDS: tuple[str, ...]`, `PLAIN_FIELDS: tuple[str, ...]`
  - `item_to_payload(item: ItemIn, anchor: datetime) -> dict`
  - `payload_to_item(ev) -> ItemIn` (`ev` cần `source, external_id, created_at, payload`)
  - `item_from_row(row) -> ItemIn` (row là `WorkItem` hoặc object tương đương)
  - `MockConnector(source, tz, session_factory=None)`

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/test_live_payload.py`:

```python
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
```

- [ ] **Step 2: Chạy test, xác nhận thất bại**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_live_payload.py -v`
Expected: FAIL (`ModuleNotFoundError: app.connectors.live`).

- [ ] **Step 3: Tạo `connectors/live.py`**

```python
"""Chuyển đổi giữa ItemIn và payload của LiveEvent.

Mốc thời gian lưu dạng offset giây so với `created_at` của sự kiện, nên item dựng lại sau mỗi lần sync
có cùng mốc giờ với lúc phát (không trôi theo "bây giờ").
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Protocol

from app.connectors.base import ItemIn

TIME_FIELDS = ("start_at", "end_at", "due_at", "sla_due_at", "source_updated_at")
PLAIN_FIELDS = (
    "kind", "title", "preview", "url", "status", "priority_raw", "requester", "requester_role",
    "participants", "location", "is_unread", "is_organizer", "tags",
)


class EventLike(Protocol):
    source: str
    external_id: str
    created_at: datetime
    payload: dict


def item_to_payload(item: ItemIn, anchor: datetime) -> dict[str, Any]:
    payload: dict[str, Any] = {f: getattr(item, f) for f in PLAIN_FIELDS}
    payload["participants"] = list(item.participants)
    payload["tags"] = list(item.tags)
    payload["offsets"] = {
        f: round((getattr(item, f) - anchor).total_seconds()) for f in TIME_FIELDS if getattr(item, f) is not None
    }
    return payload


def payload_to_item(ev: EventLike) -> ItemIn:
    p = ev.payload
    times = {f: ev.created_at + timedelta(seconds=s) for f, s in p.get("offsets", {}).items() if f in TIME_FIELDS}
    plain = {f: p[f] for f in PLAIN_FIELDS if f in p}
    return ItemIn(source=ev.source, external_id=ev.external_id, **plain, **times)


def item_from_row(row: Any) -> ItemIn:
    """WorkItem (hoặc object tương đương) -> ItemIn, sao chép list để không sửa nhầm bản gốc."""
    plain = {f: getattr(row, f) for f in PLAIN_FIELDS}
    plain["participants"] = list(row.participants or [])
    plain["tags"] = list(row.tags or [])
    times = {f: getattr(row, f) for f in TIME_FIELDS}
    return ItemIn(source=row.source, external_id=row.external_id, **plain, **times)
```

- [ ] **Step 4: Cập nhật `MockConnector`**

Trong `backend/app/connectors/mock.py`, thêm vào phần import đầu file:

```python
from sqlalchemy import select

from app.connectors.live import payload_to_item
from app.db.models import LiveEvent
```

Thay toàn bộ class `MockConnector` (cuối file) bằng:

```python
class MockConnector(Connector):
    """Dữ liệu gốc + các sự kiện giả lập đã phát (bảng live_events). Cùng external_id thì sự kiện ghi đè."""

    def __init__(self, source: str, tz, session_factory=None):  # noqa: ANN001
        self.source = source
        self.tz = tz
        self.session_factory = session_factory

    def fetch(self, ctx: UserContext, now: datetime) -> list[ItemIn]:
        base = [i for i in mock_dataset(ctx, now, self.tz) if i.source == self.source]
        if self.session_factory is None:
            return base
        with self.session_factory() as db:
            events = list(db.scalars(
                select(LiveEvent)
                .where(LiveEvent.username == ctx.username, LiveEvent.source == self.source)
                .order_by(LiveEvent.id)
            ))
        merged = {i.external_id: i for i in base}
        for ev in events:
            merged[ev.external_id] = payload_to_item(ev)
        return list(merged.values())
```

- [ ] **Step 5: Truyền `SessionLocal` từ registry**

Trong `backend/app/connectors/registry.py`, thay khối `if settings.mock_connectors:` bằng:

```python
    if settings.mock_connectors:
        from app.connectors.mock import MockConnector
        from app.db.session import SessionLocal

        return {src: MockConnector(src, settings.tz, SessionLocal) for src in ALL_SOURCES}
```

- [ ] **Step 6: Chạy test, xác nhận đạt**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_live_payload.py -v`
Expected: 5 passed.

- [ ] **Step 7: Checkpoint**

Run: `cd backend && source .venv/bin/activate && pytest -q`
Expected: toàn bộ pass.

---

### Task 3: Danh mục kịch bản (`sim_catalog.py`)

**Files:**
- Create: `backend/app/services/sim_catalog.py`
- Create: `backend/tests/test_sim_catalog.py`

**Interfaces:**
- Consumes: `ItemIn`, `UserContext`, `item_from_row`.
- Produces:
  - `persona_of(username: str) -> str` (`"rm"` nếu `lan.pham`, còn lại `"it"`)
  - `Draft(type: str, banner: str, item: ItemIn)`
  - `ScenarioCtx(user: UserContext, now: datetime, rng: random.Random, tz: ZoneInfo, rows: list = [], taken_ids: set[str] = set())`
  - `Scenario(key, label, persona, source, weight, severity, build, fallback=None)` với `build(ctx) -> Draft | None`
  - `SCENARIOS: dict[str, Scenario]`, `scenarios_for(persona: str) -> list[Scenario]`

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/test_sim_catalog.py`:

```python
import json
import random
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.connectors.base import UserContext
from app.connectors.live import TIME_FIELDS, item_to_payload
from app.services.sim_catalog import SCENARIOS, ScenarioCtx, persona_of, scenarios_for

NOW = datetime(2026, 10, 8, 3, 0, tzinfo=timezone.utc)
TZ = ZoneInfo("Asia/Ho_Chi_Minh")
IT = UserContext("an.nguyen", "an.nguyen@bank.local", "Nguyễn Văn An", manager_email="minh.tran@bank.local")
RM = UserContext("lan.pham", "lan.pham@bank.local", "Phạm Thị Lan", manager_email="hung.le@bank.local")
ROLES = {"manager", "vip_customer", "audit", "peer", "external"}
KINDS = {"email", "meeting", "task", "ticket", "page", "chat"}


def ctx(user=IT, seed=1, rows=None):
    return ScenarioCtx(user=user, now=NOW, rng=random.Random(seed), tz=TZ, rows=rows or [])


def test_catalog_sizes_and_unique_keys():
    assert len(scenarios_for("it")) == 12 and len(scenarios_for("rm")) == 6
    assert len(SCENARIOS) == 18
    assert persona_of("an.nguyen") == "it" and persona_of("lan.pham") == "rm"


@pytest.mark.parametrize("sc", list(SCENARIOS.values()), ids=lambda s: s.key)
def test_every_scenario_builds_valid_draft_or_has_fallback(sc):
    user = RM if sc.persona == "rm" else IT
    draft = sc.build(ctx(user))
    if draft is None:  # kịch bản 'update' cần đối tượng có sẵn -> phải có fallback cùng persona và cùng nguồn
        assert sc.fallback, f"{sc.key} trả None nhưng không có fallback"
        fb = SCENARIOS[sc.fallback]
        assert fb.persona == sc.persona and fb.source == sc.source
        draft = fb.build(ctx(user))
    assert draft is not None and draft.type == "new_item" and draft.banner
    it = draft.item
    assert it.source == sc.source and it.external_id and it.title
    assert it.kind in KINDS and it.requester_role in ROLES
    assert all(getattr(it, f) is None or getattr(it, f).tzinfo for f in TIME_FIELDS)
    json.dumps(item_to_payload(it, NOW))  # payload phải serialize được


def test_external_ids_unique_within_one_ctx():
    c = ctx()
    ids = [SCENARIOS["teams_mention"].build(c).item.external_id for _ in range(20)]
    assert len(set(ids)) == 20


def test_vip_mail_contains_fake_pii_for_masker():
    d = SCENARIOS["mail_vip_customer"].build(ctx())
    assert "9704229912345678" in d.item.preview and "0987654321" in d.item.preview


def test_sla_escalation_overrides_existing_ticket_without_mutating_row(item_factory):
    row = item_factory(id=7, source="sdp", external_id="50231", kind="ticket", title="[SDP#50231] x",
                       sla_due_at=NOW + timedelta(hours=2), tags=["incident"])
    d = SCENARIOS["sdp_sla_escalation"].build(ctx(rows=[row]))
    assert d.type == "update_item" and d.item.external_id == "50231"
    assert d.item.sla_due_at == NOW + timedelta(minutes=10)
    assert "escalated" in d.item.tags and row.tags == ["incident"]
    assert row.sla_due_at == NOW + timedelta(hours=2)


def test_sla_escalation_ignores_done_or_breached(item_factory):
    done = item_factory(source="sdp", external_id="1", sla_due_at=NOW + timedelta(hours=2), done_local=True)
    breached = item_factory(source="sdp", external_id="2", sla_due_at=NOW - timedelta(minutes=5))
    assert SCENARIOS["sdp_sla_escalation"].build(ctx(rows=[done, breached])) is None


def test_meeting_conflict_overlaps_target_with_same_start(item_factory):
    target = item_factory(source="exchange_calendar", external_id="m1", kind="meeting", title="Họp A",
                          start_at=NOW + timedelta(hours=2), end_at=NOW + timedelta(hours=3))
    d = SCENARIOS["meeting_conflict"].build(ctx(rows=[target]))
    assert d.item.start_at == target.start_at and d.item.end_at > d.item.start_at
    assert d.item.start_at < target.end_at and target.start_at < d.item.end_at


def test_meeting_conflict_when_target_already_started_still_overlaps(item_factory):
    target = item_factory(source="exchange_calendar", external_id="m1", kind="meeting", title="Họp A",
                          start_at=NOW - timedelta(minutes=10), end_at=NOW + timedelta(minutes=50))
    d = SCENARIOS["meeting_conflict"].build(ctx(rows=[target]))
    assert target.start_at < d.item.start_at < target.end_at


@pytest.mark.parametrize("seed", range(40))
def test_meeting_moved_never_lands_in_the_past(item_factory, seed):
    target = item_factory(source="exchange_calendar", external_id="m1", kind="meeting", title="Họp A",
                          start_at=NOW + timedelta(minutes=50), end_at=NOW + timedelta(minutes=110))
    d = SCENARIOS["meeting_moved"].build(ctx(seed=seed, rows=[target]))
    assert d.type == "update_item" and d.item.start_at >= NOW + timedelta(minutes=15)
    assert d.item.end_at - d.item.start_at == timedelta(minutes=60)
    assert d.item.title.count("[Dời giờ]") == 1


def test_meeting_moved_does_not_stack_prefix(item_factory):
    target = item_factory(source="exchange_calendar", external_id="m1", kind="meeting", title="[Dời giờ] Họp A",
                          start_at=NOW + timedelta(hours=2), end_at=NOW + timedelta(hours=3))
    d = SCENARIOS["meeting_moved"].build(ctx(rows=[target]))
    assert d.item.title.count("[Dời giờ]") == 1


def test_jira_unblocked_only_targets_blocked(item_factory):
    ok = item_factory(source="jira", external_id="A-1", status="In Progress")
    blocked = item_factory(source="jira", external_id="A-2", status="Blocked", title="[A-2] x")
    assert SCENARIOS["jira_unblocked"].build(ctx(rows=[ok])) is None
    d = SCENARIOS["jira_unblocked"].build(ctx(rows=[ok, blocked]))
    assert d.item.external_id == "A-2" and d.item.status == "In Progress"
```

- [ ] **Step 2: Chạy test, xác nhận thất bại**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_sim_catalog.py -v`
Expected: FAIL (`ModuleNotFoundError: app.services.sim_catalog`).

- [ ] **Step 3: Tạo `services/sim_catalog.py`**

```python
"""Danh mục kịch bản sự kiện giả lập. Dữ liệu hoàn toàn hư cấu, bối cảnh ngân hàng.

Mỗi kịch bản có hàm build(ctx) -> Draft | None. Kịch bản 'update_item' cần đối tượng có sẵn
(ctx.rows); nếu không có thì trả None và simulator rơi về kịch bản `fallback` (cùng nguồn).
"""
from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import partial
from typing import Any
from zoneinfo import ZoneInfo

from app.connectors.base import ItemIn, UserContext
from app.connectors.live import item_from_row

OWA = "https://mail.bank.local/owa/"
JIRA = "https://jira.bank.local/browse/"
WIKI = "https://wiki.bank.local/pages/viewpage.action?pageId="
SDP = "https://sdp.bank.local/WorkOrder.do?woMode=viewWO&woID="
TEAMS = "https://teams.microsoft.com/"
MOVED_PREFIX = "[Dời giờ] "


def persona_of(username: str) -> str:
    return "rm" if username == "lan.pham" else "it"


@dataclass
class ScenarioCtx:
    user: UserContext
    now: datetime
    rng: random.Random
    tz: ZoneInfo
    rows: list[Any] = field(default_factory=list)  # WorkItem hiện có của user (đối tượng cho kịch bản update)
    taken_ids: set[str] = field(default_factory=set)

    def hm(self, dt: datetime) -> str:
        return dt.astimezone(self.tz).strftime("%H:%M")

    def later(self, minutes: int) -> datetime:
        return self.now + timedelta(minutes=minutes)

    def claim(self, ext_id: str) -> str:
        while ext_id in self.taken_ids:
            ext_id += "x"
        self.taken_ids.add(ext_id)
        return ext_id

    def new_id(self, key: str) -> str:
        return self.claim(f"sim-{key}-{int(self.now.timestamp() * 1000)}-{self.rng.randrange(1000, 10000)}")

    @property
    def manager(self) -> str:
        default = "hung.le@bank.local" if persona_of(self.user.username) == "rm" else "minh.tran@bank.local"
        return self.user.manager_email or default


@dataclass
class Draft:
    type: str  # new_item | update_item
    banner: str
    item: ItemIn


@dataclass(frozen=True)
class Scenario:
    key: str
    label: str
    persona: str  # it | rm
    source: str
    weight: int
    severity: str  # info | warning | critical (màu banner trong app)
    build: Callable[[ScenarioCtx], Draft | None]
    fallback: str | None = None


# ---------------------------------------------------------------- Trình dựng dùng chung (kịch bản "new")


def _mail(ctx: ScenarioCtx, *, key: str, pool: list[tuple[str, str]], due_minutes: list[int], requester: str | None = None,
          role: str = "manager", tags: tuple[str, ...] = ("important", "flagged"),
          banner: str = "Mail mới từ quản lý: {subject}") -> Draft:
    subject, body = ctx.rng.choice(pool)
    due = ctx.later(ctx.rng.choice(due_minutes))
    subject, body = subject.format(hm=ctx.hm(due)), body.format(hm=ctx.hm(due))
    item = ItemIn(
        "exchange_mail", ctx.new_id(key), "email", subject, body, OWA, start_at=ctx.now, due_at=due,
        requester=requester or ctx.manager, requester_role=role, is_unread=True, tags=list(tags),
    )
    return Draft("new_item", banner.format(subject=subject), item)


def _ticket(ctx: ScenarioCtx, *, pool: list[tuple[str, str]], sla_minutes: list[int], requesters: list[str]) -> Draft:
    title, body = ctx.rng.choice(pool)
    ext = ctx.claim(str(ctx.rng.randint(50300, 50999)))
    item = ItemIn(
        "sdp", ext, "ticket", f"[SDP#{ext}] {title}", body, SDP + ext, start_at=ctx.now,
        sla_due_at=ctx.later(ctx.rng.choice(sla_minutes)), status="Open", priority_raw="High",
        requester=ctx.rng.choice(requesters), tags=["incident"],
    )
    return Draft("new_item", f"Ticket SDP mới: {title}", item)


def _chat(ctx: ScenarioCtx, *, key: str, pool: list[str], who: str) -> Draft:
    text = ctx.rng.choice(pool)
    item = ItemIn(
        "teams", ctx.new_id(key), "chat", f"{who}: {text}", text, TEAMS, start_at=ctx.now,
        requester=who, requester_role="manager", is_unread=True, tags=["mention"],
    )
    return Draft("new_item", f"Teams · {who}: {text}", item)


def _meeting_new(ctx: ScenarioCtx, *, key: str, pool: list[tuple[str, str]], locations: list[str]) -> Draft:
    title, body = ctx.rng.choice(pool)
    start = ctx.later(ctx.rng.choice([60, 90, 120, 180]))
    end = start + timedelta(minutes=ctx.rng.choice([30, 45, 60]))
    item = ItemIn(
        "exchange_calendar", ctx.new_id(key), "meeting", title, body, OWA, start_at=start, end_at=end,
        requester=ctx.manager, requester_role="manager", participants=[ctx.manager, ctx.user.email],
        location=ctx.rng.choice(locations),
    )
    return Draft("new_item", f"Lời mời họp {ctx.hm(start)}: {title}", item)


def _jira_new(ctx: ScenarioCtx, *, project: str, pool: list[tuple[str, str]], who: str) -> Draft:
    summary, body = ctx.rng.choice(pool)
    issue = ctx.claim(f"{project}-{ctx.rng.randint(2600, 2999)}")
    item = ItemIn(
        "jira", issue, "task", f"[{issue}] {summary}", body, JIRA + issue,
        due_at=ctx.later(ctx.rng.choice([240, 360, 480])), status="To Do", priority_raw="Highest",
        requester=who, requester_role="manager", tags=["bug"], source_updated_at=ctx.now,
    )
    return Draft("new_item", f"Jira mới (Highest): {summary}", item)


def _wiki(ctx: ScenarioCtx, *, pool: list[tuple[str, str]], who: str) -> Draft:
    title, space = ctx.rng.choice(pool)
    page_id = ctx.claim(str(ctx.rng.randint(880100, 889999)))
    item = ItemIn(
        "confluence", page_id, "page", title, f"Không gian: {space}. Cập nhật bởi {who}, có @mention bạn.",
        WIKI + page_id, start_at=ctx.now, requester=who, tags=["mention"], source_updated_at=ctx.now,
    )
    return Draft("new_item", f"Wiki · bạn được nhắc tên: {title}", item)


# ---------------------------------------------------------------- Kịch bản "update" (cần đối tượng có sẵn)


def _sla_escalation(ctx: ScenarioCtx) -> Draft | None:
    cands = [r for r in ctx.rows if r.source == "sdp" and not r.done_local and r.sla_due_at
             and r.sla_due_at > ctx.now + timedelta(minutes=15)]
    if not cands:
        return None
    item = item_from_row(ctx.rng.choice(cands))
    item.sla_due_at = ctx.later(10)
    item.priority_raw = "Urgent"
    if "escalated" not in item.tags:
        item.tags = [*item.tags, "escalated"]
    return Draft("update_item", f"SLA còn 10 phút: {item.title}", item)


def _meeting_conflict(ctx: ScenarioCtx) -> Draft | None:
    cands = [r for r in ctx.rows if r.kind == "meeting" and not r.done_local and r.start_at and r.end_at
             and r.end_at > ctx.now + timedelta(minutes=20)]
    if not cands:
        return None
    target = ctx.rng.choice(cands)
    start = max(target.start_at, ctx.later(10))  # bắt đầu cùng lúc (hoặc giữa) họp mục tiêu -> luôn cùng ngày
    item = ItemIn(
        "exchange_calendar", ctx.new_id("meeting_conflict"), "meeting", "Họp khẩn: rà soát sự cố giao dịch",
        "Họp đột xuất về sự cố giao dịch chuyển tiền nhanh.", OWA, start_at=start, end_at=start + timedelta(minutes=30),
        requester=ctx.manager, requester_role="manager", participants=[ctx.manager, ctx.user.email],
        location="Microsoft Teams", tags=["teams"],
    )
    return Draft("new_item", f"Họp mới trùng lịch với \"{target.title}\"", item)


def _meeting_moved(ctx: ScenarioCtx) -> Draft | None:
    cands = [r for r in ctx.rows if r.kind == "meeting" and not r.done_local and r.start_at and r.end_at
             and r.start_at > ctx.now + timedelta(minutes=45)]
    if not cands:
        return None
    row = ctx.rng.choice(cands)
    shift = timedelta(minutes=ctx.rng.choice([30, 60, -30]))
    if row.start_at + shift < ctx.later(15):
        shift = timedelta(minutes=30)
    item = item_from_row(row)
    item.start_at, item.end_at = row.start_at + shift, row.end_at + shift
    if not item.title.startswith(MOVED_PREFIX):
        item.title = MOVED_PREFIX + item.title
    return Draft("update_item", f"Họp bị dời sang {ctx.hm(item.start_at)}: {row.title}", item)


def _jira_unblocked(ctx: ScenarioCtx) -> Draft | None:
    cands = [r for r in ctx.rows if r.source == "jira" and not r.done_local and (r.status or "").lower() == "blocked"]
    if not cands:
        return None
    item = item_from_row(ctx.rng.choice(cands))
    item.status = "In Progress"
    return Draft("update_item", f"Hết bị chặn, có thể làm tiếp: {item.title}", item)


# ---------------------------------------------------------------- Nội dung mẫu (hư cấu)

IT_MGR_MAIL = [
    ("Cần báo cáo tiến độ sprint 21 trước {hm}",
     "An ơi, em gửi anh burndown và các rủi ro của sprint 21 để anh báo cáo giao ban. Hạn {hm} nhé."),
    ("Rà soát giúp anh checklist release T24 trước {hm}",
     "Em rà lại checklist release R2026.10, đặc biệt phần rollback, và phản hồi anh trước {hm}."),
    ("Tổng hợp giao dịch lỗi 3 ngày gần nhất, hạn {hm}",
     "Anh cần số lượng giao dịch lỗi theo nguyên nhân trong 3 ngày qua. Gửi anh trước {hm}."),
]
IT_AUDIT_MAIL = [
    ("Đề nghị cung cấp danh sách user đặc quyền T24 trước {hm}",
     "KTNB đề nghị phòng Core Banking cung cấp danh sách user đặc quyền kèm người phê duyệt trước {hm} ngày mai."),
    ("Yêu cầu giải trình ngoại lệ phân quyền quý III, hạn {hm}",
     "Đề nghị giải trình các trường hợp cấp quyền ngoài quy trình trong quý III. Hạn {hm}."),
]
IT_VIP_MAIL = [
    ("Đối tác cần xác nhận kết quả đối soát trước {hm}",
     "Kính gửi Quý Ngân hàng, đề nghị xác nhận kết quả đối soát cho TK 9704229912345678 trước {hm}. "
     "Liên hệ kế toán trưởng: 0987654321."),
]
IT_INCIDENTS = [
    ("KH không xem được số dư trên Mobile Banking",
     "Chi nhánh Đống Đa báo: KH chủ TK 0123456789012, SĐT 0912345678 không xem được số dư từ sáng."),
    ("Lỗi timeout khi tra cứu lịch sử giao dịch",
     "Nhiều KH báo tra cứu lịch sử giao dịch quá 30 giây. Liên hệ: 0934567890."),
    ("Không in được sao kê tại quầy",
     "Chi nhánh Cầu Giấy không in được sao kê TK 0987654321098 từ 9h."),
]
BRANCHES = ["CN Đống Đa", "CN Cầu Giấy", "CN Hoàn Kiếm", "Trung tâm Dịch vụ KH"]
IT_CHAT = [
    "@An chiều nay anh cần số liệu sự cố sớm hơn dự kiến nhé",
    "@An em xem giúp anh ticket vừa lên, khách đang chờ",
    "@An nhớ cập nhật tiến độ CORE-2481 trước giờ họp CAB",
]
IT_MEETINGS = [
    ("Họp nhanh về lỗi đối soát batch", "Trao đổi phương án xử lý lỗi timeout đối soát."),
    ("Review thiết kế API tài khoản", "Rà soát tài liệu thiết kế trước khi chốt."),
    ("Đồng bộ kế hoạch release T24", "Cập nhật tiến độ và rủi ro trước CAB."),
]
IT_JIRA = [
    ("Fix lỗi sai lệch số dư sau đối soát", "Phát hiện sai lệch số dư với một số tài khoản sau batch đối soát."),
    ("Khắc phục lỗi mất kết nối cổng thanh toán", "Cổng thanh toán ngắt kết nối ngắt quãng trên môi trường UAT."),
]
IT_WIKI = [
    ("Kế hoạch Release T24 R2026.10 (cập nhật)", "Core Banking"),
    ("Hướng dẫn rollback batch đối soát", "Vận hành CNTT"),
]

RM_CUSTOMER_MAIL = [
    ("Đề nghị giải ngân đợt bổ sung trước {hm}",
     "Kính gửi Quý Ngân hàng, công ty đề nghị giải ngân vào TK 9704229912345678 trước {hm}. "
     "Liên hệ kế toán trưởng: 0987654321."),
    ("Đề nghị xác nhận số dư hạn mức trước {hm}",
     "Công ty cần Ngân hàng xác nhận số dư hạn mức còn lại trước {hm} để làm hồ sơ thầu. Liên hệ: 0987654321."),
]
RM_MGR_MAIL = [
    ("Bổ sung phụ lục tờ trình trước {hm}", "Lan bổ sung phụ lục tài sản bảo đảm vào tờ trình trước {hm} nhé."),
    ("Cập nhật số liệu dư nợ KHDN trước {hm}", "Em cập nhật dư nợ các KH trong danh mục để anh báo cáo trước {hm}."),
]
RM_INCIDENTS = [
    ("Không tải được hồ sơ tín dụng trên LOS", "Lỗi tải tệp đính kèm khi mở hồ sơ tín dụng trên LOS."),
    ("LOS báo lỗi khi in tờ trình", "Hệ thống LOS báo lỗi 500 khi in tờ trình thẩm định."),
]
RM_MEETINGS = [
    ("Gặp KH Công ty CP Thép Hoà Việt - trao đổi hạn mức", "Trao đổi nhu cầu hạn mức tín dụng Q4."),
    ("Gặp KH Công ty TNHH Nông sản Đại Phát - tài trợ xuất khẩu", "Giới thiệu gói tài trợ xuất khẩu."),
]
RM_WIKI = [
    ("Hướng dẫn thẩm định KHDN (bản cập nhật tháng 10)", "Quản lý tín dụng"),
    ("Chính sách lãi suất cho vay KHDN Q4", "Quản lý tín dụng"),
]


def _s(key: str, label: str, persona: str, source: str, weight: int, severity: str,
       build: Callable[[ScenarioCtx], Draft | None], fallback: str | None = None) -> Scenario:
    return Scenario(key, label, persona, source, weight, severity, build, fallback)


_ALL: list[Scenario] = [
    # ----- Persona IT (an.nguyen)
    _s("mail_manager_deadline", "Mail từ quản lý cần xử lý gấp", "it", "exchange_mail", 3, "warning",
       partial(_mail, key="mail_manager_deadline", pool=IT_MGR_MAIL, due_minutes=[60, 90, 120, 180])),
    _s("mail_audit_request", "Mail yêu cầu từ Kiểm toán nội bộ", "it", "exchange_mail", 1, "warning",
       partial(_mail, key="mail_audit_request", pool=IT_AUDIT_MAIL, due_minutes=[1200, 1500, 1800],
               requester="ksnb@bank.local", role="audit", tags=("flagged",),
               banner="Mail từ Kiểm toán: {subject}")),
    _s("mail_vip_customer", "Mail từ khách hàng/đối tác VIP", "it", "exchange_mail", 1, "critical",
       partial(_mail, key="mail_vip_customer", pool=IT_VIP_MAIL, due_minutes=[60, 90, 120],
               requester="ketoan@saoviet.example", role="vip_customer", tags=("important",),
               banner="Mail từ KH VIP: {subject}")),
    _s("sdp_new_incident", "Ticket SDP mới (sắp hết SLA)", "it", "sdp", 3, "critical",
       partial(_ticket, pool=IT_INCIDENTS, sla_minutes=[60, 75, 90], requesters=BRANCHES)),
    _s("sdp_sla_escalation", "Ticket SDP sắp vi phạm SLA", "it", "sdp", 1, "critical",
       _sla_escalation, fallback="sdp_new_incident"),
    _s("teams_mention", "@mention trên Teams", "it", "teams", 2, "info",
       partial(_chat, key="teams_mention", pool=IT_CHAT, who="Trần Minh")),
    _s("meeting_new", "Lời mời họp mới", "it", "exchange_calendar", 2, "info",
       partial(_meeting_new, key="meeting_new", pool=IT_MEETINGS, locations=["Microsoft Teams", "P.1203", "P.805"])),
    _s("meeting_conflict", "Họp mới trùng lịch", "it", "exchange_calendar", 1, "warning",
       _meeting_conflict, fallback="meeting_new"),
    _s("meeting_moved", "Họp bị dời giờ", "it", "exchange_calendar", 1, "warning",
       _meeting_moved, fallback="meeting_new"),
    _s("jira_assigned_highest", "Jira mới mức Highest gán cho bạn", "it", "jira", 2, "warning",
       partial(_jira_new, project="CORE", pool=IT_JIRA, who="Trần Minh")),
    _s("jira_unblocked", "Jira hết bị chặn", "it", "jira", 1, "info",
       _jira_unblocked, fallback="jira_assigned_highest"),
    _s("confluence_mention", "@mention trong trang wiki", "it", "confluence", 1, "info",
       partial(_wiki, pool=IT_WIKI, who="Trần Minh")),
    # ----- Persona RM (lan.pham)
    _s("rm_mail_customer_disbursement", "Mail KH đề nghị giải ngân", "rm", "exchange_mail", 3, "critical",
       partial(_mail, key="rm_mail_customer_disbursement", pool=RM_CUSTOMER_MAIL, due_minutes=[60, 90, 120],
               requester="ketoan@saoviet.example", role="vip_customer", tags=("important",),
               banner="Mail từ KH VIP: {subject}")),
    _s("rm_mail_manager_deadline", "Mail từ quản lý cần xử lý gấp", "rm", "exchange_mail", 2, "warning",
       partial(_mail, key="rm_mail_manager_deadline", pool=RM_MGR_MAIL, due_minutes=[60, 120, 180])),
    _s("rm_sdp_los_incident", "Ticket LOS mới", "rm", "sdp", 2, "warning",
       partial(_ticket, pool=RM_INCIDENTS, sla_minutes=[90, 120, 180], requesters=["Phạm Thị Lan"])),
    _s("rm_meeting_new", "Lời mời gặp khách hàng", "rm", "exchange_calendar", 2, "info",
       partial(_meeting_new, key="rm_meeting_new", pool=RM_MEETINGS, locations=["Văn phòng KH", "P.902"])),
    _s("rm_meeting_moved", "Cuộc họp bị dời giờ", "rm", "exchange_calendar", 1, "warning",
       _meeting_moved, fallback="rm_meeting_new"),
    _s("rm_confluence_policy_mention", "@mention trong chính sách tín dụng", "rm", "confluence", 1, "info",
       partial(_wiki, pool=RM_WIKI, who="Phòng QLTD")),
]

SCENARIOS: dict[str, Scenario] = {s.key: s for s in _ALL}


def scenarios_for(persona: str) -> list[Scenario]:
    return [s for s in _ALL if s.persona == persona]
```

- [ ] **Step 4: Chạy test, xác nhận đạt**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_sim_catalog.py -v`
Expected: tất cả pass (18 case parametrize + các test lẻ + 40 seed).

- [ ] **Step 5: Checkpoint**

Run: `cd backend && source .venv/bin/activate && pytest -q`
Expected: toàn bộ pass.

---

### Task 4: `simulator.py` — emit, reset, truy vấn sự kiện, SimTicker

**Files:**
- Create: `backend/app/services/simulator.py`
- Create: `backend/tests/test_sim_engine.py`

**Interfaces:**
- Consumes: `LiveEvent`, `WorkItem`, `User` (models); `payload_to_item`, `item_to_payload` (Task 2); `SCENARIOS`, `ScenarioCtx`, `persona_of`, `scenarios_for` (Task 3); `recompute`, `sync_user`, `user_context`, `user_items`, `UPDATABLE_FIELDS` (`services/sync_service.py`); `get_user_settings` (`core/deps.py`).
- Produces:
  - `MAX_EVENTS = 200`
  - `emit(db, user, scenario: str | None = None, now: datetime | None = None, rng: random.Random | None = None) -> LiveEvent` — `ValueError` nếu kịch bản không hợp lệ/không đúng persona hoặc không có nguồn nào bật
  - `reset(db, user) -> None`
  - `latest_event_id(db, username) -> int`
  - `events_since(db, username, since: int, limit: int = 50) -> list[LiveEvent]`
  - `work_item_ids(db, username, events) -> dict[tuple[str, str], int]` (khoá `(source, external_id)`)
  - `SimTicker(rng=None)` với `.tick(db, now=None, active_days=14) -> list[str]` (danh sách username vừa được phát)

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/test_sim_engine.py`:

```python
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
    assert any("Họp mục tiêu (test)" in b and "Họp khẩn" in b for b in bodies)


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
```

- [ ] **Step 2: Chạy test, xác nhận thất bại**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_sim_engine.py -v`
Expected: FAIL (`ImportError: cannot import name 'simulator'`).

- [ ] **Step 3: Tạo `services/simulator.py`**

```python
"""Bộ phát sự kiện giả lập. Chỉ dùng khi MOCK_CONNECTORS=true."""
from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.connectors.live import item_to_payload, payload_to_item
from app.connectors.base import ItemIn
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
```

Lưu ý: sắp xếp lại 2 dòng import đầu cho gọn nếu linter yêu cầu (`from app.connectors.base import ItemIn` đứng trước `from app.connectors.live import ...`).

- [ ] **Step 4: Chạy test, xác nhận đạt**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_sim_engine.py -v`
Expected: 15 passed. Nếu `test_meeting_conflict_raises_conflict_alert` fail vì body alert, in `[a.body for a in ...]` để xem thứ tự `a_title`/`b_title` (test đã chấp nhận cả hai thứ tự vì kiểm tra cả hai chuỗi trong cùng body).

- [ ] **Step 5: Checkpoint**

Run: `cd backend && source .venv/bin/activate && pytest -q`
Expected: toàn bộ pass, các user demo không còn sự kiện sót lại (fixture `env` đã reset).

---

### Task 5: API `/events`, `/sim/*`

**Files:**
- Modify: `backend/app/core/deps.py` (thêm `require_mock`)
- Modify: `backend/app/schemas.py` (thêm schema)
- Create: `backend/app/api/sim.py`
- Modify: `backend/app/main.py:9,36`
- Create: `backend/tests/test_sim_api.py`

**Interfaces:**
- Consumes: `simulator.*` (Task 4), `scenarios_for`/`persona_of` (Task 3).
- Produces (HTTP, prefix `/api/v1`):
  - `GET /events?since=&limit=` → `{"events": [LiveEventOut], "latest_id": int}`; thiếu `since` → `events=[]`
  - `POST /sim/emit` body `{"scenario": str|null}` → `LiveEventOut`
  - `GET /sim/scenarios` → `[{"key","label"}]`
  - `POST /sim/reset` → 204
  - `LiveEventOut`: `id, type, scenario, source, severity, title, work_item_id (int|null), created_at`

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/test_sim_api.py`:

```python
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import AuditLog
from app.db.session import SessionLocal

API = "/api/v1"


@pytest.fixture(autouse=True)
def _clean(client, login):
    yield
    for user in ("an.nguyen", "lan.pham"):
        client.post(f"{API}/sim/reset", headers=login(user))


def test_requires_auth(client):
    assert client.get(f"{API}/events").status_code == 401
    assert client.post(f"{API}/sim/emit").status_code == 401


def test_hidden_when_not_mock(client, login, monkeypatch):
    h = login()
    monkeypatch.setattr(get_settings(), "mock_connectors", False)
    assert client.get(f"{API}/events", headers=h).status_code == 404
    assert client.post(f"{API}/sim/emit", headers=h).status_code == 404
    assert client.get(f"{API}/sim/scenarios", headers=h).status_code == 404
    assert client.post(f"{API}/sim/reset", headers=h).status_code == 404


def test_events_without_since_returns_only_cursor(client, login):
    h = login()
    client.post(f"{API}/sim/emit", json={"scenario": "teams_mention"}, headers=h)
    body = client.get(f"{API}/events", headers=h).json()
    assert body["events"] == [] and body["latest_id"] >= 1


def test_emit_then_poll_returns_event_with_resolvable_item(client, login):
    h = login()
    cursor = client.get(f"{API}/events", headers=h).json()["latest_id"]
    emitted = client.post(f"{API}/sim/emit", json={"scenario": "mail_manager_deadline"}, headers=h).json()
    assert emitted["scenario"] == "mail_manager_deadline" and "payload" not in emitted
    body = client.get(f"{API}/events", params={"since": cursor}, headers=h).json()
    assert [e["id"] for e in body["events"]] == [emitted["id"]] and body["latest_id"] == emitted["id"]
    item = client.get(f"{API}/work-items/{body['events'][0]['work_item_id']}", headers=h)
    assert item.status_code == 200 and item.json()["requester_role"] == "manager"
    assert any(i["id"] == item.json()["id"] for i in client.get(f"{API}/work-items", headers=h).json())


def test_since_cuts_and_cursor_beyond_latest_returns_empty_with_lower_latest_id(client, login):
    h = login()
    a = client.post(f"{API}/sim/emit", json={"scenario": "teams_mention"}, headers=h).json()
    b = client.post(f"{API}/sim/emit", json={"scenario": "teams_mention"}, headers=h).json()
    assert [e["id"] for e in client.get(f"{API}/events", params={"since": a["id"]}, headers=h).json()["events"]] == [b["id"]]
    far = client.get(f"{API}/events", params={"since": b["id"] + 1000}, headers=h).json()
    assert far["events"] == [] and far["latest_id"] == b["id"]  # app dựa vào đây để hạ con trỏ


def test_reset_lowers_latest_id_to_zero(client, login):
    h = login()
    client.post(f"{API}/sim/emit", json={"scenario": "teams_mention"}, headers=h)
    assert client.post(f"{API}/sim/reset", headers=h).status_code == 204
    assert client.get(f"{API}/events", params={"since": 0}, headers=h).json() == {"events": [], "latest_id": 0}


@pytest.mark.parametrize("params", [{"since": -1}, {"since": "abc"}, {"since": 0, "limit": 0}, {"since": 0, "limit": 201}])
def test_invalid_query_params_rejected(client, login, params):
    assert client.get(f"{API}/events", params=params, headers=login()).status_code == 422


def test_users_are_isolated(client, login):
    h1, h2 = login("an.nguyen"), login("lan.pham")
    client.post(f"{API}/sim/emit", json={"scenario": "teams_mention"}, headers=h1)
    assert client.get(f"{API}/events", params={"since": 0}, headers=h2).json()["events"] == []


def test_emit_validation(client, login):
    h = login()
    assert client.post(f"{API}/sim/emit", json={"scenario": "khong_co"}, headers=h).status_code == 422
    assert client.post(f"{API}/sim/emit", json={"scenario": "rm_meeting_new"}, headers=h).status_code == 422
    assert client.post(f"{API}/sim/emit", headers=h).status_code == 200  # không body = chọn ngẫu nhiên


def test_scenarios_follow_persona(client, login):
    it = client.get(f"{API}/sim/scenarios", headers=login("an.nguyen")).json()
    rm = client.get(f"{API}/sim/scenarios", headers=login("lan.pham")).json()
    assert len(it) == 12 and len(rm) == 6
    assert {"key", "label"} == set(it[0]) and all(s["label"] for s in it)


def test_audit_records_scenario_but_not_content(client, login):
    h = login()
    client.post(f"{API}/sim/emit", json={"scenario": "mail_vip_customer"}, headers=h)
    with SessionLocal() as db:
        rows = list(db.scalars(select(AuditLog).where(AuditLog.action == "sim_emit").order_by(AuditLog.id.desc())))
    assert rows[0].detail == {"scenario": "mail_vip_customer"}
```

- [ ] **Step 2: Chạy test, xác nhận thất bại**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_sim_api.py -v`
Expected: FAIL (404 ở mọi endpoint vì chưa có router).

- [ ] **Step 3: Thêm `require_mock`**

Trong `backend/app/core/deps.py`, thêm import `from app.core.config import get_settings` (cùng nhóm với import `app.core.security`) và thêm cuối file:

```python
def require_mock() -> None:
    """Endpoint giả lập chỉ tồn tại ở chế độ MOCK; ngoài ra giả vờ như không có."""
    if not get_settings().mock_connectors:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy")
```

- [ ] **Step 4: Thêm schema**

Thêm cuối `backend/app/schemas.py`:

```python
class LiveEventOut(BaseModel):
    id: int
    type: str
    scenario: str
    source: str
    severity: str
    title: str
    work_item_id: int | None
    created_at: datetime


class EventsOut(BaseModel):
    events: list[LiveEventOut]
    latest_id: int


class SimEmitIn(BaseModel):
    scenario: str | None = Field(default=None, max_length=48)


class ScenarioOut(BaseModel):
    key: str
    label: str
```

- [ ] **Step 5: Tạo router**

Tạo `backend/app/api/sim.py`:

```python
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
```

- [ ] **Step 6: Đăng ký router**

Trong `backend/app/main.py`: đổi `from app.api import ai, alerts, auth, settings, work` thành `from app.api import ai, alerts, auth, settings, sim, work` và đổi vòng lặp thành `for r in (auth.router, work.router, alerts.router, ai.router, settings.router, sim.router):`.

- [ ] **Step 7: Chạy test, xác nhận đạt**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_sim_api.py -v`
Expected: tất cả pass (kể cả 4 case parametrize).

- [ ] **Step 8: Checkpoint**

Run: `cd backend && source .venv/bin/activate && pytest -q`
Expected: toàn bộ pass.

---

### Task 6: Worker phát sự kiện tự động

**Files:**
- Modify: `backend/app/worker.py`
- Create: `backend/tests/test_worker_sim.py`

**Interfaces:**
- Consumes: `SimTicker` (Task 4).
- Produces: `worker.job_sim_tick() -> None`; `worker.build_scheduler(s: Settings) -> BlockingScheduler`; module-level `worker._ticker`.

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/test_worker_sim.py`:

```python
from app import worker
from app.core.config import Settings


def test_sim_job_registered_only_in_mock_mode():
    mock_jobs = {j.id for j in worker.build_scheduler(Settings(mock_connectors=True)).get_jobs()}
    real_jobs = {j.id for j in worker.build_scheduler(Settings(mock_connectors=False)).get_jobs()}
    assert "sim" in mock_jobs and {"sync", "dispatch", "brief"} <= mock_jobs
    assert "sim" not in real_jobs and {"sync", "dispatch", "brief"} <= real_jobs


def test_sim_job_runs_every_10_seconds():
    sched = worker.build_scheduler(Settings(mock_connectors=True))
    job = next(j for j in sched.get_jobs() if j.id == "sim")
    assert job.trigger.interval.total_seconds() == 10 and job.max_instances == 1


def test_job_sim_tick_delegates_to_ticker(monkeypatch, client):
    calls = []

    class FakeTicker:
        def tick(self, db, active_days):
            calls.append(active_days)
            return ["an.nguyen"]

    monkeypatch.setattr(worker, "_ticker", FakeTicker())
    worker.job_sim_tick()
    assert calls == [worker.ACTIVE_USER_DAYS]
```

- [ ] **Step 2: Chạy test, xác nhận thất bại**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_worker_sim.py -v`
Expected: FAIL (`AttributeError: module 'app.worker' has no attribute 'build_scheduler'`).

- [ ] **Step 3: Sửa `worker.py`**

Thêm import `from app.services.simulator import SimTicker` (cùng nhóm với các import `app.services.*`), thêm sau dòng `ACTIVE_USER_DAYS = 14`:

```python
_ticker = SimTicker()
```

Thêm sau `job_morning_briefs`:

```python
def job_sim_tick() -> None:
    with SessionLocal() as db:
        emitted = _ticker.tick(db, active_days=ACTIVE_USER_DAYS)
        if emitted:
            log.info("Đã phát sự kiện giả lập cho %s", ", ".join(emitted))
```

Thay hàm `main` bằng:

```python
def build_scheduler(s) -> BlockingScheduler:  # noqa: ANN001
    sched = BlockingScheduler(timezone=s.timezone)
    sched.add_job(job_sync_all, "interval", minutes=s.sync_interval_minutes, id="sync",
                  next_run_time=datetime.now(timezone.utc), max_instances=1, coalesce=True)
    sched.add_job(job_dispatch_alerts, "interval", minutes=1, id="dispatch", max_instances=1, coalesce=True)
    sched.add_job(job_morning_briefs, "interval", minutes=5, id="brief", max_instances=1, coalesce=True)
    if s.mock_connectors:
        sched.add_job(job_sim_tick, "interval", seconds=10, id="sim", max_instances=1, coalesce=True)
    return sched


def main() -> None:
    s = get_settings()
    init_db()
    sched = build_scheduler(s)
    log.info("Worker khởi động (sync mỗi %d phút, mock=%s)", s.sync_interval_minutes, s.mock_connectors)
    sched.start()
```

- [ ] **Step 4: Chạy test, xác nhận đạt**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_worker_sim.py -v`
Expected: 3 passed.

- [ ] **Step 5: Checkpoint backend hoàn chỉnh**

Run: `cd backend && source .venv/bin/activate && pytest -q`
Expected: toàn bộ pass (35 cũ + các test mới).

---

### Task 7: Mobile — model, repository, fixture

**Files:**
- Modify: `mobile/lib/domain/models.dart` (thêm `LiveEvent`, `LiveEventsPage`, `SimScenario`; sửa `UserSettings`)
- Modify: `mobile/lib/data/repository.dart`
- Create: `mobile/test/fixtures/events.json`, `mobile/test/fixtures/scenarios.json` (sinh từ backend thật)
- Modify: `mobile/test/fixtures/settings.json`
- Modify: `mobile/test/models_test.dart`

**Interfaces:**
- Consumes: HTTP contract của Task 5.
- Produces:
  - `LiveEvent({id, type, scenario, source, severity, title, workItemId, createdAt})` + `LiveEvent.fromJson`
  - `LiveEventsPage(List<LiveEvent> events, int latestId)` + `fromJson`
  - `SimScenario({key, label})` + `fromJson`
  - `UserSettings.liveSimEnabled` (mặc định `true`), có trong `fromJson/toJson/copyWith`
  - `WorkHubRepository.liveEvents({int? since}) -> Future<LiveEventsPage>`, `simEmit({String? scenario}) -> Future<LiveEvent>`, `simScenarios() -> Future<List<SimScenario>>`, `simReset() -> Future<void>`

- [ ] **Step 1: Sinh fixture từ backend thật**

Run (DB tạm, không đụng DB dev):

```bash
cd backend && source .venv/bin/activate && DATABASE_URL="sqlite:///$(mktemp -d)/fx.db" MOCK_CONNECTORS=true AUTH_MODE=mock python - <<'PY'
import json
from fastapi.testclient import TestClient
from app.main import app

with TestClient(app) as c:
    tok = c.post("/api/v1/auth/login", json={"username": "an.nguyen", "password": "demo"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    c.post("/api/v1/sim/emit", json={"scenario": "mail_manager_deadline"}, headers=h)
    c.post("/api/v1/sim/emit", json={"scenario": "sdp_sla_escalation"}, headers=h)
    dump = lambda name, data: open(f"../mobile/test/fixtures/{name}.json", "w").write(json.dumps(data, ensure_ascii=False, indent=2))
    dump("events", c.get("/api/v1/events", params={"since": 0}, headers=h).json())
    dump("scenarios", c.get("/api/v1/sim/scenarios", headers=h).json())
    st = c.get("/api/v1/settings", headers=h).json()
    dump("settings", st)
PY
```

Expected: tạo `events.json` (2 sự kiện, `latest_id` = id sự kiện cuối), `scenarios.json` (12 phần tử), ghi đè `settings.json` (nay có thêm `"live_sim_enabled": true`). Kiểm tra bằng `cat mobile/test/fixtures/events.json`.

- [ ] **Step 2: Viết test thất bại**

Trong `mobile/test/models_test.dart`, thêm hai test vào trong `main()` (trước test `WorkItem.isOverdue và keyTime`):

```dart
  test('LiveEventsPage và SimScenario', () {
    final p = LiveEventsPage.fromJson(fixture('events') as Map<String, dynamic>);
    expect(p.events.length, 2);
    expect(p.events.first.scenario, 'mail_manager_deadline');
    expect(p.events.first.type, 'new_item');
    expect(p.events.last.type, 'update_item');
    expect(p.events.every((e) => ['info', 'warning', 'critical'].contains(e.severity)), isTrue);
    expect(p.events.every((e) => e.workItemId != null && e.title.isNotEmpty), isTrue);
    expect(p.latestId, p.events.last.id);

    final sc = (fixture('scenarios') as List).map((e) => SimScenario.fromJson(e as Map<String, dynamic>)).toList();
    expect(sc.length, 12);
    expect(sc.map((s) => s.key), contains('sdp_sla_escalation'));
  });

  test('UserSettings giữ liveSimEnabled khi serialize', () {
    final s = UserSettings.fromJson(fixture('settings') as Map<String, dynamic>);
    expect(s.liveSimEnabled, isTrue);
    final off = s.copyWith(liveSimEnabled: false);
    expect(UserSettings.fromJson(off.toJson()).liveSimEnabled, isFalse);
    // backend cũ chưa có trường này -> mặc định bật
    final legacy = Map<String, dynamic>.from(fixture('settings') as Map)..remove('live_sim_enabled');
    expect(UserSettings.fromJson(legacy).liveSimEnabled, isTrue);
  });
```

- [ ] **Step 3: Chạy test, xác nhận thất bại**

Run: `cd mobile && flutter test test/models_test.dart`
Expected: FAIL (không tìm thấy `LiveEventsPage` / `liveSimEnabled`).

- [ ] **Step 4: Sửa `UserSettings` trong `models.dart`**

Trong constructor thêm `this.liveSimEnabled = true,` sau `required this.focusTimeSuggestions,`; thêm field `final bool liveSimEnabled;` sau `final bool focusTimeSuggestions;`; trong `fromJson` thêm `liveSimEnabled: j['live_sim_enabled'] as bool? ?? true,`; trong `toJson` thêm `'live_sim_enabled': liveSimEnabled,`; trong `copyWith` thêm tham số `bool? liveSimEnabled,` và dòng `liveSimEnabled: liveSimEnabled ?? this.liveSimEnabled,`.

- [ ] **Step 5: Thêm model mới vào cuối `models.dart`**

```dart
/// Sự kiện giả lập (chỉ có ở backend chế độ MOCK).
class LiveEvent {
  LiveEvent({
    required this.id,
    required this.type,
    required this.scenario,
    required this.source,
    required this.severity,
    required this.title,
    this.workItemId,
    required this.createdAt,
  });

  final int id;
  final String type; // new_item | update_item
  final String scenario;
  final String source;
  final String severity; // info | warning | critical
  final String title;
  final int? workItemId;
  final DateTime createdAt;

  factory LiveEvent.fromJson(Map<String, dynamic> j) => LiveEvent(
        id: j['id'] as int,
        type: j['type'] as String,
        scenario: j['scenario'] as String,
        source: j['source'] as String,
        severity: j['severity'] as String? ?? 'info',
        title: j['title'] as String,
        workItemId: j['work_item_id'] as int?,
        createdAt: _dt(j['created_at'])!,
      );
}

class LiveEventsPage {
  const LiveEventsPage(this.events, this.latestId);

  final List<LiveEvent> events;
  final int latestId;

  factory LiveEventsPage.fromJson(Map<String, dynamic> j) => LiveEventsPage(
        (j['events'] as List? ?? const []).map((e) => LiveEvent.fromJson(e as Map<String, dynamic>)).toList(),
        j['latest_id'] as int? ?? 0,
      );
}

class SimScenario {
  const SimScenario({required this.key, required this.label});

  final String key;
  final String label;

  factory SimScenario.fromJson(Map<String, dynamic> j) =>
      SimScenario(key: j['key'] as String, label: j['label'] as String);
}
```

- [ ] **Step 6: Thêm hàm vào `repository.dart`**

Thêm trước dấu `}` đóng class (sau `registerDevice`):

```dart

  // ---- Giả lập realtime (chỉ backend MOCK; nơi khác trả 404)

  Future<LiveEventsPage> liveEvents({int? since}) => _call(() async {
        final r = await _dio.get('/events', queryParameters: {'since': ?since});
        return LiveEventsPage.fromJson(r.data as Map<String, dynamic>);
      });

  Future<LiveEvent> simEmit({String? scenario}) => _call(() async =>
      LiveEvent.fromJson((await _dio.post('/sim/emit', data: {'scenario': scenario})).data as Map<String, dynamic>));

  Future<List<SimScenario>> simScenarios() => _call(() async =>
      ((await _dio.get('/sim/scenarios')).data as List).map((e) => SimScenario.fromJson(e as Map<String, dynamic>)).toList());

  Future<void> simReset() => _call(() => _dio.post('/sim/reset'));
```

- [ ] **Step 7: Chạy test, xác nhận đạt**

Run: `cd mobile && flutter test test/models_test.dart`
Expected: All tests passed.

- [ ] **Step 8: Checkpoint**

Run: `cd mobile && flutter analyze && flutter test`
Expected: `No issues found!` và toàn bộ test pass.

---

### Task 8: Mobile — `LiveEventsController`

**Files:**
- Create: `mobile/lib/data/live_events.dart`
- Create: `mobile/test/live_events_test.dart`

**Interfaces:**
- Consumes: `repositoryProvider` (`data/providers.dart`), `WorkHubRepository.liveEvents` và `LiveEventsPage`/`LiveEvent` (Task 7), `ApiException` (`core/api_client.dart`).
- Produces:
  - `const liveBaseInterval = Duration(seconds: 8)`, `const liveMaxInterval = Duration(seconds: 30)`
  - `LiveFeedState({bool? available, List<LiveEvent> batch = const [], int seq = 0})` — `available`: `null` chưa biết / `true` / `false` (backend không bật mô phỏng)
  - `String liveBannerText(List<LiveEvent> batch)`
  - `LiveEventsController extends Notifier<LiveFeedState>` với `start()`, `stop()`, `reset()`, `Future<void> poll()`, `Duration get interval`
  - `liveEventsProvider = NotifierProvider<LiveEventsController, LiveFeedState>`

- [ ] **Step 1: Viết test thất bại**

Tạo `mobile/test/live_events_test.dart`:

```dart
import 'dart:async';

import 'package:ai_work_hub/core/api_client.dart';
import 'package:ai_work_hub/data/live_events.dart';
import 'package:ai_work_hub/data/providers.dart';
import 'package:ai_work_hub/data/repository.dart';
import 'package:ai_work_hub/domain/models.dart';
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

LiveEvent ev(int id, {String title = 'Mail mới', String severity = 'warning'}) => LiveEvent(
      id: id,
      type: 'new_item',
      scenario: 's',
      source: 'exchange_mail',
      severity: severity,
      title: title,
      workItemId: id * 10,
      createdAt: DateTime(2026, 10, 8, 9),
    );

class FakeRepo extends WorkHubRepository {
  FakeRepo(this.responses) : super(Dio());

  final List<Object> responses; // LiveEventsPage hoặc Exception
  final List<int?> sinceArgs = [];
  Completer<void>? gate;

  @override
  Future<LiveEventsPage> liveEvents({int? since}) async {
    sinceArgs.add(since);
    if (gate != null) await gate!.future;
    final r = responses[sinceArgs.length - 1];
    if (r is Exception) throw r;
    return r as LiveEventsPage;
  }
}

ProviderContainer containerWith(FakeRepo repo) {
  final c = ProviderContainer(overrides: [repositoryProvider.overrideWithValue(repo)]);
  addTearDown(c.dispose);
  return c;
}

void main() {
  test('lần poll đầu chỉ lấy con trỏ, không phát lại lịch sử', () async {
    final repo = FakeRepo([LiveEventsPage([ev(1), ev(2)], 2)]);
    final c = containerWith(repo);
    await c.read(liveEventsProvider.notifier).poll();
    final s = c.read(liveEventsProvider);
    expect(repo.sinceArgs, [null]);
    expect(s.batch, isEmpty);
    expect(s.seq, 0);
    expect(s.available, isTrue);
  });

  test('poll tiếp theo gửi con trỏ, công bố lô sự kiện và tiến con trỏ', () async {
    final repo = FakeRepo([
      LiveEventsPage([], 5),
      LiveEventsPage([ev(6), ev(7)], 7),
      LiveEventsPage([], 7),
    ]);
    final c = containerWith(repo);
    final ctrl = c.read(liveEventsProvider.notifier);
    await ctrl.poll();
    await ctrl.poll();
    var s = c.read(liveEventsProvider);
    expect(s.batch.map((e) => e.id), [6, 7]);
    expect(s.seq, 1);
    await ctrl.poll();
    expect(repo.sinceArgs, [null, 5, 7]);
    s = c.read(liveEventsProvider);
    expect(s.seq, 1, reason: 'không có sự kiện mới thì không đổi seq');
  });

  test('server hạ latest_id (reset / dựng lại DB): app hạ con trỏ và vẫn nhận sự kiện mới', () async {
    final repo = FakeRepo([
      LiveEventsPage([], 10),
      LiveEventsPage([], 3), // latest_id < con trỏ
      LiveEventsPage([ev(4)], 4),
    ]);
    final c = containerWith(repo);
    final ctrl = c.read(liveEventsProvider.notifier);
    await ctrl.poll();
    await ctrl.poll();
    await ctrl.poll();
    expect(repo.sinceArgs, [null, 10, 3]);
    expect(c.read(liveEventsProvider).batch.map((e) => e.id), [4]);
  });

  test('404: đánh dấu không khả dụng và không gọi lại', () async {
    final repo = FakeRepo([ApiException('Không tìm thấy', 404)]);
    final c = containerWith(repo);
    final ctrl = c.read(liveEventsProvider.notifier);
    await ctrl.poll();
    expect(c.read(liveEventsProvider).available, isFalse);
    await ctrl.poll();
    expect(repo.sinceArgs.length, 1);
  });

  test('lỗi mạng giãn dần tới 30s rồi về 8s khi thành công', () async {
    final err = ApiException('Không kết nối được máy chủ.');
    final repo = FakeRepo([LiveEventsPage([], 1), err, err, err, err, LiveEventsPage([], 1)]);
    final c = containerWith(repo);
    final ctrl = c.read(liveEventsProvider.notifier);
    expect(ctrl.interval, liveBaseInterval);
    await ctrl.poll();
    final seen = <Duration>[];
    for (var i = 0; i < 4; i++) {
      await ctrl.poll();
      seen.add(ctrl.interval);
    }
    expect(seen, [const Duration(seconds: 16), liveMaxInterval, liveMaxInterval, liveMaxInterval]);
    await ctrl.poll();
    expect(ctrl.interval, liveBaseInterval);
  });

  test('hai poll chồng nhau chỉ gọi server một lần', () async {
    final repo = FakeRepo([LiveEventsPage([], 1)])..gate = Completer<void>();
    final c = containerWith(repo);
    final ctrl = c.read(liveEventsProvider.notifier);
    final a = ctrl.poll();
    final b = ctrl.poll();
    repo.gate!.complete();
    await Future.wait([a, b]);
    expect(repo.sinceArgs.length, 1);
  });

  test('reset xoá con trỏ: poll kế tiếp lại gửi since = null', () async {
    final repo = FakeRepo([LiveEventsPage([], 5), LiveEventsPage([], 9)]);
    final c = containerWith(repo);
    final ctrl = c.read(liveEventsProvider.notifier);
    await ctrl.poll();
    ctrl.reset();
    expect(c.read(liveEventsProvider).available, isNull);
    await ctrl.poll();
    expect(repo.sinceArgs, [null, null]);
  });

  test('liveBannerText', () {
    expect(liveBannerText([]), '');
    expect(liveBannerText([ev(1, title: 'A')]), 'A');
    expect(liveBannerText([ev(1, title: 'A'), ev(2, title: 'B'), ev(3, title: 'C')]), '3 mục mới · C');
  });
}
```

- [ ] **Step 2: Chạy test, xác nhận thất bại**

Run: `cd mobile && flutter test test/live_events_test.dart`
Expected: FAIL (không tìm thấy `data/live_events.dart`).

- [ ] **Step 3: Tạo `lib/data/live_events.dart`**

```dart
import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/api_client.dart';
import '../domain/models.dart';
import 'providers.dart';

const liveBaseInterval = Duration(seconds: 8);
const liveMaxInterval = Duration(seconds: 30);

/// `available`: null = chưa biết, true = backend có mô phỏng, false = backend không bật (404).
/// Mỗi lần có lô sự kiện mới `seq` tăng lên để UI biết mà phản ứng (invalidate provider, hiện banner).
class LiveFeedState {
  const LiveFeedState({this.available, this.batch = const [], this.seq = 0});

  final bool? available;
  final List<LiveEvent> batch;
  final int seq;

  LiveFeedState copyWith({bool? available}) =>
      LiveFeedState(available: available ?? this.available, batch: batch, seq: seq);
}

String liveBannerText(List<LiveEvent> batch) {
  if (batch.isEmpty) return '';
  if (batch.length == 1) return batch.single.title;
  return '${batch.length} mục mới · ${batch.last.title}';
}

/// Poll `/events?since=` khi app mở. Chỉ lo việc lấy sự kiện; làm mới màn hình và banner do `app.dart` xử lý.
class LiveEventsController extends Notifier<LiveFeedState> {
  Timer? _timer;
  int? _cursor;
  bool _running = false;
  bool _busy = false;
  bool _disposed = false;
  Duration _interval = liveBaseInterval;

  Duration get interval => _interval;

  @override
  LiveFeedState build() {
    ref.onDispose(() {
      _disposed = true;
      _running = false;
      _timer?.cancel();
    });
    return const LiveFeedState();
  }

  void start() {
    if (_running || state.available == false) return;
    _running = true;
    _loop();
  }

  void stop() {
    _running = false;
    _timer?.cancel();
    _timer = null;
  }

  /// Đăng xuất: quên con trỏ và trạng thái để phiên sau bắt đầu sạch.
  void reset() {
    stop();
    _cursor = null;
    _interval = liveBaseInterval;
    state = const LiveFeedState();
  }

  Future<void> _loop() async {
    await poll();
    if (!_running || _disposed) return;
    _timer = Timer(_interval, _loop);
  }

  Future<void> poll() async {
    if (_busy || _disposed || state.available == false) return;
    _busy = true;
    try {
      final since = _cursor;
      final page = await ref.read(repositoryProvider).liveEvents(since: since);
      if (_disposed) return;
      _interval = liveBaseInterval;
      if (state.available != true) state = state.copyWith(available: true);
      if (since == null || page.latestId < since) {
        _cursor = page.latestId; // lần đầu, hoặc server đã reset: lấy con trỏ mới, không phát lại
        return;
      }
      if (page.events.isEmpty) return;
      _cursor = page.events.last.id;
      state = LiveFeedState(available: true, batch: page.events, seq: state.seq + 1);
    } on ApiException catch (e) {
      if (_disposed) return;
      if (e.statusCode == 404) {
        stop();
        state = state.copyWith(available: false);
      } else {
        final next = _interval * 2;
        _interval = next > liveMaxInterval ? liveMaxInterval : next;
      }
    } finally {
      _busy = false;
    }
  }
}

final liveEventsProvider = NotifierProvider<LiveEventsController, LiveFeedState>(LiveEventsController.new);
```

- [ ] **Step 4: Chạy test, xác nhận đạt**

Run: `cd mobile && flutter test test/live_events_test.dart`
Expected: All tests passed (8 test). Nếu test "lỗi mạng giãn dần" lệch, kiểm tra: lần lỗi thứ 1 → 16s, thứ 2 → 30s (cap), thứ 3, 4 → 30s; lần poll thành công kế tiếp về 8s.

- [ ] **Step 5: Checkpoint**

Run: `cd mobile && flutter analyze && flutter test`
Expected: `No issues found!` và toàn bộ test pass.

---

### Task 9: Mobile — nối vào app (banner, vòng đời) và mục Settings

**Files:**
- Modify: `mobile/lib/app/app.dart` (viết lại toàn bộ)
- Modify: `mobile/lib/features/settings/settings_screen.dart`

**Interfaces:**
- Consumes: `liveEventsProvider`, `LiveFeedState`, `liveBannerText` (Task 8); `WorkHubRepository.simEmit/simScenarios/simReset` và `UserSettings.liveSimEnabled` (Task 7); `refreshWorkData`, `authProvider`, `routerProvider`; `showItemSheetById` (`features/item/item_sheet.dart`); `Severity.color` (`app/theme.dart`).
- Produces: hành vi UI — banner khi có sự kiện, tự dừng khi app ở nền / đăng xuất, mục "Dữ liệu giả lập" trong Settings (chỉ hiện khi `available == true`).

- [ ] **Step 1: Thay toàn bộ `lib/app/app.dart`**

```dart
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/live_events.dart';
import '../data/providers.dart';
import '../features/item/item_sheet.dart';
import 'router.dart';
import 'theme.dart';

class AiWorkHubApp extends ConsumerStatefulWidget {
  const AiWorkHubApp({super.key});

  @override
  ConsumerState<AiWorkHubApp> createState() => _AiWorkHubAppState();
}

class _AiWorkHubAppState extends ConsumerState<AiWorkHubApp> with WidgetsBindingObserver {
  final _messengerKey = GlobalKey<ScaffoldMessengerState>();
  bool _foreground = true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final auth = ref.read(authProvider.notifier);
    final live = ref.read(liveEventsProvider.notifier);
    if (state == AppLifecycleState.paused) {
      _foreground = false;
      auth.onPaused();
      live.stop();
    } else if (state == AppLifecycleState.resumed) {
      _foreground = true;
      auth.onResumed();
      if (ref.read(authProvider).status == AuthStatus.signedIn) {
        ref.invalidate(todayProvider);
        ref.read(notificationSyncProvider).resync().ignore();
        live.start();
      }
    }
  }

  void _onAuth(AuthStatus status) {
    final live = ref.read(liveEventsProvider.notifier);
    switch (status) {
      case AuthStatus.signedIn:
        if (_foreground) live.start();
      case AuthStatus.signedOut:
        live.reset();
      case AuthStatus.unknown || AuthStatus.locked:
        live.stop();
    }
  }

  void _onLive(LiveFeedState? prev, LiveFeedState next) {
    if (next.batch.isEmpty || next.seq == (prev?.seq ?? 0)) return;
    refreshWorkData(ref);
    final messenger = _messengerKey.currentState;
    if (messenger == null) return;
    final last = next.batch.last;
    messenger
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(
        behavior: SnackBarBehavior.floating,
        duration: const Duration(seconds: 6),
        backgroundColor: Severity.color(last.severity),
        content: Text(liveBannerText(next.batch), style: const TextStyle(color: Colors.white)),
        action: last.workItemId == null
            ? null
            : SnackBarAction(label: 'Mở', textColor: Colors.white, onPressed: () => _openItem(last.workItemId!)),
      ));
  }

  void _openItem(int id) {
    final ctx = ref.read(routerProvider).routerDelegate.navigatorKey.currentContext;
    if (ctx != null) showItemSheetById(ctx, ref, id);
  }

  @override
  Widget build(BuildContext context) {
    ref.listen<AuthState>(authProvider, (_, next) => _onAuth(next.status));
    ref.listen<LiveFeedState>(liveEventsProvider, _onLive);
    return MaterialApp.router(
      title: 'AI Work Hub',
      debugShowCheckedModeBanner: false,
      scaffoldMessengerKey: _messengerKey,
      theme: buildTheme(Brightness.light),
      darkTheme: buildTheme(Brightness.dark),
      routerConfig: ref.watch(routerProvider),
      locale: const Locale('vi'),
      supportedLocales: const [Locale('vi'), Locale('en')],
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
    );
  }
}
```

- [ ] **Step 2: Thêm import và hàm xử lý vào `settings_screen.dart`**

Thêm import (sau `import '../../core/api_client.dart';`): `import '../../data/live_events.dart';`

Thêm ba phương thức vào `_SettingsScreenState` (ngay sau `_addVip`):

```dart
  Future<void> _emitSim([String? scenario]) async {
    try {
      await ref.read(repositoryProvider).simEmit(scenario: scenario);
      await ref.read(liveEventsProvider.notifier).poll(); // hiện banner ngay, không đợi nhịp 8 giây
    } catch (e) {
      if (mounted) showSnack(context, ApiException.from(e).message);
    }
  }

  Future<void> _pickScenario() async {
    try {
      final list = await ref.read(repositoryProvider).simScenarios();
      if (!mounted) return;
      final key = await showModalBottomSheet<String>(
        context: context,
        builder: (ctx) => SafeArea(
          child: ListView(shrinkWrap: true, children: [
            for (final sc in list) ListTile(title: Text(sc.label), onTap: () => Navigator.pop(ctx, sc.key)),
          ]),
        ),
      );
      if (key != null) await _emitSim(key);
    } catch (e) {
      if (mounted) showSnack(context, ApiException.from(e).message);
    }
  }

  Future<void> _resetSim() async {
    try {
      await ref.read(repositoryProvider).simReset();
      refreshWorkData(ref);
      if (mounted) showSnack(context, 'Đã đặt lại dữ liệu giả lập');
    } catch (e) {
      if (mounted) showSnack(context, ApiException.from(e).message);
    }
  }
```

- [ ] **Step 3: Thêm mục UI**

Trong `build` của `settings_screen.dart`, chèn ngay **trước** dòng `const SectionHeader('Bảo mật & quyền riêng tư', icon: Icons.shield_outlined),`:

```dart
            if (ref.watch(liveEventsProvider).available == true) ...[
              const SectionHeader('Dữ liệu giả lập', icon: Icons.bolt_outlined),
              Card(
                child: Column(children: [
                  SwitchListTile(
                    value: s.liveSimEnabled,
                    onChanged: (v) => _save(s.copyWith(liveSimEnabled: v)),
                    title: const Text('Tự động phát sự kiện mới'),
                    subtitle: const Text('Cứ 30–90 giây có thêm mail, ticket, họp... (chế độ MOCK)'),
                  ),
                  ListTile(
                    leading: const Icon(Icons.flash_on_outlined),
                    title: const Text('Phát sự kiện ngay'),
                    onTap: _emitSim,
                  ),
                  ListTile(
                    leading: const Icon(Icons.list_alt_outlined),
                    title: const Text('Chọn kịch bản...'),
                    onTap: _pickScenario,
                  ),
                  ListTile(
                    leading: const Icon(Icons.restart_alt),
                    title: const Text('Đặt lại dữ liệu giả lập'),
                    onTap: _resetSim,
                  ),
                ]),
              ),
            ],

```

Lưu ý: `onTap: _emitSim` hợp lệ vì `_emitSim([String? scenario])` có tham số tuỳ chọn; nếu analyzer than phiền kiểu `void Function()`, đổi thành `onTap: () => _emitSim()`.

- [ ] **Step 4: Phân tích tĩnh và chạy test**

Run: `cd mobile && flutter analyze && flutter test`
Expected: `No issues found!`; toàn bộ test pass (test cũ + `live_events_test` + `models_test`).

- [ ] **Step 5: Checkpoint**

Không có test tự động cho dây nối UI (cần thiết bị/plugin). Phần này được xác minh ở Task 10, bước kiểm thử thủ công.

---

### Task 10: Tài liệu và kiểm thử end-to-end

**Files:**
- Modify: `README.md` (mục "Chạy nhanh", bảng API)
- Modify: `docs/architecture.md` (thêm mục luồng sự kiện giả lập)

**Interfaces:** không có (chỉ tài liệu và xác minh).

- [ ] **Step 1: Cập nhật README**

Trong `README.md`, ngay sau đoạn "Dữ liệu mẫu được sinh theo giờ hiện tại..." (mục "Chạy nhanh" → Backend), thêm:

```markdown
**Dữ liệu giả lập realtime (chỉ chế độ MOCK).** Khi `MOCK_CONNECTORS=true` và worker đang chạy, cứ 30–90 giây mỗi người dùng nhận
một sự kiện mới (mail từ quản lý/Kiểm toán/KH VIP, ticket SDP mới hoặc sắp vi phạm SLA, @mention Teams/wiki, họp mới/trùng/dời giờ,
Jira mới hoặc hết bị chặn). App tự làm mới và hiện banner trong vòng ~8 giây. Trong **Cài đặt → Dữ liệu giả lập** có công tắc
bật/tắt, nút "Phát sự kiện ngay", chọn kịch bản và "Đặt lại". Không chạy worker thì vẫn phát thủ công được. Ngoài chế độ MOCK,
các endpoint này trả 404 và mục cài đặt không hiện.
```

Trong bảng API, thêm 4 dòng (đánh dấu "chỉ MOCK"):

```markdown
| GET | `/api/v1/events?since=&limit=` | (chỉ MOCK) Sự kiện giả lập mới hơn `since`; thiếu `since` chỉ trả `latest_id` |
| POST | `/api/v1/sim/emit` | (chỉ MOCK) Phát một sự kiện ngay, body tuỳ chọn `{"scenario": "..."}` |
| GET | `/api/v1/sim/scenarios` | (chỉ MOCK) Danh sách kịch bản theo vai trò người dùng |
| POST | `/api/v1/sim/reset` | (chỉ MOCK) Xoá sự kiện giả lập, trả dữ liệu về ban đầu |
```

Trong sơ đồ cấu trúc thư mục, thêm vào dòng `services/` các tên `simulator, sim_catalog`.

- [ ] **Step 2: Cập nhật architecture**

Chạy `tail -30 docs/architecture.md` để xem định dạng tiêu đề hiện có, rồi thêm cuối file (giữ cùng cấp tiêu đề với các mục chính):

```markdown
## Luồng sự kiện giả lập (chỉ MOCK)

1. `worker.job_sim_tick` (10 giây/lần) hỏi `SimTicker`; user nào bật `live_sim_enabled` và đã tới lượt thì `simulator.emit`.
   `POST /sim/emit` gọi cùng hàm này trong tiến trình API (hai tiến trình dùng chung DB, không cần IPC).
2. `emit` chọn kịch bản theo persona và nguồn đang bật → ghi `live_events` → upsert `WorkItem` → `recompute()` (chấm điểm + sinh `Alert`)
   trong một transaction.
3. `MockConnector.fetch` = dữ liệu gốc + item dựng lại từ `live_events` (mốc thời gian lưu dạng offset so với `created_at`),
   nên lần sync 5 phút không xoá dữ liệu giả lập.
4. App poll `GET /events?since=<con trỏ>` mỗi 8 giây khi ở foreground; có sự kiện thì invalidate Today/Alerts/Brief và hiện banner.
   Nếu `latest_id` của server nhỏ hơn con trỏ (sau reset) app hạ con trỏ xuống.
```

- [ ] **Step 3: Chạy toàn bộ test hai phía**

Run: `cd backend && source .venv/bin/activate && pytest -q` rồi `cd ../mobile && flutter analyze && flutter test`
Expected: backend toàn bộ pass; mobile `No issues found!` và toàn bộ pass.

- [ ] **Step 4: Kiểm thử end-to-end phía backend bằng HTTP thật**

Dùng DB tạm để không đụng DB dev. Terminal 1:

```bash
cd backend && source .venv/bin/activate && export DATABASE_URL="sqlite:///$(mktemp -d)/e2e.db" && uvicorn app.main:app --port 8000
```

Terminal 2 (cùng `DATABASE_URL` như terminal 1: copy đường dẫn từ lệnh trên, hoặc `export` cùng một giá trị):

```bash
cd backend && source .venv/bin/activate && export DATABASE_URL="<cùng giá trị>" && python -m app.worker
```

Terminal 3:

```bash
TOKEN=$(curl -s localhost:8000/api/v1/auth/login -H 'content-type: application/json' -d '{"username":"an.nguyen","password":"demo"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
H="Authorization: Bearer $TOKEN"
curl -s "localhost:8000/api/v1/events" -H "$H"                      # {"events":[],"latest_id":0}
sleep 45
curl -s "localhost:8000/api/v1/events?since=0" -H "$H"              # có ít nhất 1 sự kiện do worker phát
curl -s -XPOST localhost:8000/api/v1/sim/emit -H "$H" -H 'content-type: application/json' -d '{"scenario":"sdp_sla_escalation"}'
curl -s -XPOST localhost:8000/api/v1/sync -H "$H" >/dev/null        # sync xong sự kiện vẫn còn:
curl -s "localhost:8000/api/v1/events?since=0" -H "$H" | python3 -c 'import sys,json;d=json.load(sys.stdin);print(len(d["events"]),"sự kiện, latest_id",d["latest_id"])'
curl -s "localhost:8000/api/v1/work-items?source=sdp" -H "$H" | python3 -c 'import sys,json;[print(i["title"],i["sla_due_at"]) for i in json.load(sys.stdin)]'
```

Expected: sau ~45 giây có sự kiện tự động; ticket SDP bị leo thang có `sla_due_at` cách thời điểm phát ~10 phút (không bị "trượt" về +95 phút sau sync). (Dùng `python3` hệ thống ở đây chỉ để parse JSON từ stdin, không cài gói; nếu muốn tuân quy tắc venv tuyệt đối, thay bằng `python` sau khi `source .venv/bin/activate`.)

Tắt uvicorn và worker (Ctrl+C) khi xong.

- [ ] **Step 5: Kiểm thử thủ công trên app**

Chạy backend + worker như Step 4 (DB dev bình thường, `cd backend && uvicorn app.main:app --reload` và `python -m app.worker`), rồi `cd mobile && flutter run`. Đăng nhập `an.nguyen / demo` và kiểm tra:

1. Mở màn Today, đợi tối đa ~90 giây: xuất hiện banner màu theo mức độ ("Mail mới từ quản lý: ..."), danh sách Top 3 / hạn chót cập nhật không cần kéo-làm-mới.
2. Chạm "Mở" trên banner: mở đúng bottom sheet của item.
3. Cài đặt → Dữ liệu giả lập: "Phát sự kiện ngay" hiện banner trong vài giây; "Chọn kịch bản..." phát đúng kịch bản; tắt công tắc thì sau đó không còn sự kiện tự động.
4. "Đặt lại dữ liệu giả lập": item sim biến mất, không có banner nào nữa; phát tiếp vẫn nhận được sự kiện mới (con trỏ đã hạ).
5. Đưa app xuống nền ~1 phút rồi mở lại: banner tóm tắt "N mục mới · ..." xuất hiện một lần.
6. Đăng xuất rồi đăng nhập `lan.pham / demo`: nhận sự kiện của persona RM (mail KH giải ngân, ticket LOS...), không lẫn sự kiện của an.nguyen.
7. Tắt backend: app không crash, không spam lỗi; bật lại thì tự nối lại.

Ghi kết quả từng mục (đạt/không đạt) cho người duyệt. Nếu mục nào không đạt, dừng và xử lý theo `superpowers:systematic-debugging` trước khi báo hoàn tất.

---

## Self-Review

**1. Spec coverage**

| Mục spec | Task |
|---|---|
| 3.1 bảng `live_events`, cắt 200 dòng | 1 (model), 4 (`_trim`, test `trim_keeps_latest`) |
| 3.2 `live_sim_enabled` + `ALTER TABLE` dev | 1 |
| 3.3 `MockConnector` hợp nhất sự kiện, offset thời gian | 2 |
| 3.4 `emit` (chọn kịch bản, ghi event, upsert, recompute) | 4 |
| 3.5 danh mục 12 IT + 6 RM, fallback | 3 |
| 3.6 `job_sim_tick` 10s, 10–30s đầu, 30–90s sau, chỉ đăng ký khi mock | 4 (`SimTicker`), 6 |
| 3.7 endpoint `/events`, `/sim/emit|scenarios|reset`, 404 ngoài mock, audit, không trả payload | 5 |
| 3.8 lỗi/an toàn (422, rollback, chỉ mock) | 4 (`failed_emit`), 5 |
| 4 mobile: model, repository, controller, banner, Settings, vòng đời app | 7, 8, 9 |
| 5 kiểm thử backend + mobile + thủ công | 1–8 (tự động), 10 (thủ công) |
| 7 tài liệu README + architecture | 10 |

Khoảng trống đã xử lý: "banner gom nhiều sự kiện" nằm ở `liveBannerText` (Task 8); "chạm banner mở item" ở `_openItem` (Task 9). Một chi tiết spec nói `resync()` lịch nhắc cục bộ: được gọi qua `refreshWorkData(ref)` trong `_onLive` (Task 9).

**2. Quét placeholder:** không còn "TBD/TODO"; mọi bước code đều có nội dung. Hai chỗ có điều kiện cần người thực thi xem tại chỗ (đều có hướng dẫn cụ thể): thứ tự `a_title/b_title` trong alert xung đột (Task 4 Step 4), và định dạng tiêu đề `architecture.md` (Task 10 Step 2).

**3. Nhất quán kiểu/tên:** `payload_to_item`/`item_to_payload`/`item_from_row` (Task 2) khớp cách dùng ở Task 3–4; `ScenarioCtx(user, now, rng, tz, rows, taken_ids)` khớp giữa test Task 3 và `emit` Task 4; `SimTicker.tick(db, now, active_days)` khớp worker Task 6 (`_ticker.tick(db, active_days=...)`) và `FakeTicker.tick(self, db, active_days)` trong test; `LiveEventOut`/`EventsOut` (Task 5) khớp `LiveEvent.fromJson`/`LiveEventsPage.fromJson` (Task 7); `liveBaseInterval`/`liveMaxInterval`/`interval` dùng nhất quán Task 8–9; `liveSimEnabled` ⇄ `live_sim_enabled` khớp.

**4. Review Focus:** 5 dòng đều có test ghim: (1) `test_since_cuts_and_cursor_beyond_latest...` + `test_reset_lowers_latest_id_to_zero` (Task 5) và test "server hạ latest_id" (Task 8); (2) `test_two_emits_at_same_instant_do_not_collide`; (3) `test_done_local_survives_update_and_sync`; (4) `test_random_pick_skips_disabled_sources`; (5) `test_invalid_query_params_rejected`.
