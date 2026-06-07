"""Built-in simulator device.

Generates ISCEV-realistic waveforms so the whole pipeline (acquire -> store
-> auto-mark -> report) works without any hardware. The morphology of each
trace is composed from Gaussian components positioned at the expected
implicit times for that protocol step.
"""
from __future__ import annotations

import numpy as np

from app.acquisition.base import AcquiredTrace, AcquisitionDevice, DeviceState


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
    "vep_pr": [(-3.5, 75, 10), (11.0, 100, 12), (-4.5, 138, 22)],
    "vep_flash": [(-4.0, 80, 16), (8.5, 122, 26)],
    "mferg": [(-120, 14, 3), (210, 30, 5), (-40, 55, 12)],
}


class SimulatedDevice(AcquisitionDevice):
    name = "simulator"

    def connect(self) -> None:
        self.state = DeviceState.CONNECTED

    def disconnect(self) -> None:
        self.state = DeviceState.DISCONNECTED

    def acquire_step(self, step: dict, eye: str) -> AcquiredTrace:
        if not self.is_connected:
            raise RuntimeError("Device is not connected")

        self.state = DeviceState.ACQUIRING
        kind = step["kind"]
        duration = float(step["duration_ms"])
        fs = float(step["sampling_rate"])
        n = max(2, int(round(duration * fs / 1000.0)))
        t = np.linspace(0, duration, n, endpoint=False)

        # Deterministic but eye-dependent variation for realism.
        rng = np.random.default_rng(abs(hash((step["key"], eye))) % (2 ** 32))
        eye_gain = 1.0 + (0.04 if eye == "OD" else -0.04) + rng.normal(0, 0.03)

        y = np.zeros_like(t)
        if kind == "flicker":
            # 30 Hz steady-state response, first positive peak near ~16 ms.
            rate = float(step["stimulus"].get("rate_hz", 30))
            y = 65 * np.sin(2 * np.pi * rate * (t - 8) / 1000.0)
            y *= np.clip(t / 30.0, 0, 1)  # ramp-in of the steady state
        else:
            for amp, center, width in _RECIPES.get(kind, []):
                y = y + _gauss(t, amp, center, width)

        y = y * eye_gain
        # Pre-stimulus flat baseline (first ~5 ms).
        y[t < 4] *= 0.05
        # Recording noise (~1.5% of peak, min floor for small signals).
        noise_sd = max(0.05, 0.015 * float(np.max(np.abs(y)) or 1.0))
        y = y + rng.normal(0, noise_sd, size=n)

        self.state = DeviceState.CONNECTED
        return AcquiredTrace(
            eye=eye,
            step=step["key"],
            sampling_rate=fs,
            duration_ms=duration,
            samples=[round(float(v), 3) for v in y],
        )
