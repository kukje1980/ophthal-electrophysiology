"""Patient CRUD operations."""
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import Patient
from app.schemas import PatientCreate, PatientUpdate


def create(db: Session, data: PatientCreate) -> Patient:
    obj = Patient(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def update(db: Session, patient_id: int, data: PatientUpdate) -> Optional[Patient]:
    obj = db.get(Patient, patient_id)
    if not obj:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    db.commit()
    db.refresh(obj)
    return obj


def get(db: Session, patient_id: int) -> Optional[Patient]:
    return db.get(Patient, patient_id)


def list_all(db: Session, q: Optional[str] = None) -> List[Patient]:
    query = db.query(Patient)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Patient.name.ilike(like))
            | (Patient.mrn.ilike(like))
            | (Patient.phone.ilike(like))
        )
    return query.order_by(Patient.created_at.desc()).all()


def delete(db: Session, patient_id: int) -> bool:
    obj = db.get(Patient, patient_id)
    if not obj:
        return False
    db.delete(obj)
    db.commit()
    return True
