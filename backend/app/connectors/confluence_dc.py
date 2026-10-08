"""Confluence Data Center on-prem qua REST API (CQL search).

Lấy 2 nhóm: trang có @mention người dùng (7 ngày) và trang người dùng đang
watch vừa được cập nhật (2 ngày). Xác thực bằng PAT của service account chỉ đọc.
"""
from __future__ import annotations

import logging
from datetime import datetime

import httpx

from app.connectors.base import Connector, ConnectorError, ItemIn, UserContext
from app.connectors.http import client, parse_iso
from app.core.config import Settings

log = logging.getLogger(__name__)


def _cql_quote(value: str) -> str:
    return '"' + value.replace('"', '\\"') + '"'


class ConfluenceDcConnector(Connector):
    source = "confluence"

    def __init__(self, settings: Settings, http: httpx.Client | None = None):
        self.s = settings
        self.base = settings.confluence_base_url.rstrip("/")
        self.http = http or client(settings, headers={"Authorization": f"Bearer {settings.confluence_token}"})

    def _search(self, cql: str) -> list[dict]:
        r = self.http.get(
            f"{self.base}/rest/api/content/search",
            params={"cql": cql, "limit": 50, "expand": "version,space"},
        )
        r.raise_for_status()
        return r.json().get("results", [])

    def fetch(self, ctx: UserContext, now: datetime) -> list[ItemIn]:
        u = _cql_quote(ctx.username)
        queries = [
            ("mention", f'type = page AND mention = {u} AND lastmodified >= now("-7d") ORDER BY lastmodified DESC'),
            ("watching", f'type = page AND watcher = {u} AND lastmodified >= now("-2d") ORDER BY lastmodified DESC'),
        ]
        out: dict[str, ItemIn] = {}
        try:
            for tag, cql in queries:
                for page in self._search(cql):
                    pid = str(page["id"])
                    if pid in out:
                        out[pid].tags.append(tag)
                        continue
                    version = page.get("version") or {}
                    by = (version.get("by") or {}).get("displayName", "")
                    space = (page.get("space") or {}).get("name", "")
                    out[pid] = ItemIn(
                        source="confluence",
                        external_id=pid,
                        kind="page",
                        title=page.get("title", ""),
                        preview=f"Không gian: {space}. Cập nhật bởi {by}." if by else f"Không gian: {space}.",
                        url=self.base + (page.get("_links") or {}).get("webui", ""),
                        requester=by,
                        tags=[tag],
                        source_updated_at=parse_iso(version.get("when")),
                        start_at=parse_iso(version.get("when")),
                    )
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            log.warning("Confluence lỗi cho %s: %s", ctx.username, exc)
            raise ConnectorError(f"Confluence: {exc}") from exc
        return list(out.values())
