"""Built-in simulator device.

Implements the same Amplifier + Stimulator split as a real system so the whole
pipeline (acquire -> store -> auto-mark -> report) works without hardware:

* :class:`SimulatedStimulator` accepts a programmed stimulus and emits a
  trigger for each sweep.
* :func:`simulate_response` is the "patient": given the loaded stimulus it
  produces the clean evoked biological response. Morphology is composed from
  Gaussian components placed at the expected implicit times for that step.
* :class:`SimulatedAmplifier` is the recording chain: it captures the
  triggered response and adds realistic recording noise (which the averaging
  loop in :class:`~app.acquisition.base.CompositeDevice` then reduces).

A real driver replaces these two classes with vendor transport code; nothing
above the acquisition layer changes.
"""
from __future__ import annotations

import numpy as np

from app.acquisition.amplifier import (
    Amplifier,
    AmplifierState,
    ImpedanceReport,
)
from app.acquisition.base import CompositeDevice
from app.acquisition.stimulator import (
    Stimulator,
    StimulatorState,
    StimulusCommand,
    TriggerEvent,
)


def _gauss(t, amp, center, width):
    return amp * np.exp(-((t - center) ** 2) / (2.0 * width ** 2))


# Component recipes per step *kind*: list of (amp_uv, center_ms, width_ms).
# Positive amplitude -> upward (cornea-positive) deflection.
_RECIPES = {
    "rod_b": [(280, 95, 22)],
    "combined": [(-260, 16, 4), (520, 48, 13),
                 (45, 20, 1.6), (60, 26, 1.6), (40, 32, 1.6)],
    "op": [(70, 16, 1.5), (95, 22, 1.5), (75, 28, 1.5), (45, 34, 1.6)],
    "cone": [(-35, 14, 3), (130, 30, 6), (25, 45, 6)],
    "perg": [(-1.6, 33, 4), (5.5, 52, 9), (-4.2, 95, 22)],
    # vep_pr third trough ~145 ms = N145 (ISCEV VEP 2025 naming).
    "vep_pr": [(-3.5, 75, 10), (11.0, 100, 12), (-4.5, 145, 22)],
    "vep_flash": [(-4.0, 80, 16), (8.5, 122, 26)],
    "mferg": [(-120, 14, 3), (210, 30, 5), (-40, 55, 12)],
}


def simulate_response(stimulus: StimulusCommand, eye: str,
                      t: np.ndarray) -> np.ndarray:
    """Clean (noise-free) evoked response for a loaded stimulus and eye."""
    kind = stimulus.step_kind
    # Deterministic, eye-dependent gain variation for realism.
    rng = np.random.default_rng(
        abs(hash((stimulus.step_key, eye, "gain"))) % (2 ** 32)
    )
    eye_gain = 1.0 + (0.04 if eye == "OD" else -0.04) + rng.normal(0, 0.03)

    y = np.zeros_like(t)
    if kind == "flicker":
        rate = float(stimulus.rate_hz or 30.0)
        y = 65 * np.sin(2 * np.pi * rate * (t - 8) / 1000.0)
        y *= np.clip(t / 30.0, 0, 1)  # ramp-in of the steady state
    else:
        for amp, center, width in _RECIPES.get(kind, []):
            y = y + _gauss(t, amp, center, width)

    y = y * eye_gain
    y[t < 4] *= 0.05  # flat pre-stimulus baseline
    return y


class SimulatedStimulator(Stimulator):
    """Ganzfeld / pattern stimulator stand-in."""

    name = "sim-stimulator"

    def connect(self) -> None:
        self.state = StimulatorState.READY

    def disconnect(self) -> None:
        self.state = StimulatorState.DISCONNECTED

    def present(self, sweep_index: int = 0) -> TriggerEvent:
        if not self.is_connected:
            raise RuntimeError("Stimulator is not connected")
        if self.command is None:
            raise RuntimeError("No stimulus loaded")
        # A real driver would drive the bowl/display and raise a TTL pulse here.
        return TriggerEvent(sweep_index=sweep_index, t0_ms=0.0)


class SimulatedAmplifier(Amplifier):
    """Recording-chain stand-in: synthesises the response and adds noise."""

    name = "sim-amplifier"

    def __init__(self, connection: str = ""):
        super().__init__(connection)
        self._rng = np.random.default_rng()
        self._seed_key = None

    def connect(self) -> None:
        self.state = AmplifierState.READY

    def disconnect(self) -> None:
        self.state = AmplifierState.DISCONNECTED

    def check_impedance(self, limit_kohm: float = 5.0) -> ImpedanceReport:
        rng = np.random.default_rng(abs(hash(self.connection)) % (2 ** 32))
        channels = self.settings.channels if self.settings else ["active"]
        values = {ch: round(float(rng.uniform(1.0, 4.0)), 2) for ch in channels}
        values["reference"] = round(float(rng.uniform(1.0, 4.0)), 2)
        return ImpedanceReport(values_kohm=values, limit_kohm=limit_kohm)

    def arm(self) -> None:
        if not self.is_connected:
            raise RuntimeError("Amplifier is not connected")
        self.state = AmplifierState.ARMED

    def capture_sweep(self, stimulus: StimulusCommand, eye: str) -> np.ndarray:
        if self.state != AmplifierState.ARMED:
            raise RuntimeError("Amplifier must be armed before capture")
        if self.settings is None:
            raise RuntimeError("Amplifier is not configured")

        # Reseed deterministically when the (step, eye) changes so a run is
        # reproducible while individual sweeps still differ.
        key = (stimulus.step_key, eye)
        if key != self._seed_key:
            self._rng = np.random.default_rng(abs(hash(key)) % (2 ** 32))
            self._seed_key = key

        s = self.settings
        n = s.n_samples()
        t = np.linspace(0, s.sweep_duration_ms, n, endpoint=False)
        clean = simulate_response(stimulus, eye, t)

        noise_sd = max(0.05, 0.015 * float(np.max(np.abs(clean)) or 1.0))
        sweep = clean + self._rng.normal(0, noise_sd, size=n)

        self.state = AmplifierState.READY
        return sweep


class SimulatedDevice(CompositeDevice):
    """ISCEV simulator: a simulated amplifier + stimulator pair."""

    name = "simulator"

    def __init__(self, connection: str = ""):
        super().__init__(
            amplifier=SimulatedAmplifier(connection),
            stimulator=SimulatedStimulator(connection),
            connection=connection,
        )
