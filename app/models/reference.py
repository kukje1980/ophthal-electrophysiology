"""Laboratory normative reference range ORM model.

ISCEV requires each laboratory to establish its own normative data for its
equipment and population. Rows here (optionally per age band) override the
built-in demonstration values in app/iscev/reference.py.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, UniqueConstraint

from app.database import Base


class ReferenceRange(Base):
    __tablename__ = "reference_ranges"
    __table_args__ = (
        UniqueConstraint("step_key", "marker", "age_min", "age_max",
                         name="uq_reference_band"),
    )

    id = Column(Integer, primary_key=True, index=True)
    step_key = Column(String(32), nullable=False, index=True)
    marker = Column(String(16), nullable=False)
    # optional age band (years); both None = applies to all ages
    age_min = Column(Integer, nullable=True)
    age_max = Column(Integer, nullable=True)
    # limits (None = not checked)
    amp_min = Column(Float, nullable=True)   # µV
    amp_max = Column(Float, nullable=True)
    lat_min = Column(Float, nullable=True)   # ms
    lat_max = Column(Float, nullable=True)
    n = Column(Integer, nullable=True)        # normal subjects behind the range
    source = Column(String(16), nullable=True, default="lab")  # lab/demo/csv/computed
    note = Column(String(128), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def limits(self) -> dict:
        """Non-null limits as the dict shape classify() expects."""
        return {k: v for k, v in (
            ("amp_min", self.amp_min), ("amp_max", self.amp_max),
            ("lat_min", self.lat_min), ("lat_max", self.lat_max),
        ) if v is not None}
