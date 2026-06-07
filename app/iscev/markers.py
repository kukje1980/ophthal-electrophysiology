"""Automatic marker (peak/trough) detection for ISCEV waveforms.

Given a recorded trace and the protocol step it belongs to, locate the
standard components (a-wave, b-wave, P50, N95, P100, ...), measure their
implicit time (latency) and amplitude, and classify each against the
reference ranges.

Amplitudes follow common clinical conventions:
  * trough markers are measured from the pre-stimulus baseline,
  * a peak that follows a named trough (e.g. b after a, P100 after N75)
    is measured peak-to-trough from that preceding component.
"""
from __future__ import annotations

from typing import List

import numpy as np

from app.iscev.reference import classify

# polarity: "neg" -> look for a minimum, "pos" -> look for a maximum.
# win: (start_ms, end_ms) search window.
# from: optional preceding marker used as the amplitude reference.
_DEFAULT = {
    "a": {"win": (8, 30), "pol": "neg"},
    "b": {"win": (30, 90), "pol": "pos", "from": "a"},
    "OP1": {"win": (12, 22), "pol": "pos"},
    "OP2": {"win": (18, 28), "pol": "pos"},
    "OP3": {"win": (24, 34), "pol": "pos"},
    "OP4": {"win": (30, 45), "pol": "pos"},
    "N1": {"win": (8, 25), "pol": "neg"},
    "P1": {"win": (25, 45), "pol": "pos", "from": "N1"},
    "N35": {"win": (25, 45), "pol": "neg"},
    "P50": {"win": (40, 65), "pol": "pos", "from": "N35"},
    "N95": {"win": (80, 110), "pol": "neg", "from": "P50"},
    "N75": {"win": (60, 90), "pol": "neg"},
    "P100": {"win": (85, 125), "pol": "pos", "from": "N75"},
    # N145: renamed from N135 in the ISCEV VEP 2025 standard.
    "N145": {"win": (120, 180), "pol": "neg", "from": "P100"},
    "N2": {"win": (60, 110), "pol": "neg"},
    "P2": {"win": (90, 160), "pol": "pos", "from": "N2"},
}

# Step-specific overrides where the same marker name needs a different window.
# The mfERG components N1/P1/N2 peak much earlier (~15/30/55 ms) than the
# flash-VEP N1/P1/N2, so they get their own short windows per step.
_OVERRIDE = {
    ("LA3.0_30Hz", "P1"): {"win": (12, 40), "pol": "pos"},
    ("mfERG61", "N1"): {"win": (8, 22), "pol": "neg"},
    ("mfERG61", "P1"): {"win": (22, 45), "pol": "pos", "from": "N1"},
    ("mfERG61", "N2"): {"win": (45, 75), "pol": "neg", "from": "P1"},
    ("mfERG103", "N1"): {"win": (8, 22), "pol": "neg"},
    ("mfERG103", "P1"): {"win": (22, 45), "pol": "pos", "from": "N1"},
    ("mfERG103", "N2"): {"win": (45, 75), "pol": "neg", "from": "P1"},
}


def _config(step_key: str, marker: str) -> dict:
    return _OVERRIDE.get((step_key, marker), _DEFAULT.get(marker, {}))


def detect_markers(samples: List[float], duration_ms: float,
                   step_key: str, markers: List[str]) -> List[dict]:
    """Detect the requested markers on a single trace.

    Returns a list of dicts: {marker, latency_ms, amplitude_uv, flag}.
    """
    y = np.asarray(samples, dtype=float)
    n = len(y)
    if n == 0:
        return []

    t = np.linspace(0, duration_ms, n, endpoint=False)
    # Pre-stimulus baseline: mean of the first 5 ms (or first 5 samples).
    base_n = max(1, int(n * 5.0 / duration_ms)) if duration_ms else 1
    baseline = float(np.mean(y[:base_n]))

    found = {}  # marker -> (idx, value)
    results: List[dict] = []

    # Detect in a stable order so "from" references already exist.
    order = sorted(markers, key=lambda m: _config(step_key, m).get("win", (0, 0))[0])

    for marker in order:
        cfg = _config(step_key, marker)
        if not cfg:
            continue
        w0, w1 = cfg["win"]
        mask = (t >= w0) & (t <= w1)
        if not mask.any():
            continue
        idxs = np.where(mask)[0]
        seg = y[idxs]
        if cfg["pol"] == "neg":
            local = int(np.argmin(seg))
        else:
            local = int(np.argmax(seg))
        idx = int(idxs[local])
        value = float(y[idx])
        latency = float(t[idx])

        ref_marker = cfg.get("from")
        if ref_marker and ref_marker in found:
            ref_value = found[ref_marker][1]
            amplitude = abs(value - ref_value)
        else:
            amplitude = abs(value - baseline)

        found[marker] = (idx, value)
        results.append({
            "marker": marker,
            "latency_ms": round(latency, 2),
            "amplitude_uv": round(amplitude, 2),
            "flag": classify(step_key, marker, latency, amplitude),
        })

    # Keep chronological order in the output for display.
    results.sort(key=lambda r: r["latency_ms"])
    return results
