"""Waveform and measurement schemas."""
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class MeasurementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    marker: str
    latency_ms: float
    amplitude_uv: float
    is_auto: bool
    flag: Optional[str] = None


class WaveformOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    eye: str
    step: str
    sampling_rate: float
    duration_ms: float
    samples: List[float]
    measurements: List[MeasurementOut] = []
