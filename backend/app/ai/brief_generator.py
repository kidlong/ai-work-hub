"""Smart Summary: Morning Brief cho từng người.

Bước 1 (luôn chạy, không cần LLM): tính toán dữ kiện có cấu trúc — lịch hôm nay,
hạn chót, rủi ro, Top 3, khung giờ tập trung.
Bước 2 (nếu bật LLM): LLM viết lại phần diễn giải (headline, lý do, gợi ý) dựa trên
dữ kiện đã che PII. item_id do LLM trả về được kiểm tra để chống bịa.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from app.ai.llm_client import LlmClient
from app.ai.pii_masker import PiiMasker
from app.ai.prompts import BRIEF_SYSTEM
from app.services.calendar_insights import DayInsights

SOURCE_LABEL = {
    "exchange_calendar": "Lịch", "exchange_mail": "Email", "jira": "Jira",
    "confluence": "Confluence", "sdp": "SDP", "teams": "Teams",
}


def _hm(dt: datetime, tz) -> str:  # noqa: ANN001
    return dt.astimezone(tz).strftime("%H:%M")


def _greeting(name: str, now: datetime, tz) -> str:  # noqa: ANN001
    h = now.astimezone(tz).hour
    part = "buổi sáng" if h < 11 else ("buổi trưa" if h < 13 else ("buổi chiều" if h < 18 else "buổi tối"))
    first = name.split()[-1] if name else ""
    return f"Chào {part}, {first}!"


def build_facts(display_name: str, items: list, insights: DayInsights, now: datetime, tz) -> dict:  # noqa: ANN001
    local_today = now.astimezone(tz).date()
    end_of_day = datetime.combine(local_today, datetime.max.time(), tzinfo=tz)
    active = [i for i in items if not i.done_local]

    meetings = sorted(
        [i for i in active if i.kind == "meeting" and i.start_at and i.start_at.astimezone(tz).date() == local_today],
        key=lambda i: i.start_at,
    )
    conflict_ids = {c.a_id for c in insights.conflicts} | {c.b_id for c in insights.conflicts}
    schedule = [
        {
            "item_id": m.id,
            "time": f"{_hm(m.start_at, tz)}-{_hm(m.end_at, tz) if m.end_at else ''}",
            "title": m.title,
            "location": m.location,
            "note": "Trùng lịch" if m.id in conflict_ids else ("Bạn chủ trì" if m.is_organizer else ""),
        }
        for m in meetings
    ]
    due_today = sorted(
        [i for i in active if i.kind != "meeting" and i.due_at and now <= i.due_at <= end_of_day],
        key=lambda i: i.due_at,
    )
    overdue = [i for i in active if i.kind != "meeting" and i.due_at and i.due_at < now]
    sla_breached = [i for i in active if i.sla_due_at and i.sla_due_at < now]
    sla_risk = [i for i in active if i.sla_due_at and now <= i.sla_due_at <= now + timedelta(hours=4)]
    important_unread = [
        i for i in active
        if i.kind in ("email", "chat") and i.is_unread and i.requester_role in ("manager", "vip_customer", "audit")
    ]

    ranked = sorted([i for i in active if i.score > 0], key=lambda i: -i.score)
    top = [
        {
            "item_id": i.id,
            "title": i.title,
            "source": i.source,
            "url": i.url,
            "why": "; ".join(i.score_reasons[:2]) or "Ưu tiên cao",
        }
        for i in ranked[:3]
    ]

    risks: list[str] = []
    for c in insights.conflicts:
        risks.append(f"Trùng lịch {_hm(c.start, tz)}-{_hm(c.end, tz)}: \"{c.a_title}\" và \"{c.b_title}\".")
    for i in sla_breached:
        risks.append(f"{i.title} đã vi phạm SLA.")
    for i in overdue[:3]:
        risks.append(f"{i.title} đã quá hạn từ {i.due_at.astimezone(tz).strftime('%H:%M %d/%m')}.")
    if insights.overloaded:
        risks.append(f"Lịch họp chiếm {int(insights.load_ratio * 100)}% thời gian làm việc.")

    suggestions: list[str] = []
    if sla_breached or sla_risk:
        first = (sla_breached or sla_risk)[0]
        suggestions.append(f"Xử lý ngay {first.title} và cập nhật cho người yêu cầu.")
    if insights.conflicts:
        c = insights.conflicts[0]
        suggestions.append(f"Chọn một trong hai cuộc họp lúc {_hm(c.start, tz)} và báo người tổ chức cuộc còn lại.")
    if insights.focus_slots:
        f = insights.focus_slots[0]
        suggestions.append(f"Chặn {_hm(f.start, tz)}-{_hm(f.end, tz)} làm focus time cho việc ưu tiên số 1.")
    if important_unread:
        suggestions.append(f"Trả lời {len(important_unread)} tin nhắn quan trọng chưa đọc (quản lý/KH VIP/kiểm toán).")
    if due_today:
        suggestions.append(f"Hoàn tất {due_today[0].title} trước {_hm(due_today[0].due_at, tz)}.")

    parts = [f"{len(meetings)} cuộc họp"]
    if due_today:
        parts.append(f"{len(due_today)} việc đến hạn")
    if overdue:
        parts.append(f"{len(overdue)} việc quá hạn")
    if sla_breached:
        parts.append(f"{len(sla_breached)} ticket đã vi phạm SLA")
    elif sla_risk:
        parts.append(f"{len(sla_risk)} ticket sắp chạm SLA")
    headline = "Hôm nay bạn có " + ", ".join(parts) + "."

    return {
        "date": local_today.isoformat(),
        "greeting": _greeting(display_name, now, tz),
        "headline": headline,
        "top_priorities": top,
        "schedule": schedule,
        "deadlines": [
            {"item_id": i.id, "title": i.title, "due": _hm(i.due_at, tz), "source": i.source} for i in due_today
        ],
        "risks": risks[:5],
        "suggestions": suggestions[:4],
        "focus_slots": [f"{_hm(f.start, tz)}-{_hm(f.end, tz)}" for f in insights.focus_slots],
        "stats": {
            "meetings": len(meetings),
            "meeting_minutes": insights.meeting_minutes,
            "due_today": len(due_today),
            "overdue": len(overdue),
            "sla_breached": len(sla_breached),
            "sla_risk": len(sla_risk),
            "important_unread": len(important_unread),
        },
        "closing": "Chúc bạn một ngày làm việc hiệu quả!",
    }


def _llm_context(facts: dict, items: list, masker: PiiMasker, tz) -> str:  # noqa: ANN001
    candidates = sorted([i for i in items if not i.done_local and i.score > 0], key=lambda i: -i.score)[:12]
    lines = []
    for i in candidates:
        due = i.due_at or i.sla_due_at or i.start_at
        lines.append({
            "item_id": i.id,
            "nguon": SOURCE_LABEL.get(i.source, i.source),
            "tieu_de": masker.mask(i.title),
            "thoi_diem": due.astimezone(tz).strftime("%H:%M %d/%m") if due else None,
            "trang_thai": i.status,
            "diem_uu_tien": i.score,
            "ly_do": i.score_reasons[:3],
            "noi_dung": masker.mask((i.preview or "")[:200]),
        })
    payload = {
        "lich_hom_nay": [{**s, "title": masker.mask(s["title"])} for s in facts["schedule"]],
        "rui_ro_da_phat_hien": [masker.mask(r) for r in facts["risks"]],
        "khung_gio_tap_trung": facts["focus_slots"],
        "thong_ke": facts["stats"],
        "cac_muc_uu_tien_cao": lines,
    }
    return json.dumps(payload, ensure_ascii=False)


def generate_brief(display_name: str, items: list, insights: DayInsights, now: datetime, tz,  # noqa: ANN001
                   llm: LlmClient | None = None) -> tuple[dict, str]:
    facts = build_facts(display_name, items, insights, now, tz)
    llm = llm or LlmClient()
    if not llm.enabled:
        return facts, "fallback"

    masker = PiiMasker()
    ctx = _llm_context(facts, items, masker, tz)
    out = llm.chat_json(BRIEF_SYSTEM, "Dữ liệu công việc hôm nay (JSON):\n" + ctx)
    if not out:
        return facts, "fallback"

    valid_ids = {i.id: i for i in items}
    brief = dict(facts)
    if isinstance(out.get("headline"), str) and out["headline"].strip():
        brief["headline"] = masker.unmask(out["headline"].strip())
    tops = []
    for t in out.get("top_priorities") or []:
        try:
            iid = int(t.get("item_id"))
        except (TypeError, ValueError, AttributeError):
            continue
        it = valid_ids.get(iid)
        if it is None or any(x["item_id"] == iid for x in tops):
            continue
        tops.append({"item_id": iid, "title": it.title, "source": it.source, "url": it.url,
                     "why": masker.unmask(str(t.get("why", ""))) or "Ưu tiên cao"})
    if len(tops) >= 2:
        brief["top_priorities"] = tops[:3]
    for key, limit in (("risks", 5), ("suggestions", 4)):
        vals = [masker.unmask(str(v)) for v in (out.get(key) or []) if str(v).strip()]
        if vals:
            brief[key] = vals[:limit]
    if isinstance(out.get("closing"), str) and out["closing"].strip():
        brief["closing"] = masker.unmask(out["closing"].strip())
    return brief, "llm"
