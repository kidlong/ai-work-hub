"""Worker chạy nền (process riêng): đồng bộ định kỳ, gửi nhắc, tạo Morning Brief.

Chạy:  python -m app.worker
Chỉ nên chạy 1 instance worker (hoặc dùng distributed lock nếu scale ngang).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import User
from app.db.session import SessionLocal, init_db
from app.services.brief_service import run_morning_briefs
from app.services.push_service import dispatch_due_alerts
from app.services.simulator import SimTicker
from app.services.sync_service import sync_user

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("worker")

ACTIVE_USER_DAYS = 14
_ticker = SimTicker()


def job_sync_all() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=ACTIVE_USER_DAYS)
    with SessionLocal() as db:
        users = list(db.scalars(select(User).where(User.last_login_at >= cutoff)))
        for u in users:
            try:
                sync_user(db, u)
            except Exception:
                log.exception("Đồng bộ lỗi cho %s", u.username)
                db.rollback()


def job_dispatch_alerts() -> None:
    with SessionLocal() as db:
        n = dispatch_due_alerts(db)
        if n:
            log.info("Đã gửi %d nhắc việc", n)


def job_morning_briefs() -> None:
    with SessionLocal() as db:
        n = run_morning_briefs(db)
        if n:
            log.info("Đã gửi %d Morning Brief", n)


def job_sim_tick() -> None:
    with SessionLocal() as db:
        emitted = _ticker.tick(db, active_days=ACTIVE_USER_DAYS)
        if emitted:
            log.info("Đã phát sự kiện giả lập cho %s", ", ".join(emitted))


def build_scheduler(s) -> BlockingScheduler:  # noqa: ANN001
    sched = BlockingScheduler(timezone=s.timezone)
    sched.add_job(job_sync_all, "interval", minutes=s.sync_interval_minutes, id="sync",
                  next_run_time=datetime.now(timezone.utc), max_instances=1, coalesce=True)
    sched.add_job(job_dispatch_alerts, "interval", minutes=1, id="dispatch", max_instances=1, coalesce=True)
    sched.add_job(job_morning_briefs, "interval", minutes=5, id="brief", max_instances=1, coalesce=True)
    if s.mock_connectors:
        sched.add_job(job_sim_tick, "interval", seconds=10, id="sim", max_instances=1, coalesce=True)
    return sched


def main() -> None:
    s = get_settings()
    init_db()
    sched = build_scheduler(s)
    log.info("Worker khởi động (sync mỗi %d phút, mock=%s)", s.sync_interval_minutes, s.mock_connectors)
    sched.start()


if __name__ == "__main__":
    main()
