"""Exam schemas."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from app.schemas.waveform import WaveformOut


class ExamCreate(BaseModel):
    patient_id: int
    protocol: str  # ISCEV protocol key
    eyes: List[str] = ["OD", "OS"]
    operator: Optional[str] = None
    note: Optional[str] = None


class ExamSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    patient_id: int
    test_type: str
    protocol: str
    device: Optional[str] = None
    operator: Optional[str] = None
    status: str
    performed_at: datetime


class ExamOut(ExamSummary):
    note: Optional[str] = None
    waveforms: List[WaveformOut] = []
