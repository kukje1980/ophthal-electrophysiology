"""Exam CRUD plus the acquire -> store -> auto-mark pipeline."""
from datetime import datetime
from typing import List, Optional

import numpy as np
from sqlalchemy.orm import Session

from app.acquisition import get_active_device
from app.crud import reference as reference_crud
from app.iscev import detect_markers, get_protocol, remeasure, snap_latency
from app.models import Exam, Measurement, Patient, Waveform
from app.schemas import ExamCreate, ExamRecord


class ExamLocked(Exception):
    """Raised when modifying a signed report without reopening it first."""


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
        status="completed",
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
        if exam.signed_at:
            raise ExamLocked("Exam is signed; reopen it before adding steps")
    else:
        exam = Exam(
            patient_id=data.patient_id, test_type=protocol["test_type"],
            protocol=data.protocol, device=data.device or "live-stream",
            operator=data.operator, status="completed", note=data.note,
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


# -- manual marker review ---------------------------------------------------

def _step_markers(exam: Exam, step_key: str) -> List[str]:
    try:
        protocol = get_protocol(exam.protocol)
    except KeyError:
        return []
    step = next((s for s in protocol["steps"] if s["key"] == step_key), None)
    return list(step["markers"]) if step else []


def get_waveform(db: Session, exam_id: int, waveform_id: int) -> Optional[Waveform]:
    wf = db.get(Waveform, waveform_id)
    return wf if wf is not None and wf.exam_id == exam_id else None


def _apply(db: Session, wf: Waveform, latencies: dict, manual: set) -> Waveform:
    """Replace a waveform's measurements by re-measuring at ``latencies``."""
    ref_lookup = _ref_lookup(db, wf.exam.patient_id)
    was_manual = {m.marker for m in wf.measurements if not m.is_auto}
    wf.measurements.clear()
    for m in remeasure(wf.samples, wf.duration_ms, wf.step, latencies, ref_lookup):
        wf.measurements.append(Measurement(
            marker=m["marker"], latency_ms=m["latency_ms"],
            amplitude_uv=m["amplitude_uv"], flag=m["flag"],
            is_auto=m["marker"] not in (manual | was_manual),
        ))
    db.commit()
    db.refresh(wf)
    return wf


def edit_marker(db: Session, wf: Waveform, marker: str, latency_ms: float,
                snap: bool = True) -> Waveform:
    """Move (or add) one marker to a manually chosen implicit time. Dependent
    amplitudes (e.g. b measured from a) are recomputed."""
    if wf.exam.signed_at:
        raise ExamLocked("Exam is signed; reopen it before editing markers")
    if marker not in _step_markers(wf.exam, wf.step):
        raise KeyError(f"Marker '{marker}' is not defined for step '{wf.step}'")
    if not 0 <= latency_ms <= wf.duration_ms:
        raise ValueError("latency_ms is outside the recorded epoch")
    if snap:
        latency_ms = snap_latency(wf.samples, wf.duration_ms, wf.step,
                                  marker, latency_ms)
    latencies = {m.marker: m.latency_ms for m in wf.measurements}
    latencies[marker] = latency_ms
    return _apply(db, wf, latencies, {marker})


def remove_marker(db: Session, wf: Waveform, marker: str) -> Waveform:
    """Drop a marker, e.g. a non-recordable (extinguished) component."""
    if wf.exam.signed_at:
        raise ExamLocked("Exam is signed; reopen it before editing markers")
    latencies = {m.marker: m.latency_ms for m in wf.measurements
                 if m.marker != marker}
    return _apply(db, wf, latencies, set())


def reset_markers(db: Session, wf: Waveform) -> Waveform:
    """Discard manual edits and re-run automatic detection."""
    if wf.exam.signed_at:
        raise ExamLocked("Exam is signed; reopen it before editing markers")
    ref_lookup = _ref_lookup(db, wf.exam.patient_id)
    wf.measurements.clear()
    for m in detect_markers(wf.samples, wf.duration_ms, wf.step,
                            _step_markers(wf.exam, wf.step), ref_lookup=ref_lookup):
        wf.measurements.append(Measurement(
            marker=m["marker"], latency_ms=m["latency_ms"],
            amplitude_uv=m["amplitude_uv"], is_auto=True, flag=m["flag"],
        ))
    db.commit()
    db.refresh(wf)
    return wf


# -- interpretation and sign-off ---------------------------------------------

def set_interpretation(db: Session, exam: Exam, text: Optional[str]) -> Exam:
    if exam.signed_at:
        raise ExamLocked("Exam is signed; reopen it before editing the interpretation")
    exam.interpretation = (text or "").strip() or None
    db.commit()
    db.refresh(exam)
    return exam


def sign(db: Session, exam: Exam, signer: str, text: Optional[str] = None) -> Exam:
    if exam.signed_at:
        raise ExamLocked("Exam is already signed")
    if text is not None:
        exam.interpretation = text.strip() or None
    if not exam.interpretation:
        raise ValueError("An interpretation is required before signing")
    exam.signed_by = signer
    exam.signed_at = datetime.utcnow()
    exam.status = "signed"
    db.commit()
    db.refresh(exam)
    return exam


def reopen(db: Session, exam: Exam) -> Exam:
    """Unlock a signed report for amendment (the caller audits who/why)."""
    exam.signed_by = None
    exam.signed_at = None
    exam.status = "completed"
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
