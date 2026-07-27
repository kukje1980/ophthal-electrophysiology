"""Real-time sample streaming — the continuous face of an amplifier.

The sweep-based ``Amplifier`` contract (arm -> capture one sweep) models the
averaged acquisition. Real recorders, however, stream samples continuously at
a fixed rate; the host buffers them and epochs around triggers. ``SampleStream``
is that continuous contract:

    stream.open(sampling_rate)          # start the transport
    while running:
        chunk = stream.read()           # new samples since the last read
        ring.extend(chunk)              # host-side ring buffer
        # on each trigger: epoch = ring[t0 : t0 + sweep] ; average
    stream.close()

A concrete driver implements ``open`` / ``read`` / ``close`` over its transport
(serial / TCP / vendor SDK / LSL). The built-in :class:`SimulatedStream`
generates a live, wall-clock-paced ERG-like signal so the streaming path and
the live monitor work without any hardware.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod

import numpy as np


class SampleStream(ABC):
    """A continuous source of microvolt samples at a fixed sampling rate."""

    name: str = "abstract-stream"

    def __init__(self, connection: str = "", sampling_rate: float = 1000.0):
        self.connection = connection
        self.sampling_rate = sampling_rate
        self.running = False

    @abstractmethod
    def open(self) -> None:
        """Start the transport / begin streaming. Set ``running = True``."""

    @abstractmethod
    def read(self) -> np.ndarray:
        """Return all samples that arrived since the previous call.

        May be empty. Should not block for long; the caller polls it in a
        loop and paces itself.
        """

    @abstractmethod
    def close(self) -> None:
        """Stop streaming and release the transport."""


class SimulatedStream(SampleStream):
    """Wall-clock-paced simulator: a repeating cornea-positive ERG epoch
    (b-wave bump every 500 ms) on a noisy baseline, so the live view shows a
    realistic, continuously scrolling trace."""

    name = "sim-stream"

    def __init__(self, connection: str = "sim://localhost",
                 sampling_rate: float = 1000.0):
        super().__init__(connection, sampling_rate)
        self._count = 0          # total samples emitted
        self._next_time = 0.0    # wall-clock time the next sample is due

    def open(self) -> None:
        self._count = 0
        self._next_time = time.time()
        self.running = True

    def _synth(self, idx: np.ndarray) -> np.ndarray:
        fs = self.sampling_rate
        t = idx / fs
        period = 0.5  # one evoked response every 500 ms
        phase_ms = (t % period) * 1000.0
        # b-wave-like Gaussian bump + small oscillatory ripple + drift + noise
        y = 210.0 * np.exp(-((phase_ms - 110.0) ** 2) / (2 * 26.0 ** 2))
        y += -70.0 * np.exp(-((phase_ms - 22.0) ** 2) / (2 * 5.0 ** 2))  # a-wave
        y += 8.0 * np.sin(2 * np.pi * 8.0 * t)      # slow drift
        rng = np.random.default_rng((idx[0] if len(idx) else 0) & 0xFFFFFFFF)
        y = y + rng.normal(0, 3.0, size=len(idx))
        return y

    def read(self) -> np.ndarray:
        if not self.running:
            return np.empty(0)
        now = time.time()
        n_due = int((now - self._next_time) * self.sampling_rate)
        if n_due <= 0:
            return np.empty(0)
        n_due = min(n_due, int(self.sampling_rate))  # cap a burst at 1 s
        idx = np.arange(self._count, self._count + n_due)
        samples = self._synth(idx)
        self._count += n_due
        self._next_time += n_due / self.sampling_rate
        return samples

    def close(self) -> None:
        self.running = False


def get_live_stream(sampling_rate: float = 1000.0) -> SampleStream:
    """Return a stream for the live monitor. Swappable for a real driver."""
    return SimulatedStream(sampling_rate=sampling_rate)
