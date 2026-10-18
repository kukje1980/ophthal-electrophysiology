"""Exam CRUD plus the acquire -> store -> auto-mark pipeline, cursor editing,
interpretation and sign-off."""
from datetime import datetime
from typing import List, Optional

import numpy as np
from sqlalchemy.orm import Session

from app.acquisition import get_active_device
from app.crud import reference as reference_crud
from app.iscev import (
    analyse_exam, detect_markers, get_protocol, marker_config, remeasure,
)
from app.models import Exam, Measurement, Patient, Waveform
from app.models.exam import STATUS_COMPLETED, STATUS_SIGNED
from app.schemas import ExamCreate, ExamRecord


class ExamLocked(Exception):
    """Raised when a signed (read-only) report is edited."""


def get(db: Session, exam_id: int) -> Optional[Exam]:
    return db.get(Exam, exam_id)


def list_for_patient(db: Session, patient_id: int) -> List[Exam]:
    return (
        db.query(Exam)
        .filter(Exam.patient_id == patient_id)
        .order_by(Exam.performed_at.desc())
        .all()
    )


def list_recent(db: Session, limit: int = 20) -> List[Exam]:
    return db.query(Exam).order_by(Exam.performed_at.desc()).limit(limit).all()


def list_unsigned(db: Session, limit: int = 50) -> List[Exam]:
    """Studies acquired but not yet signed off (the reading worklist)."""
    return (db.query(Exam).filter(Exam.status != STATUS_SIGNED)
            .order_by(Exam.performed_at.asc()).limit(limit).all())


def count_all(db: Session) -> int:
    return db.query(Exam).count()


def _ref_lookup(db: Session, patient_id: int):
    """Laboratory reference lookup for this patient's age (falls back to the
    built-in demonstration ranges when the lab has no row)."""
    patient = db.get(Patient, patient_id)
    return reference_crud.make_lookup(db, patient.age if patient else None)


def _store_trace(db: Session, exam_id: int, eye: str, step: dict,
                 samples, sampling_rate: float, duration_ms: float,
                 ref_lookup) -> Waveform:
    """Persist one trace and its auto-detected, classified markers."""
    wf = Waveform(
        exam_id=exam_id, eye=eye, step=step["key"],
        sampling_rate=sampling_rate, duration_ms=duration_ms,
        samples=list(samples),
    )
    db.add(wf)
    db.flush()  # assign wf.id
    for m in detect_markers(wf.samples, duration_ms, step["key"],
                            step["markers"], ref_lookup=ref_lookup):
        db.add(Measurement(
            waveform_id=wf.id, marker=m["marker"],
            latency_ms=m["latency_ms"], amplitude_uv=m["amplitude_uv"],
            is_auto=True, flag=m["flag"],
        ))
    return wf


def run_exam(db: Session, data: ExamCreate) -> Exam:
    """Acquire every step of a protocol for the requested eyes and persist it.

    The acquisition device is obtained from the registry, so this same code
    path works for the simulator and for any real driver.
    """
    protocol = get_protocol(data.protocol)
    device = get_active_device()
    device.configure(protocol)
    ref_lookup = _ref_lookup(db, data.patient_id)

    exam = Exam(
        patient_id=data.patient_id,
        test_type=protocol["test_type"],
        protocol=data.protocol,
        device=device.name,
        operator=data.operator,
        status=STATUS_COMPLETED,
        note=data.note,
    )
    db.add(exam)
    db.flush()  # assign exam.id

    for step in protocol["steps"]:
        for eye in data.eyes:
            trace = device.acquire_step(step, eye)
            _store_trace(db, exam.id, trace.eye, step, trace.samples,
                         trace.sampling_rate, trace.duration_ms, ref_lookup)

    db.commit()
    db.refresh(exam)
    return exam


