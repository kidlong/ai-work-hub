"""Exchange Server on-prem qua EWS (Exchange Web Services) bằng thư viện exchangelib.

Mô hình truy cập: 1 service account có role ApplicationImpersonation, được giới hạn
bằng Management Scope chỉ gồm mailbox của nhóm người dùng được phép. Backend
impersonate từng mailbox để đọc lịch và hộp thư. Không ghi/sửa gì trong mailbox.

Thiết lập phía Exchange (ví dụ, chạy trên Exchange Management Shell):

    New-ManagementScope -Name "AIWorkHubScope" -RecipientRestrictionFilter {MemberOfGroup -eq "CN=AIWorkHub-Users,OU=Groups,DC=bank,DC=local"}
    New-ManagementRoleAssignment -Name "AIWorkHub-Impersonation" -Role ApplicationImpersonation `
        -User svc-aiworkhub -CustomRecipientWriteScope "AIWorkHubScope"
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from app.connectors.base import Connector, ConnectorError, ItemIn, UserContext, classify_requester
from app.core.config import Settings

log = logging.getLogger(__name__)

CALENDAR_DAYS_AHEAD = 7
MAIL_DAYS_BACK = 3
MAX_MAIL = 150


FLAG_STATUS_FLAGGED = 2  # PidTagFlagStatus: 1 = hoàn thành, 2 = đang gắn cờ
_props_registered = False


def _register_flag_properties() -> None:
    """EWS không trả cờ follow-up như field chuẩn trong exchangelib -> đọc qua MAPI extended property."""
    global _props_registered
    if _props_registered:
        return
    from exchangelib import ExtendedProperty, Message

    class FlagStatus(ExtendedProperty):
        property_tag = 0x1090  # PidTagFlagStatus
        property_type = "Integer"

    class TaskDueDate(ExtendedProperty):
        distinguished_property_set_id = "Task"
        property_id = 0x8105  # PidLidTaskDueDate
        property_type = "SystemTime"

    Message.register("flag_status", FlagStatus)
    Message.register("task_due_date", TaskDueDate)
    _props_registered = True


def _install_ca(ca_file: str) -> None:
    """Cho exchangelib tin CA nội bộ của ngân hàng."""
    import requests.adapters
    from exchangelib.protocol import BaseProtocol

    class RootCAAdapter(requests.adapters.HTTPAdapter):
        def cert_verify(self, conn, url, verify, cert):  # noqa: ANN001
            super().cert_verify(conn=conn, url=url, verify=ca_file, cert=cert)

    BaseProtocol.HTTP_ADAPTER_CLS = RootCAAdapter


def _owa_url(ews_url: str, item) -> str:  # noqa: ANN001
    qs = getattr(item, "web_client_read_form_query_string", None)
    if qs:
        return qs if qs.startswith("http") else ews_url.split("/EWS")[0] + "/owa/" + qs
    return ews_url.split("/EWS")[0] + "/owa/"


def _aware(dt) -> datetime | None:  # noqa: ANN001
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt if dt.tzinfo else None
    return None


class ExchangeEwsConnector:
    """Đọc lịch (exchange_calendar) và hộp thư (exchange_mail) trong một lần đăng nhập EWS."""

    def __init__(self, settings: Settings):
        self.s = settings
        _register_flag_properties()
        if settings.exchange_ca_cert_file:
            _install_ca(settings.exchange_ca_cert_file)

    def _account(self, ctx: UserContext):
        from exchangelib import BASIC, GSSAPI, IMPERSONATION, NTLM, Account, Configuration, Credentials

        # KERBEROS/GSSAPI cần thêm gói requests-gssapi và keytab cho service account
        auth = {"NTLM": NTLM, "KERBEROS": GSSAPI, "GSSAPI": GSSAPI, "BASIC": BASIC}.get(
            self.s.exchange_auth_type.upper(), NTLM)
        creds = Credentials(username=self.s.exchange_service_user, password=self.s.exchange_service_password)
        config = Configuration(service_endpoint=self.s.exchange_ews_url, credentials=creds, auth_type=auth)
        return Account(
            primary_smtp_address=ctx.email,
            config=config,
            autodiscover=False,
            access_type=IMPERSONATION,
        )

    def fetch_calendar(self, ctx: UserContext, now: datetime) -> list[ItemIn]:
        from exchangelib import EWSDateTime

        try:
            acc = self._account(ctx)
            start = EWSDateTime.from_datetime(now - timedelta(hours=2))
            end = EWSDateTime.from_datetime(now + timedelta(days=CALENDAR_DAYS_AHEAD))
            qs = acc.calendar.view(start=start, end=end).only(
                "subject", "start", "end", "location", "organizer", "required_attendees",
                "optional_attendees", "is_cancelled", "text_body", "last_modified_time",
                "web_client_read_form_query_string", "is_all_day",
            )
            out: list[ItemIn] = []
            for it in qs:
                if getattr(it, "is_cancelled", False):
                    continue
                organizer = getattr(getattr(it, "organizer", None), "email_address", "") or ""
                attendees = [
                    a.mailbox.email_address
                    for a in (list(it.required_attendees or []) + list(it.optional_attendees or []))
                    if getattr(a, "mailbox", None) and a.mailbox.email_address
                ]
                body = (it.text_body or "").strip()
                out.append(
                    ItemIn(
                        source="exchange_calendar",
                        external_id=f"{it.id}:{_aware(it.start).isoformat() if _aware(it.start) else ''}",
                        kind="meeting",
                        title=it.subject or "(Không tiêu đề)",
                        preview=body[:600],
                        url=_owa_url(self.s.exchange_ews_url, it),
                        start_at=_aware(it.start),
                        end_at=_aware(it.end),
                        requester=organizer,
                        requester_role=classify_requester(organizer, ctx),
                        participants=attendees[:50],
                        location=str(it.location or ""),
                        is_organizer=organizer.lower() == ctx.email.lower(),
                        tags=["teams"] if "teams.microsoft.com" in body.lower() else [],
                        source_updated_at=_aware(it.last_modified_time),
                    )
                )
            return out
        except Exception as exc:  # exchangelib ném nhiều loại lỗi khác nhau
            log.warning("EWS calendar lỗi cho %s: %s", ctx.username, exc)
            raise ConnectorError(f"Exchange calendar: {exc}") from exc

    def fetch_mail(self, ctx: UserContext, now: datetime) -> list[ItemIn]:
        from exchangelib import EWSDateTime

        try:
            acc = self._account(ctx)
            since = EWSDateTime.from_datetime(now - timedelta(days=MAIL_DAYS_BACK))
            qs = (
                acc.inbox.filter(datetime_received__gte=since)
                .only("subject", "sender", "datetime_received", "is_read", "importance",
                      "flag_status", "task_due_date", "text_body", "web_client_read_form_query_string")
                .order_by("-datetime_received")[:MAX_MAIL]
            )
            out: list[ItemIn] = []
            for m in qs:
                sender = getattr(getattr(m, "sender", None), "email_address", "") or ""
                flagged = getattr(m, "flag_status", None) == FLAG_STATUS_FLAGGED
                due = getattr(m, "task_due_date", None) if flagged else None
                due_at = None
                if due is not None:
                    # Hạn của cờ follow-up là theo ngày; quy về 17:30 giờ địa phương ngày đó
                    d = due.astimezone(self.s.tz) if getattr(due, "tzinfo", None) else due
                    due_at = datetime(d.year, d.month, d.day, 17, 30, tzinfo=self.s.tz)
                tags = []
                if m.importance == "High":
                    tags.append("important")
                if flagged:
                    tags.append("flagged")
                # Bỏ qua mail đã đọc, không cờ, không quan trọng -> giảm nhiễu
                if m.is_read and not flagged and "important" not in tags:
                    continue
                out.append(
                    ItemIn(
                        source="exchange_mail",
                        external_id=str(m.id),
                        kind="email",
                        title=m.subject or "(Không tiêu đề)",
                        preview=(m.text_body or "").strip()[:600],
                        url=_owa_url(self.s.exchange_ews_url, m),
                        start_at=_aware(m.datetime_received),
                        due_at=due_at,
                        requester=sender,
                        requester_role=classify_requester(sender, ctx),
                        is_unread=not m.is_read,
                        tags=tags,
                        source_updated_at=_aware(m.datetime_received),
                    )
                )
            return out
        except Exception as exc:
            log.warning("EWS mail lỗi cho %s: %s", ctx.username, exc)
            raise ConnectorError(f"Exchange mail: {exc}") from exc


class ExchangeCalendarConnector(Connector):
    source = "exchange_calendar"

    def __init__(self, ews: ExchangeEwsConnector):
        self.ews = ews

    def fetch(self, ctx: UserContext, now: datetime) -> list[ItemIn]:
        return self.ews.fetch_calendar(ctx, now)


class ExchangeMailConnector(Connector):
    source = "exchange_mail"

    def __init__(self, ews: ExchangeEwsConnector):
        self.ews = ews

    def fetch(self, ctx: UserContext, now: datetime) -> list[ItemIn]:
        return self.ews.fetch_mail(ctx, now)
