"""Patient API (authenticated; role-gated; audited)."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.crud import patient as crud
from app.crud import user as audit_crud
from app.database import get_db
from app.schemas import PatientCreate, PatientOut, PatientSearchOut, PatientUpdate
from app.security import decrypt_phi, require_permission

router = APIRouter(prefix="/api/patients", tags=["patients"])


@router.post("", response_model=PatientOut, status_code=201)
def create_patient(data: PatientCreate, request: Request,
                   db: Session = Depends(get_db),
                   user=Depends(require_permission("edit_patient"))):
    try:
        patient = crud.create(db, data)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"MRN '{data.mrn}' already exists")
    audit_crud.audit(db, user=user, action="patient.create", entity="patient",
                     entity_id=patient.id, detail=f"MRN {patient.mrn}",
                     request=request)
    return patient


@router.get("", response_model=List[PatientOut])
def list_patients(q: Optional[str] = None,
                  limit: int = Query(50, ge=1, le=200),
                  db: Session = Depends(get_db),
                  _=Depends(require_permission("view_patient"))):
    """Search by ID / name prefix or birth date, else the latest registered."""
    return crud.list_all(db, q, limit)


@router.get("/search", response_model=List[PatientSearchOut])
def search_patients(q: str, limit: int = Query(20, ge=1, le=50),
                    db: Session = Depends(get_db),
                    _=Depends(require_permission("view_patient"))):
    """Reception-desk picker: the top matches with their visit history."""
    hits = crud.search(db, q, limit)
    summary = crud.visit_summary(db, [p.id for p in hits])
    return [{**PatientSearchOut.model_validate(p).model_dump(), **summary[p.id]}
            for p in hits]


@router.get("/{patient_id}", response_model=PatientOut)
def get_patient(patient_id: int, request: Request, db: Session = Depends(get_db),
                user=Depends(require_permission("view_patient"))):
    obj = crud.get(db, patient_id)
    if not obj:
        raise HTTPException(404, "Patient not found")
    audit_crud.audit(db, user=user, action="patient.view", entity="patient",
                     entity_id=patient_id, request=request)
    return obj


@router.get("/{patient_id}/national-id")
def reveal_national_id(patient_id: int, request: Request,
                       db: Session = Depends(get_db),
                       user=Depends(require_permission("view_phi"))):
    """Return the full (decrypted) national id. Restricted and always audited."""
    obj = crud.get(db, patient_id)
    if not obj:
        raise HTTPException(404, "Patient not found")
    audit_crud.audit(db, user=user, action="phi.view", entity="patient",
                     entity_id=patient_id, detail="national_id", request=request)
    return {"national_id": decrypt_phi(obj.national_id)}


@router.put("/{patient_id}", response_model=PatientOut)
def update_patient(patient_id: int, data: PatientUpdate, request: Request,
                   db: Session = Depends(get_db),
                   user=Depends(require_permission("edit_patient"))):
    try:
        obj = crud.update(db, patient_id, data)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"MRN '{data.mrn}' already exists")
    if not obj:
        raise HTTPException(404, "Patient not found")
    audit_crud.audit(db, user=user, action="patient.update", entity="patient",
                     entity_id=patient_id,
                     detail=",".join(data.model_dump(exclude_unset=True).keys()),
                     request=request)
    return obj


@router.delete("/{patient_id}", status_code=204)
def delete_patient(patient_id: int, request: Request,
                   db: Session = Depends(get_db),
                   user=Depends(require_permission("delete_patient"))):
    if not crud.delete(db, patient_id):
        raise HTTPException(404, "Patient not found")
    audit_crud.audit(db, user=user, action="patient.delete", entity="patient",
                     entity_id=patient_id, request=request)
