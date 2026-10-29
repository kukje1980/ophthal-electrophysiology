"""Automatic marker (peak/trough) detection for ISCEV waveforms.

Given a recorded trace and the protocol step it belongs to, locate the
standard components (a-wave, b-wave, P50, N95, P100, ...), measure their
implicit time (latency) and amplitude, and classify each against the
reference ranges.

Amplitudes follow common clinical conventions:
  * trough markers are measured from the pre-stimulus baseline,
  * a peak that follows a named trough (e.g. b after a, P100 after N75)
    is measured peak-to-trough from that preceding component.

The same measurement rules are applied when an operator moves a cursor by
hand (:func:`remeasure`), so automatic and manual markers are always
comparable.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

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


def marker_config(step_key: str, marker: str) -> dict:
    """Search window / polarity / amplitude reference for a marker on a step
    (empty dict when the marker is unknown)."""
    return _OVERRIDE.get((step_key, marker), _DEFAULT.get(marker, {}))


_config = marker_config  # backwards-compatible alias


def known_markers() -> List[str]:
    """Every marker name the detector knows about."""
    return sorted(_DEFAULT.keys())


def _time_axis(n: int, duration_ms: float) -> np.ndarray:
    return np.linspace(0, duration_ms, n, endpoint=False)


def _baseline(y: np.ndarray, duration_ms: float) -> float:
    """Pre-stimulus baseline: mean of the first 5 ms (or first 5 samples)."""
    n = len(y)
    base_n = max(1, int(n * 5.0 / duration_ms)) if duration_ms else 1
    return float(np.mean(y[:base_n]))


def _index_at(t: np.ndarray, latency_ms: float) -> int:
    """Sample index nearest to a latency (clamped into the trace)."""
    if len(t) < 2:
        return 0
    dt = float(t[1] - t[0])
    return int(np.clip(round(latency_ms / dt), 0, len(t) - 1))


def _measure_all(y: np.ndarray, duration_ms: float, step_key: str,
                 positions: Iterable[Tuple[str, float]],
                 ref_lookup=None, manual: Optional[set] = None) -> List[dict]:
    """Amplitude + classification for markers at known latencies.

    ``positions`` are (marker, latency_ms) pairs. Amplitude is measured from
    the referenced preceding component when it is present, else from the
    pre-stimulus baseline — identical for auto-detected and hand-placed
    cursors so the two are always comparable.
    """
    t = _time_axis(len(y), duration_ms)
    baseline = _baseline(y, duration_ms)
    manual = manual or set()

    values: Dict[str, float] = {}
    pos_list = list(positions)
    for marker, lat in pos_list:
        values[marker] = float(y[_index_at(t, lat)])

    results = []
    for marker, lat in pos_list:
        cfg = marker_config(step_key, marker)
        ref_marker = cfg.get("from")
        if ref_marker and ref_marker in values:
            amplitude = abs(values[marker] - values[ref_marker])
        else:
            amplitude = abs(values[marker] - baseline)
        idx = _index_at(t, lat)
        latency = float(t[idx])
        ref = ref_lookup(step_key, marker) if ref_lookup else None
        results.append({
            "marker": marker,
            "latency_ms": round(latency, 2),
            "amplitude_uv": round(amplitude, 2),
            "flag": classify(step_key, marker, latency, amplitude, ref=ref),
            "is_auto": marker not in manual,
        })
    results.sort(key=lambda r: r["latency_ms"])
    return results


def detect_markers(samples: List[float], duration_ms: float,
                   step_key: str, markers: List[str],
                   ref_lookup=None) -> List[dict]:
    """Detect the requested markers on a single trace.

    ``ref_lookup(step_key, marker)`` may return a laboratory limits dict (or
    None to fall back to the built-in demonstration ranges).

    Returns a list of dicts: {marker, latency_ms, amplitude_uv, flag, is_auto}.
    """
    y = np.asarray(samples, dtype=float)
    n = len(y)
    if n == 0:
        return []

    t = _time_axis(n, duration_ms)
    positions: List[Tuple[str, float]] = []
    for marker in markers:
        cfg = marker_config(step_key, marker)
        if not cfg:
            continue
        w0, w1 = cfg["win"]
        mask = (t >= w0) & (t <= w1)
        if not mask.any():
            continue
        idxs = np.where(mask)[0]
        seg = y[idxs]
        local = int(np.argmin(seg)) if cfg["pol"] == "neg" else int(np.argmax(seg))
        positions.append((marker, float(t[int(idxs[local])])))

    return _measure_all(y, duration_ms, step_key, positions, ref_lookup)


def remeasure(samples: List[float], duration_ms: float, step_key: str,
              positions: Iterable[Tuple[str, float]], ref_lookup=None,
              manual: Optional[set] = None) -> List[dict]:
    """Re-measure amplitudes and flags for markers at operator-chosen
    latencies (e.g. after a cursor was moved). ``manual`` names the markers
    that were placed by hand so ``is_auto`` is reported correctly.

    Moving one marker also re-measures the components that reference it
    (e.g. moving N75 changes the P100 peak-to-trough amplitude).
    """
    y = np.asarray(samples, dtype=float)
    if len(y) == 0:
        return []
    return _measure_all(y, duration_ms, step_key, positions, ref_lookup, manual)
