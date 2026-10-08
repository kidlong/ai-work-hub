"""Jira Data Center on-prem qua REST API v2.

Xác thực: Personal Access Token (Bearer) của service account chỉ có quyền ĐỌC
(Browse projects) trên các project cần thiết. Lọc theo assignee = username AD.
Production nên chuyển sang OAuth 2.0 per-user (incoming application link) để
quyền xem dữ liệu khớp đúng quyền của từng người.
"""
from __future__ import annotations

import logging
from datetime import datetime

import httpx

from app.connectors.base import Connector, ConnectorError, ItemIn, UserContext, classify_requester
from app.connectors.http import client, date_end_of_workday, parse_iso
from app.core.config import Settings

log = logging.getLogger(__name__)

FIELDS = "summary,status,priority,duedate,updated,reporter,issuetype,description,labels"


def _jql_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


class JiraDcConnector(Connector):
    source = "jira"

    def __init__(self, settings: Settings, http: httpx.Client | None = None):
        self.s = settings
        self.base = settings.jira_base_url.rstrip("/")
        self.http = http or client(settings, headers={"Authorization": f"Bearer {settings.jira_token}"})

    def fetch(self, ctx: UserContext, now: datetime) -> list[ItemIn]:
        jql = (
            f"assignee = {_jql_quote(ctx.username)} AND resolution = Unresolved "
            "ORDER BY priority DESC, duedate ASC"
        )
        try:
            r = self.http.get(
                f"{self.base}/rest/api/2/search",
                params={"jql": jql, "fields": FIELDS, "maxResults": 100},
            )
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("Jira lỗi cho %s: %s", ctx.username, exc)
            raise ConnectorError(f"Jira: {exc}") from exc
        return [self._map(issue, ctx) for issue in data.get("issues", [])]

    def _map(self, issue: dict, ctx: UserContext) -> ItemIn:
        f = issue.get("fields", {})
        reporter = f.get("reporter") or {}
        reporter_id = reporter.get("emailAddress") or reporter.get("name") or ""
        status = (f.get("status") or {}).get("name", "")
        issue_type = (f.get("issuetype") or {}).get("name", "")
        desc = f.get("description") or ""
        return ItemIn(
            source="jira",
            external_id=issue["key"],
            kind="task",
            title=f"[{issue['key']}] {f.get('summary', '')}",
            preview=str(desc)[:600],
            url=f"{self.base}/browse/{issue['key']}",
            due_at=date_end_of_workday(f.get("duedate"), self.s),
            status=status,
            priority_raw=(f.get("priority") or {}).get("name", ""),
            requester=reporter.get("displayName", reporter_id),
            requester_role=classify_requester(reporter_id, ctx),
            tags=[t for t in [issue_type.lower(), *(f.get("labels") or [])] if t],
            source_updated_at=parse_iso(f.get("updated")),
        )
