import json
from datetime import datetime, timezone

import httpx
import pytest

from app.connectors.base import ConnectorError, UserContext, classify_requester
from app.connectors.confluence_dc import ConfluenceDcConnector
from app.connectors.jira_dc import JiraDcConnector
from app.connectors.sdp import SdpConnector
from app.core.config import Settings

S = Settings(jira_base_url="https://jira.bank.local", confluence_base_url="https://wiki.bank.local",
             sdp_base_url="https://sdp.bank.local")
CTX = UserContext(username="an.nguyen", email="an.nguyen@bank.local", display_name="Nguyễn Văn An",
                  manager_email="minh.tran@bank.local", vip_senders=["vip-corp.vn"])
NOW = datetime(2026, 10, 8, 2, 0, tzinfo=timezone.utc)


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_classify_requester():
    assert classify_requester("minh.tran@bank.local", CTX) == "manager"
    assert classify_requester("ceo@vip-corp.vn", CTX) == "vip_customer"
    assert classify_requester("ksnb@bank.local", CTX) == "audit"
    assert classify_requester("someone@partner.com", CTX) == "external"
    assert classify_requester("hoa.do@bank.local", CTX) == "peer"


def test_jira_maps_issues_and_builds_jql():
    seen = {}

    def handler(req: httpx.Request):
        seen["jql"] = req.url.params["jql"]
        return httpx.Response(200, json={"issues": [{
            "key": "CORE-1",
            "fields": {
                "summary": "Fix lỗi", "status": {"name": "In Progress"}, "priority": {"name": "Highest"},
                "duedate": "2026-10-08", "updated": "2026-10-08T09:12:33.000+0700",
                "reporter": {"name": "minh.tran", "emailAddress": "minh.tran@bank.local", "displayName": "Trần Minh"},
                "issuetype": {"name": "Bug"}, "labels": ["prod"], "description": "mô tả",
            },
        }]})

    items = JiraDcConnector(S, _client(handler)).fetch(CTX, NOW)
    assert 'assignee = "an.nguyen"' in seen["jql"] and "resolution = Unresolved" in seen["jql"]
    it = items[0]
    assert it.title == "[CORE-1] Fix lỗi" and it.url == "https://jira.bank.local/browse/CORE-1"
    assert it.requester_role == "manager" and it.priority_raw == "Highest"
    assert it.due_at.hour == 17 and it.due_at.minute == 30
    assert it.source_updated_at == datetime(2026, 10, 8, 2, 12, 33, tzinfo=timezone.utc)
    assert "bug" in it.tags


def test_jira_error_raises_connector_error():
    with pytest.raises(ConnectorError):
        JiraDcConnector(S, _client(lambda r: httpx.Response(401))).fetch(CTX, NOW)


def test_sdp_maps_sla_and_sends_criteria():
    seen = {}

    def handler(req: httpx.Request):
        seen["input"] = json.loads(req.url.params["input_data"])
        return httpx.Response(200, json={"requests": [{
            "id": "50231", "display_id": "50231", "subject": "Lỗi chuyển tiền",
            "status": {"name": "Open"}, "priority": {"name": "High"},
            "requester": {"name": "CN Hoàn Kiếm", "email_id": "cn.hk@bank.local"},
            "due_by_time": {"value": "1791511200000"}, "is_overdue": True,
            "request_type": {"name": "Incident"}, "created_time": {"value": "1791500000000"},
        }]})

    it = SdpConnector(S, _client(handler)).fetch(CTX, NOW)[0]
    crit = seen["input"]["list_info"]["search_criteria"]
    assert crit[0]["value"] == "an.nguyen@bank.local"
    assert it.sla_due_at == datetime.fromtimestamp(1791511200, tz=timezone.utc)
    assert set(it.tags) == {"incident", "overdue"}
    assert "woID=50231" in it.url


def test_confluence_dedupes_mention_and_watch():
    page = {"id": "1", "title": "Kế hoạch", "_links": {"webui": "/x/1"},
            "version": {"when": "2026-10-08T01:00:00.000Z", "by": {"displayName": "Trần Minh"}},
            "space": {"name": "Core"}}
    items = ConfluenceDcConnector(S, _client(lambda r: httpx.Response(200, json={"results": [page]}))).fetch(CTX, NOW)
    assert len(items) == 1
    assert items[0].tags == ["mention", "watching"]
    assert items[0].url == "https://wiki.bank.local/x/1"
