"""Microsoft Teams qua Microsoft Graph (cloud).

Teams KHÔNG có bản on-prem. Lịch họp Teams đã có trong Exchange calendar (hybrid),
connector này chỉ bổ sung tin nhắn chat có @mention / 1-1 gần đây.

Yêu cầu: App registration trên Entra ID với application permission `Chat.Read.All`
(admin consent), egress tới graph.microsoft.com & login.microsoftonline.com qua proxy.
Mặc định TẮT (TEAMS_ENABLED=false).
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta

import httpx

from app.connectors.base import Connector, ConnectorError, ItemIn, UserContext
from app.connectors.http import client, parse_iso
from app.core.config import Settings

log = logging.getLogger(__name__)
_TAG_RE = re.compile(r"<[^>]+>")


class TeamsGraphConnector(Connector):
    source = "teams"

    def __init__(self, settings: Settings, http: httpx.Client | None = None):
        self.s = settings
        self.http = http or client(settings)
        self._token: str | None = None
        self._token_exp = 0.0

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        r = self.http.post(
            f"https://login.microsoftonline.com/{self.s.graph_tenant_id}/oauth2/v2.0/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.s.graph_client_id,
                "client_secret": self.s.graph_client_secret,
                "scope": "https://graph.microsoft.com/.default",
            },
        )
        r.raise_for_status()
        body = r.json()
        self._token = body["access_token"]
        self._token_exp = time.time() + int(body.get("expires_in", 3600))
        return self._token

    def fetch(self, ctx: UserContext, now: datetime) -> list[ItemIn]:
        try:
            token = self._get_token()
            r = self.http.get(
                f"https://graph.microsoft.com/v1.0/users/{ctx.email}/chats",
                params={"$expand": "lastMessagePreview", "$top": 50},
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            chats = r.json().get("value", [])
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            log.warning("Graph/Teams lỗi cho %s: %s", ctx.username, exc)
            raise ConnectorError(f"Teams: {exc}") from exc

        out: list[ItemIn] = []
        cutoff = now - timedelta(hours=24)
        for chat in chats:
            msg = chat.get("lastMessagePreview") or {}
            created = parse_iso(msg.get("createdDateTime"))
            if not created or created < cutoff:
                continue
            sender = ((msg.get("from") or {}).get("user") or {})
            sender_name = sender.get("displayName", "")
            if sender_name and sender_name == ctx.display_name:
                continue
            content = (msg.get("body") or {}).get("content", "")
            mentioned = "<at" in content
            if chat.get("chatType") != "oneOnOne" and not mentioned:
                continue
            text = _TAG_RE.sub("", content).strip()
            out.append(
                ItemIn(
                    source="teams",
                    external_id=f"{chat['id']}:{msg.get('id', '')}",
                    kind="chat",
                    title=f"{sender_name or 'Teams'}: {text[:80]}",
                    preview=text[:600],
                    url=chat.get("webUrl", ""),
                    start_at=created,
                    requester=sender_name,
                    requester_role="peer",  # Graph preview không trả email người gửi
                    is_unread=True,
                    tags=["mention"] if mentioned else ["direct"],
                    source_updated_at=created,
                )
            )
        return out
