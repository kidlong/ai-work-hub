import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _login(client, user="an.nguyen"):
    r = client.post("/api/v1/auth/login", json={"username": user, "password": "demo"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, r.json()


def test_auth_required_and_bad_password(client):
    assert client.get("/api/v1/today").status_code == 401
    assert client.post("/api/v1/auth/login", json={"username": "an.nguyen", "password": "x"}).status_code == 401
    assert client.get("/api/v1/today", headers={"Authorization": "Bearer abc"}).status_code == 401


def test_login_refresh_and_me(client):
    h, tokens = _login(client)
    assert client.get("/api/v1/auth/me", headers=h).json()["display_name"] == "Nguyễn Văn An"
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200
    # access token không dùng làm refresh token được
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]}).status_code == 401


def test_today_dashboard(client):
    h, _ = _login(client)
    r = client.get("/api/v1/today", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["greeting"].endswith("An!")
    assert len(d["top_priorities"]) == 3
    assert d["stats"]["sla_breached"] >= 1


def test_work_items_sorted_and_filtered(client):
    h, _ = _login(client)
    items = client.get("/api/v1/work-items", headers=h).json()
    scores = [i["score"] for i in items]
    assert scores == sorted(scores, reverse=True)
    sdp = client.get("/api/v1/work-items", params={"source": "sdp"}, headers=h).json()
    assert sdp and all(i["source"] == "sdp" for i in sdp)


def test_alerts_generated(client):
    h, _ = _login(client)
    allr = client.get("/api/v1/alerts", params={"scope": "all"}, headers=h).json()
    kinds = {a["kind"] for a in allr}
    assert "sla_breached" in kinds or "digest" in kinds
    a = allr[0]
    assert client.post(f"/api/v1/alerts/{a['id']}/snooze", json={"minutes": 30}, headers=h).json()["status"] == "snoozed"
    assert client.post(f"/api/v1/alerts/{a['id']}/ack", headers=h).json()["status"] == "acked"


def test_brief_ask_and_meeting_prep(client):
    h, _ = _login(client)
    b = client.get("/api/v1/brief/today", headers=h).json()
    assert b["generated_by"] == "fallback"
    assert b["content"]["headline"].startswith("Hôm nay bạn có")
    assert len(b["content"]["top_priorities"]) == 3

    r = client.post("/api/v1/ask", json={"question": "Ticket SDP nào đã quá hạn?"}, headers=h).json()
    assert r["items"] and all(i["source"] == "sdp" for i in r["items"])

    meetings = client.get("/api/v1/work-items", params={"kind": "meeting"}, headers=h).json()
    cab = next(m for m in meetings if "CAB" in m["title"])
    prep = client.get(f"/api/v1/meetings/{cab['id']}/prep", headers=h).json()
    titles = " ".join(r["title"] for r in prep["related"])
    assert "CORE-2481" in titles and "Kế hoạch Release" in titles


def test_done_snooze_and_isolation_between_users(client):
    h, _ = _login(client)
    h2, _ = _login(client, "lan.pham")
    item = client.get("/api/v1/work-items", headers=h).json()[0]
    # user khác không được xem / thao tác mục của An
    assert client.get(f"/api/v1/work-items/{item['id']}", headers=h2).status_code == 404
    assert client.post(f"/api/v1/work-items/{item['id']}/done", headers=h2).status_code == 404
    assert client.post(f"/api/v1/work-items/{item['id']}/done", headers=h).json()["done_local"] is True
    ids = [i["id"] for i in client.get("/api/v1/work-items", headers=h).json()]
    assert item["id"] not in ids
    client.post(f"/api/v1/work-items/{item['id']}/undone", headers=h)
    r = client.post(f"/api/v1/work-items/{item['id']}/snooze", json={"minutes": 60}, headers=h).json()
    assert r["snoozed_until"]


def test_settings_validation_and_sources(client):
    h, _ = _login(client)
    st = client.get("/api/v1/settings", headers=h).json()
    st["meeting_lead_minutes"] = 10
    assert client.put("/api/v1/settings", json=st, headers=h).json()["meeting_lead_minutes"] == 10
    assert client.put("/api/v1/settings", json={**st, "quiet_start": "25:00"}, headers=h).status_code == 422
    assert client.put("/api/v1/settings", json={**st, "enabled_sources": ["gmail"]}, headers=h).status_code == 422
    srcs = client.get("/api/v1/sources", headers=h).json()
    assert {s["id"] for s in srcs} >= {"exchange_mail", "jira", "sdp"}


def test_devices_and_manual_sync(client):
    h, _ = _login(client)
    assert client.post("/api/v1/devices", json={"token": "fcm-token-1234567890", "platform": "android"}, headers=h).status_code == 204
    r = client.post("/api/v1/sync", headers=h).json()
    assert r["result"]["jira"] > 0
