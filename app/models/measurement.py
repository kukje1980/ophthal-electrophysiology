"""Measurement ORM model - one detected/edited marker on a waveform."""
from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class Measurement(Base):
    __tablename__ = "measurements"

    id = Column(Integer, primary_key=True, index=True)
    waveform_id = Column(
        Integer, ForeignKey("waveforms.id"), nullable=False, index=True
    )

    # Marker name: a, b, OP2, P50, N95, N75, P100, N135, N1, P1 ...
    marker = Column(String(16), nullable=False)
    latency_ms = Column(Float, nullable=False)  # implicit time / peak time
    amplitude_uv = Column(Float, nullable=False)
    is_auto = Column(Boolean, default=True)  # auto-detected vs manually edited
    flag = Column(String(16), nullable=True)  # normal / borderline / abnormal

    waveform = relationship("Waveform", back_populates="measurements")
