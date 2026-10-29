"""Waveform and measurement schemas."""
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class MeasurementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    marker: str
    latency_ms: float
    amplitude_uv: float
    is_auto: bool
    flag: Optional[str] = None


class MeasurementMove(BaseModel):
    """Move an existing cursor to a new implicit time (ms)."""

    latency_ms: float = Field(..., ge=0)


class MeasurementAdd(BaseModel):
    """Place a marker by hand on a waveform."""

    marker: str = Field(..., min_length=1, max_length=16)
    latency_ms: float = Field(..., ge=0)


class WaveformOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    eye: str
    step: str
    sampling_rate: float
    duration_ms: float
    samples: List[float]
    measurements: List[MeasurementOut] = []
