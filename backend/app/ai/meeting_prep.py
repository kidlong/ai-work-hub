"""Meeting Prep: trước giờ họp, gom tài liệu & việc liên quan và gợi ý nội dung chuẩn bị."""
from __future__ import annotations

import json
import re
from datetime import datetime

from app.ai.llm_client import LlmClient
from app.ai.pii_masker import PiiMasker
from app.ai.prompts import PREP_SYSTEM
from app.ai.textutil import JIRA_KEY_RE, fold, keywords


def _first_sentence(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    m = re.split(r"(?<=[.!?])\s", text, maxsplit=1)
    return m[0][:300]


def find_related(meeting, items: list) -> list[dict]:  # noqa: ANN001
    text = f"{meeting.title} {meeting.preview}"
    keys = set(JIRA_KEY_RE.findall(text))
    mtokens = keywords(meeting.title, min_len=4)
    folded_text = fold(text)
    participants = {p.lower() for p in (meeting.participants or [])}

    related: list[dict] = []
    for it in items:
        if it.id == meeting.id or it.kind == "meeting" or it.done_local:
            continue
        reason = None
        ext_key = it.external_id if it.source == "jira" else ""
        if ext_key and ext_key in keys:
            reason = f"Được nêu trong nội dung cuộc họp ({ext_key})"
        elif it.source == "confluence" and len(fold(it.title)) > 8 and fold(it.title) in folded_text:
            reason = "Tài liệu được dẫn trong thư mời"
        else:
            overlap = mtokens & keywords(it.title, min_len=4)
            if len(overlap) >= 2:
                reason = "Cùng chủ đề: " + ", ".join(sorted(overlap)[:3])
            elif it.requester and it.requester.lower() in participants and it.kind in ("email", "task", "ticket"):
                reason = "Việc còn tồn với người dự họp"
        if reason:
            related.append({
                "item_id": it.id, "title": it.title, "source": it.source, "url": it.url,
                "status": it.status, "reason": reason, "score": it.score,
            })
    related.sort(key=lambda r: -r["score"])
    return related[:8]


def build_prep(meeting, items: list, now: datetime, tz, llm: LlmClient | None = None) -> dict:  # noqa: ANN001
    related = find_related(meeting, items)
    minutes_to_start = int((meeting.start_at - now).total_seconds() // 60) if meeting.start_at else None
    talking = []
    for r in related[:4]:
        status = f" (trạng thái: {r['status']})" if r["status"] else ""
        talking.append(f"Chuẩn bị cập nhật về {r['title']}{status}.")
    if meeting.is_organizer:
        talking.insert(0, "Bạn chủ trì: chốt mục tiêu, thời lượng từng phần và người ghi biên bản.")
    prep = {
        "meeting": {
            "item_id": meeting.id,
            "title": meeting.title,
            "start": meeting.start_at.astimezone(tz).strftime("%H:%M %d/%m") if meeting.start_at else None,
            "end": meeting.end_at.astimezone(tz).strftime("%H:%M") if meeting.end_at else None,
            "location": meeting.location,
            "url": meeting.url,
            "organizer": meeting.requester,
            "is_organizer": meeting.is_organizer,
            "attendees": meeting.participants or [],
            "minutes_to_start": minutes_to_start,
            "ended": bool(meeting.end_at and meeting.end_at < now),
        },
        "purpose": _first_sentence(meeting.preview) or "Thư mời không có mô tả. Hãy hỏi người tổ chức về mục tiêu cuộc họp.",
        "related": related,
        "talking_points": talking or ["Xem lại thư mời và chuẩn bị câu hỏi về mục tiêu cuộc họp."],
        "questions": [],
        "generated_by": "fallback",
    }

    llm = llm or LlmClient()
    if not llm.enabled:
        return prep
    masker = PiiMasker()
    ctx = {
        "cuoc_hop": {
            "tieu_de": masker.mask(meeting.title),
            "noi_dung": masker.mask((meeting.preview or "")[:800]),
            "thoi_gian": prep["meeting"]["start"],
            "ban_chu_tri": meeting.is_organizer,
            "so_nguoi_du": len(meeting.participants or []),
        },
        "cac_muc_lien_quan": [
            {"tieu_de": masker.mask(r["title"]), "nguon": r["source"], "trang_thai": r["status"], "ly_do": r["reason"]}
            for r in related
        ],
    }
    out = llm.chat_json(PREP_SYSTEM, json.dumps(ctx, ensure_ascii=False))
    if out:
        if isinstance(out.get("purpose"), str) and out["purpose"].strip():
            prep["purpose"] = masker.unmask(out["purpose"].strip())
        tp = [masker.unmask(str(t)) for t in (out.get("talking_points") or []) if str(t).strip()]
        if tp:
            prep["talking_points"] = tp[:5]
        prep["questions"] = [masker.unmask(str(q)) for q in (out.get("questions") or []) if str(q).strip()][:3]
        prep["generated_by"] = "llm"
    return prep
