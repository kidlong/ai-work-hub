"""Phân tích lịch: họp trùng, quá tải, chuỗi họp liên tục, khung giờ tập trung."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Protocol


class MeetingLike(Protocol):
    id: int | None
    title: str
    start_at: datetime | None
    end_at: datetime | None


@dataclass
class Conflict:
    a_id: int | None
    b_id: int | None
    a_title: str
    b_title: str
    start: datetime
    end: datetime


@dataclass
class FocusSlot:
    start: datetime
    end: datetime

    @property
    def minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


@dataclass
class DayInsights:
    day: date
    meeting_count: int = 0
    meeting_minutes: int = 0
    load_ratio: float = 0.0
    overloaded: bool = False
    conflicts: list[Conflict] = field(default_factory=list)
    back_to_back: list[list[str]] = field(default_factory=list)
    focus_slots: list[FocusSlot] = field(default_factory=list)


WORK_START = time(8, 0)
WORK_END = time(17, 30)
LUNCH = (time(12, 0), time(13, 0))
WORKDAY_MINUTES = 8.5 * 60 - 60
OVERLOAD_RATIO = 0.65
FOCUS_MIN_MINUTES = 90
BACK_TO_BACK_GAP = timedelta(minutes=10)


def analyze_day(meetings: list[MeetingLike], day: date, tz, now: datetime | None = None) -> DayInsights:  # noqa: ANN001
    """`now`: nếu truyền vào, khung giờ tập trung chỉ tính phần còn lại của ngày."""
    ws = datetime.combine(day, WORK_START, tzinfo=tz)
    we = datetime.combine(day, WORK_END, tzinfo=tz)
    ms = sorted(
        [m for m in meetings if m.start_at and m.end_at and m.start_at.astimezone(tz).date() == day],
        key=lambda m: m.start_at,
    )
    res = DayInsights(day=day, meeting_count=len(ms))

    # Tổng thời lượng (hợp các khoảng để không đếm trùng)
    merged: list[list[datetime]] = []
    for m in ms:
        s, e = max(m.start_at, ws), min(m.end_at, we)
        if e <= s:
            continue
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    res.meeting_minutes = int(sum((e - s).total_seconds() for s, e in merged) // 60)
    res.load_ratio = round(res.meeting_minutes / WORKDAY_MINUTES, 2)
    res.overloaded = res.load_ratio >= OVERLOAD_RATIO

    # Họp trùng
    for i, a in enumerate(ms):
        for b in ms[i + 1:]:
            if b.start_at >= a.end_at:
                break
            res.conflicts.append(
                Conflict(a.id, b.id, a.title, b.title, max(a.start_at, b.start_at), min(a.end_at, b.end_at))
            )

    # Chuỗi họp liên tục (>= 3 cuộc, nghỉ < 10 phút)
    chain: list = []
    for m in ms:
        if chain and m.start_at - chain[-1].end_at <= BACK_TO_BACK_GAP and m.start_at >= chain[-1].start_at:
            chain.append(m)
        else:
            if len(chain) >= 3:
                res.back_to_back.append([c.title for c in chain])
            chain = [m]
    if len(chain) >= 3:
        res.back_to_back.append([c.title for c in chain])

    # Khung giờ tập trung: khoảng trống >= 90 phút trong giờ làm, trừ giờ trưa
    busy = merged + [[datetime.combine(day, LUNCH[0], tzinfo=tz), datetime.combine(day, LUNCH[1], tzinfo=tz)]]
    busy.sort()
    cursor = max(ws, now) if now else ws
    for s, e in busy:
        if s - cursor >= timedelta(minutes=FOCUS_MIN_MINUTES):
            res.focus_slots.append(FocusSlot(cursor, s))
        cursor = max(cursor, e)
    if we - cursor >= timedelta(minutes=FOCUS_MIN_MINUTES):
        res.focus_slots.append(FocusSlot(cursor, we))
    return res
