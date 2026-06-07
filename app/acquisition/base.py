"""Abstract acquisition device contract.

A driver represents one piece of recording hardware (or a simulator). The
rest of the application depends only on this interface.
"""
from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List


class DeviceState(str, enum.Enum):
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    ACQUIRING = "acquiring"
    ERROR = "error"


@dataclass
class AcquiredTrace:
    """One recorded sweep returned by a device."""

    eye: str  # OD / OS
    step: str  # protocol step key
    sampling_rate: float  # Hz
    duration_ms: float
    samples: List[float] = field(default_factory=list)  # microvolts


class AcquisitionDevice(ABC):
    """Base class every concrete device driver must implement."""

    #: short, unique driver name used by the registry / config
    name: str = "abstract"

    def __init__(self, connection: str = ""):
        self.connection = connection
        self.state = DeviceState.DISCONNECTED
        self._protocol: dict | None = None

    # -- lifecycle --------------------------------------------------------
    @abstractmethod
    def connect(self) -> None:
        """Open the link to the hardware. Set state to CONNECTED on success."""

    @abstractmethod
    def disconnect(self) -> None:
        """Close the link and set state to DISCONNECTED."""

    def configure(self, protocol: dict) -> None:
        """Load a protocol onto the device (stimulus, filters, averaging)."""
        self._protocol = protocol

    # -- acquisition ------------------------------------------------------
    @abstractmethod
    def acquire_step(self, step: dict, eye: str) -> AcquiredTrace:
        """Run one protocol step for one eye and return the averaged trace.

        Implementations should drive the stimulator, collect/average sweeps
        and return the result. Long acquisitions may update ``self.state``.
        """

    # -- status -----------------------------------------------------------
    def status(self) -> dict:
        return {
            "name": self.name,
            "connection": self.connection,
            "state": self.state.value,
            "protocol_loaded": self._protocol is not None,
        }

    @property
    def is_connected(self) -> bool:
        return self.state in (DeviceState.CONNECTED, DeviceState.ACQUIRING)
