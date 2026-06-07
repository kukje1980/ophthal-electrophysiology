"""Exam CRUD plus the acquire -> store -> auto-mark pipeline."""
from typing import List, Optional

from sqlalchemy.orm import Session

from app.acquisition import get_active_device
from app.iscev import detect_markers, get_protocol
from app.models import Exam, Measurement, Waveform
from app.schemas import ExamCreate


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


def run_exam(db: Session, data: ExamCreate) -> Exam:
    """Acquire every step of a protocol for the requested eyes and persist it.

    The acquisition device is obtained from the registry, so this same code
    path works for the simulator and for any real driver.
    """
    protocol = get_protocol(data.protocol)
    device = get_active_device()
    device.configure(protocol)

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
            wf = Waveform(
                exam_id=exam.id,
                eye=trace.eye,
                step=trace.step,
                sampling_rate=trace.sampling_rate,
                duration_ms=trace.duration_ms,
                samples=trace.samples,
            )
            db.add(wf)
            db.flush()  # assign wf.id

            for m in detect_markers(
                trace.samples, trace.duration_ms, step["key"], step["markers"]
            ):
                db.add(Measurement(
                    waveform_id=wf.id,
                    marker=m["marker"],
                    latency_ms=m["latency_ms"],
                    amplitude_uv=m["amplitude_uv"],
                    is_auto=True,
                    flag=m["flag"],
                ))

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
