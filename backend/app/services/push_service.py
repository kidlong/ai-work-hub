"""Gửi push notification.

Mặc định (PUSH_INCLUDE_CONTENT=false) push KHÔNG chứa nội dung nghiệp vụ: chỉ báo
"Bạn có N nhắc việc mới" + alert_id. App mở ra sẽ tải chi tiết qua BFF (trong VPN/MDM).
Lý do: FCM/APNs là dịch vụ ngoài, không được để dữ liệu ngân hàng đi qua.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import Alert, Device

log = logging.getLogger("push")


class PushProvider:
    def send(self, token: str, platform: str, title: str, body: str, data: dict) -> bool:
        raise NotImplementedError


class LogPushProvider(PushProvider):
    def send(self, token: str, platform: str, title: str, body: str, data: dict) -> bool:
        log.info("PUSH -> %s…(%s) | %s | %s | %s", token[:8], platform, title, body, data)
        return True


class FcmPushProvider(PushProvider):
    """FCM HTTP v1. Cần `pip install .[fcm]` và service account JSON."""

    def __init__(self, s: Settings):
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2 import service_account

        creds = service_account.Credentials.from_service_account_file(
            s.fcm_service_account_file, scopes=["https://www.googleapis.com/auth/firebase.messaging"]
        )
        self.session = AuthorizedSession(creds)
        self.url = f"https://fcm.googleapis.com/v1/projects/{s.fcm_project_id}/messages:send"

    def send(self, token: str, platform: str, title: str, body: str, data: dict) -> bool:
        msg = {
            "message": {
                "token": token,
                "notification": {"title": title, "body": body},
                "data": {k: str(v) for k, v in data.items()},
                "android": {"priority": "high"},
                "apns": {"payload": {"aps": {"sound": "default"}}},
            }
        }
        r = self.session.post(self.url, json=msg, timeout=10)
        if r.status_code >= 400:
            log.warning("FCM lỗi %s: %s", r.status_code, r.text[:200])
            return False
        return True


_provider: PushProvider | None = None


def get_provider() -> PushProvider:
    global _provider
    if _provider is None:
        s = get_settings()
        _provider = FcmPushProvider(s) if s.push_provider == "fcm" else LogPushProvider()
    return _provider


def push_to_user(db: Session, username: str, title: str, body: str, data: dict) -> int:
    sent = 0
    for d in db.scalars(select(Device).where(Device.username == username)):
        try:
            if get_provider().send(d.token, d.platform, title, body, data):
                sent += 1
        except Exception as exc:  # không để lỗi push làm hỏng worker
            log.warning("Push lỗi cho %s: %s", username, exc)
    return sent


def dispatch_due_alerts(db: Session, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    s = get_settings()
    due = list(db.scalars(select(Alert).where(Alert.status.in_(["pending", "snoozed"]), Alert.fire_at <= now)))
    by_user: dict[str, list[Alert]] = {}
    for a in due:
        by_user.setdefault(a.username, []).append(a)
    for username, alerts in by_user.items():
        alerts.sort(key=lambda a: {"critical": 0, "warning": 1, "info": 2}[a.severity])
        if s.push_include_content and len(alerts) == 1:
            title, body = alerts[0].title, alerts[0].body
        else:
            crit = sum(1 for a in alerts if a.severity == "critical")
            title = "AI Work Hub"
            body = f"Bạn có {len(alerts)} nhắc việc mới" + (f" ({crit} khẩn)" if crit else "")
        push_to_user(db, username, title, body, {"type": "alerts", "alert_id": alerts[0].id, "count": len(alerts)})
        for a in alerts:
            a.status = "sent"
    db.commit()
    return len(due)
