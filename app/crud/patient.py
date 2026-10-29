"""Patient CRUD operations, including the reception-desk search.

Patients are soft-deleted: ``delete`` hides the record (and its exams) but
never removes it, and an administrator can ``restore`` it.
"""
import re
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.crud import idempotency
from app.models import Exam, Patient, Visit
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
    """One page of patients (newest first) and the total match count.

    ``q`` matches part of the name, ID or phone, or a birth date typed as at
    the desk (see ``parse_birth``)."""
    query = _active(db)
    if q and q.strip():
        q = q.strip()
        like = f"%{q}%"
        cond = (Patient.name.ilike(like)) | (Patient.mrn.ilike(like)) | (Patient.phone.ilike(like))
        born = parse_birth(q)
        if born:
            cond = cond | (Patient.birth_date == born)
        query = query.filter(cond)
    total = query.count()
    rows = (query.order_by(Patient.created_at.desc(), Patient.id.desc())
            .offset(offset).limit(limit).all())
    return rows, total


def parse_birth(q: str) -> Optional[date]:
    """Read a birth date typed at the desk: ``19680302``, ``680302`` (as on
    the national id), ``1968-03-02``, ``1968.3.2`` or ``1968/03/02``."""
    q = q.strip()
    m = re.fullmatch(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})", q)
    if m:
        y, mo, d = (int(g) for g in m.groups())
    elif re.fullmatch(r"\d{8}", q):
        y, mo, d = int(q[:4]), int(q[4:6]), int(q[6:])
    elif re.fullmatch(r"\d{6}", q):
        yy, mo, d = int(q[:2]), int(q[2:4]), int(q[4:])
        y = 2000 + yy if yy <= date.today().year % 100 else 1900 + yy
    else:
        return None
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def _prefix(column, q: str):
    """Index-friendly "starts with": a range scan instead of LIKE '%q%'."""
    return (column >= q) & (column < q + "\uffff")


def quick_search(db: Session, q: str, limit: int = 20) -> List[Patient]:
    """Reception picker: patients whose ID or name starts with ``q``, or born
    on the date ``q``.

    Each part is a range scan on its own index capped at ``limit`` rows, so
    the cost stays flat however many patients accumulate. Order: exact ID,
    ID prefix, birth date, name prefix. Patients in the trash are left out.
    """
    q = q.strip()
    if not q:
        return []
    found: Dict[int, Patient] = {}

    def take(rows):
        for p in rows:
            if len(found) >= limit:
                return
            found.setdefault(p.id, p)

    take(_active(db).filter(Patient.mrn == q).all())
    take(_active(db).filter(_prefix(Patient.mrn, q))
         .order_by(Patient.mrn).limit(limit).all())
    born = parse_birth(q)
    if born:
        take(_active(db).filter(Patient.birth_date == born)
             .order_by(Patient.name).limit(limit).all())
    take(_active(db).filter(_prefix(Patient.name, q))
         .order_by(Patient.name, Patient.mrn).limit(limit).all())
    return list(found.values())


def visit_summary(db: Session, patient_ids: List[int]) -> Dict[int, dict]:
    """Last visit date, number of visits and the latest diagnosis / doctor for
    a handful of patients (the search hits). Exams recorded without a
    reception count as one visit per day."""
    out = {pid: {"last_visit": None, "visit_count": 0,
                 "last_diagnosis": None, "last_doctor": None}
           for pid in patient_ids}
    if not patient_ids:
        return out
    rows = (db.query(Visit.patient_id, Visit.visit_date, Visit.diagnosis,
                     Visit.attending_doctor)
            .filter(Visit.patient_id.in_(patient_ids))
            .order_by(Visit.visit_date.desc(), Visit.id.desc()).all())
    for pid, day, diagnosis, doctor in rows:
        s = out[pid]
        if s["visit_count"] == 0:
            s.update(last_visit=day, last_diagnosis=diagnosis, last_doctor=doctor)
        s["visit_count"] += 1
    loose = (db.query(Exam.patient_id, func.date(Exam.performed_at))
             .filter(Exam.patient_id.in_(patient_ids), Exam.visit_id.is_(None),
                     Exam.deleted_at.is_(None))
             .distinct().all())
    for pid, day in loose:
        day = date.fromisoformat(day) if isinstance(day, str) else day
        s = out[pid]
        s["visit_count"] += 1
        if day and (s["last_visit"] is None or day > s["last_visit"]):
            s["last_visit"] = day
    return out


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
