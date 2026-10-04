"""Exam CRUD plus the acquire -> store -> auto-mark pipeline."""
from typing import List, Optional

import numpy as np
from sqlalchemy.orm import Session

from app.acquisition import get_active_device
from app.crud import reference as reference_crud
from app.iscev import detect_markers, get_protocol
from app.models import Exam, Measurement, Patient, Waveform
from app.schemas import ExamCreate, ExamRecord


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


def delete(db: Session, exam_id: int) -> bool:
    obj = db.get(Exam, exam_id)
    if not obj:
        return False
    db.delete(obj)
    db.commit()
    return True
