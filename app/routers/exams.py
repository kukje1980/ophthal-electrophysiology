"""Exam API - run an acquisition, read results, interpret and sign
(authenticated; audited)."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.crud import exam as crud
from app.crud import patient as patient_crud
from app.crud import user as audit_crud
from app.crud.exam import ExamLocked
from app.database import get_db
from app.schemas import (
    ExamCreate, ExamInterpretation, ExamOut, ExamRecord, ExamSummary,
)
from app.security import require_permission

router = APIRouter(prefix="/api/exams", tags=["exams"])


def _display_name(user) -> str:
    return user.full_name or user.username


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
    except ExamLocked as e:
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
def list_exams(patient_id: Optional[int] = None, unsigned: bool = False,
               db: Session = Depends(get_db),
               _=Depends(require_permission("view_report"))):
    """Exams of a patient, or (``unsigned=true``) the reading worklist."""
    if patient_id is not None:
        return crud.list_for_patient(db, patient_id)
    if unsigned:
        return crud.list_unsigned(db)
    return crud.list_recent(db, limit=100)


@router.get("/{exam_id}", response_model=ExamOut)
def get_exam(exam_id: int, request: Request, db: Session = Depends(get_db),
             user=Depends(require_permission("view_report"))):
    obj = crud.get(db, exam_id)
    if not obj:
        raise HTTPException(404, "Exam not found")
    audit_crud.audit(db, user=user, action="exam.view", entity="exam",
                     entity_id=exam_id, request=request)
    return obj


@router.get("/{exam_id}/analysis")
def exam_analysis(exam_id: int, db: Session = Depends(get_db),
                  _=Depends(require_permission("view_report"))):
    """Interocular comparison, derived ratios and a summary of the flags."""
    obj = crud.get(db, exam_id)
    if not obj:
        raise HTTPException(404, "Exam not found")
    return crud.analysis(obj)


@router.get("/{exam_id}/export.csv", response_class=PlainTextResponse)
def exam_export_csv(exam_id: int, request: Request,
                    db: Session = Depends(get_db),
                    user=Depends(require_permission("view_report"))):
    obj = crud.get(db, exam_id)
    if not obj:
        raise HTTPException(404, "Exam not found")
    audit_crud.audit(db, user=user, action="exam.export", entity="exam",
                     entity_id=exam_id, detail="csv", request=request)
    return PlainTextResponse(
        crud.export_csv(obj), media_type="text/csv",
        headers={"Content-Disposition":
                 f'attachment; filename="exam_{exam_id}_measurements.csv"'})


@router.put("/{exam_id}/interpretation", response_model=ExamOut)
def set_interpretation(exam_id: int, data: ExamInterpretation,
                       request: Request, db: Session = Depends(get_db),
                       user=Depends(require_permission("interpret_exam"))):
    obj = crud.get(db, exam_id)
    if not obj:
        raise HTTPException(404, "Exam not found")
    try:
        obj = crud.set_interpretation(db, obj, data.interpretation,
                                      data.impression, _display_name(user))
    except ExamLocked as e:
        raise HTTPException(409, str(e))
    audit_crud.audit(db, user=user, action="exam.interpret", entity="exam",
                     entity_id=exam_id, request=request)
    return obj


@router.post("/{exam_id}/sign", response_model=ExamOut)
def sign_exam(exam_id: int, request: Request, db: Session = Depends(get_db),
              user=Depends(require_permission("sign_report"))):
    obj = crud.get(db, exam_id)
    if not obj:
        raise HTTPException(404, "Exam not found")
    try:
        obj = crud.sign(db, obj, _display_name(user))
    except ExamLocked as e:
        raise HTTPException(409, str(e))
    audit_crud.audit(db, user=user, action="exam.sign", entity="exam",
                     entity_id=exam_id, request=request)
    return obj


@router.post("/{exam_id}/reopen", response_model=ExamOut)
def reopen_exam(exam_id: int, request: Request, db: Session = Depends(get_db),
                user=Depends(require_permission("sign_report"))):
    obj = crud.get(db, exam_id)
    if not obj:
        raise HTTPException(404, "Exam not found")
    if not obj.is_signed:
        raise HTTPException(409, "Report is not signed")
    previous = obj.signed_by
    obj = crud.reopen(db, obj)
    audit_crud.audit(db, user=user, action="exam.reopen", entity="exam",
                     entity_id=exam_id, detail=f"previously signed by {previous}",
                     request=request)
    return obj


@router.delete("/{exam_id}", status_code=204)
def delete_exam(exam_id: int, request: Request, db: Session = Depends(get_db),
                user=Depends(require_permission("delete_exam"))):
    obj = crud.get(db, exam_id)
    if not obj:
        raise HTTPException(404, "Exam not found")
    if obj.is_signed:
        raise HTTPException(409, "Signed reports cannot be deleted; re-open first")
    crud.delete(db, exam_id)
    audit_crud.audit(db, user=user, action="exam.delete", entity="exam",
                     entity_id=exam_id, request=request)
