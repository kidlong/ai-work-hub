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
