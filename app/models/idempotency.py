"""Idempotency keys — make write requests safe to retry over a flaky network.

The browser sends an ``Idempotency-Key`` header with every write. The key is
stored in the *same transaction* as the record it created, so when a response
is lost and the request is retried, the server returns the record that was
already saved instead of creating a duplicate.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from app.database import Base


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    id = Column(Integer, primary_key=True)
    key = Column(String(96), unique=True, nullable=False)  # "<user_id>:<client key>"
    entity = Column(String(32), nullable=False)             # patient / exam
    entity_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
