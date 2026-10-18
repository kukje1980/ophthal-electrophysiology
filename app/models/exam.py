"""Exam ORM model - one electrophysiology study for a patient."""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base

# Exam life-cycle. A *signed* report is read-only: markers and the
# interpretation can no longer be changed until a clinician re-opens it.
STATUS_COMPLETED = "completed"   # acquired, awaiting interpretation
STATUS_SIGNED = "signed"         # interpreted and signed off


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
    status = Column(String(16), default=STATUS_COMPLETED)  # completed / signed
    performed_at = Column(DateTime, default=datetime.utcnow)
    note = Column(String(512), nullable=True)

    # -- interpretation / sign-off ----------------------------------------
    interpretation = Column(Text, nullable=True)     # findings (free text)
    impression = Column(String(512), nullable=True)  # one-line conclusion
    interpreted_by = Column(String(64), nullable=True)
    interpreted_at = Column(DateTime, nullable=True)
    signed_by = Column(String(64), nullable=True)
    signed_at = Column(DateTime, nullable=True)

    patient = relationship("Patient", back_populates="exams")
    waveforms = relationship(
        "Waveform", back_populates="exam", cascade="all, delete-orphan"
    )

    @property
    def is_signed(self) -> bool:
        return self.status == STATUS_SIGNED
