"""Laboratory reference-range API (normative data management)."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.crud import reference as crud
from app.crud import user as audit_crud
from app.database import get_db
from app.security import require_permission

router = APIRouter(prefix="/api/reference", tags=["reference"])


class RangeIn(BaseModel):
    step_key: str = Field(..., max_length=32)
    marker: str = Field(..., max_length=16)
    age_min: Optional[int] = None
    age_max: Optional[int] = None
    amp_min: Optional[float] = None
    amp_max: Optional[float] = None
    lat_min: Optional[float] = None
    lat_max: Optional[float] = None
    n: Optional[int] = None
    source: Optional[str] = Field(None, max_length=16)
    note: Optional[str] = Field(None, max_length=128)


class RangeOut(RangeIn):
    id: int

    model_config = {"from_attributes": True}


class CsvIn(BaseModel):
    csv: str
    method: str = "sd2"   # compute only: sd2 | pct
    save: bool = False    # compute only: persist the result


@router.get("", response_model=List[RangeOut])
def list_ranges(db: Session = Depends(get_db),
                _=Depends(require_permission("view_report"))):
    return crud.list_all(db)


@router.put("", response_model=RangeOut)
def upsert_range(data: RangeIn, request: Request, db: Session = Depends(get_db),
                 user=Depends(require_permission("manage_reference"))):
    row = crud.upsert(db, data.model_dump())
    audit_crud.audit(db, user=user, action="reference.upsert", entity="reference",
                     entity_id=row.id, detail=f"{row.step_key}/{row.marker}",
                     request=request)
    return row


@router.delete("/{row_id}", status_code=204)
def delete_range(row_id: int, request: Request, db: Session = Depends(get_db),
                 user=Depends(require_permission("manage_reference"))):
    if not crud.delete(db, row_id):
        raise HTTPException(404, "Reference range not found")
    audit_crud.audit(db, user=user, action="reference.delete", entity="reference",
                     entity_id=row_id, request=request)


@router.post("/import")
def import_ranges(data: CsvIn, request: Request, db: Session = Depends(get_db),
                  user=Depends(require_permission("manage_reference"))):
    n = crud.import_ranges_csv(db, data.csv)
    audit_crud.audit(db, user=user, action="reference.import", entity="reference",
                     detail=f"{n} rows", request=request)
    return {"imported": n}


@router.post("/compute")
def compute_ranges(data: CsvIn, request: Request, db: Session = Depends(get_db),
                   user=Depends(require_permission("manage_reference"))):
    """Compute normative limits from normal-subject measurements (CSV:
    step_key,marker,latency_ms,amplitude_uv). Preview unless save=true."""
    if data.method not in ("sd2", "pct"):
        raise HTTPException(400, "method must be 'sd2' or 'pct'")
    ranges = crud.compute_from_csv(data.csv, data.method)
    saved = 0
    if data.save:
        saved = crud.save_computed(db, ranges)
        audit_crud.audit(db, user=user, action="reference.compute", entity="reference",
                         detail=f"{data.method}, {saved} rows", request=request)
    return {"ranges": ranges, "saved": saved}


@router.post("/seed-demo")
def seed_demo(request: Request, replace: bool = False, db: Session = Depends(get_db),
              user=Depends(require_permission("manage_reference"))):
    n = crud.seed_demo(db, replace=replace)
    audit_crud.audit(db, user=user, action="reference.seed_demo", entity="reference",
                     detail=f"{n} rows, replace={replace}", request=request)
    return {"seeded": n}
