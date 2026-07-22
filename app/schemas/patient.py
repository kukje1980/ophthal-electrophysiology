"""Patient schemas."""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PatientBase(BaseModel):
    """All patient fields, every one optional (shared by create/update/out)."""

    # demographics
    mrn: Optional[str] = Field(None, max_length=32)
    name: Optional[str] = Field(None, max_length=128)
    name_en: Optional[str] = Field(None, max_length=128)
    national_id: Optional[str] = Field(None, max_length=32)
    birth_date: Optional[date] = None
    sex: Optional[str] = Field(None, max_length=1)
    # contact
    phone: Optional[str] = Field(None, max_length=32)
    email: Optional[str] = Field(None, max_length=128)
    address: Optional[str] = Field(None, max_length=256)
    guardian_name: Optional[str] = Field(None, max_length=64)
    guardian_relation: Optional[str] = Field(None, max_length=32)
    guardian_phone: Optional[str] = Field(None, max_length=32)
    # registration / insurance / referral
    insurance_type: Optional[str] = Field(None, max_length=32)
    insurance_no: Optional[str] = Field(None, max_length=64)
    referring_doctor: Optional[str] = Field(None, max_length=64)
    referral_clinic: Optional[str] = Field(None, max_length=128)
    chief_complaint: Optional[str] = Field(None, max_length=256)
    # systemic / general history
    diabetes: Optional[bool] = None
    diabetes_years: Optional[float] = None
    hypertension: Optional[bool] = None
    smoking: Optional[str] = Field(None, max_length=16)
    systemic_history: Optional[str] = Field(None, max_length=256)
    medications: Optional[str] = Field(None, max_length=256)
    allergies: Optional[str] = Field(None, max_length=256)
    family_ocular_history: Optional[str] = Field(None, max_length=256)
    # ocular history
    ocular_history_od: Optional[str] = Field(None, max_length=256)
    ocular_history_os: Optional[str] = Field(None, max_length=256)
    # baseline ocular examination
    va_od: Optional[str] = Field(None, max_length=16)
    va_os: Optional[str] = Field(None, max_length=16)
    refraction_od: Optional[str] = Field(None, max_length=64)
    refraction_os: Optional[str] = Field(None, max_length=64)
    iop_od: Optional[float] = None
    iop_os: Optional[float] = None
    lens_status_od: Optional[str] = Field(None, max_length=16)
    lens_status_os: Optional[str] = Field(None, max_length=16)
    pupil_od: Optional[str] = Field(None, max_length=32)
    pupil_os: Optional[str] = Field(None, max_length=32)
    note: Optional[str] = Field(None, max_length=512)


class PatientCreate(PatientBase):
    mrn: str = Field(..., max_length=32)
    name: str = Field(..., max_length=128)


class PatientUpdate(PatientBase):
    """Partial update — every field optional."""


class PatientOut(PatientBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    mrn: str
    name: str
    age: Optional[int] = None
    # national_id is stored encrypted; never serialise the ciphertext. Only a
    # masked form is returned, and the full value via a separate audited route.
    national_id: Optional[str] = Field(default=None, exclude=True)
    national_id_masked: Optional[str] = None
    created_at: datetime
