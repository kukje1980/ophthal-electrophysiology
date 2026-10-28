"""Visit (검사 접수) CRUD, the reception transaction and picker options."""
from collections import Counter
from datetime import date
from typing import List, Optional

from sqlalchemy.orm import Session, selectinload

from app.models import Patient, User, Visit
from app.schemas import PatientCreate, VisitCreate
from app.security import encrypt_phi

# Common indications for visual electrophysiology, offered as suggestions
# alongside the diagnoses this laboratory has already used.
COMMON_DIAGNOSES = [
    "망막색소변성 (Retinitis pigmentosa)",
    "스타가르트병 (Stargardt disease)",
    "원추/원추간상세포 이영양증 (Cone / cone-rod dystrophy)",
    "선천정지야맹 (CSNB)",
    "황반이영양증 (Macular dystrophy)",
    "유전성 망막질환 의심 (Suspected inherited retinal disease)",
    "하이드록시클로로퀸 망막독성 검사 (HCQ screening)",
    "당뇨망막병증 (Diabetic retinopathy)",
    "망막혈관폐쇄 (Retinal vascular occlusion)",
    "시신경염 (Optic neuritis)",
    "허혈시신경병증 (Ischaemic optic neuropathy)",
    "녹내장 (Glaucoma)",
    "원인불명 시력저하 (Unexplained visual loss)",
    "비기질적 시력저하 감별 (Functional visual loss)",
]

ELECTRODES = ["DTL", "JET (콘택트렌즈)", "HK-loop", "Gold foil", "Burian-Allen",
              "피부전극 (Skin)"]

TEST_TYPES = ["ffERG", "PERG", "VEP", "mfERG"]

# ISCEV ffERG: at least 20 min dark adaptation and 10 min light adaptation.
DEFAULT_DARK_ADAPT_MIN = 20
DEFAULT_LIGHT_ADAPT_MIN = 10


def _fields(data: VisitCreate, exclude_unset: bool = False) -> dict:
    fields = data.model_dump(exclude_unset=exclude_unset)
    if "tests" in fields:
        fields["tests"] = ",".join(t for t in fields["tests"] if t in TEST_TYPES)
    if not fields.get("visit_date"):  # the date is required: default or keep it
        if exclude_unset:
            fields.pop("visit_date", None)
        else:
            fields["visit_date"] = date.today()
    return fields


def get(db: Session, visit_id: int) -> Optional[Visit]:
    return db.get(Visit, visit_id)


def receive(db: Session, patient_id: Optional[int],
            new_patient: Optional[PatientCreate], data: VisitCreate):
    """Register a visit for an existing patient, or create the patient and
    its first visit in one transaction. Returns ``(patient, visit, created)``;
    raises LookupError / ValueError, or IntegrityError for a duplicate ID."""
    created = False
    if patient_id is not None:
        patient = db.get(Patient, patient_id)
        if patient is None:
            raise LookupError("Patient not found")
    elif new_patient is not None:
        fields = new_patient.model_dump()
        if fields.get("national_id"):
            fields["national_id"] = encrypt_phi(fields["national_id"])
        patient = Patient(**fields)
        db.add(patient)
        db.flush()
        created = True
    else:
        raise ValueError("patient_id or patient is required")
    visit = Visit(patient_id=patient.id, **_fields(data))
    db.add(visit)
    db.commit()
    db.refresh(patient)
    db.refresh(visit)
    return patient, visit, created


def update(db: Session, visit_id: int, data: VisitCreate) -> Optional[Visit]:
    visit = db.get(Visit, visit_id)
    if visit is None:
        return None
    for k, v in _fields(data, exclude_unset=True).items():
        setattr(visit, k, v)
    db.commit()
    db.refresh(visit)
    return visit


def delete(db: Session, visit_id: int) -> bool:
    """Cancel a reception. Refused (ValueError) once exams were recorded."""
    visit = db.get(Visit, visit_id)
    if visit is None:
        return False
    if visit.exams:
        raise ValueError("검사가 기록된 접수는 취소할 수 없습니다.")
    db.delete(visit)
    db.commit()
    return True


def list_for_patient(db: Session, patient_id: int, limit: int = 100) -> List[Visit]:
    return (db.query(Visit).options(selectinload(Visit.exams))
            .filter(Visit.patient_id == patient_id)
            .order_by(Visit.visit_date.desc(), Visit.id.desc())
            .limit(limit).all())


def list_on(db: Session, day: date) -> List[Visit]:
    """One day's receptions (the desk's worklist), oldest first."""
    return (db.query(Visit)
            .options(selectinload(Visit.patient), selectinload(Visit.exams))
            .filter(Visit.visit_date == day)
            .order_by(Visit.created_at, Visit.id).all())


def options(db: Session) -> dict:
    """Suggestions for the reception form: doctors (clinician accounts plus
    names used before), diagnoses (this lab's most used first, then the
    common list), electrodes and the conditions used last time."""
    recent = (db.query(Visit.attending_doctor, Visit.diagnosis, Visit.electrode,
                       Visit.dark_adapt_min, Visit.light_adapt_min)
              .order_by(Visit.id.desc()).limit(500).all())
    clinicians = [u.full_name or u.username for u in
                  db.query(User).filter(User.role == "clinician",
                                        User.is_active.is_(True))
                  .order_by(User.full_name).all()]
    used_doctors = [d for d, _ in Counter(r[0] for r in recent if r[0]).most_common()]
    used_dx = [d for d, _ in Counter(r[1] for r in recent if r[1]).most_common(30)]
    last = recent[0] if recent else None
    return {
        "doctors": list(dict.fromkeys(clinicians + used_doctors)),
        "diagnoses": list(dict.fromkeys(used_dx + COMMON_DIAGNOSES)),
        "electrodes": list(dict.fromkeys(
            ([last[2]] if last and last[2] else []) + ELECTRODES)),
        "tests": TEST_TYPES,
        "defaults": {
            "electrode": last[2] if last else None,
            "dark_adapt_min": (last[3] if last and last[3] is not None
                               else DEFAULT_DARK_ADAPT_MIN),
            "light_adapt_min": (last[4] if last and last[4] is not None
                                else DEFAULT_LIGHT_ADAPT_MIN),
        },
    }
