"""Exam API - run an acquisition and read results (authenticated; audited)."""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.crud import exam as crud
from app.crud import patient as patient_crud
from app.crud import user as audit_crud
from app.database import get_db
from app.schemas import ExamCreate, ExamOut, ExamSummary
from app.security import require_permission

router = APIRouter(prefix="/api/exams", tags=["exams"])


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
def get_exam(exam_id: int, db: Session = Depends(get_db),
             _=Depends(require_permission("view_report"))):
    obj = crud.get(db, exam_id)
    if not obj:
        raise HTTPException(404, "Exam not found")
    return obj


@router.delete("/{exam_id}", status_code=204)
def delete_exam(exam_id: int, request: Request, db: Session = Depends(get_db),
                user=Depends(require_permission("delete_exam"))):
    if not crud.delete(db, exam_id):
        raise HTTPException(404, "Exam not found")
    audit_crud.audit(db, user=user, action="exam.delete", entity="exam",
                     entity_id=exam_id, request=request)
