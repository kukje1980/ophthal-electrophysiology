"""Laboratory reference-range CRUD, CSV import and normative computation."""
from __future__ import annotations

import csv
import io
import statistics
from collections import defaultdict
from typing import Callable, Dict, List, Optional

import numpy as np
from sqlalchemy.orm import Session

from app.iscev.reference import REFERENCE_RANGES
from app.models import ReferenceRange

_LIMIT_KEYS = ("amp_min", "amp_max", "lat_min", "lat_max")


# -- lookup -----------------------------------------------------------------

def lookup(db: Session, step_key: str, marker: str,
           age: Optional[int] = None) -> Optional[dict]:
    """Return the limits dict for a marker, preferring an age band that
    contains ``age``, then an all-ages row. None -> caller falls back to the
    built-in demonstration values."""
    rows = (db.query(ReferenceRange)
            .filter(ReferenceRange.step_key == step_key,
                    ReferenceRange.marker == marker).all())
    if not rows:
        return None
    if age is not None:
        for r in rows:
            lo = r.age_min if r.age_min is not None else -1
            hi = r.age_max if r.age_max is not None else 10 ** 6
            if (r.age_min is not None or r.age_max is not None) and lo <= age <= hi:
                return r.limits()
    for r in rows:
        if r.age_min is None and r.age_max is None:
            return r.limits()
    return rows[0].limits()


def make_lookup(db: Session, age: Optional[int]) -> Callable[[str, str], Optional[dict]]:
    return lambda step_key, marker: lookup(db, step_key, marker, age)


# -- CRUD -------------------------------------------------------------------

def list_all(db: Session) -> List[ReferenceRange]:
    return (db.query(ReferenceRange)
            .order_by(ReferenceRange.step_key, ReferenceRange.marker,
                      ReferenceRange.age_min).all())


def upsert(db: Session, data: dict) -> ReferenceRange:
    """Create or update the row identified by (step_key, marker, age band)."""
    q = db.query(ReferenceRange).filter(
        ReferenceRange.step_key == data["step_key"],
        ReferenceRange.marker == data["marker"],
        ReferenceRange.age_min.is_(data.get("age_min")),
        ReferenceRange.age_max.is_(data.get("age_max")),
    )
    row = q.first()
    if row is None:
        row = ReferenceRange(step_key=data["step_key"], marker=data["marker"],
                             age_min=data.get("age_min"), age_max=data.get("age_max"))
        db.add(row)
    for k in (*_LIMIT_KEYS, "n", "source", "note"):
        if k in data:
            setattr(row, k, data[k])
    if not row.source:
        row.source = "lab"
    db.commit()
    db.refresh(row)
    return row


def delete(db: Session, row_id: int) -> bool:
    row = db.get(ReferenceRange, row_id)
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True


def count(db: Session) -> int:
    return db.query(ReferenceRange).count()


def seed_demo(db: Session, replace: bool = False) -> int:
    """Load the built-in demonstration ranges (source='demo')."""
    if replace:
        db.query(ReferenceRange).delete()
        db.commit()
    n = 0
    for (step_key, marker), limits in REFERENCE_RANGES.items():
        upsert(db, {"step_key": step_key, "marker": marker, **limits,
                    "source": "demo", "note": "demonstration value"})
        n += 1
    return n


# -- CSV import of ranges ---------------------------------------------------

def _num(v):
    v = (v or "").strip()
    return float(v) if v else None


def import_ranges_csv(db: Session, text: str) -> int:
    """CSV columns: step_key,marker,amp_min,amp_max,lat_min,lat_max,age_min,age_max,n,note"""
    rows = csv.DictReader(io.StringIO(text))
    n = 0
    for r in rows:
        if not (r.get("step_key") and r.get("marker")):
            continue
        data = {"step_key": r["step_key"].strip(), "marker": r["marker"].strip(),
                "source": "csv", "note": (r.get("note") or "").strip() or None}
        for k in _LIMIT_KEYS:
            data[k] = _num(r.get(k))
        for k in ("age_min", "age_max", "n"):
            v = _num(r.get(k))
            data[k] = int(v) if v is not None else None
        upsert(db, data)
        n += 1
    return n


# -- normative computation from volunteer measurements ----------------------

def compute_from_csv(text: str, method: str = "sd2") -> List[dict]:
    """Compute normative limits from normal-subject measurements.

    CSV columns: step_key,marker,latency_ms,amplitude_uv[,age]
    method 'sd2': amp_min = mean-2SD, lat_min/max = mean∓2SD
           'pct': amp_min = 5th percentile, lat_min/max = 5th/95th percentile
    Returns a list of range dicts (not yet saved).
    """
    groups: Dict[tuple, dict] = defaultdict(lambda: {"amp": [], "lat": []})
    for r in csv.DictReader(io.StringIO(text)):
        try:
            key = (r["step_key"].strip(), r["marker"].strip())
            groups[key]["amp"].append(abs(float(r["amplitude_uv"])))
            groups[key]["lat"].append(float(r["latency_ms"]))
        except (KeyError, ValueError, AttributeError):
            continue

    out = []
    for (step_key, marker), g in sorted(groups.items()):
        amp, lat = np.asarray(g["amp"]), np.asarray(g["lat"])
        n = int(len(amp))
        if n < 2:
            continue
        if method == "pct":
            amp_min = float(np.percentile(amp, 5))
            lat_min = float(np.percentile(lat, 5))
            lat_max = float(np.percentile(lat, 95))
        else:  # sd2
            amp_min = float(amp.mean() - 2 * amp.std(ddof=1))
            lat_min = float(lat.mean() - 2 * lat.std(ddof=1))
            lat_max = float(lat.mean() + 2 * lat.std(ddof=1))
        out.append({
            "step_key": step_key, "marker": marker, "n": n,
            "amp_min": round(max(0.0, amp_min), 2), "amp_max": None,
            "lat_min": round(max(0.0, lat_min), 2), "lat_max": round(lat_max, 2),
            "amp_mean": round(float(amp.mean()), 2), "amp_sd": round(float(amp.std(ddof=1)), 2),
            "lat_mean": round(float(lat.mean()), 2), "lat_sd": round(float(lat.std(ddof=1)), 2),
            "source": "computed", "note": f"{method}, n={n}",
        })
    return out


def save_computed(db: Session, ranges: List[dict]) -> int:
    n = 0
    for r in ranges:
        upsert(db, {k: r.get(k) for k in
                    ("step_key", "marker", *_LIMIT_KEYS, "n", "source", "note",
                     "age_min", "age_max")})
        n += 1
    return n
