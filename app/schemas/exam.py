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


class ExamRecord(BaseModel):
    """One trigger-averaged epoch recorded from the live stream, to be stored
    as a protocol step of an exam (new exam, or appended to ``exam_id``)."""

    patient_id: int
    protocol: str
    step_key: str
    eye: str = "OD"
    samples: List[float]
    sampling_rate: float        # Hz of the provided samples
    duration_ms: float          # length of the provided epoch
    n_sweeps: int = 1
    exam_id: Optional[int] = None
    device: Optional[str] = None
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
