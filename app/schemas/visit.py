"""Visit (검사 접수) and reception schemas."""
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.exam import ExamSummary
from app.schemas.patient import PatientCreate, PatientOut


class VisitBase(BaseModel):
    visit_date: Optional[date] = None  # defaults to today
    attending_doctor: Optional[str] = Field(None, max_length=64)
    diagnosis: Optional[str] = Field(None, max_length=256)
    tests: List[str] = []  # requested test types, e.g. ["ffERG", "VEP"]
    va_od: Optional[str] = Field(None, max_length=16)
    va_os: Optional[str] = Field(None, max_length=16)
    pupil_od: Optional[float] = Field(None, ge=0, le=12)
    pupil_os: Optional[float] = Field(None, ge=0, le=12)
    dark_adapt_min: Optional[int] = Field(None, ge=0, le=240)
    light_adapt_min: Optional[int] = Field(None, ge=0, le=240)
    electrode: Optional[str] = Field(None, max_length=32)
    refraction: Optional[str] = Field(None, max_length=128)
    operator: Optional[str] = Field(None, max_length=64)
    note: Optional[str] = Field(None, max_length=512)

    @field_validator("tests", mode="before")
    @classmethod
    def _split_tests(cls, v):
        """Stored as "ffERG,VEP" on the model; exposed as a list."""
        if v is None:
            return []
        if isinstance(v, str):
            return [t for t in v.split(",") if t]
        return v


class VisitCreate(VisitBase):
    pass


class VisitOut(VisitBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    patient_id: int
    visit_date: date
    created_at: datetime
    exams: List[ExamSummary] = []


class PatientBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    mrn: str
    name: str
    sex: Optional[str] = None
    birth_date: Optional[date] = None
    age: Optional[int] = None


class VisitListOut(VisitOut):
    patient: PatientBrief


class ReceptionIn(BaseModel):
    """One reception: an existing patient (``patient_id``) or a new one
    (``patient``), plus this visit's details — stored together."""

    patient_id: Optional[int] = None
    patient: Optional[PatientCreate] = None
    visit: VisitCreate


class ReceptionOut(BaseModel):
    patient: PatientOut
    visit: VisitOut


class PatientSearchOut(PatientBrief):
    """A patient search hit with a short visit history for the picker."""

    last_visit: Optional[date] = None
    visit_count: int = 0
    last_diagnosis: Optional[str] = None
    last_doctor: Optional[str] = None
