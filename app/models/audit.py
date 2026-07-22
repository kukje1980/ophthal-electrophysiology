"""Audit log ORM model — an append-only record of security-relevant actions."""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    at = Column(DateTime, default=datetime.utcnow, index=True)

    user_id = Column(Integer, nullable=True, index=True)
    username = Column(String(64), nullable=True)  # denormalised for retention
    action = Column(String(48), nullable=False)   # e.g. login, patient.update, phi.view
    entity = Column(String(32), nullable=True)     # patient / exam / user
    entity_id = Column(Integer, nullable=True)
    detail = Column(String(256), nullable=True)
    ip = Column(String(45), nullable=True)
