from __future__ import annotations

from datetime import datetime, time, timezone

import httpx

from app.core.config import Settings


def client(settings: Settings, **kwargs) -> httpx.Client:
    """httpx client dùng CA nội bộ. Biến môi trường HTTPS_PROXY/NO_PROXY được tôn trọng
    (hệ thống on-prem nên nằm trong NO_PROXY, Graph đi qua egress proxy)."""
    return httpx.Client(verify=settings.tls_verify, timeout=httpx.Timeout(15.0, connect=5.0), **kwargs)


def parse_iso(value: str | None) -> datetime | None:
    """Parse ISO-8601 kể cả dạng Jira '2026-10-08T09:12:33.000+0700'."""
    if not value:
        return None
    v = value.strip()
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    if len(v) > 5 and v[-5] in "+-" and v[-3] != ":":  # +0700 -> +07:00
        v = v[:-2] + ":" + v[-2:]
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def date_end_of_workday(value: str | None, settings: Settings) -> datetime | None:
    """'2026-10-09' -> 17:30 giờ địa phương ngày đó (hạn chót theo ngày)."""
    if not value:
        return None
    try:
        d = datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    return datetime.combine(d, time(17, 30), tzinfo=settings.tz)


def epoch_ms(value) -> datetime | None:  # noqa: ANN001
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    except (TypeError, ValueError):
        return None
