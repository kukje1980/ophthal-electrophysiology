"""Patient ORM model."""
from datetime import datetime

from sqlalchemy import Column, Date, DateTime, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True)
    mrn = Column(String(32), unique=True, index=True, nullable=False)
    name = Column(String(128), nullable=False)
    birth_date = Column(Date, nullable=True)
    sex = Column(String(1), nullable=True)  # M / F / O
    note = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    exams = relationship(
        "Exam", back_populates="patient", cascade="all, delete-orphan"
    )
