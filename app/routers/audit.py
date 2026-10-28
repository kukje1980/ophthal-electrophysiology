"""Audit-log API (admin only)."""
import csv
import io
from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.crud import user as crud
from app.database import SessionLocal, get_db
from app.models import AuditLog
from app.schemas.user import AuditOut
from app.security import require_permission

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=List[AuditOut])
def list_audit(limit: int = Query(200, ge=1, le=1000),
               offset: int = Query(0, ge=0),
               db: Session = Depends(get_db),
               _=Depends(require_permission("view_audit"))):
    return crud.list_audit(db, limit=limit, offset=offset)


@router.get("/export")
def export_audit(request: Request,
                 since: Optional[date] = None, until: Optional[date] = None,
                 db: Session = Depends(get_db),
                 user=Depends(require_permission("view_audit"))):
    """Download the audit log as CSV (optionally a date range, until is
    inclusive). Streamed in batches, so it stays fast and memory-flat however
    large the log grows. The export itself is audited."""
    start = datetime.combine(since, datetime.min.time()) if since else None
    end = datetime.combine(until + timedelta(days=1), datetime.min.time()) if until else None
    q = db.query(AuditLog)
    if start:
        q = q.filter(AuditLog.at >= start)
    if end:
        q = q.filter(AuditLog.at < end)
    total = q.count()
    crud.audit(db, user=user, action="audit.export",
               detail=f"{total} rows {since or ''}..{until or ''}", request=request)

    def rows():
        # own session: the request's session is closed once the response starts
        s = SessionLocal()
        try:
            buf = io.StringIO()
            writer = csv.writer(buf)
            buf.write("﻿")  # BOM so Excel opens the Korean text correctly
            writer.writerow(["at", "username", "action", "entity", "entity_id",
                             "detail", "ip"])
            for i, r in enumerate(crud.iter_audit(s, since=start, until=end), 1):
                writer.writerow([
                    r.at.isoformat() if r.at else "", r.username or "", r.action,
                    r.entity or "", r.entity_id if r.entity_id is not None else "",
                    r.detail or "", r.ip or "",
                ])
                if i % 500 == 0:
                    yield buf.getvalue()
                    buf.seek(0)
                    buf.truncate()
            yield buf.getvalue()
        finally:
            s.close()

    return StreamingResponse(
        rows(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=audit_log.csv"},
    )
