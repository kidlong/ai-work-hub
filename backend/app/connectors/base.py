from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class UserContext:
    username: str
    email: str
    display_name: str
    manager_email: str = ""
    vip_senders: list[str] = field(default_factory=list)
    internal_domain: str = "bank.local"


@dataclass
class ItemIn:
    """Bản ghi đã chuẩn hoá từ một hệ thống nguồn (chưa chấm điểm)."""

    source: str
    external_id: str
    kind: str
    title: str
    preview: str = ""
    url: str = ""
    start_at: datetime | None = None
    end_at: datetime | None = None
    due_at: datetime | None = None
    sla_due_at: datetime | None = None
    status: str = ""
    priority_raw: str = ""
    requester: str = ""
    requester_role: str = "peer"
    participants: list[str] = field(default_factory=list)
    location: str = ""
    is_unread: bool = False
    is_organizer: bool = False
    tags: list[str] = field(default_factory=list)
    source_updated_at: datetime | None = None


class ConnectorError(Exception):
    pass


class Connector(ABC):
    """Mỗi hệ thống nguồn là một connector. Connector chỉ ĐỌC dữ liệu."""

    source: str

    @abstractmethod
    def fetch(self, ctx: UserContext, now: datetime) -> list[ItemIn]:
        """Lấy dữ liệu liên quan tới người dùng. Lỗi mạng/quyền -> raise ConnectorError."""


_AUDIT_RE = re.compile(r"(kiem\s*toan|kiểm\s*toán|audit|compliance|tuân\s*thủ|thanh\s*tra|ttgs|ksnb)", re.I)


def classify_requester(identity: str, ctx: UserContext) -> str:
    """Phân loại người yêu cầu để engine ưu tiên: manager | vip_customer | audit | external | peer."""
    ident = (identity or "").strip().lower()
    if not ident:
        return "peer"
    if ctx.manager_email and ident == ctx.manager_email.lower():
        return "manager"
    if any(ident == v.lower() or ident.endswith("@" + v.lower().lstrip("@")) for v in ctx.vip_senders):
        return "vip_customer"
    if _AUDIT_RE.search(ident):
        return "audit"
    if "@" in ident and not ident.endswith("@" + ctx.internal_domain):
        return "external"
    return "peer"
