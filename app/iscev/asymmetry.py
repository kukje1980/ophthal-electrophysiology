"""Interocular (OD vs OS) comparison and exam-level analysis summary.

ISCEV reports interpret each eye against the laboratory reference range *and*
against the fellow eye: a P100 that is within normal limits in both eyes can
still be abnormal when one eye lags the other by more than ~10 ms, and a
relative amplitude loss of more than ~50 % is suspicious even when both eyes
are nominally "normal".

The thresholds below are representative demonstration values (like the
built-in reference ranges) and should be replaced by laboratory data.
Interocular latency difference is in ms; the amplitude ratio is the smaller
amplitude divided by the larger one (1.0 = symmetric).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional

# (step_key, marker) -> limits. "*" matches any step for that marker.
INTEROCULAR_LIMITS: Dict[tuple, dict] = {
    # pattern-reversal VEP P100: the classic interocular latency criterion
    ("PR_1deg", "P100"): {"lat_diff_border": 6.0, "lat_diff_abn": 10.0,
                          "amp_ratio_border": 0.6, "amp_ratio_abn": 0.5},
    ("PR_0.25deg", "P100"): {"lat_diff_border": 6.0, "lat_diff_abn": 10.0,
                             "amp_ratio_border": 0.6, "amp_ratio_abn": 0.5},
    ("FVEP", "P2"): {"lat_diff_border": 10.0, "lat_diff_abn": 15.0,
                     "amp_ratio_border": 0.6, "amp_ratio_abn": 0.5},
    # PERG: P50 is very reproducible between eyes
    ("PERG", "P50"): {"lat_diff_border": 3.0, "lat_diff_abn": 5.0,
                      "amp_ratio_border": 0.75, "amp_ratio_abn": 0.6},
    ("PERG", "N95"): {"lat_diff_border": 5.0, "lat_diff_abn": 8.0,
                      "amp_ratio_border": 0.7, "amp_ratio_abn": 0.55},
    # ffERG: amplitude asymmetry matters more than small timing shifts
    ("*", "a"): {"lat_diff_border": 2.0, "lat_diff_abn": 4.0,
                 "amp_ratio_border": 0.7, "amp_ratio_abn": 0.55},
    ("*", "b"): {"lat_diff_border": 3.0, "lat_diff_abn": 6.0,
                 "amp_ratio_border": 0.7, "amp_ratio_abn": 0.55},
}
# fallback for any other marker
_GENERIC = {"lat_diff_border": 6.0, "lat_diff_abn": 10.0,
            "amp_ratio_border": 0.7, "amp_ratio_abn": 0.5}

_ORDER = {"normal": 0, "borderline": 1, "abnormal": 2}


def interocular_limits(step_key: str, marker: str) -> dict:
    return (INTEROCULAR_LIMITS.get((step_key, marker))
            or INTEROCULAR_LIMITS.get(("*", marker))
            or _GENERIC)


def _worse(a: str, b: str) -> str:
    return a if _ORDER[a] >= _ORDER[b] else b


def compare_eyes(step_key: str, marker: str, od: dict, os_: dict) -> dict:
    """Compare one marker between the two eyes.

    ``od`` / ``os_`` are measurement dicts with ``latency_ms`` and
    ``amplitude_uv``. Returns the latency difference, the amplitude ratio and
    a flag for each plus an overall flag.
    """
    lim = interocular_limits(step_key, marker)
    lat_diff = abs(float(od["latency_ms"]) - float(os_["latency_ms"]))
    a1, a2 = abs(float(od["amplitude_uv"])), abs(float(os_["amplitude_uv"]))
    hi, lo = max(a1, a2), min(a1, a2)
    amp_ratio = (lo / hi) if hi > 0 else 1.0

    if lat_diff > lim["lat_diff_abn"]:
        lat_flag = "abnormal"
    elif lat_diff > lim["lat_diff_border"]:
        lat_flag = "borderline"
    else:
        lat_flag = "normal"

    if amp_ratio < lim["amp_ratio_abn"]:
        amp_flag = "abnormal"
    elif amp_ratio < lim["amp_ratio_border"]:
        amp_flag = "borderline"
    else:
        amp_flag = "normal"

    # which eye is the "worse" one for the narrative
    slower = "OD" if od["latency_ms"] > os_["latency_ms"] else "OS"
    smaller = "OD" if a1 < a2 else "OS"
    return {
        "marker": marker,
        "lat_diff_ms": round(lat_diff, 2),
        "lat_flag": lat_flag,
        "slower_eye": slower if lat_diff > 0 else None,
        "amp_ratio": round(amp_ratio, 3),
        "amp_flag": amp_flag,
        "smaller_eye": smaller if a1 != a2 else None,
        "flag": _worse(lat_flag, amp_flag),
        "limits": lim,
    }


def analyse_exam(waveforms: List) -> dict:
    """Exam-level analysis from ORM/dict waveforms.

    Each waveform needs ``step``, ``eye`` and ``measurements`` (objects or
    dicts with ``marker``, ``latency_ms``, ``amplitude_uv``, ``flag``).

    Returns::

        {
          "steps": [{"step": ..., "interocular": [...], "ratios": {...}}],
          "abnormal": [...], "borderline": [...],   # per-eye findings
          "asymmetry": [...],                        # interocular findings
          "overall": "normal" | "borderline" | "abnormal",
          "summary": ["...", ...],                   # plain-language lines
        }
    """
    def _get(obj, key):
        return obj[key] if isinstance(obj, dict) else getattr(obj, key)

    by_step: Dict[str, Dict[str, dict]] = defaultdict(dict)
    order: List[str] = []
    for wf in waveforms:
        step, eye = _get(wf, "step"), _get(wf, "eye")
        if step not in by_step:
            order.append(step)
        ms = {}
        for m in _get(wf, "measurements"):
            ms[_get(m, "marker")] = {
                "marker": _get(m, "marker"),
                "latency_ms": float(_get(m, "latency_ms")),
                "amplitude_uv": float(_get(m, "amplitude_uv")),
                "flag": _get(m, "flag") or "normal",
            }
        by_step[step][eye] = ms

    steps_out, abnormal, borderline, asym, summary = [], [], [], [], []
    overall = "normal"

    for step in order:
        eyes = by_step[step]
        # per-eye flags
        for eye, ms in eyes.items():
            for m in ms.values():
                line = (f"{step} {eye} {m['marker']}: "
                        f"{m['latency_ms']:.1f} ms / {m['amplitude_uv']:.2f} µV")
                if m["flag"] == "abnormal":
                    abnormal.append({"step": step, "eye": eye, **m})
                    summary.append(f"[비정상] {line}")
                elif m["flag"] == "borderline":
                    borderline.append({"step": step, "eye": eye, **m})
                    summary.append(f"[경계] {line}")
                overall = _worse(overall, m["flag"])

        # interocular comparison
        inter = []
        if "OD" in eyes and "OS" in eyes:
            for marker in eyes["OD"]:
                if marker in eyes["OS"]:
                    c = compare_eyes(step, marker, eyes["OD"][marker],
                                     eyes["OS"][marker])
                    inter.append(c)
                    if c["flag"] != "normal":
                        asym.append({"step": step, **c})
                        bits = []
                        if c["lat_flag"] != "normal":
                            bits.append(f"잠복기 차이 {c['lat_diff_ms']:.1f} ms"
                                        f" ({c['slower_eye']} 지연)")
                        if c["amp_flag"] != "normal":
                            bits.append(f"진폭비 {c['amp_ratio']:.2f}"
                                        f" ({c['smaller_eye']} 감소)")
                        tag = "비정상" if c["flag"] == "abnormal" else "경계"
                        summary.append(f"[양안차 {tag}] {step} {marker}: "
                                       + ", ".join(bits))
                        overall = _worse(overall, c["flag"])

        # derived ratios (PERG N95:P50 per eye)
        ratios: Dict[str, Optional[float]] = {}
        for eye, ms in eyes.items():
            if "P50" in ms and "N95" in ms and ms["P50"]["amplitude_uv"] > 0:
                ratios[f"N95:P50 {eye}"] = round(
                    ms["N95"]["amplitude_uv"] / ms["P50"]["amplitude_uv"], 2)
        steps_out.append({"step": step, "interocular": inter, "ratios": ratios})

    if not summary:
        summary.append("모든 마커가 정상 범위이며 양안 대칭입니다.")

    return {
        "steps": steps_out,
        "abnormal": abnormal,
        "borderline": borderline,
        "asymmetry": asym,
        "overall": overall,
        "summary": summary,
    }
