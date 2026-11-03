"""Clinical photo schemas."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PhotoUpdate(BaseModel):
    eye: Optional[str] = Field(None, max_length=2)
    modality: Optional[str] = Field(None, max_length=16)
    taken_at: Optional[datetime] = None
    title: Optional[str] = Field(None, max_length=128)
    note: Optional[str] = Field(None, max_length=512)

    @field_validator("eye", "modality", "taken_at", "title", "note", mode="before")
    @classmethod
    def _blank_is_none(cls, v):
        return None if isinstance(v, str) and not v.strip() else v


class PhotoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    patient_id: int
    patient_name: Optional[str] = None
    patient_mrn: Optional[str] = None
    eye: Optional[str] = None
    modality: Optional[str] = None
    modality_label: Optional[str] = None
    taken_at: Optional[datetime] = None
    title: Optional[str] = None
    note: Optional[str] = None
    original_name: Optional[str] = None
    content_type: str
    width: int
    height: int
    size_bytes: int
    source_id: Optional[int] = None
    uploaded_by: Optional[str] = None
    created_at: datetime
