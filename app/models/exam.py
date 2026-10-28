"""Exam ORM model - one electrophysiology study for a patient."""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class Exam(Base):
    __tablename__ = "exams"
    __table_args__ = (
        # a patient's exam history, newest first
        Index("ix_exams_patient_performed", "patient_id", "performed_at"),
        # recent exams (dashboard) and the trash
        Index("ix_exams_active_performed", "deleted_at", "performed_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(
        Integer, ForeignKey("patients.id"), nullable=False, index=True
    )

    # Test type: ffERG / PERG / VEP / mfERG
    test_type = Column(String(16), nullable=False)
    # ISCEV protocol key (see app.iscev.protocols)
    protocol = Column(String(64), nullable=False)

    device = Column(String(64), nullable=True)
    operator = Column(String(64), nullable=True)
    status = Column(String(16), default="completed")  # completed / draft
    performed_at = Column(DateTime, default=datetime.utcnow)
    note = Column(String(512), nullable=True)

    # soft delete (see Patient.deleted_at)
    deleted_at = Column(DateTime, nullable=True)
    deleted_by = Column(String(64), nullable=True)

    patient = relationship("Patient", back_populates="exams")
    waveforms = relationship(
        "Waveform", back_populates="exam", cascade="all, delete-orphan"
    )
