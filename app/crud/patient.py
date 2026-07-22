"""Patient CRUD operations."""
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import Patient
from app.schemas import PatientCreate, PatientUpdate
from app.security import encrypt_phi


def create(db: Session, data: PatientCreate) -> Patient:
    fields = data.model_dump()
    if fields.get("national_id"):
        fields["national_id"] = encrypt_phi(fields["national_id"])
    obj = Patient(**fields)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def update(db: Session, patient_id: int, data: PatientUpdate) -> Optional[Patient]:
    obj = db.get(Patient, patient_id)
    if not obj:
        return None
    fields = data.model_dump(exclude_unset=True)
    if "national_id" in fields:
        fields["national_id"] = encrypt_phi(fields["national_id"])
    for field, value in fields.items():
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
