"""Approximate adult normal reference ranges for ISCEV markers.

These are representative ranges for demonstration. Each laboratory must
establish its own normative data; values are intentionally kept in one place
so they are easy to replace with lab-specific norms.

Each entry maps a (step_key, marker) to a dict with optional limits:
    amp_min / amp_max : microvolts
    lat_min / lat_max : milliseconds (implicit/peak time)
Amplitude is compared on its absolute value.
"""
from __future__ import annotations

REFERENCE_RANGES = {
    # ffERG ---------------------------------------------------------------
    ("DA0.01", "b"): {"amp_min": 160, "lat_max": 110},
    ("DA3.0", "a"): {"amp_min": 150, "lat_max": 25},
    ("DA3.0", "b"): {"amp_min": 250, "lat_max": 55},
    ("DA10.0", "a"): {"amp_min": 180, "lat_max": 22},
    ("DA10.0", "b"): {"amp_min": 280, "lat_max": 50},
    ("LA3.0", "a"): {"amp_min": 20, "lat_max": 18},
    ("LA3.0", "b"): {"amp_min": 80, "lat_max": 36},
    ("LA3.0_30Hz", "P1"): {"amp_min": 50, "lat_max": 32},
    # PERG ----------------------------------------------------------------
    ("PERG", "P50"): {"amp_min": 2.0, "lat_min": 45, "lat_max": 60},
    ("PERG", "N95"): {"amp_min": 3.0, "lat_min": 90, "lat_max": 105},
    # VEP -----------------------------------------------------------------
    ("PR_1deg", "P100"): {"amp_min": 5.0, "lat_min": 90, "lat_max": 115},
    ("PR_0.25deg", "P100"): {"amp_min": 4.0, "lat_min": 95, "lat_max": 120},
    ("FVEP", "P2"): {"amp_min": 4.0, "lat_min": 90, "lat_max": 150},
    # mfERG ---------------------------------------------------------------
    ("mfERG61", "P1"): {"amp_min": 60, "lat_max": 40},
    ("mfERG103", "P1"): {"amp_min": 40, "lat_max": 40},
}


def classify(step_key: str, marker: str, latency_ms: float,
             amplitude_uv: float) -> str:
    """Return 'normal', 'borderline' or 'abnormal' for a measurement.

    A value within limits is normal; within 10% past a limit is borderline;
    beyond that is abnormal. Markers without a reference return 'normal'.
    """
    ref = REFERENCE_RANGES.get((step_key, marker))
    if not ref:
        return "normal"

    amp = abs(amplitude_uv)
    status = "normal"

    def degrade(new):
        nonlocal status
        order = {"normal": 0, "borderline": 1, "abnormal": 2}
        if order[new] > order[status]:
            status = new

    if "amp_min" in ref:
        if amp < ref["amp_min"] * 0.9:
            degrade("abnormal")
        elif amp < ref["amp_min"]:
            degrade("borderline")
    if "lat_max" in ref:
        if latency_ms > ref["lat_max"] * 1.1:
            degrade("abnormal")
        elif latency_ms > ref["lat_max"]:
            degrade("borderline")
    if "lat_min" in ref:
        if latency_ms < ref["lat_min"] * 0.9:
            degrade("abnormal")
        elif latency_ms < ref["lat_min"]:
            degrade("borderline")

    return status
