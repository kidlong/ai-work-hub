"""ManageEngine ServiceDesk Plus on-prem qua REST API v3.

Lấy các request đang mở mà người dùng là technician. `due_by_time` của SDP
chính là hạn SLA giải quyết -> map sang sla_due_at để SLA Guard theo dõi.
Xác thực bằng technician API key (header `authtoken`) của tài khoản tích hợp chỉ đọc.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

import httpx

from app.connectors.base import Connector, ConnectorError, ItemIn, UserContext, classify_requester
from app.connectors.http import client, epoch_ms
from app.core.config import Settings

log = logging.getLogger(__name__)

CLOSED_STATUSES = ["Closed", "Resolved", "Cancelled", "Đã đóng", "Đã giải quyết"]


class SdpConnector(Connector):
    source = "sdp"

    def __init__(self, settings: Settings, http: httpx.Client | None = None):
        self.s = settings
        self.base = settings.sdp_base_url.rstrip("/")
        self.http = http or client(
            settings,
            headers={"authtoken": settings.sdp_authtoken, "Accept": "application/vnd.manageengine.sdp.v3+json"},
        )

    def fetch(self, ctx: UserContext, now: datetime) -> list[ItemIn]:
        input_data = {
            "list_info": {
                "row_count": 100,
                "start_index": 1,
                "sort_field": "due_by_time",
                "sort_order": "asc",
                "search_criteria": [
                    {"field": "technician.email_id", "condition": "is", "value": ctx.email},
                    {
                        "field": "status.name",
                        "condition": "is not",
                        "values": CLOSED_STATUSES,
                        "logical_operator": "AND",
                    },
                ],
            }
        }
        try:
            r = self.http.get(f"{self.base}/api/v3/requests", params={"input_data": json.dumps(input_data)})
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("SDP lỗi cho %s: %s", ctx.username, exc)
            raise ConnectorError(f"SDP: {exc}") from exc
        return [self._map(req, ctx) for req in data.get("requests", [])]

    def _map(self, req: dict, ctx: UserContext) -> ItemIn:
        requester = req.get("requester") or {}
        req_id = str(req.get("id"))
        tags = ["incident" if (req.get("request_type") or {}).get("name", "").lower() == "incident" else "request"]
        if req.get("is_overdue"):
            tags.append("overdue")
        return ItemIn(
            source="sdp",
            external_id=req_id,
            kind="ticket",
            title=f"[SDP#{req.get('display_id', req_id)}] {req.get('subject', '')}",
            preview=(req.get("short_description") or "")[:600],
            url=f"{self.base}/WorkOrder.do?woMode=viewWO&woID={req_id}",
            sla_due_at=epoch_ms((req.get("due_by_time") or {}).get("value")),
            status=(req.get("status") or {}).get("name", ""),
            priority_raw=(req.get("priority") or {}).get("name", ""),
            requester=requester.get("name", ""),
            requester_role=classify_requester(requester.get("email_id", ""), ctx),
            tags=tags,
            start_at=epoch_ms((req.get("created_time") or {}).get("value")),
            source_updated_at=epoch_ms((req.get("last_updated_time") or {}).get("value")),
        )
