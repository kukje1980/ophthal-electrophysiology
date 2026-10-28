"""Exam API - run an acquisition and read results (authenticated; audited)."""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.crud import exam as crud
from app.crud import idempotency
from app.crud import patient as patient_crud
from app.crud import user as audit_crud
from app.database import get_db
from app.schemas import ExamCreate, ExamOut, ExamRecord, ExamSummary
from app.security import require_permission

router = APIRouter(prefix="/api/exams", tags=["exams"])


@router.post("/record", response_model=ExamOut, status_code=201)
def record_exam_step(data: ExamRecord, request: Request,
                     db: Session = Depends(get_db),
                     user=Depends(require_permission("run_exam"))):
    """Store a trigger-averaged epoch from the live stream as a protocol step.

    Safe to retry with the same Idempotency-Key: a retried save never adds the
    epoch twice."""
    key = idempotency.key_from(request, user)
    if (exam := _replay(db, key)) is not None:
        return exam
    if not patient_crud.get(db, data.patient_id):
        raise HTTPException(404, "Patient not found")
    try:
        exam = crud.record_step(db, data, idem_key=key)
    except KeyError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except IntegrityError:
        db.rollback()
        if (exam := _replay(db, key)) is not None:
            return exam
        raise
    audit_crud.audit(db, user=user, action="exam.record", entity="exam",
                     entity_id=exam.id,
                     detail=f"{data.protocol}/{data.step_key} {data.eye} n={data.n_sweeps}",
                     request=request)
    return exam


def _replay(db: Session, key):
    """The exam a retried request already created, if any."""
    hit = idempotency.lookup(db, key)
    if not hit:
        return None
    exam = crud.get(db, hit[1])
    if exam is None:  # created, then deleted before the retry arrived
        raise HTTPException(409, "이 요청은 이미 처리되었습니다 (해당 검사는 삭제됨).")
    return exam


@router.post("", response_model=ExamOut, status_code=201)
def run_exam(data: ExamCreate, request: Request, db: Session = Depends(get_db),
             user=Depends(require_permission("run_exam"))):
    key = idempotency.key_from(request, user)
    if (exam := _replay(db, key)) is not None:
        return exam
    if not patient_crud.get(db, data.patient_id):
        raise HTTPException(404, "Patient not found")
    try:
        exam = crud.run_exam(db, data, idem_key=key)
    except KeyError as e:
        raise HTTPException(400, str(e))
    except crud.DeviceBusy as e:
        # Retry-After tells the client a retry (same key) is safe.
        raise HTTPException(409, str(e), headers={"Retry-After": "3"})
    except RuntimeError as e:
        raise HTTPException(503, f"Acquisition failed: {e}")
    except IntegrityError:
        db.rollback()
        if (exam := _replay(db, key)) is not None:
            return exam
        raise
    audit_crud.audit(db, user=user, action="exam.run", entity="exam",
                     entity_id=exam.id, detail=f"{exam.protocol}",
                     request=request)
    return exam


@router.get("", response_model=List[ExamSummary])
def list_exams(patient_id: int, response: Response,
               limit: int = Query(200, ge=1, le=1000),
               offset: int = Query(0, ge=0),
               db: Session = Depends(get_db),
               _=Depends(require_permission("view_report"))):
    """A patient's exams, newest first; the total is in X-Total-Count."""
    rows, total = crud.list_for_patient(db, patient_id, limit=limit, offset=offset)
    response.headers["X-Total-Count"] = str(total)
    return rows


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
    """Soft delete: the exam moves to the trash (restorable by an admin)."""
    if not crud.delete(db, exam_id, by=user.username):
        raise HTTPException(404, "Exam not found")
    audit_crud.audit(db, user=user, action="exam.delete", entity="exam",
                     entity_id=exam_id, request=request)