def record_step(db: Session, data: ExamRecord) -> Exam:
    """Store a trigger-averaged epoch from the live stream as one protocol
    step (new exam, or appended to an existing one of the same patient).

    The epoch is resampled onto the step's own sampling rate / duration so
    the standard marker windows and reference ranges apply unchanged.
    """
    protocol = get_protocol(data.protocol)
    step = next((s for s in protocol["steps"] if s["key"] == data.step_key), None)
    if step is None:
        raise KeyError(f"Step '{data.step_key}' is not in protocol '{data.protocol}'")

    if data.exam_id:
        exam = db.get(Exam, data.exam_id)
        if exam is None or exam.patient_id != data.patient_id:
            raise KeyError("Exam not found for this patient")
        if exam.status == STATUS_SIGNED:
            raise ExamLocked("Exam is signed; re-open it before adding traces")
    else:
        exam = Exam(
            patient_id=data.patient_id, test_type=protocol["test_type"],
            protocol=data.protocol, device=data.device or "live-stream",
            operator=data.operator, status=STATUS_COMPLETED, note=data.note,
        )
        db.add(exam)
        db.flush()

    # resample the epoch onto the protocol step's grid
    src = np.asarray(data.samples, dtype=float)
    t_src = np.linspace(0, data.duration_ms, len(src), endpoint=False)
    n_dst = max(2, int(round(step["duration_ms"] / 1000.0 * step["sampling_rate"])))
    t_dst = np.linspace(0, step["duration_ms"], n_dst, endpoint=False)
    y = np.interp(t_dst, t_src, src)  # clamps beyond the source epoch

    _store_trace(db, exam.id, data.eye, step, y.round(3).tolist(),
                 step["sampling_rate"], step["duration_ms"],
                 _ref_lookup(db, data.patient_id))
    note = f"n={data.n_sweeps} sweeps (live)"
    exam.note = f"{exam.note}; {note}" if exam.note and note not in exam.note else (exam.note or note)
    db.commit()
    db.refresh(exam)
    return exam


def delete(db: Session, exam_id: int) -> bool:
    obj = db.get(Exam, exam_id)
    if not obj:
        return False
    db.delete(obj)
    db.commit()
    return True


# -- analysis ---------------------------------------------------------------

def analysis(exam: Exam) -> dict:
    """Interocular comparison, derived ratios and a plain-language summary."""
    return analyse_exam(exam.waveforms)


# -- cursor (marker) editing ------------------------------------------------

def _require_unlocked(exam: Exam) -> None:
    if exam.status == STATUS_SIGNED:
        raise ExamLocked("Report is signed; re-open it to edit markers")


def _apply_measurements(db: Session, wf: Waveform, manual: set) -> None:
    """Re-measure every cursor on a waveform at its current latency and
    write the amplitudes / flags back (dependent components included)."""
    ref_lookup = _ref_lookup(db, wf.exam.patient_id)
    by_marker = {m.marker: m for m in wf.measurements}
    results = remeasure(wf.samples, wf.duration_ms, wf.step,
                        [(m.marker, m.latency_ms) for m in wf.measurements],
                        ref_lookup=ref_lookup, manual=manual)
    for r in results:
        m = by_marker[r["marker"]]
        m.latency_ms = r["latency_ms"]
        m.amplitude_uv = r["amplitude_uv"]
        m.flag = r["flag"]
        m.is_auto = r["is_auto"]


def _manual_set(wf: Waveform) -> set:
    return {m.marker for m in wf.measurements if not m.is_auto}


def move_marker(db: Session, measurement_id: int, latency_ms: float) -> Optional[Measurement]:
    """Move a cursor to ``latency_ms`` (clamped into the trace) and re-measure
    it and the components that reference it."""
    m = db.get(Measurement, measurement_id)
    if m is None:
        return None
    wf = m.waveform
    _require_unlocked(wf.exam)
    m.latency_ms = float(min(max(latency_ms, 0.0), wf.duration_ms))
    m.is_auto = False
    _apply_measurements(db, wf, _manual_set(wf))
    db.commit()
    db.refresh(m)
    return m


