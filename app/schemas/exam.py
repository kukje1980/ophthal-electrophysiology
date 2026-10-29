"""Exam schemas."""
from datetime import datetime
from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.waveform import WaveformOut


Eye = Literal["OD", "OS"]
# NaN / Infinity are not valid JSON: one stored sample would break every
# later read of the exam in the browser.
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]


class ExamCreate(BaseModel):
    patient_id: int
    protocol: str = Field(..., max_length=64)  # ISCEV protocol key
    eyes: List[Eye] = Field(["OD", "OS"], min_length=1, max_length=2)
    operator: Optional[str] = Field(None, max_length=64)
    note: Optional[str] = Field(None, max_length=512)
    visit_id: Optional[int] = None  # reception this exam belongs to


class ExamRecord(BaseModel):
    """One trigger-averaged epoch recorded from the live stream, to be stored
    as a protocol step of an exam (new exam, or appended to ``exam_id``)."""

    patient_id: int
    protocol: str = Field(..., max_length=64)
    step_key: str = Field(..., max_length=64)
    eye: Eye = "OD"
    samples: List[FiniteFloat] = Field(..., min_length=2, max_length=200_000)
    sampling_rate: float = Field(..., gt=0, le=1_000_000)  # Hz of the provided samples
    duration_ms: float = Field(..., gt=0, le=600_000)      # length of the provided epoch
    n_sweeps: int = Field(1, ge=1)
    n_rejected: int = Field(0, ge=0)  # epochs dropped by artifact rejection
    exam_id: Optional[int] = None
    visit_id: Optional[int] = None  # reception, when a new exam is created
    device: Optional[str] = Field(None, max_length=64)
    operator: Optional[str] = Field(None, max_length=64)
    note: Optional[str] = Field(None, max_length=512)


class ExamSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    patient_id: int
    visit_id: Optional[int] = None
    test_type: str
    protocol: str
    device: Optional[str] = None
    operator: Optional[str] = None
    status: str
    performed_at: datetime


class ExamOut(ExamSummary):
    note: Optional[str] = None
    waveforms: List[WaveformOut] = []
