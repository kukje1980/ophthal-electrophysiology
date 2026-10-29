"""Real-time sample streaming — the continuous face of an amplifier.

The sweep-based ``Amplifier`` contract models averaged acquisition; real
recorders stream samples continuously and the host epochs around triggers.
``SampleStream`` is that continuous contract:

    stream.open()                       # start the transport
    while running:
        chunk = stream.read()           # new samples since the last read,
                                        # shape (n,) or (len(signals), n)
        # host: ring buffer -> epoch on each trigger -> average
        imp = stream.impedances()       # optional live electrode impedance
    stream.close()

Concrete drivers (serial / TCP / vendor SDK / LSL) implement the transport;
the built-in :class:`SimulatedStream` generates a live, wall-clock-paced
two-eye (OD/OS) ERG-like signal with periodic triggers and drifting
impedances so the whole real-time path works without hardware.
"""
from __future__ import annotations

import math
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Type

import numpy as np


def split_options(conn: str):
    """Split ``'<head>;key=value;...'`` into ``(head, {key: value})``."""
    parts = [p.strip() for p in (conn or "").split(";")]
    opts = {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            opts[k.strip()] = v.strip()
    return parts[0], opts


class SampleStream(ABC):
    """A continuous source of microvolt samples at a fixed sampling rate."""

    name: str = "abstract-stream"

    def __init__(self, connection: str = "", sampling_rate: float = 1000.0):
        self.connection = connection
        self.sampling_rate = sampling_rate
        self.running = False
        #: electrode channel labels
        self.channels: List[str] = ["active"]
        #: labels of the signal rows returned by read() — "OD" / "OS" when a
        #: row is a known eye, so the host can record both eyes at once
        self.signals: List[str] = ["ch1"]
        #: samples between hardware triggers (None if no periodic trigger)
        self.trigger_period_samples: Optional[int] = None
        #: local sample indices of external triggers found in the last read()
        #: (used by drivers whose triggers are event-based, e.g. a DAQ line)
        self.last_triggers: List[int] = []

    @abstractmethod
    def open(self) -> None:
        """Start the transport / begin streaming. Set ``running = True``."""

    @abstractmethod
    def read(self) -> np.ndarray:
        """Return all samples that arrived since the previous call (may be
        empty): shape ``(n,)`` for one signal or ``(len(signals), n)``.
        Should not block for long; the caller polls in a loop."""

    @abstractmethod
    def close(self) -> None:
        """Stop streaming and release the transport."""

    def impedances(self) -> Optional[Dict[str, float]]:
        """Return per-electrode impedance in kΩ, or None if unsupported."""
        return None


class SimulatedStream(SampleStream):
    """Wall-clock-paced simulator: a repeating cornea-negative a-wave +
    cornea-positive b-wave every 500 ms on a noisy baseline for both eyes
    (OD, OS), with a trigger at the start of each epoch and drifting
    electrode impedances.

    Connection options exercise the bench checks without hardware:
    ``;hum=<µV>`` adds mains hum (``;mains=50|60``, default 60 Hz),
    ``;blink=1`` adds periodic blink artifacts and ``;cal=<µV>`` replaces the
    ERG by a 1 Hz square calibration pulse of that amplitude (like an
    amplifier's CAL button), e.g. ``sim://localhost;hum=20;blink=1``.
    """

    name = "sim-stream"
    _EYE_GAIN = (1.0, 0.92)  # OS slightly smaller than OD

    def __init__(self, connection: str = "sim://localhost",
                 sampling_rate: float = 1000.0):
        super().__init__(connection, sampling_rate)
        self.channels = ["OD-active", "OD-ref", "OS-active", "OS-ref", "ground"]
        self.signals = ["OD", "OS"]
        self.trigger_period_samples = int(round(0.5 * sampling_rate))
        self._count = 0
        self._next_time = 0.0
        _, opts = split_options(connection)
        self._hum = float(opts.get("hum") or 0.0)
        self._mains = float(opts.get("mains") or 60.0)
        self._cal = float(opts.get("cal") or 0.0)
        self._blink = opts.get("blink") in ("1", "true")

    def open(self) -> None:
        self._count = 0
        self._next_time = time.time()
        self.running = True

    def _synth(self, idx: np.ndarray, ch: int) -> np.ndarray:
        fs = self.sampling_rate
        t = idx / fs
        if self._cal:  # square CAL pulse: 500 ms high / 500 ms low
            y = np.where((t % 1.0) < 0.5, self._cal, 0.0)
        else:
            phase_ms = (t % 0.5) * 1000.0
            y = 210.0 * np.exp(-((phase_ms - 110.0) ** 2) / (2 * 26.0 ** 2))
            y += -70.0 * np.exp(-((phase_ms - 22.0) ** 2) / (2 * 5.0 ** 2))
            y *= self._EYE_GAIN[ch]
            y += 8.0 * np.sin(2 * np.pi * 8.0 * t)
        if self._hum:
            y += self._hum * np.sin(2 * np.pi * self._mains * t + ch)
        if self._blink:  # ~600 µV, 40 ms-wide blink once every 3.7 s
            y += 600.0 * np.exp(-(((t % 3.7) - 1.0) ** 2) / (2 * 0.04 ** 2))
        start = int(idx[0]) if len(idx) else 0
        rng = np.random.default_rng([start & 0xFFFFFFFF, ch])
        return y + rng.normal(0, 3.0, size=len(idx))

    def read(self) -> np.ndarray:
        if not self.running:
            return np.empty((len(self.signals), 0))
        now = time.time()
        n_due = int((now - self._next_time) * self.sampling_rate)
        if n_due <= 0:
            return np.empty((len(self.signals), 0))
        n_due = min(n_due, int(self.sampling_rate))
        idx = np.arange(self._count, self._count + n_due)
        samples = np.vstack([self._synth(idx, ch)
                             for ch in range(len(self.signals))])
        self._count += n_due
        self._next_time += n_due / self.sampling_rate
        return samples

    def impedances(self) -> Dict[str, float]:
        t = time.time()
        base = {"OD-active": 2.6, "OD-ref": 1.9, "OS-active": 4.6,
                "OS-ref": 2.2, "ground": 1.1}
        return {k: round(max(0.4, v + 0.7 * math.sin(t / 3.0 + i)), 2)
                for i, (k, v) in enumerate(base.items())}

    def close(self) -> None:
        self.running = False


# ---------------------------------------------------------------------------
# Stream driver registry (mirrors the sweep-device registry)
# ---------------------------------------------------------------------------
_STREAM_DRIVERS: Dict[str, Type[SampleStream]] = {}


def register_stream(name: str, cls: Type[SampleStream]) -> None:
    _STREAM_DRIVERS[name] = cls


def list_stream_drivers() -> List[str]:
    return sorted(_STREAM_DRIVERS)


def get_stream(name: str, connection: str = "",
               sampling_rate: float = 1000.0) -> SampleStream:
    if name not in _STREAM_DRIVERS:
        raise KeyError(
            f"Unknown stream driver '{name}'. "
            f"Available: {', '.join(list_stream_drivers()) or '(none)'}"
        )
    return _STREAM_DRIVERS[name](connection=connection,
                                 sampling_rate=sampling_rate)


def get_live_stream(driver: Optional[str] = None,
                    connection: Optional[str] = None,
                    sampling_rate: float = 1000.0) -> SampleStream:
    """Return the configured live stream (driver + connection overridable)."""
    from app.config import settings

    name = driver or settings.LIVE_STREAM_DRIVER
    conn = connection if connection is not None else settings.STREAM_CONNECTION
    return get_stream(name, conn, sampling_rate)


register_stream(SimulatedStream.name, SimulatedStream)
# Real transport drivers register themselves on import.
from app.acquisition import hw_streams  # noqa: E402,F401
