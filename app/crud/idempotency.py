"""Idempotency-key bookkeeping (see app.models.idempotency).

``remember`` adds the key to the caller's session *without committing*, so it
is committed atomically with the record it refers to.
"""
from datetime import datetime, timedelta
from typing import Optional, Tuple

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import IdempotencyKey

HEADER = "Idempotency-Key"
RETENTION_DAYS = 7


def key_from(request: Request, user) -> Optional[str]:
    """Scoped key for this request, or None when the client sent no key.
    Keys are scoped per user so one account can never replay another's."""
    raw = (request.headers.get(HEADER) or "").strip()
    if not raw:
        return None
    return f"{getattr(user, 'id', 0)}:{raw[:80]}"


def lookup(db: Session, key: Optional[str]) -> Optional[Tuple[str, int]]:
    if not key:
        return None
    row = db.query(IdempotencyKey).filter(IdempotencyKey.key == key).first()
    return (row.entity, row.entity_id) if row else None


def remember(db: Session, key: Optional[str], entity: str, entity_id: int) -> None:
    if key:
        db.add(IdempotencyKey(key=key, entity=entity, entity_id=entity_id))


def purge(db: Session, days: int = RETENTION_DAYS) -> int:
    cutoff = datetime.utcnow() - timedelta(days=days)
    n = (db.query(IdempotencyKey)
         .filter(IdempotencyKey.created_at < cutoff)
         .delete(synchronize_session=False))
    db.commit()
    return n
