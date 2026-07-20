"""Patient API."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.crud import patient as crud
from app.database import get_db
from app.schemas import PatientCreate, PatientOut, PatientUpdate

router = APIRouter(prefix="/api/patients", tags=["patients"])


@router.post("", response_model=PatientOut, status_code=201)
def create_patient(data: PatientCreate, db: Session = Depends(get_db)):
    try:
        return crud.create(db, data)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"MRN '{data.mrn}' already exists")


@router.get("", response_model=List[PatientOut])
def list_patients(q: Optional[str] = None, db: Session = Depends(get_db)):
    return crud.list_all(db, q)


@router.get("/{patient_id}", response_model=PatientOut)
def get_patient(patient_id: int, db: Session = Depends(get_db)):
    obj = crud.get(db, patient_id)
    if not obj:
        raise HTTPException(404, "Patient not found")
    return obj


@router.put("/{patient_id}", response_model=PatientOut)
def update_patient(patient_id: int, data: PatientUpdate,
                   db: Session = Depends(get_db)):
    try:
        obj = crud.update(db, patient_id, data)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"MRN '{data.mrn}' already exists")
    if not obj:
        raise HTTPException(404, "Patient not found")
    return obj


@router.delete("/{patient_id}", status_code=204)
def delete_patient(patient_id: int, db: Session = Depends(get_db)):
    if not crud.delete(db, patient_id):
        raise HTTPException(404, "Patient not found")
