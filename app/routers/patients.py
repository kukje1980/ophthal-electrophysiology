"""Patient API (authenticated; role-gated; audited)."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.crud import idempotency
from app.crud import patient as crud
from app.crud import user as audit_crud
from app.database import get_db
from app.schemas import PatientCreate, PatientOut, PatientSearchOut, PatientUpdate
from app.security import decrypt_phi, require_permission

router = APIRouter(prefix="/api/patients", tags=["patients"])


def _mrn_conflict(e: crud.DuplicateMRN) -> HTTPException:
    if e.in_trash:
        return HTTPException(409, f"등록번호 '{e.mrn}'는 삭제된(휴지통) 환자가 사용 중입니다 "
                                  f"— 관리자에게 복원을 요청하세요.")
    return HTTPException(409, f"MRN '{e.mrn}' already exists")


@router.post("", response_model=PatientOut, status_code=201)
def create_patient(data: PatientCreate, request: Request,
                   db: Session = Depends(get_db),
                   user=Depends(require_permission("edit_patient"))):
    key = idempotency.key_from(request, user)
    hit = idempotency.lookup(db, key)
    if hit:  # a retried request whose first attempt already succeeded
        return crud.get(db, hit[1], include_deleted=True)
    try:
        patient = crud.create(db, data, idem_key=key)
    except (crud.DuplicateMRN, IntegrityError) as e:
        db.rollback()
        hit = idempotency.lookup(db, key)  # raced with its own earlier attempt
        if hit:
            return crud.get(db, hit[1], include_deleted=True)
        if isinstance(e, crud.DuplicateMRN):
            raise _mrn_conflict(e)
        raise HTTPException(409, f"MRN '{data.mrn}' already exists")
    audit_crud.audit(db, user=user, action="patient.create", entity="patient",
                     entity_id=patient.id, detail=f"MRN {patient.mrn}",
                     request=request)
    return patient


@router.get("", response_model=List[PatientOut])
def list_patients(response: Response, q: Optional[str] = Query(None, max_length=128),
                  limit: int = Query(50, ge=1, le=500),
                  offset: int = Query(0, ge=0),
                  db: Session = Depends(get_db),
                  _=Depends(require_permission("view_patient"))):
    """One page of patients, newest first; the total is in X-Total-Count."""
    rows, total = crud.search(db, q, limit=limit, offset=offset)
    response.headers["X-Total-Count"] = str(total)
    return rows


@router.get("/search", response_model=List[PatientSearchOut])
def search_patients(q: str = Query(..., max_length=128), limit: int = Query(20, ge=1, le=50),
                    db: Session = Depends(get_db),
                    _=Depends(require_permission("view_patient"))):
    """Reception-desk picker: the top matches with their visit history."""
    hits = crud.quick_search(db, q, limit)
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
    except crud.DuplicateMRN as e:
        raise _mrn_conflict(e)
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
    """Soft delete: the patient and their exams move to the trash and can be
    restored by an administrator; nothing is physically removed."""
    if not crud.delete(db, patient_id, by=user.username):
        raise HTTPException(404, "Patient not found")
    audit_crud.audit(db, user=user, action="patient.delete", entity="patient",
                     entity_id=patient_id, request=request)
