"""Audit-log API (admin only)."""
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.crud import user as crud
from app.database import get_db
from app.schemas.user import AuditOut
from app.security import require_permission

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=List[AuditOut])
def list_audit(limit: int = 200, db: Session = Depends(get_db),
               _=Depends(require_permission("view_audit"))):
    return crud.list_audit(db, limit=limit)
