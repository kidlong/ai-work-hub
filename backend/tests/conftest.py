import os
import tempfile
from types import SimpleNamespace

import pytest

_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_db.name}"
os.environ["MOCK_CONNECTORS"] = "true"
os.environ["AUTH_MODE"] = "mock"
os.environ["LLM_ENABLED"] = "false"


def make_item(**kw):
    """WorkItem giả lập (duck-typing) cho test engine."""
    base = dict(
        id=1, kind="task", source="jira", title="Việc", preview="", url="", external_id="X-1",
        start_at=None, end_at=None, due_at=None, sla_due_at=None, status="", priority_raw="",
        requester="", requester_role="peer", participants=[], location="", is_unread=False,
        is_organizer=False, tags=[], bucket="low", score=0.0, score_reasons=[], done_local=False,
        snoozed_until=None, source_updated_at=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.fixture
def item_factory():
    return make_item


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
