from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base, UTCDateTime


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(128), primary_key=True)
    email: Mapped[str] = mapped_column(String(256))
    display_name: Mapped[str] = mapped_column(String(256))
    title: Mapped[str] = mapped_column(String(256), default="")
    department: Mapped[str] = mapped_column(String(256), default="")
    manager_email: Mapped[str] = mapped_column(String(256), default="")
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class UserSettings(Base):
    __tablename__ = "user_settings"

    username: Mapped[str] = mapped_column(ForeignKey("users.username"), primary_key=True)
    brief_time: Mapped[str] = mapped_column(String(5), default="07:30")
    quiet_start: Mapped[str] = mapped_column(String(5), default="21:00")
    quiet_end: Mapped[str] = mapped_column(String(5), default="07:00")
    meeting_lead_minutes: Mapped[int] = mapped_column(Integer, default=15)
    vip_senders: Mapped[list] = mapped_column(JSON, default=list)
    enabled_sources: Mapped[list] = mapped_column(
        JSON,
        default=lambda: ["exchange_mail", "exchange_calendar", "jira", "confluence", "sdp", "teams"],
    )
    focus_time_suggestions: Mapped[bool] = mapped_column(Boolean, default=True)


class WorkItem(Base):
    """Mô hình hợp nhất cho mọi thứ cần làm/cần biết từ các hệ thống nguồn."""

    __tablename__ = "work_items"
    __table_args__ = (
        UniqueConstraint("username", "source", "external_id", name="uq_item_source"),
        Index("ix_items_user_score", "username", "score"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(ForeignKey("users.username"), index=True)
    source: Mapped[str] = mapped_column(String(32))  # exchange_mail | exchange_calendar | teams | jira | confluence | sdp
    external_id: Mapped[str] = mapped_column(String(512))
    kind: Mapped[str] = mapped_column(String(32))  # email | meeting | task | ticket | page | chat
    title: Mapped[str] = mapped_column(String(1024))
    preview: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(String(2048), default="")
    start_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    end_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    sla_due_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(64), default="")
    priority_raw: Mapped[str] = mapped_column(String(64), default="")
    requester: Mapped[str] = mapped_column(String(256), default="")
    requester_role: Mapped[str] = mapped_column(String(32), default="peer")  # manager | vip_customer | audit | peer | external
    participants: Mapped[list] = mapped_column(JSON, default=list)
    location: Mapped[str] = mapped_column(String(512), default="")
    is_unread: Mapped[bool] = mapped_column(Boolean, default=False)
    is_organizer: Mapped[bool] = mapped_column(Boolean, default=False)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    source_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    # Kết quả engine
    score: Mapped[float] = mapped_column(Float, default=0.0)
    bucket: Mapped[str] = mapped_column(String(16), default="low")
    score_reasons: Mapped[list] = mapped_column(JSON, default=list)

    # Trạng thái do người dùng thao tác trên app (không ghi ngược về hệ thống nguồn)
    done_local: Mapped[bool] = mapped_column(Boolean, default=False)
    snoozed_until: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    synced_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (UniqueConstraint("username", "group_key", name="uq_alert_group"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(ForeignKey("users.username"), index=True)
    work_item_id: Mapped[int | None] = mapped_column(ForeignKey("work_items.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16))  # info | warning | critical
    title: Mapped[str] = mapped_column(String(512))
    body: Mapped[str] = mapped_column(Text, default="")
    fire_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | sent | acked | snoozed | dismissed
    group_key: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class DailyBrief(Base):
    __tablename__ = "daily_briefs"
    __table_args__ = (UniqueConstraint("username", "brief_date", name="uq_brief_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(ForeignKey("users.username"), index=True)
    brief_date: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD theo giờ địa phương
    content: Mapped[dict] = mapped_column(JSON)
    generated_by: Mapped[str] = mapped_column(String(16))  # llm | fallback
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    pushed: Mapped[bool] = mapped_column(Boolean, default=False)


class Device(Base):
    __tablename__ = "devices"

    token: Mapped[str] = mapped_column(String(512), primary_key=True)
    username: Mapped[str] = mapped_column(ForeignKey("users.username"), index=True)
    platform: Mapped[str] = mapped_column(String(16))
    registered_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    username: Mapped[str] = mapped_column(String(128), index=True)
    action: Mapped[str] = mapped_column(String(64))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
