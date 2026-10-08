"""Ask AI: hỏi đáp tự nhiên trên dữ liệu công việc của chính người dùng.

Retrieval đơn giản, chạy hoàn toàn trong backend: nhận diện ý định (nguồn, thời gian,
quá hạn, SLA, ưu tiên) + so khớp từ khoá không dấu. Sau đó LLM soạn câu trả lời từ
các mục tìm được (đã che PII). Không có LLM -> trả lời theo mẫu.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.ai.llm_client import LlmClient
from app.ai.pii_masker import PiiMasker
from app.ai.prompts import ASK_SYSTEM
from app.ai.textutil import fold, keywords

SOURCE_HINTS = {
    "jira": ["jira", "task", "story", "bug", "issue"],
    "sdp": ["sdp", "ticket", "su co", "incident", "yeu cau ho tro", "servicedesk", "service desk"],
    "exchange_mail": ["mail", "email", "thu "],
    "confluence": ["confluence", "wiki", "tai lieu", "trang "],
    "teams": ["teams", "chat", "tin nhan"],
}
# So khớp CÓ dấu: "họp" khác "hợp" (hợp đồng) nên không thể dùng bản bỏ dấu
RAW_HINTS = {"exchange_calendar": ["họp", "lịch", "meeting"]}
INTENT_WORDS = {
    "ticket", "jira", "sdp", "mail", "email", "hop", "lich", "meeting", "confluence", "wiki", "teams", "chat",
    "qua", "han", "sla", "tre", "uu", "tien", "quan", "trong", "gap", "nay", "mai", "tuan", "nao", "toi",
    "cua", "dang", "con", "nhung", "bao", "nhieu", "cac", "task", "issue", "viec",
    "sap", "vi", "pham", "gan", "chua", "doc", "nen", "lam", "truoc", "tiep", "theo", "chieu", "sang",
    "toi", "khong", "nao", "ticket", "yeu", "cau", "trang", "tai", "lieu", "tin", "nhan",
}


@dataclass
class AskIntent:
    sources: set[str] = field(default_factory=set)
    start: datetime | None = None
    end: datetime | None = None
    overdue: bool = False
    sla: bool = False
    sla_soon: bool = False
    priority: bool = False
    terms: set[str] = field(default_factory=set)


def parse_intent(question: str, now: datetime, tz) -> AskIntent:  # noqa: ANN001
    q = " " + fold(question) + " "
    it = AskIntent()
    for src, hints in SOURCE_HINTS.items():
        if any(h in q for h in hints):
            it.sources.add(src)
    raw = question.lower()
    for src, hints in RAW_HINTS.items():
        if any(h in raw for h in hints):
            it.sources.add(src)
    local = now.astimezone(tz)
    sod = local.replace(hour=0, minute=0, second=0, microsecond=0)
    if "sang mai" in q:
        it.start, it.end = sod + timedelta(days=1), sod + timedelta(days=1, hours=12)
    elif "chieu mai" in q:
        it.start, it.end = sod + timedelta(days=1, hours=12), sod + timedelta(days=1, hours=18)
    elif "ngay mai" in q or re.search(r"\bmai\b", q):
        it.start, it.end = sod + timedelta(days=1), sod + timedelta(days=2)
    elif "sang nay" in q:
        it.start, it.end = sod, sod + timedelta(hours=12)
    elif "chieu nay" in q:
        it.start, it.end = sod + timedelta(hours=12), sod + timedelta(hours=18)
    elif "toi nay" in q:
        it.start, it.end = sod + timedelta(hours=18), sod + timedelta(days=1)
    elif re.search(r"sap toi|tiep theo|sap dien ra", q):
        it.start, it.end = now, now + timedelta(hours=24)
    elif "hom nay" in q:
        it.start, it.end = sod, sod + timedelta(days=1)
    elif "tuan nay" in q:
        it.start = sod - timedelta(days=local.weekday())
        it.end = it.start + timedelta(days=7)
    elif "tuan sau" in q or "tuan toi" in q:
        it.start = sod - timedelta(days=local.weekday()) + timedelta(days=7)
        it.end = it.start + timedelta(days=7)
    it.overdue = bool(re.search(r"qua han|tre han|bi tre|overdue", q))
    it.sla = "sla" in q
    it.sla_soon = it.sla and bool(re.search(r"sap|gan|con bao lau", q))
    if it.sla and re.search(r"da vi pham|bi vi pham|qua sla", q):
        it.overdue = True
    it.priority = bool(re.search(r"uu tien|quan trong|gap|khan|lam gi truoc|top", q))
    it.terms = {t for t in keywords(question) if t not in INTENT_WORDS}
    return it


def _when(i) -> datetime | None:  # noqa: ANN001
    return i.start_at if i.kind == "meeting" else (i.due_at or i.sla_due_at or i.start_at)


def retrieve(items: list, intent: AskIntent, now: datetime, limit: int = 10) -> list:
    res = [i for i in items if not i.done_local]
    if intent.sources:
        res = [i for i in res if i.source in intent.sources]
    if intent.start and intent.end:
        res = [i for i in res if (w := _when(i)) and intent.start <= w < intent.end]
        # Cuộc họp đã kết thúc thì không còn ý nghĩa với câu hỏi "có họp gì"
        res = [i for i in res if not (i.kind == "meeting" and i.end_at and i.end_at < now)]
    if intent.overdue:
        res = [i for i in res if (i.due_at and i.due_at < now and i.kind != "meeting")
               or (i.sla_due_at and i.sla_due_at < now)]
    if intent.sla:
        res = [i for i in res if i.sla_due_at]
        if intent.sla_soon:
            res = [i for i in res if now <= i.sla_due_at <= now + timedelta(hours=24)]
    matched_terms = False
    if intent.terms:
        scored = []
        for i in res:
            hay = keywords(f"{i.title} {i.preview} {i.requester}")
            hit = len(intent.terms & hay)
            if hit:
                scored.append((hit, i))
        if scored:
            matched_terms = True
            res = [i for _, i in sorted(scored, key=lambda x: (-x[0], -x[1].score))]
        elif not (intent.sources or intent.start or intent.overdue or intent.sla or intent.priority):
            res = []
    if not matched_terms:
        if intent.sources == {"exchange_calendar"}:
            res.sort(key=lambda i: i.start_at or now)  # lịch họp: theo thứ tự thời gian
        elif intent.sla:
            res.sort(key=lambda i: i.sla_due_at)  # SLA: gần hạn nhất lên đầu
        else:
            res.sort(key=lambda i: -i.score)
    return res[:limit]


def _fallback_answer(question: str, found: list, intent: AskIntent, tz) -> str:  # noqa: ANN001
    if not found:
        return "Mình không tìm thấy mục công việc nào khớp với câu hỏi. Bạn thử diễn đạt khác hoặc nêu rõ nguồn (Jira, SDP, email, lịch họp)."
    lines = [f"Mình tìm thấy {len(found)} mục phù hợp:"]
    for i in found[:8]:
        w = _when(i)
        when = f" — {w.astimezone(tz).strftime('%H:%M %d/%m')}" if w else ""
        status = f" ({i.status})" if i.status else ""
        lines.append(f"• {i.title}{status}{when} [#{i.id}]")
    if intent.priority and found:
        lines.append(f"Nên làm trước: {found[0].title} [#{found[0].id}].")
    return "\n".join(lines)


def answer(question: str, items: list, now: datetime, tz, llm: LlmClient | None = None) -> dict:  # noqa: ANN001
    intent = parse_intent(question, now, tz)
    found = retrieve(items, intent, now)
    llm = llm or LlmClient()
    result = {
        "question": question,
        "items": [i.id for i in found],
        "generated_by": "fallback",
        "answer": _fallback_answer(question, found, intent, tz),
    }
    if not llm.enabled:
        return result

    masker = PiiMasker()
    ctx = [
        {
            "id": i.id,
            "nguon": i.source,
            "tieu_de": masker.mask(i.title),
            "thoi_diem": (_when(i).astimezone(tz).strftime("%H:%M %d/%m") if _when(i) else None),
            "trang_thai": i.status,
            "uu_tien": i.bucket,
            "noi_dung": masker.mask((i.preview or "")[:300]),
        }
        for i in found
    ]
    user_msg = (
        f"Bây giờ là {now.astimezone(tz).strftime('%H:%M %A %d/%m/%Y')}.\n"
        f"Câu hỏi: {masker.mask(question)}\n"
        f"Các mục công việc liên quan (JSON):\n{json.dumps(ctx, ensure_ascii=False)}"
    )
    text = llm.chat(ASK_SYSTEM, user_msg, temperature=0.1, max_tokens=700)
    if text:
        result["answer"] = masker.unmask(text.strip())
        result["generated_by"] = "llm"
    return result
