"""Stateful real-time filters for streamed samples (noise reduction).

These keep their filter state across chunks, so they can be applied to a
continuous stream chunk-by-chunk without discontinuities:

  * :class:`Notch`   — 2nd-order IIR notch (RBJ biquad) to remove mains hum
                       (50/60 Hz) from the raw stream.
  * :class:`DCBlock` — 1st-order high-pass to remove DC offset / slow drift
                       (baseline correction) before averaging.

Both are pure numpy so they add no dependency.
"""
from __future__ import annotations

import math

import numpy as np


class Notch:
    """Biquad notch at ``f0`` Hz with quality factor ``q`` (bandwidth ~ f0/q)."""

    def __init__(self, fs: float, f0: float = 60.0, q: float = 30.0):
        w0 = 2.0 * math.pi * f0 / fs
        alpha = math.sin(w0) / (2.0 * q)
        cos_w0 = math.cos(w0)
        a0 = 1.0 + alpha
        self.b0 = 1.0 / a0
        self.b1 = -2.0 * cos_w0 / a0
        self.b2 = 1.0 / a0
        self.a1 = -2.0 * cos_w0 / a0
        self.a2 = (1.0 - alpha) / a0
        self._z1 = 0.0
        self._z2 = 0.0

    def process(self, x: np.ndarray) -> np.ndarray:
        y = np.empty_like(x, dtype=float)
        z1, z2 = self._z1, self._z2
        b0, b1, b2, a1, a2 = self.b0, self.b1, self.b2, self.a1, self.a2
        for i, xi in enumerate(x):  # direct form II transposed
            yi = b0 * xi + z1
            z1 = b1 * xi - a1 * yi + z2
            z2 = b2 * xi - a2 * yi
            y[i] = yi
        self._z1, self._z2 = z1, z2
        return y


class DCBlock:
    """1st-order high-pass (DC blocker): y[n] = x[n] - x[n-1] + R*y[n-1]."""

    def __init__(self, fs: float, fc: float = 0.3):
        self.r = 1.0 - (2.0 * math.pi * fc / fs)
        self._x1 = 0.0
        self._y1 = 0.0

    def process(self, x: np.ndarray) -> np.ndarray:
        y = np.empty_like(x, dtype=float)
        x1, y1, r = self._x1, self._y1, self.r
        for i, xi in enumerate(x):
            yi = xi - x1 + r * y1
            y[i] = yi
            x1, y1 = xi, yi
        self._x1, self._y1 = x1, y1
        return y


class FilterChain:
    """Apply a sequence of stateful filters in order."""

    def __init__(self, *filters):
        self.filters = [f for f in filters if f is not None]

    def process(self, x: np.ndarray) -> np.ndarray:
        for f in self.filters:
            x = f.process(x)
        return x
