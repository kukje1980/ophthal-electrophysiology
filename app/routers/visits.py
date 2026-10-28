"""Reception (검사 접수) and visit API (authenticated; role-gated; audited)."""
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.crud import user as audit_crud
from app.crud import visit as crud
from app.database import get_db
from app.schemas import ReceptionIn, ReceptionOut, VisitCreate, VisitListOut, VisitOut
from app.security import require_permission

router = APIRouter(tags=["visits"])


@router.post("/api/reception", response_model=ReceptionOut, status_code=201)
def receive_patient(data: ReceptionIn, request: Request,
                    db: Session = Depends(get_db),
                    user=Depends(require_permission("edit_patient"))):
    """Register a visit for an existing patient, or a new patient + visit."""
    try:
        patient, visit, created = crud.receive(db, data.patient_id, data.patient,
                                               data.visit)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"ID '{data.patient.mrn}'는 이미 등록된 환자입니다.")
    if created:
        audit_crud.audit(db, user=user, action="patient.create", entity="patient",
                         entity_id=patient.id, detail=f"MRN {patient.mrn}",
                         request=request)
    audit_crud.audit(db, user=user, action="visit.create", entity="visit",
                     entity_id=visit.id,
                     detail=f"patient {patient.id} {visit.tests or ''}",
                     request=request)
    return {"patient": patient, "visit": visit}


@router.get("/api/visits/options")
def visit_options(db: Session = Depends(get_db),
                  _=Depends(require_permission("view_patient"))):
    """Suggestions for the reception form (doctors, diagnoses, electrodes)."""
    return crud.options(db)


@router.get("/api/visits", response_model=List[VisitListOut])
def list_visits(patient_id: Optional[int] = None, on: Optional[date] = None,
                db: Session = Depends(get_db),
                _=Depends(require_permission("view_patient"))):
    """A patient's visit history, or one day's receptions (default today)."""
    if patient_id is not None:
        return crud.list_for_patient(db, patient_id)
    return crud.list_on(db, on or date.today())


@router.get("/api/visits/{visit_id}", response_model=VisitListOut)
def get_visit(visit_id: int, db: Session = Depends(get_db),
              _=Depends(require_permission("view_patient"))):
    visit = crud.get(db, visit_id)
    if not visit:
        raise HTTPException(404, "Visit not found")
    return visit


@router.put("/api/visits/{visit_id}", response_model=VisitOut)
def update_visit(visit_id: int, data: VisitCreate, request: Request,
                 db: Session = Depends(get_db),
                 user=Depends(require_permission("edit_patient"))):
    visit = crud.update(db, visit_id, data)
    if not visit:
        raise HTTPException(404, "Visit not found")
    audit_crud.audit(db, user=user, action="visit.update", entity="visit",
                     entity_id=visit_id,
                     detail=",".join(data.model_dump(exclude_unset=True).keys()),
                     request=request)
    return visit


@router.delete("/api/visits/{visit_id}", status_code=204)
def cancel_visit(visit_id: int, request: Request, db: Session = Depends(get_db),
                 user=Depends(require_permission("edit_patient"))):
    try:
        if not crud.delete(db, visit_id):
            raise HTTPException(404, "Visit not found")
    except ValueError as e:
        raise HTTPException(409, str(e))
    audit_crud.audit(db, user=user, action="visit.delete", entity="visit",
                     entity_id=visit_id, request=request)
