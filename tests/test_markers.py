"""Unit tests for the ISCEV analysis layer (no HTTP)."""
import numpy as np

from app.iscev import (
    analyse_exam, classify, compare_eyes, detect_markers, marker_config,
    remeasure,
)


def _gauss(t, amp, c, w):
    return amp * np.exp(-((t - c) ** 2) / (2 * w ** 2))


def synthetic_vep(duration_ms=300, fs=1000, p100_at=100.0, gain=1.0):
    t = np.linspace(0, duration_ms, int(duration_ms / 1000 * fs), endpoint=False)
    y = (_gauss(t, -3.5, 75, 10) + _gauss(t, 11.0, p100_at, 12)
         + _gauss(t, -4.5, 145, 22)) * gain
    y[t < 4] = 0
    return y.tolist(), duration_ms


def test_detect_markers_finds_pattern_reversal_components():
    y, dur = synthetic_vep()
    ms = {m["marker"]: m for m in detect_markers(y, dur, "PR_1deg", ["N75", "P100", "N145"])}
    assert set(ms) == {"N75", "P100", "N145"}
    # the N75 trough is pulled slightly earlier by the overlapping P100 peak
    assert abs(ms["N75"]["latency_ms"] - 75) <= 5
    assert abs(ms["P100"]["latency_ms"] - 100) <= 2
    assert abs(ms["N145"]["latency_ms"] - 145) <= 3
    # P100 is measured peak-to-trough from N75 -> ~ 11 + 3.5 µV
    assert 12 < ms["P100"]["amplitude_uv"] < 16
    assert all(m["is_auto"] for m in ms.values())
    assert ms["P100"]["flag"] == "normal"


def test_delayed_p100_is_flagged():
    y, dur = synthetic_vep(p100_at=130)
    ms = {m["marker"]: m for m in detect_markers(y, dur, "PR_1deg", ["N75", "P100", "N145"])}
    # automatic detection is confined to the 85-125 ms search window: the
    # peak it finds sits at the window edge, past the 115 ms limit but
    # within the 10 % borderline band
    assert 115 < ms["P100"]["latency_ms"] <= 125
    assert ms["P100"]["flag"] == "borderline"
    # an operator placing the cursor on the true peak gets 'abnormal'
    manual = {m["marker"]: m for m in remeasure(
        y, dur, "PR_1deg", [("N75", ms["N75"]["latency_ms"]), ("P100", 130.0)],
        manual={"P100"})}
    assert manual["P100"]["latency_ms"] == 130.0
    assert manual["P100"]["flag"] == "abnormal"
    assert manual["P100"]["is_auto"] is False


def test_remeasure_moves_cursor_and_updates_dependents():
    y, dur = synthetic_vep()
    auto = {m["marker"]: m for m in detect_markers(y, dur, "PR_1deg", ["N75", "P100", "N145"])}
    moved = {m["marker"]: m for m in remeasure(
        y, dur, "PR_1deg",
        [("N75", 90.0), ("P100", auto["P100"]["latency_ms"]), ("N145", auto["N145"]["latency_ms"])],
        manual={"N75"})}
    assert moved["N75"]["latency_ms"] == 90.0
    assert moved["N75"]["is_auto"] is False
    assert moved["P100"]["is_auto"] is True
    # N75 moved towards the P100 peak -> peak-to-trough amplitude shrinks
    assert moved["P100"]["amplitude_uv"] < auto["P100"]["amplitude_uv"]


def test_marker_config_overrides_per_step():
    assert marker_config("mfERG61", "P1")["win"] == (22, 45)
    assert marker_config("FVEP", "P2")["from"] == "N2"
    assert marker_config("PERG", "nope") == {}


def test_classify_borderline_band():
    ref = {"amp_min": 10, "lat_max": 100}
    assert classify("x", "y", 95, 12, ref=ref) == "normal"
    assert classify("x", "y", 105, 12, ref=ref) == "borderline"   # <10% over
    assert classify("x", "y", 120, 12, ref=ref) == "abnormal"
    assert classify("x", "y", 95, 9.5, ref=ref) == "borderline"
    assert classify("x", "y", 95, 5, ref=ref) == "abnormal"


def test_compare_eyes_interocular_latency_and_amplitude():
    od = {"latency_ms": 100, "amplitude_uv": 10}
    os_ = {"latency_ms": 112, "amplitude_uv": 4}
    c = compare_eyes("PR_1deg", "P100", od, os_)
    assert c["lat_diff_ms"] == 12 and c["lat_flag"] == "abnormal"
    assert c["slower_eye"] == "OS"
    assert c["amp_ratio"] == 0.4 and c["amp_flag"] == "abnormal"
    assert c["smaller_eye"] == "OS" and c["flag"] == "abnormal"

    sym = compare_eyes("PR_1deg", "P100", od, {"latency_ms": 103, "amplitude_uv": 9})
    assert sym["flag"] == "normal"


def test_analyse_exam_builds_summary():
    wfs = [
        {"step": "PR_1deg", "eye": "OD", "measurements": [
            {"marker": "P100", "latency_ms": 100, "amplitude_uv": 10, "flag": "normal"}]},
        {"step": "PR_1deg", "eye": "OS", "measurements": [
            {"marker": "P100", "latency_ms": 118, "amplitude_uv": 9, "flag": "abnormal"}]},
    ]
    a = analyse_exam(wfs)
    assert a["overall"] == "abnormal"
    assert len(a["abnormal"]) == 1 and a["abnormal"][0]["eye"] == "OS"
    assert len(a["asymmetry"]) == 1 and a["asymmetry"][0]["marker"] == "P100"
    assert any("양안차" in s for s in a["summary"])

    normal = analyse_exam([{"step": "PERG", "eye": "OD", "measurements": [
        {"marker": "P50", "latency_ms": 50, "amplitude_uv": 4, "flag": "normal"},
        {"marker": "N95", "latency_ms": 95, "amplitude_uv": 6, "flag": "normal"}]}])
    assert normal["overall"] == "normal"
    assert normal["steps"][0]["ratios"]["N95:P50 OD"] == 1.5
