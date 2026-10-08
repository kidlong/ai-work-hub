"""Smart Notification engine: sinh nhắc việc từ WorkItem đã chấm điểm.

Quy tắc:
- Họp: nhắc trước N phút (mặc định 15).
- Việc có hạn: nhắc trước 24h và 2h; quá hạn -> nhắc ngay (1 lần/ngày).
- SLA: cảnh báo trước 2h; vi phạm -> nhắc ngay mức critical.
- Mail/chat chưa đọc từ quản lý / KH VIP / kiểm toán -> nhắc ngay.
- @mention trên Confluence/Teams -> nhắc (info).
- Họp trùng, ngày quá tải -> nhắc ngay để kịp sắp xếp.
Sau đó áp giờ yên lặng (trừ critical) và gom nhóm chống spam.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Protocol

from app.services.calendar_insights import DayInsights

HORIZON = timedelta(hours=36)
STALE_GRACE = timedelta(minutes=10)
DIGEST_WINDOW_MIN = 10
DIGEST_THRESHOLD = 3


class AlertItem(Protocol):
    id: int | None
    kind: str
    source: str
    title: str
    start_at: datetime | None
    end_at: datetime | None
    due_at: datetime | None
    sla_due_at: datetime | None
    requester: str
    requester_role: str
    is_unread: bool
    is_organizer: bool
    tags: list
    bucket: str
    location: str
    done_local: bool
    snoozed_until: datetime | None


@dataclass
class AlertRules:
    meeting_lead_minutes: int = 15
    quiet_start: str = "21:00"
    quiet_end: str = "07:00"


@dataclass
class AlertDraft:
    kind: str
    severity: str
    title: str
    body: str
    fire_at: datetime
    group_key: str
    work_item_id: int | None = None


SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}
IMPORTANT_ROLES = {"manager", "vip_customer", "audit"}
ROLE_LABEL = {"manager": "quản lý", "vip_customer": "KH VIP", "audit": "Kiểm toán/Tuân thủ"}


def _hm(dt: datetime, tz) -> str:  # noqa: ANN001
    return dt.astimezone(tz).strftime("%H:%M")


def _parse_hm(v: str) -> time:
    h, m = v.split(":")
    return time(int(h), int(m))


def in_quiet_hours(dt: datetime, rules: AlertRules, tz) -> bool:  # noqa: ANN001
    t = dt.astimezone(tz).time()
    qs, qe = _parse_hm(rules.quiet_start), _parse_hm(rules.quiet_end)
    if qs == qe:
        return False
    if qs < qe:
        return qs <= t < qe
    return t >= qs or t < qe


def next_quiet_end(dt: datetime, rules: AlertRules, tz) -> datetime:  # noqa: ANN001
    local = dt.astimezone(tz)
    qe = _parse_hm(rules.quiet_end)
    candidate = local.replace(hour=qe.hour, minute=qe.minute, second=0, microsecond=0)
    if candidate <= local:
        candidate += timedelta(days=1)
    return candidate


def _item_alerts(it: AlertItem, rules: AlertRules, now: datetime, tz) -> list[AlertDraft]:  # noqa: ANN001
    out: list[AlertDraft] = []
    today = now.astimezone(tz).strftime("%Y%m%d")
    iid = it.id

    if it.kind == "meeting" and it.start_at:
        fire = it.start_at - timedelta(minutes=rules.meeting_lead_minutes)
        sev = "warning" if (it.is_organizer or it.requester_role in IMPORTANT_ROLES) else "info"
        where = f" tại {it.location}" if it.location else ""
        out.append(AlertDraft(
            "meeting_soon", sev, f"Họp lúc {_hm(it.start_at, tz)}: {it.title}",
            f"Bắt đầu sau {rules.meeting_lead_minutes} phút{where}. Mở Meeting Prep để xem tài liệu liên quan.",
            fire, f"meeting:{iid}:{it.start_at.isoformat()}", iid,
        ))

    if it.due_at and it.kind != "meeting":
        for hours, sev in ((24, "info"), (2, "warning")):
            fire = it.due_at - timedelta(hours=hours)
            if fire >= now - STALE_GRACE:
                out.append(AlertDraft(
                    "due_soon", sev, f"Sắp đến hạn ({_hm(it.due_at, tz)}): {it.title}",
                    f"Còn {hours} giờ trước hạn chót." if hours >= 24 else "Còn khoảng 2 giờ trước hạn chót.",
                    fire, f"due{hours}:{iid}:{it.due_at.isoformat()}", iid,
                ))
        if it.due_at < now:
            sev = "critical" if it.bucket == "critical" else "warning"
            out.append(AlertDraft(
                "overdue", sev, f"Quá hạn: {it.title}",
                f"Hạn chót {it.due_at.astimezone(tz).strftime('%H:%M %d/%m')} đã qua. Cập nhật tiến độ hoặc xin gia hạn.",
                now, f"overdue:{iid}:{today}", iid,
            ))

    if it.sla_due_at:
        warn = it.sla_due_at - timedelta(hours=2)
        if it.sla_due_at >= now:
            out.append(AlertDraft(
                "sla_risk", "warning", f"SLA sắp vi phạm ({_hm(it.sla_due_at, tz)}): {it.title}",
                "Còn dưới 2 giờ trước hạn SLA. Cân nhắc escalate nếu chưa xử lý được.",
                max(warn, now), f"sla_risk:{iid}:{it.sla_due_at.isoformat()}", iid,
            ))
        else:
            out.append(AlertDraft(
                "sla_breached", "critical", f"ĐÃ VI PHẠM SLA: {it.title}",
                "Ticket đã quá hạn SLA. Cần cập nhật cho người yêu cầu và báo cáo quản lý.",
                now, f"sla_breached:{iid}:{it.sla_due_at.isoformat()}", iid,
            ))

    already_overdue = any(d.kind == "overdue" for d in out)
    if it.kind in ("email", "chat") and it.is_unread and it.requester_role in IMPORTANT_ROLES and not already_overdue:
        label = ROLE_LABEL[it.requester_role]
        out.append(AlertDraft(
            "important_message", "warning", f"Tin nhắn từ {label}: {it.title}",
            f"Người gửi: {it.requester}.", it.start_at or now, f"msg:{iid}", iid,
        ))
    elif "mention" in {t.lower() for t in (it.tags or [])} and it.kind in ("page", "chat"):
        out.append(AlertDraft(
            "mention", "info", f"Bạn được nhắc tên: {it.title}", f"Nguồn: {it.source}.",
            it.start_at or now, f"mention:{iid}", iid,
        ))
    return out


def _insight_alerts(ins: DayInsights, now: datetime, tz) -> list[AlertDraft]:  # noqa: ANN001
    out: list[AlertDraft] = []
    day = ins.day.strftime("%Y%m%d")
    for c in ins.conflicts:
        if c.end < now:
            continue
        out.append(AlertDraft(
            "conflict", "warning", f"Trùng lịch {_hm(c.start, tz)}-{_hm(c.end, tz)}",
            f"\"{c.a_title}\" trùng với \"{c.b_title}\". Hãy chọn tham dự một cuộc hoặc đề nghị dời lịch.",
            now, f"conflict:{c.a_id}:{c.b_id}:{day}", c.b_id,
        ))
    if ins.overloaded:
        out.append(AlertDraft(
            "overload", "info", f"Ngày {ins.day.strftime('%d/%m')} có {ins.meeting_count} cuộc họp ({ins.meeting_minutes // 60}h{ins.meeting_minutes % 60:02d})",
            "Lịch họp chiếm phần lớn thời gian làm việc. Cân nhắc từ chối các cuộc họp không bắt buộc.",
            now, f"overload:{day}", None,
        ))
    return out


def apply_quiet_hours(drafts: list[AlertDraft], rules: AlertRules, tz) -> list[AlertDraft]:  # noqa: ANN001
    for d in drafts:
        if d.severity != "critical" and in_quiet_hours(d.fire_at, rules, tz):
            d.fire_at = next_quiet_end(d.fire_at, rules, tz)
    return drafts


def digest(drafts: list[AlertDraft], tz) -> list[AlertDraft]:  # noqa: ANN001
    """Gom các nhắc 'info' rơi vào cùng cửa sổ 10 phút thành 1 bản tin để tránh spam."""
    buckets: dict[datetime, list[AlertDraft]] = defaultdict(list)
    keep: list[AlertDraft] = []
    for d in drafts:
        if d.severity == "info" and d.kind != "meeting_soon":
            b = d.fire_at.replace(second=0, microsecond=0)
            b = b - timedelta(minutes=b.minute % DIGEST_WINDOW_MIN)
            buckets[b].append(d)
        else:
            keep.append(d)
    for b, group in buckets.items():
        if len(group) > DIGEST_THRESHOLD:
            titles = "; ".join(g.title for g in group[:5])
            keep.append(AlertDraft(
                "digest", "info", f"Bạn có {len(group)} cập nhật mới",
                titles + ("…" if len(group) > 5 else ""),
                b, "digest:" + ",".join(sorted(g.group_key for g in group))[:200], None,
            ))
        else:
            keep.extend(group)
    return keep


def generate_alerts(
    items: list[AlertItem],
    insights: list[DayInsights],
    rules: AlertRules,
    now: datetime,
    tz,  # noqa: ANN001
) -> list[AlertDraft]:
    drafts: list[AlertDraft] = []
    for it in items:
        if it.done_local:
            continue
        for d in _item_alerts(it, rules, now, tz):
            if it.snoozed_until and d.fire_at < it.snoozed_until:
                d.fire_at = it.snoozed_until
            drafts.append(d)
    for ins in insights:
        drafts.extend(_insight_alerts(ins, now, tz))

    drafts = [d for d in drafts if now - STALE_GRACE <= d.fire_at <= now + HORIZON
              or d.kind in ("overdue", "sla_breached", "important_message", "conflict")]
    # Tin nhắn quá cũ (> 1 ngày) không nhắc nữa
    drafts = [d for d in drafts if not (d.kind in ("important_message", "mention") and d.fire_at < now - timedelta(days=1))]
    for d in drafts:
        if d.fire_at < now:
            d.fire_at = now
    drafts = apply_quiet_hours(drafts, rules, tz)
    drafts = digest(drafts, tz)
    drafts.sort(key=lambda d: (d.fire_at, -SEVERITY_RANK[d.severity]))
    return drafts
