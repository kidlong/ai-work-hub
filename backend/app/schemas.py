from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

_HM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class LoginIn(BaseModel):
    username: str = Field(min_length=2, max_length=128)
    password: str = Field(min_length=1, max_length=256)


class RefreshIn(BaseModel):
    refresh_token: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    username: str
    email: str
    display_name: str
    title: str
    department: str
    last_sync_at: datetime | None


class WorkItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    source: str
    kind: str
    title: str
    preview: str
    url: str
    start_at: datetime | None
    end_at: datetime | None
    due_at: datetime | None
    sla_due_at: datetime | None
    status: str
    priority_raw: str
    requester: str
    requester_role: str
    participants: list[str]
    location: str
    is_unread: bool
    is_organizer: bool
    tags: list[str]
    score: float
    bucket: str
    score_reasons: list[str]
    done_local: bool
    snoozed_until: datetime | None


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    work_item_id: int | None
    kind: str
    severity: str
    title: str
    body: str
    fire_at: datetime
    status: str


class FocusSlotOut(BaseModel):
    start: datetime
    end: datetime
    minutes: int


class ConflictOut(BaseModel):
    a_id: int | None
    b_id: int | None
    a_title: str
    b_title: str
    start: datetime
    end: datetime


class InsightOut(BaseModel):
    day: str
    meeting_count: int
    meeting_minutes: int
    load_ratio: float
    overloaded: bool
    conflicts: list[ConflictOut]
    back_to_back: list[list[str]]
    focus_slots: list[FocusSlotOut]


class TodayOut(BaseModel):
    greeting: str
    user: UserOut
    stats: dict
    top_priorities: list[WorkItemOut]
    next_meetings: list[WorkItemOut]
    deadlines: list[WorkItemOut]
    insights: InsightOut
    pending_alerts: int
    brief_ready: bool


class BriefOut(BaseModel):
    date: str
    generated_by: str
    created_at: datetime
    content: dict


class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=500)


class AskOut(BaseModel):
    question: str
    answer: str
    generated_by: str
    items: list[WorkItemOut]


class SnoozeIn(BaseModel):
    minutes: int = Field(ge=5, le=60 * 24 * 7)


class SettingsIO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    brief_time: str = "07:30"
    quiet_start: str = "21:00"
    quiet_end: str = "07:00"
    meeting_lead_minutes: int = Field(default=15, ge=0, le=120)
    vip_senders: list[str] = Field(default_factory=list, max_length=200)
    enabled_sources: list[str] = Field(default_factory=list)
    focus_time_suggestions: bool = True
    live_sim_enabled: bool = True

    @field_validator("brief_time", "quiet_start", "quiet_end")
    @classmethod
    def _hm(cls, v: str) -> str:
        if not _HM.match(v):
            raise ValueError("Định dạng giờ phải là HH:MM")
        return v


class DeviceIn(BaseModel):
    token: str = Field(min_length=10, max_length=512)
    platform: str = Field(pattern="^(android|ios)$")


class LiveEventOut(BaseModel):
    id: int
    type: str
    scenario: str
    source: str
    severity: str
    title: str
    work_item_id: int | None
    created_at: datetime


class EventsOut(BaseModel):
    events: list[LiveEventOut]
    latest_id: int


class SimEmitIn(BaseModel):
    scenario: str | None = Field(default=None, max_length=48)


class ScenarioOut(BaseModel):
    key: str
    label: str
