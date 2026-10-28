"""Patient CRUD operations.

Patients are soft-deleted: ``delete`` hides the record (and its exams) but
never removes it, and an administrator can ``restore`` it.
"""
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.crud import idempotency
from app.models import Patient
from app.schemas import PatientCreate, PatientUpdate
from app.security import encrypt_phi


class DuplicateMRN(ValueError):
    """The MRN is already used (possibly by a patient in the trash)."""

    def __init__(self, mrn: str, in_trash: bool):
        self.mrn, self.in_trash = mrn, in_trash
        super().__init__(mrn)


def _active(db: Session):
    return db.query(Patient).filter(Patient.deleted_at.is_(None))


def create(db: Session, data: PatientCreate, idem_key: Optional[str] = None) -> Patient:
    existing = db.query(Patient).filter(Patient.mrn == data.mrn).first()
    if existing is not None:
        raise DuplicateMRN(data.mrn, in_trash=existing.deleted_at is not None)
    fields = data.model_dump()
    if fields.get("national_id"):
        fields["national_id"] = encrypt_phi(fields["national_id"])
    obj = Patient(**fields)
    db.add(obj)
    db.flush()
    idempotency.remember(db, idem_key, "patient", obj.id)
    db.commit()
    db.refresh(obj)
    return obj


def update(db: Session, patient_id: int, data: PatientUpdate) -> Optional[Patient]:
    obj = get(db, patient_id)
    if not obj:
        return None
    fields = data.model_dump(exclude_unset=True)
    if "mrn" in fields and fields["mrn"] != obj.mrn:
        clash = db.query(Patient).filter(Patient.mrn == fields["mrn"]).first()
        if clash is not None:
            raise DuplicateMRN(fields["mrn"], in_trash=clash.deleted_at is not None)
    if "national_id" in fields:
        fields["national_id"] = encrypt_phi(fields["national_id"])
    for field, value in fields.items():
        setattr(obj, field, value)
    db.commit()
    db.refresh(obj)
    return obj


def get(db: Session, patient_id: int, include_deleted: bool = False) -> Optional[Patient]:
    obj = db.get(Patient, patient_id)
    if obj is None or (obj.deleted_at is not None and not include_deleted):
        return None
    return obj


def search(db: Session, q: Optional[str] = None, limit: int = 50,
           offset: int = 0) -> Tuple[List[Patient], int]:
    """One page of patients (newest first) and the total match count."""
    query = _active(db)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Patient.name.ilike(like))
            | (Patient.mrn.ilike(like))
            | (Patient.phone.ilike(like))
        )
    total = query.count()
    rows = (query.order_by(Patient.created_at.desc(), Patient.id.desc())
            .offset(offset).limit(limit).all())
    return rows, total


def count(db: Session) -> int:
    return _active(db).count()


def delete(db: Session, patient_id: int, by: Optional[str] = None) -> bool:
    obj = get(db, patient_id)
    if not obj:
        return False
    obj.deleted_at = datetime.utcnow()
    obj.deleted_by = by
    db.commit()
    return True


def restore(db: Session, patient_id: int) -> Optional[Patient]:
    obj = db.get(Patient, patient_id)
    if obj is None or obj.deleted_at is None:
        return None
    obj.deleted_at = None
    obj.deleted_by = None
    db.commit()
    db.refresh(obj)
    return obj


def list_deleted(db: Session, limit: int = 500) -> List[Patient]:
    return (db.query(Patient).filter(Patient.deleted_at.isnot(None))
            .order_by(Patient.deleted_at.desc()).limit(limit).all())
