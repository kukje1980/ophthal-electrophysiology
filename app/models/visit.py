"""Visit ORM model — one reception (검사 접수) of a patient for testing.

Everything that changes from visit to visit lives here rather than on the
patient record, so the history is kept and each report prints the values of
its own day: attending doctor, diagnosis / reason for testing, requested
tests, the day's visual acuity and pupil size, and the ISCEV recording
conditions (adaptation times, electrode, refractive correction). Exams
recorded for the visit point back to it.
"""
from datetime import date, datetime

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class Visit(Base):
    __tablename__ = "visits"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(
        Integer, ForeignKey("patients.id"), nullable=False, index=True
    )
    visit_date = Column(Date, nullable=False, index=True, default=date.today)

    attending_doctor = Column(String(64), nullable=True)
    diagnosis = Column(String(256), nullable=True)  # diagnosis / reason for testing
    tests = Column(String(64), nullable=True)  # requested test types, "ffERG,VEP"

    # the day's state of each eye
    va_od = Column(String(16), nullable=True)  # best-corrected visual acuity
    va_os = Column(String(16), nullable=True)
    pupil_od = Column(Float, nullable=True)  # pupil diameter at recording (mm)
    pupil_os = Column(Float, nullable=True)

    # recording conditions an ISCEV report documents
    dark_adapt_min = Column(Integer, nullable=True)
    light_adapt_min = Column(Integer, nullable=True)
    electrode = Column(String(32), nullable=True)
    refraction = Column(String(128), nullable=True)  # correction for pattern tests

    operator = Column(String(64), nullable=True)
    note = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="visits")
    exams = relationship("Exam", back_populates="visit")
