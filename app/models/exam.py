"""Exam ORM model - one electrophysiology study for a patient."""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class Exam(Base):
    __tablename__ = "exams"

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

    patient = relationship("Patient", back_populates="exams")
    waveforms = relationship(
        "Waveform", back_populates="exam", cascade="all, delete-orphan"
    )
