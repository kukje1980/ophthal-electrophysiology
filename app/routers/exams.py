"""Exam API - run an acquisition and read results (authenticated; audited)."""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.crud import exam as crud
from app.crud import patient as patient_crud
from app.crud import user as audit_crud
from app.database import get_db
from app.schemas import (
    ExamCreate, ExamInterpretation, ExamOut, ExamRecord, ExamSummary, MarkerEdit,
    WaveformOut,
)
from app.security import require_permission

router = APIRouter(prefix="/api/exams", tags=["exams"])


@router.post("/record", response_model=ExamOut, status_code=201)
def record_exam_step(data: ExamRecord, request: Request,
                     db: Session = Depends(get_db),
                     user=Depends(require_permission("run_exam"))):
    """Store a trigger-averaged epoch from the live stream as a protocol step."""
    if not patient_crud.get(db, data.patient_id):
        raise HTTPException(404, "Patient not found")
    if not data.samples or len(data.samples) < 2:
        raise HTTPException(400, "samples must contain at least 2 values")
    try:
        exam = crud.record_step(db, data)
    except KeyError as e:
        raise HTTPException(400, str(e))
    except crud.ExamLocked as e:
        raise HTTPException(409, str(e))
    audit_crud.audit(db, user=user, action="exam.record", entity="exam",
                     entity_id=exam.id,
                     detail=f"{data.protocol}/{data.step_key} {data.eye} n={data.n_sweeps}",
                     request=request)
    return exam


@router.post("", response_model=ExamOut, status_code=201)
def run_exam(data: ExamCreate, request: Request, db: Session = Depends(get_db),
             user=Depends(require_permission("run_exam"))):
    if not patient_crud.get(db, data.patient_id):
        raise HTTPException(404, "Patient not found")
    try:
        exam = crud.run_exam(db, data)
    except KeyError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(503, f"Acquisition failed: {e}")
    audit_crud.audit(db, user=user, action="exam.run", entity="exam",
                     entity_id=exam.id, detail=f"{exam.protocol}",
                     request=request)
    return exam


@router.get("", response_model=List[ExamSummary])
def list_exams(patient_id: int, db: Session = Depends(get_db),
               _=Depends(require_permission("view_report"))):
    return crud.list_for_patient(db, patient_id)


@router.get("/{exam_id}", response_model=ExamOut)
def get_exam(exam_id: int, request: Request, db: Session = Depends(get_db),
             user=Depends(require_permission("view_report"))):
    obj = crud.get(db, exam_id)
    if not obj:
        raise HTTPException(404, "Exam not found")
    audit_crud.audit(db, user=user, action="exam.view", entity="exam",
                     entity_id=exam_id, request=request)
    return obj


@router.delete("/{exam_id}", status_code=204)
def delete_exam(exam_id: int, request: Request, db: Session = Depends(get_db),
                user=Depends(require_permission("delete_exam"))):
    if not crud.delete(db, exam_id):
        raise HTTPException(404, "Exam not found")
    audit_crud.audit(db, user=user, action="exam.delete", entity="exam",
                     entity_id=exam_id, request=request)


# -- manual marker review ---------------------------------------------------

def _waveform(db: Session, exam_id: int, waveform_id: int):
    wf = crud.get_waveform(db, exam_id, waveform_id)
    if not wf:
        raise HTTPException(404, "Waveform not found")
    return wf


def _marker_call(fn, *args):
    try:
        return fn(*args)
    except crud.ExamLocked as e:
        raise HTTPException(409, str(e))
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e).strip("'\""))


@router.put("/{exam_id}/waveforms/{waveform_id}/markers/{marker}",
            response_model=WaveformOut)
def edit_marker(exam_id: int, waveform_id: int, marker: str, data: MarkerEdit,
                request: Request, db: Session = Depends(get_db),
                user=Depends(require_permission("run_exam"))):
    """Move or add a marker cursor; amplitudes and flags are recomputed."""
    wf = _waveform(db, exam_id, waveform_id)
    wf = _marker_call(crud.edit_marker, db, wf, marker, data.latency_ms, data.snap)
    m = next((m for m in wf.measurements if m.marker == marker), None)
    audit_crud.audit(db, user=user, action="marker.edit", entity="exam",
                     entity_id=exam_id,
                     detail=f"{wf.step} {wf.eye} {marker} -> "
                            f"{m.latency_ms if m else data.latency_ms} ms",
                     request=request)
    return wf


@router.delete("/{exam_id}/waveforms/{waveform_id}/markers/{marker}",
               response_model=WaveformOut)
def remove_marker(exam_id: int, waveform_id: int, marker: str, request: Request,
                  db: Session = Depends(get_db),
                  user=Depends(require_permission("run_exam"))):
    """Remove a marker (non-recordable component)."""
    wf = _waveform(db, exam_id, waveform_id)
    wf = _marker_call(crud.remove_marker, db, wf, marker)
    audit_crud.audit(db, user=user, action="marker.remove", entity="exam",
                     entity_id=exam_id, detail=f"{wf.step} {wf.eye} {marker}",
                     request=request)
    return wf


@router.post("/{exam_id}/waveforms/{waveform_id}/markers/reset",
             response_model=WaveformOut)
def reset_markers(exam_id: int, waveform_id: int, request: Request,
                  db: Session = Depends(get_db),
                  user=Depends(require_permission("run_exam"))):
    """Discard manual edits and re-run automatic marker detection."""
    wf = _waveform(db, exam_id, waveform_id)
    wf = _marker_call(crud.reset_markers, db, wf)
    audit_crud.audit(db, user=user, action="marker.reset", entity="exam",
                     entity_id=exam_id, detail=f"{wf.step} {wf.eye}",
                     request=request)
    return wf


# -- interpretation and sign-off ---------------------------------------------

def _exam(db: Session, exam_id: int):
    obj = crud.get(db, exam_id)
    if not obj:
        raise HTTPException(404, "Exam not found")
    return obj


@router.put("/{exam_id}/interpretation", response_model=ExamOut)
def save_interpretation(exam_id: int, data: ExamInterpretation, request: Request,
                        db: Session = Depends(get_db),
                        user=Depends(require_permission("sign_report"))):
    exam = _marker_call(crud.set_interpretation, db, _exam(db, exam_id),
                        data.interpretation)
    audit_crud.audit(db, user=user, action="exam.interpret", entity="exam",
                     entity_id=exam_id, request=request)
    return exam


@router.post("/{exam_id}/sign", response_model=ExamOut)
def sign_exam(exam_id: int, data: ExamInterpretation, request: Request,
              db: Session = Depends(get_db),
              user=Depends(require_permission("sign_report"))):
    """Sign the report with its interpretation; it is then locked."""
    signer = user.full_name or user.username
    exam = _marker_call(crud.sign, db, _exam(db, exam_id), signer,
                        data.interpretation)
    audit_crud.audit(db, user=user, action="exam.sign", entity="exam",
                     entity_id=exam_id, request=request)
    return exam


@router.post("/{exam_id}/reopen", response_model=ExamOut)
def reopen_exam(exam_id: int, request: Request, db: Session = Depends(get_db),
                user=Depends(require_permission("sign_report"))):
    """Reopen a signed report for amendment."""
    exam = _exam(db, exam_id)
    if not exam.signed_at:
        raise HTTPException(409, "Exam is not signed")
    previous = exam.signed_by
    exam = crud.reopen(db, exam)
    audit_crud.audit(db, user=user, action="exam.reopen", entity="exam",
                     entity_id=exam_id, detail=f"previously signed by {previous}",
                     request=request)
    return exam
