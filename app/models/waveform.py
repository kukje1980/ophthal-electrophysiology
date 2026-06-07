"""Waveform ORM model - a single recorded trace (one eye, one step)."""
from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.types import JSON

from app.database import Base


class Waveform(Base):
    __tablename__ = "waveforms"

    id = Column(Integer, primary_key=True, index=True)
    exam_id = Column(
        Integer, ForeignKey("exams.id"), nullable=False, index=True
    )

    eye = Column(String(2), nullable=False)  # OD / OS
    step = Column(String(64), nullable=False)  # protocol step key/label

    sampling_rate = Column(Float, nullable=False)  # Hz
    duration_ms = Column(Float, nullable=False)
    # Amplitude samples in microvolts, stored as JSON list. The time axis is
    # reconstructed from sampling_rate / duration_ms.
    samples = Column(JSON, nullable=False)
    note = Column(Text, nullable=True)

    exam = relationship("Exam", back_populates="waveforms")
    measurements = relationship(
        "Measurement", back_populates="waveform", cascade="all, delete-orphan"
    )
