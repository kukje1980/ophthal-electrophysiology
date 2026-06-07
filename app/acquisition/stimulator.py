"""Visual stimulator interface.

The stimulator is the stimulus side of an electrophysiology system: a
Ganzfeld bowl (flash / background / flicker) or a pattern display
(checkerboard reversal, multifocal m-sequence). For every sweep it presents
the programmed stimulus and emits a hardware trigger (TTL) that the amplifier
is armed to record from.

A concrete driver subclasses :class:`Stimulator` and implements the transport
(serial / TCP-SCPI / vendor SDK) plus the trigger line.
"""
from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


class StimulatorState(str, enum.Enum):
    DISCONNECTED = "disconnected"
    READY = "ready"
    PRESENTING = "presenting"
    ERROR = "error"


@dataclass
class StimulusCommand:
    """One stimulus program. Fields not relevant to ``kind`` stay ``None``."""

    # "flash" | "flicker" | "pattern" | "mfocal"
    kind: str

    # Flash / flicker (Ganzfeld) -----------------------------------------
    intensity_cd_s_m2: Optional[float] = None
    background_cd_m2: Optional[float] = None
    color: str = "white"
    adaptation: str = "dark"  # dark | light
    rate_hz: Optional[float] = None  # flicker / reversal frequency

    # Pattern / multifocal (display) -------------------------------------
    check_deg: Optional[float] = None
    field_deg: Optional[float] = None
    contrast: Optional[float] = None
    reversal_hz: Optional[float] = None
    hexagons: Optional[int] = None

    # Bookkeeping (used by simulated/replay devices) ----------------------
    step_key: str = ""
    step_kind: str = ""
    label: str = ""


@dataclass
class TriggerEvent:
    """Returned by :meth:`Stimulator.present` when a stimulus + trigger fires."""

    sweep_index: int
    t0_ms: float = 0.0


class Stimulator(ABC):
    """Contract every concrete stimulator driver must implement."""

    name: str = "abstract-stimulator"

    def __init__(self, connection: str = ""):
        self.connection = connection
        self.state = StimulatorState.DISCONNECTED
        self.command: Optional[StimulusCommand] = None

    # -- lifecycle --------------------------------------------------------
    @abstractmethod
    def connect(self) -> None:
        """Open the link to the stimulator; set state to READY on success."""

    @abstractmethod
    def disconnect(self) -> None:
        """Close the link; set state to DISCONNECTED."""

    def load(self, command: StimulusCommand) -> None:
        """Program the stimulus (intensity, background, pattern, rate)."""
        self.command = command

    # -- presentation -----------------------------------------------------
    @abstractmethod
    def present(self, sweep_index: int = 0) -> TriggerEvent:
        """Present the loaded stimulus once and emit the trigger pulse.

        The amplifier must already be armed; the returned :class:`TriggerEvent`
        marks the trigger time the amplifier records from.
        """

    # -- status -----------------------------------------------------------
    def status(self) -> dict:
        return {
            "name": self.name,
            "connection": self.connection,
            "state": self.state.value,
            "loaded": self.command is not None,
        }

    @property
    def is_connected(self) -> bool:
        return self.state in (
            StimulatorState.READY,
            StimulatorState.PRESENTING,
        )
