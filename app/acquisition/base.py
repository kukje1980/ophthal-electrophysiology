"""Abstract acquisition device contract.

A driver represents one piece of recording hardware (or a simulator). The
rest of the application depends only on this interface.
"""
from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

from app.acquisition.amplifier import Amplifier, AmplifierSettings
from app.acquisition.stimulator import Stimulator, StimulusCommand


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


# ---------------------------------------------------------------------------
# Protocol-step -> amplifier / stimulator mapping
# ---------------------------------------------------------------------------
# Default band-pass per step kind (high-pass, low-pass) in Hz, following the
# ISCEV recording recommendations. A step may override via stimulus["filter"].
_FILTERS = {
    "rod_b": (0.3, 300.0),
    "combined": (0.3, 300.0),
    "op": (75.0, 300.0),
    "cone": (0.3, 300.0),
    "flicker": (0.3, 300.0),
    "perg": (1.0, 100.0),
    "vep_pr": (1.0, 100.0),
    "vep_flash": (1.0, 100.0),
    "mferg": (10.0, 300.0),
}

# Sweeps to average and recording-chain gain per step kind. Cortical and
# pattern responses are small and need heavy averaging + high gain; full-field
# ERG responses are large and need only a few sweeps.
_SWEEPS = {
    "rod_b": 3, "combined": 3, "op": 4, "cone": 4, "flicker": 20,
    "perg": 100, "vep_pr": 64, "vep_flash": 32, "mferg": 1,
}
_GAIN = {
    "rod_b": 5_000.0, "combined": 2_000.0, "op": 5_000.0, "cone": 5_000.0,
    "flicker": 5_000.0, "perg": 50_000.0, "vep_pr": 20_000.0,
    "vep_flash": 20_000.0, "mferg": 5_000.0,
}
# Per-sweep artifact rejection threshold (µV); None disables it. Applied to the
# small cortical/pattern responses where blinks/movement dominate.
_ARTIFACT = {"perg": 120.0, "vep_pr": 120.0, "vep_flash": 120.0}

# Which stimulator stimulus class each step kind drives.
_STIM_KIND = {
    "rod_b": "flash", "combined": "flash", "op": "flash", "cone": "flash",
    "vep_flash": "flash", "flicker": "flicker", "perg": "pattern",
    "vep_pr": "pattern", "mferg": "mfocal",
}


def _parse_filter(spec: Optional[str]) -> Optional[Tuple[float, float]]:
    """Parse a step's filter string like '75-300Hz' into (hp, lp)."""
    if not spec:
        return None
    cleaned = spec.lower().replace("hz", "").strip()
    if "-" not in cleaned:
        return None
    lo, hi = cleaned.split("-", 1)
    try:
        return float(lo), float(hi)
    except ValueError:
        return None


def _resample(x: np.ndarray, n: int) -> np.ndarray:
    if len(x) == n:
        return x
    xp = np.linspace(0.0, 1.0, len(x))
    xq = np.linspace(0.0, 1.0, n)
    return np.interp(xq, xp, x)


class CompositeDevice(AcquisitionDevice):
    """An acquisition device assembled from an :class:`Amplifier` and a
    :class:`Stimulator`.

    This is the realistic split that mirrors clinical hardware: two separate
    instruments linked by a trigger line. It implements the standard
    trigger-synchronised averaging loop once, so concrete devices only need to
    supply the two drivers:

        configure amplifier + load stimulus -> (impedance check) -> arm ->
        for each sweep: stimulator.present() raises the trigger and
        amplifier.capture_sweep() records it; sweeps over the artifact
        threshold are rejected; accepted sweeps are averaged into the trace.
    """

    name = "composite"

    def __init__(self, amplifier: Amplifier, stimulator: Stimulator,
                 connection: str = ""):
        super().__init__(connection)
        self.amplifier = amplifier
        self.stimulator = stimulator
        self.last_impedance = None

    # -- lifecycle --------------------------------------------------------
    def connect(self) -> None:
        self.amplifier.connect()
        self.stimulator.connect()
        self.state = DeviceState.CONNECTED

    def disconnect(self) -> None:
        self.stimulator.disconnect()
        self.amplifier.disconnect()
        self.state = DeviceState.DISCONNECTED

    # -- mapping ----------------------------------------------------------
    def amplifier_settings(self, step: dict) -> AmplifierSettings:
        kind = step["kind"]
        stim = step.get("stimulus", {})
        hp, lp = _parse_filter(stim.get("filter")) or _FILTERS.get(
            kind, (0.3, 300.0)
        )
        return AmplifierSettings(
            sampling_rate=float(step["sampling_rate"]),
            sweep_duration_ms=float(step["duration_ms"]),
            gain=_GAIN.get(kind, 10_000.0),
            hp_filter_hz=hp,
            lp_filter_hz=lp,
            n_sweeps=_SWEEPS.get(kind, 1),
            artifact_threshold_uv=_ARTIFACT.get(kind),
        )

    def stimulus_command(self, step: dict) -> StimulusCommand:
        kind = step["kind"]
        stim = step.get("stimulus", {})
        return StimulusCommand(
            kind=_STIM_KIND.get(kind, "flash"),
            intensity_cd_s_m2=stim.get("cd_s_m2"),
            background_cd_m2=(
                30.0 if stim.get("adaptation") == "light" else None
            ),
            adaptation=stim.get("adaptation", "dark"),
            rate_hz=stim.get("rate_hz") or stim.get("reversal_hz"),
            check_deg=stim.get("check_deg"),
            field_deg=stim.get("field_deg"),
            contrast=stim.get("contrast"),
            reversal_hz=stim.get("reversal_hz"),
            hexagons=stim.get("hexagons"),
            step_key=step["key"],
            step_kind=kind,
            label=step.get("label", step["key"]),
        )

    # -- acquisition ------------------------------------------------------
    def acquire_step(self, step: dict, eye: str) -> AcquiredTrace:
        if not self.is_connected:
            raise RuntimeError("Device is not connected")

        self.state = DeviceState.ACQUIRING
        settings = self.amplifier_settings(step)
        command = self.stimulus_command(step)

        self.amplifier.configure(settings)
        self.stimulator.load(command)
        self.last_impedance = self.amplifier.check_impedance()

        n = settings.n_samples()
        acc = np.zeros(n, dtype=float)
        last = acc
        kept = 0
        for i in range(max(1, settings.n_sweeps)):
            self.amplifier.arm()
            self.stimulator.present(i)  # raises the trigger
            sweep = np.asarray(
                self.amplifier.capture_sweep(command, eye), dtype=float
            )
            if sweep.shape[0] != n:
                sweep = _resample(sweep, n)
            last = sweep
            thr = settings.artifact_threshold_uv
            if thr is not None and float(np.max(np.abs(sweep))) > thr:
                continue  # artifact - reject this sweep
            acc += sweep
            kept += 1

        avg = acc / kept if kept else last

        self.state = DeviceState.CONNECTED
        return AcquiredTrace(
            eye=eye,
            step=step["key"],
            sampling_rate=settings.sampling_rate,
            duration_ms=settings.sweep_duration_ms,
            samples=[round(float(v), 3) for v in avg],
        )

    # -- status -----------------------------------------------------------
    def status(self) -> dict:
        s = super().status()
        s["amplifier"] = self.amplifier.status()
        s["stimulator"] = self.stimulator.status()
        if self.last_impedance is not None:
            s["impedance"] = {
                "values_kohm": self.last_impedance.values_kohm,
                "max_kohm": round(self.last_impedance.max_kohm, 2),
                "ok": self.last_impedance.ok,
            }
        return s
