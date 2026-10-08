from __future__ import annotations

from datetime import datetime, time, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.brief_generator import generate_brief
from app.core.audit import audit
from app.core.config import get_settings
from app.core.deps import get_user_settings
from app.db.models import DailyBrief, User
from app.services.push_service import push_to_user
from app.services.sync_service import insights_for, user_items


def get_or_create_brief(db: Session, user: User, now: datetime | None = None, force: bool = False) -> DailyBrief:
    now = now or datetime.now(timezone.utc)
    tz = get_settings().tz
    day = now.astimezone(tz).date().isoformat()
    brief = db.scalar(select(DailyBrief).where(DailyBrief.username == user.username, DailyBrief.brief_date == day))
    if brief and not force:
        return brief
    items = user_items(db, user.username)
    content, by = generate_brief(user.display_name, items, insights_for(items, now, days=1)[0], now, tz)
    if brief is None:
        brief = DailyBrief(username=user.username, brief_date=day, content=content, generated_by=by)
        db.add(brief)
    else:
        brief.content, brief.generated_by, brief.created_at = content, by, now
    db.commit()
    audit(db, user.username, "brief_generated", by=by, date=day)
    return brief


def run_morning_briefs(db: Session, now: datetime | None = None) -> int:
    """Gọi định kỳ (5 phút/lần): tạo + push brief cho người đã tới giờ brief_time hôm nay."""
    now = now or datetime.now(timezone.utc)
    tz = get_settings().tz
    local = now.astimezone(tz)
    if local.weekday() >= 5:  # bỏ qua thứ 7, CN
        return 0
    count = 0
    for user in db.scalars(select(User).where(User.last_sync_at.is_not(None))):
        st = get_user_settings(db, user.username)
        h, m = (int(x) for x in st.brief_time.split(":"))
        if local.time() < time(h, m):
            continue
        brief = get_or_create_brief(db, user, now)
        if not brief.pushed:
            push_to_user(db, user.username, "Morning Brief", "Tóm tắt công việc hôm nay của bạn đã sẵn sàng.",
                         {"type": "brief", "date": brief.brief_date})
            brief.pushed = True
            db.commit()
            count += 1
    return count
