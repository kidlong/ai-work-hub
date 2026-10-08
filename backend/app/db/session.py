from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

from sqlalchemy import DateTime, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from app.core.config import get_settings


class UTCDateTime(TypeDecorator):
    """Lưu datetime dạng UTC (naive trong DB), luôn trả về datetime có tzinfo=UTC.

    Giúp SQLite (dev) và PostgreSQL (prod) cư xử giống nhau.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):  # noqa: ANN001
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Datetime phải có timezone")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect):  # noqa: ANN001
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc)


class Base(DeclarativeBase):
    pass


def _make_engine(url: str):
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


engine = _make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def ensure_dev_columns(eng=None) -> None:  # noqa: ANN001
    """Chỉ cho dev: DB cũ chưa có cột mới thì ALTER TABLE (dự án chưa dùng Alembic)."""
    eng = eng or engine
    insp = inspect(eng)
    if "user_settings" not in insp.get_table_names():
        return
    if "live_sim_enabled" in {c["name"] for c in insp.get_columns("user_settings")}:
        return
    default = "1" if eng.dialect.name == "sqlite" else "TRUE"
    with eng.begin() as conn:
        conn.execute(text(f"ALTER TABLE user_settings ADD COLUMN live_sim_enabled BOOLEAN NOT NULL DEFAULT {default}"))


def init_db() -> None:
    from app.db import models  # noqa: F401  (đăng ký model)

    Base.metadata.create_all(bind=engine)
    if get_settings().app_env == "dev":
        ensure_dev_columns()


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
