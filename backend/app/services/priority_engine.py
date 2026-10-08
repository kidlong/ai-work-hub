"""Chấm điểm ưu tiên 0-100 cho mỗi WorkItem, kèm lý do dễ hiểu (tiếng Việt).

Các yếu tố: áp lực thời gian (hạn/giờ họp), SLA, vai trò người yêu cầu,
độ ưu tiên gốc, trạng thái, tín hiệu email/chat. Có thể giải thích được
(explainable) để người dùng tin vào thứ tự sắp xếp.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


class Scorable(Protocol):
    kind: str
    source: str
    start_at: datetime | None
    end_at: datetime | None
    due_at: datetime | None
    sla_due_at: datetime | None
    status: str
    priority_raw: str
    requester_role: str
    is_unread: bool
    is_organizer: bool
    tags: list


@dataclass
class ScoreResult:
    score: float
    bucket: str
    reasons: list[str]


ROLE_WEIGHT = {
    "audit": (20, "Yêu cầu từ Kiểm toán/Tuân thủ"),
    "vip_customer": (18, "Khách hàng VIP"),
    "manager": (15, "Từ quản lý trực tiếp"),
    "external": (5, "Đối tác bên ngoài"),
}

PRIORITY_WEIGHT = {
    "highest": 20, "critical": 20, "urgent": 20, "blocker": 20, "khẩn cấp": 20,
    "high": 12, "cao": 12, "major": 12,
    "medium": 5, "normal": 5, "trung bình": 5,
}

DONE_STATUSES = {"done", "closed", "resolved", "cancelled", "đã đóng", "đã giải quyết", "hoàn thành"}


def _hours(delta_seconds: float) -> float:
    return delta_seconds / 3600.0


def _fmt_hours(h: float) -> str:
    minutes = max(1, round(h * 60))
    if minutes < 60:
        return f"{minutes} phút"
    hh, mm = divmod(minutes, 60)
    if hh >= 24:
        return f"{hh // 24} ngày"
    return f"{hh} giờ" if mm == 0 or hh >= 6 else f"{hh} giờ {mm} phút"


def bucket_of(score: float) -> str:
    if score >= 70:
        return "critical"
    if score >= 45:
        return "high"
    if score >= 20:
        return "normal"
    return "low"


def score_item(item: Scorable, now: datetime) -> ScoreResult:
    score = 0.0
    reasons: list[str] = []

    if (item.status or "").strip().lower() in DONE_STATUSES:
        return ScoreResult(0.0, "low", ["Đã hoàn thành"])

    # 1) Áp lực thời gian
    if item.kind == "meeting" and item.start_at:
        if item.end_at and item.end_at < now:
            return ScoreResult(0.0, "low", ["Cuộc họp đã kết thúc"])
        h = _hours((item.start_at - now).total_seconds())
        if h <= 0:
            score += 35
            reasons.append("Đang diễn ra")
        elif h <= 1:
            score += 35
            reasons.append(f"Bắt đầu sau {_fmt_hours(h)}")
        elif h <= 4:
            score += 22
            reasons.append(f"Bắt đầu sau {_fmt_hours(h)}")
        elif h <= 24:
            score += 12
            reasons.append("Diễn ra trong 24 giờ tới")
        if item.is_organizer:
            score += 5
            reasons.append("Bạn là người chủ trì")
    elif item.due_at:
        h = _hours((item.due_at - now).total_seconds())
        if h < 0:
            score += 40
            reasons.append(f"Quá hạn {_fmt_hours(-h)}")
        elif h <= 2:
            score += 35
            reasons.append(f"Đến hạn sau {_fmt_hours(h)}")
        elif h <= 24:
            score += 25
            reasons.append(f"Đến hạn sau {_fmt_hours(h)}")
        elif h <= 72:
            score += 12
            reasons.append("Đến hạn trong 3 ngày")

    # 2) SLA (SDP / Jira Service Management)
    if item.sla_due_at:
        h = _hours((item.sla_due_at - now).total_seconds())
        if h < 0:
            score += 45
            reasons.append(f"ĐÃ VI PHẠM SLA {_fmt_hours(-h)}")
        elif h <= 1:
            score += 35
            reasons.append(f"SLA còn {_fmt_hours(h)}")
        elif h <= 4:
            score += 25
            reasons.append(f"SLA còn {_fmt_hours(h)}")
        elif h <= 24:
            score += 10
            reasons.append("SLA đến hạn trong ngày")

    # 3) Người yêu cầu
    if item.requester_role in ROLE_WEIGHT:
        w, label = ROLE_WEIGHT[item.requester_role]
        score += w
        reasons.append(label)

    # 4) Độ ưu tiên gốc
    pr = (item.priority_raw or "").strip().lower()
    if pr in PRIORITY_WEIGHT and PRIORITY_WEIGHT[pr] > 0:
        score += PRIORITY_WEIGHT[pr]
        reasons.append(f"Ưu tiên {item.priority_raw}")

    # 5) Tín hiệu bổ sung
    tags = {t.lower() for t in (item.tags or [])}
    if (item.status or "").lower() == "blocked":
        score += 8
        reasons.append("Đang bị chặn (blocked) - cần gỡ vướng")
    if "incident" in tags:
        score += 6
        reasons.append("Sự cố (incident)")
    if "important" in tags:
        score += 8
        reasons.append("Đánh dấu quan trọng")
    if "flagged" in tags:
        score += 6
        reasons.append("Đã gắn cờ theo dõi")
    if "mention" in tags:
        score += 6
        reasons.append("Bạn được @nhắc tên")
    if item.is_unread and item.kind in ("email", "chat"):
        score += 4
        reasons.append("Chưa đọc")

    score = max(0.0, min(100.0, score))
    return ScoreResult(round(score, 1), bucket_of(score), reasons)
