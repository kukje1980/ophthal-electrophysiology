"""Patient schemas."""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PatientCreate(BaseModel):
    mrn: str = Field(..., max_length=32)
    name: str = Field(..., max_length=128)
    birth_date: Optional[date] = None
    sex: Optional[str] = Field(None, max_length=1)
    note: Optional[str] = Field(None, max_length=512)


class PatientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    mrn: str
    name: str
    birth_date: Optional[date] = None
    sex: Optional[str] = None
    note: Optional[str] = None
    created_at: datetime
