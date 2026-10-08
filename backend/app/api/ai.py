from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.ai.ask_service import answer
from app.ai.meeting_prep import build_prep
from app.core.audit import audit
from app.core.config import get_settings
from app.core.deps import current_user
from app.db.models import User, WorkItem
from app.db.session import get_db
from app.schemas import AskIn, AskOut, BriefOut
from app.services.brief_service import get_or_create_brief
from app.services.sync_service import user_items

router = APIRouter(tags=["ai"])

ASK_LIMIT_PER_MINUTE = 20
_ask_hits: dict[str, deque] = defaultdict(deque)


def _rate_limit(username: str) -> None:
    q = _ask_hits[username]
    now = time.monotonic()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= ASK_LIMIT_PER_MINUTE:
        raise HTTPException(429, "Bạn hỏi hơi nhanh, vui lòng thử lại sau ít phút")
    q.append(now)


def _brief_out(b) -> BriefOut:  # noqa: ANN001
    return BriefOut(date=b.brief_date, generated_by=b.generated_by, created_at=b.created_at, content=b.content)


@router.get("/brief/today", response_model=BriefOut)
def brief_today(user: User = Depends(current_user), db: Session = Depends(get_db)) -> BriefOut:
    return _brief_out(get_or_create_brief(db, user))


@router.post("/brief/regenerate", response_model=BriefOut)
def brief_regenerate(user: User = Depends(current_user), db: Session = Depends(get_db)) -> BriefOut:
    _rate_limit(user.username)
    return _brief_out(get_or_create_brief(db, user, force=True))


@router.get("/meetings/{item_id}/prep")
def meeting_prep(item_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    m = db.get(WorkItem, item_id)
    if m is None or m.username != user.username or m.kind != "meeting":
        raise HTTPException(404, "Không tìm thấy cuộc họp")
    prep = build_prep(m, user_items(db, user.username), datetime.now(timezone.utc), get_settings().tz)
    audit(db, user.username, "meeting_prep", item_id=item_id, by=prep["generated_by"])
    return prep


@router.post("/ask", response_model=AskOut)
def ask(body: AskIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> AskOut:
    _rate_limit(user.username)
    items = user_items(db, user.username)
    res = answer(body.question, items, datetime.now(timezone.utc), get_settings().tz)
    by_id = {i.id: i for i in items}
    # Không ghi nội dung câu hỏi vào audit (có thể chứa thông tin khách hàng)
    audit(db, user.username, "ask", by=res["generated_by"], hits=len(res["items"]))
    return AskOut(
        question=res["question"],
        answer=res["answer"],
        generated_by=res["generated_by"],
        items=[by_id[i] for i in res["items"] if i in by_id],
    )