def add_marker(db: Session, waveform_id: int, marker: str,
               latency_ms: float) -> Optional[Measurement]:
    """Place a marker by hand. Replaces an existing cursor of the same name."""
    wf = db.get(Waveform, waveform_id)
    if wf is None:
        return None
    _require_unlocked(wf.exam)
    if not marker_config(wf.step, marker):
        raise KeyError(f"Unknown marker '{marker}'")
    existing = next((x for x in wf.measurements if x.marker == marker), None)
    if existing is None:
        existing = Measurement(waveform_id=wf.id, marker=marker,
                               latency_ms=0.0, amplitude_uv=0.0)
        db.add(existing)
        wf.measurements.append(existing)
        db.flush()
    existing.latency_ms = float(min(max(latency_ms, 0.0), wf.duration_ms))
    existing.is_auto = False
    _apply_measurements(db, wf, _manual_set(wf))
    db.commit()
    db.refresh(existing)
    return existing


def remove_marker(db: Session, measurement_id: int) -> bool:
    m = db.get(Measurement, measurement_id)
    if m is None:
        return False
    wf = m.waveform
    _require_unlocked(wf.exam)
    wf.measurements.remove(m)
    db.delete(m)
    db.flush()
    if wf.measurements:
        _apply_measurements(db, wf, _manual_set(wf))
    db.commit()
    return True


def redetect(db: Session, waveform_id: int) -> Optional[Waveform]:
    """Discard every cursor on a waveform and run the automatic detection
    again (the protocol step's standard marker set)."""
    wf = db.get(Waveform, waveform_id)
    if wf is None:
        return None
    _require_unlocked(wf.exam)
    protocol = get_protocol(wf.exam.protocol)
    step = next((s for s in protocol["steps"] if s["key"] == wf.step), None)
    markers = step["markers"] if step else [m.marker for m in wf.measurements]
    for m in list(wf.measurements):
        db.delete(m)
    wf.measurements.clear()
    db.flush()
    for r in detect_markers(wf.samples, wf.duration_ms, wf.step, markers,
                            ref_lookup=_ref_lookup(db, wf.exam.patient_id)):
        db.add(Measurement(waveform_id=wf.id, marker=r["marker"],
                           latency_ms=r["latency_ms"],
                           amplitude_uv=r["amplitude_uv"],
                           is_auto=True, flag=r["flag"]))
    db.commit()
    db.refresh(wf)
    return wf


# -- interpretation & sign-off ---------------------------------------------

def set_interpretation(db: Session, exam: Exam, interpretation: Optional[str],
                       impression: Optional[str], by: str) -> Exam:
    _require_unlocked(exam)
    exam.interpretation = interpretation
    exam.impression = impression
    exam.interpreted_by = by
    exam.interpreted_at = datetime.utcnow()
    db.commit()
    db.refresh(exam)
    return exam


def sign(db: Session, exam: Exam, by: str) -> Exam:
    """Sign the report: it becomes read-only."""
    if exam.status == STATUS_SIGNED:
        raise ExamLocked("Report is already signed")
    exam.status = STATUS_SIGNED
    exam.signed_by = by
    exam.signed_at = datetime.utcnow()
    db.commit()
    db.refresh(exam)
    return exam


def reopen(db: Session, exam: Exam) -> Exam:
    """Re-open a signed report for amendment (the previous signature is
    cleared; the audit log keeps who signed and who re-opened)."""
    exam.status = STATUS_COMPLETED
    exam.signed_by = None
    exam.signed_at = None
    db.commit()
    db.refresh(exam)
    return exam


def export_csv(exam: Exam) -> str:
    """Measurements of an exam as CSV text."""
    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["exam_id", "patient_id", "test_type", "protocol", "step",
                "eye", "marker", "latency_ms", "amplitude_uv", "flag",
                "is_auto"])
    for wf in exam.waveforms:
        for m in sorted(wf.measurements, key=lambda x: x.latency_ms):
            w.writerow([exam.id, exam.patient_id, exam.test_type, exam.protocol,
                        wf.step, wf.eye, m.marker, m.latency_ms, m.amplitude_uv,
                        m.flag or "", int(bool(m.is_auto))])
    return buf.getvalue()
