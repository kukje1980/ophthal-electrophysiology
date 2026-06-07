"""ISCEV standard protocol definitions.

Each protocol describes one or more *steps*. A step carries everything the
acquisition layer needs (sampling rate, sweep duration, stimulus parameters)
and everything the analysis layer needs (which markers to look for).

References: ISCEV Standard for full-field clinical ERG (2022 update,
Robson et al.), clinical PERG (2024 update), clinical VEP (2025 update,
which renamed the pattern-reversal N135 component to N145) and clinical
mfERG (2021 update).
"""
from __future__ import annotations

from typing import Dict, List

# Marker sets expected per step type ---------------------------------------
MARKERS = {
    "rod_b": ["b"],
    "combined": ["a", "b"],
    "op": ["OP1", "OP2", "OP3", "OP4"],
    "cone": ["a", "b"],
    "flicker": ["P1"],
    "perg": ["N35", "P50", "N95"],
    "vep_pr": ["N75", "P100", "N145"],  # N135 renamed to N145 (VEP 2025)
    "vep_flash": ["N2", "P2"],
    "mferg": ["N1", "P1", "N2"],
}


def _step(key, label, kind, duration_ms, sampling_rate, **stim) -> dict:
    return {
        "key": key,
        "label": label,
        "kind": kind,
        "duration_ms": duration_ms,
        "sampling_rate": sampling_rate,
        "markers": MARKERS[kind],
        "stimulus": stim,
    }


# Full ISCEV protocol catalogue --------------------------------------------
PROTOCOLS: Dict[str, dict] = {
    # ---- Full-field ERG (ffERG) -----------------------------------------
    "ffERG_standard": {
        "test_type": "ffERG",
        "label": "Full-field ERG (ISCEV standard)",
        "standard": "ISCEV ffERG 2022",
        "steps": [
            _step("DA0.01", "Dark-adapted 0.01 ERG (rod)", "rod_b",
                  250, 2000, cd_s_m2=0.01, adaptation="dark"),
            _step("DA3.0", "Dark-adapted 3.0 ERG (combined)", "combined",
                  250, 2000, cd_s_m2=3.0, adaptation="dark"),
            _step("DA10.0", "Dark-adapted 10.0 ERG (strong flash)", "combined",
                  250, 2000, cd_s_m2=10.0, adaptation="dark"),
            _step("DA3.0_OP", "Dark-adapted oscillatory potentials", "op",
                  120, 4000, cd_s_m2=3.0, adaptation="dark",
                  filter="75-300Hz"),
            _step("LA3.0", "Light-adapted 3.0 ERG (cone)", "cone",
                  150, 2000, cd_s_m2=3.0, adaptation="light",
                  background="30 cd/m2"),
            _step("LA3.0_30Hz", "Light-adapted 30 Hz flicker", "flicker",
                  300, 2000, cd_s_m2=3.0, adaptation="light", rate_hz=30),
        ],
    },
    # ---- Pattern ERG (PERG) ---------------------------------------------
    "PERG_standard": {
        "test_type": "PERG",
        "label": "Pattern ERG (ISCEV standard)",
        "standard": "ISCEV PERG 2024",
        "steps": [
            # ISCEV PERG: 0.8 deg checks, 15x15 deg field, 98% contrast,
            # transient recording at < 6 reversals/s (here 4 rev/s).
            _step("PERG", "Transient pattern ERG", "perg",
                  150, 2000, check_deg=0.8, field_deg=15,
                  reversal_hz=4, contrast=0.98),
        ],
    },
    # ---- Visual evoked potential (VEP) ----------------------------------
    "VEP_pattern_reversal": {
        "test_type": "VEP",
        "label": "Pattern-reversal VEP",
        "standard": "ISCEV VEP 2025",
        "steps": [
            # ISCEV VEP: large 1.0 deg (60') and small 0.25 deg (15') checks,
            # 2 reversals/s, field >= 15 deg.
            _step("PR_1deg", "Pattern reversal 1.0 deg (60') checks", "vep_pr",
                  300, 1000, check_deg=1.0, field_deg=15,
                  reversal_hz=2, contrast=0.97),
            _step("PR_0.25deg", "Pattern reversal 0.25 deg (15') checks",
                  "vep_pr", 300, 1000, check_deg=0.25, field_deg=15,
                  reversal_hz=2, contrast=0.97),
        ],
    },
    "VEP_flash": {
        "test_type": "VEP",
        "label": "Flash VEP",
        "standard": "ISCEV VEP 2025",
        "steps": [
            # ISCEV flash VEP: flash subtending a field of at least 20 deg.
            _step("FVEP", "Flash VEP", "vep_flash",
                  300, 1000, cd_s_m2=3.0, field_deg=20),
        ],
    },
    # ---- Multifocal ERG (mfERG) -----------------------------------------
    "mfERG_61": {
        "test_type": "mfERG",
        "label": "Multifocal ERG (61 hexagons)",
        "standard": "ISCEV mfERG 2021",
        "steps": [
            # ISCEV mfERG: light-adapted, 61/103 hexagons over 40-50 deg,
            # >=90% contrast, 60-75 Hz base frame rate.
            _step("mfERG61", "61-hexagon mfERG (summed)", "mferg",
                  80, 2000, hexagons=61, field_deg=50, adaptation="light",
                  contrast=0.98, frame_hz=75, filter="10-300Hz"),
        ],
    },
    "mfERG_103": {
        "test_type": "mfERG",
        "label": "Multifocal ERG (103 hexagons)",
        "standard": "ISCEV mfERG 2021",
        "steps": [
            _step("mfERG103", "103-hexagon mfERG (summed)", "mferg",
                  80, 2000, hexagons=103, field_deg=50, adaptation="light",
                  contrast=0.98, frame_hz=75, filter="10-300Hz"),
        ],
    },
}

# Group protocols by test type for the UI ----------------------------------
TEST_TYPES: Dict[str, List[dict]] = {}
for _key, _proto in PROTOCOLS.items():
    TEST_TYPES.setdefault(_proto["test_type"], []).append(
        {"key": _key, "label": _proto["label"]}
    )


def get_protocol(key: str) -> dict:
    if key not in PROTOCOLS:
        raise KeyError(f"Unknown protocol: {key}")
    return PROTOCOLS[key]
