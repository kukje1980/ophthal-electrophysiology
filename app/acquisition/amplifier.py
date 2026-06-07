"""Biopotential amplifier interface.

The amplifier is the recording side of an electrophysiology system: it sets
gain, band-pass / notch filtering and sampling, checks electrode impedance,
then captures triggered sweeps. It knows nothing about the stimulus - it only
records whatever the eye produces after a trigger arrives from the stimulator.

Real systems separate the amplifier from the stimulator (they are usually
distinct boxes linked by a TTL trigger line), so they are modelled as distinct
contracts here. A concrete driver subclasses :class:`Amplifier` and implements
the transport (serial / TCP-SCPI / vendor SDK).
"""
from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np


class AmplifierState(str, enum.Enum):
    DISCONNECTED = "disconnected"
    READY = "ready"
    ARMED = "armed"  # waiting for the next stimulus trigger
    ERROR = "error"


@dataclass
class AmplifierSettings:
    """Acquisition settings programmed onto the amplifier for one step."""

    sampling_rate: float  # Hz
    sweep_duration_ms: float

    gain: float = 10_000.0  # V/V (input-referred output is reported in µV)
    hp_filter_hz: float = 0.3  # high-pass cutoff
    lp_filter_hz: float = 300.0  # low-pass cutoff
    notch_hz: Optional[float] = 60.0  # mains notch; None disables it

    n_sweeps: int = 1  # sweeps to average per result
    pre_trigger_ms: float = 0.0  # baseline captured before the trigger
    artifact_threshold_uv: Optional[float] = None  # reject sweeps over this
    channels: List[str] = field(default_factory=lambda: ["active"])

    def n_samples(self) -> int:
        return max(2, int(round(self.sampling_rate * self.sweep_duration_ms
                                / 1000.0)))


@dataclass
class ImpedanceReport:
    """Electrode-offset / impedance check result.

    ISCEV recommends keeping electrode impedance low (commonly < 5 kΩ).
    """

    values_kohm: Dict[str, float]
    limit_kohm: float = 5.0

    @property
    def max_kohm(self) -> float:
        return max(self.values_kohm.values(), default=0.0)

    @property
    def ok(self) -> bool:
        return self.max_kohm <= self.limit_kohm


class Amplifier(ABC):
    """Contract every concrete amplifier driver must implement."""

    name: str = "abstract-amplifier"

    def __init__(self, connection: str = ""):
        self.connection = connection
        self.state = AmplifierState.DISCONNECTED
        self.settings: Optional[AmplifierSettings] = None

    # -- lifecycle --------------------------------------------------------
    @abstractmethod
    def connect(self) -> None:
        """Open the link to the amplifier; set state to READY on success."""

    @abstractmethod
    def disconnect(self) -> None:
        """Close the link; set state to DISCONNECTED."""

    def configure(self, settings: AmplifierSettings) -> None:
        """Program gain, filters, sampling and averaging for the next step."""
        self.settings = settings

    # -- quality control --------------------------------------------------
    @abstractmethod
    def check_impedance(self, limit_kohm: float = 5.0) -> ImpedanceReport:
        """Measure per-electrode impedance before recording."""

    # -- acquisition ------------------------------------------------------
    @abstractmethod
    def arm(self) -> None:
        """Prepare to capture the next triggered sweep (state -> ARMED)."""

    @abstractmethod
    def capture_sweep(self, stimulus, eye: str) -> np.ndarray:
        """Block until the stimulator trigger fires, then return one sweep.

        The returned array is in microvolts and ``settings.n_samples()`` long.
        Real drivers ignore ``stimulus`` / ``eye`` (the montage is selected
        elsewhere); they are passed so simulated or replay amplifiers can
        synthesise a physiological response.
        """

    # -- status -----------------------------------------------------------
    def status(self) -> dict:
        return {
            "name": self.name,
            "connection": self.connection,
            "state": self.state.value,
            "configured": self.settings is not None,
        }

    @property
    def is_connected(self) -> bool:
        return self.state in (
            AmplifierState.READY,
            AmplifierState.ARMED,
        )
