"""Patient CRUD operations, including the reception-desk search."""
import re
from datetime import date
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Exam, Patient, Visit
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


def count(db: Session) -> int:
    return db.query(func.count(Patient.id)).scalar() or 0


def list_all(db: Session, q: Optional[str] = None, limit: int = 50) -> List[Patient]:
    """Search when ``q`` is given, else the most recently registered."""
    if q and q.strip():
        return search(db, q, limit)
    return db.query(Patient).order_by(Patient.created_at.desc()).limit(limit).all()


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


def search(db: Session, q: str, limit: int = 20) -> List[Patient]:
    """Patients whose ID or name starts with ``q``, or born on the date ``q``.

    Each part is a range scan on its own index capped at ``limit`` rows, so
    the cost stays flat however many patients accumulate. Order: exact ID,
    ID prefix, birth date, name prefix.
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

    take(db.query(Patient).filter(Patient.mrn == q).all())
    take(db.query(Patient).filter(_prefix(Patient.mrn, q))
         .order_by(Patient.mrn).limit(limit).all())
    born = parse_birth(q)
    if born:
        take(db.query(Patient).filter(Patient.birth_date == born)
             .order_by(Patient.name).limit(limit).all())
    take(db.query(Patient).filter(_prefix(Patient.name, q))
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
             .filter(Exam.patient_id.in_(patient_ids), Exam.visit_id.is_(None))
             .distinct().all())
    for pid, day in loose:
        day = date.fromisoformat(day) if isinstance(day, str) else day
        s = out[pid]
        s["visit_count"] += 1
        if day and (s["last_visit"] is None or day > s["last_visit"]):
            s["last_visit"] = day
    return out


def delete(db: Session, patient_id: int) -> bool:
    obj = db.get(Patient, patient_id)
    if not obj:
        return False
    db.delete(obj)
    db.commit()
    return True
