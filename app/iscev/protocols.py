"""ISCEV standard protocol definitions.

Each protocol describes one or more *steps*. A step carries everything the
acquisition layer needs (sampling rate, sweep duration, stimulus parameters)
and everything the analysis layer needs (which markers to look for).

References: ISCEV standards for full-field ERG (2022 update), PERG (2013),
clinical VEP (2016) and mfERG (2021).
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
    "vep_pr": ["N75", "P100", "N135"],
    "vep_flash": ["N2", "P2"],
    "mferg": ["N1", "P1"],
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
        "steps": [
            _step("PERG", "Transient pattern ERG", "perg",
                  150, 2000, check_deg=0.8, field_deg=15,
                  reversal_hz=4, contrast=0.97),
        ],
    },
    # ---- Visual evoked potential (VEP) ----------------------------------
    "VEP_pattern_reversal": {
        "test_type": "VEP",
        "label": "Pattern-reversal VEP",
        "steps": [
            _step("PR_1deg", "Pattern reversal 1.0 deg checks", "vep_pr",
                  300, 1000, check_deg=1.0, reversal_hz=2, contrast=0.97),
            _step("PR_0.25deg", "Pattern reversal 0.25 deg checks", "vep_pr",
                  300, 1000, check_deg=0.25, reversal_hz=2, contrast=0.97),
        ],
    },
    "VEP_flash": {
        "test_type": "VEP",
        "label": "Flash VEP",
        "steps": [
            _step("FVEP", "Flash VEP", "vep_flash",
                  300, 1000, cd_s_m2=3.0),
        ],
    },
    # ---- Multifocal ERG (mfERG) -----------------------------------------
    "mfERG_61": {
        "test_type": "mfERG",
        "label": "Multifocal ERG (61 hexagons)",
        "steps": [
            _step("mfERG61", "61-hexagon mfERG (summed)", "mferg",
                  80, 2000, hexagons=61, field_deg=40),
        ],
    },
    "mfERG_103": {
        "test_type": "mfERG",
        "label": "Multifocal ERG (103 hexagons)",
        "steps": [
            _step("mfERG103", "103-hexagon mfERG (summed)", "mferg",
                  80, 2000, hexagons=103, field_deg=40),
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
