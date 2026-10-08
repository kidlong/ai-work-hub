from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.db.models import AuditLog

log = logging.getLogger("audit")


def audit(db: Session, username: str, action: str, **detail) -> None:
    """Ghi audit log. Không ghi nội dung nghiệp vụ / PII vào detail."""
    db.add(AuditLog(username=username, action=action, detail=detail))
    db.commit()
    log.info("audit user=%s action=%s detail=%s", username, action, detail)
