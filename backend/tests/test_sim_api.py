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
