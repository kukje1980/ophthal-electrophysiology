"""Audit-log API (admin only)."""
import csv
import io
from typing import List

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
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


@router.get("/export")
def export_audit(request: Request, db: Session = Depends(get_db),
                 user=Depends(require_permission("view_audit"))):
    """Download the audit log as CSV. The export itself is audited."""
    rows = crud.list_audit(db, limit=100_000)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["at", "username", "action", "entity", "entity_id",
                     "detail", "ip"])
    for r in rows:
        writer.writerow([
            r.at.isoformat() if r.at else "", r.username or "", r.action,
            r.entity or "", r.entity_id if r.entity_id is not None else "",
            r.detail or "", r.ip or "",
        ])
    buf.seek(0)
    crud.audit(db, user=user, action="audit.export",
               detail=f"{len(rows)} rows", request=request)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_log.csv"},
    )
