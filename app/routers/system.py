"""System health, backups and the trash (soft-deleted records).

* ``GET /health`` — public liveness probe (database reachable?) for monitoring
  tools and for the browser's connection indicator.
* ``/api/system/*``, ``/api/backups/*``, ``/api/trash/*`` — administrator only.
"""
import logging
import shutil
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app import backup
from app.config import settings
from app.crud import exam as exam_crud
from app.crud import patient as patient_crud
from app.crud import user as audit_crud
from app.database import IS_SQLITE, SessionLocal, engine, get_db, init_db, quick_check, sqlite_path
from app.models import AuditLog, Exam, Measurement, Patient, Waveform
from app.security import require_permission
from app.security.crypto import phi_key_problems

router = APIRouter(tags=["system"])
log = logging.getLogger("app.system")

_admin = require_permission("manage_system")


@router.get("/health")
def health():
    """Liveness probe. 200 when the database answers, 503 otherwise."""
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
    except Exception as e:  # noqa: BLE001
        log.error("health check: database unreachable: %s", e)
        return JSONResponse({"status": "error", "db": "error"}, status_code=503)
    return {"status": "ok", "db": "ok", "time": datetime.now().isoformat(timespec="seconds")}


def _warnings(bk: dict, disk_free: Optional[int], phi_bad: int) -> list:
    out = []
    if settings.SECRET_KEY == "dev-insecure-change-me":
        out.append("기본 SECRET_KEY를 사용 중입니다 — 운영 환경에서는 반드시 변경하고, "
                   "PHI_ENCRYPTION_KEY를 별도로 설정·보관하세요.")
    if phi_bad:
        out.append(f"암호화된 주민등록번호 {phi_bad}건을 복호화할 수 없습니다 — "
                   f"SECRET_KEY / PHI_ENCRYPTION_KEY가 바뀌었는지 확인하세요.")
    if not bk.get("supported"):
        out.append("내장 백업은 SQLite만 지원합니다 — 사용 중인 DB의 백업 도구(pg_dump 등)로 "
                   "정기 백업을 구성하세요.")
    else:
        if not bk["enabled"]:
            out.append("자동 백업이 꺼져 있습니다 (BACKUP_ENABLED=0).")
        if bk["last"] is None:
            out.append("아직 정상 백업이 없습니다 — 지금 백업을 실행하세요.")
        elif bk["last_age_hours"] is not None and \
                bk["last_age_hours"] > max(24.0, 2 * bk["interval_hours"]):
            out.append(f"마지막 백업이 {bk['last_age_hours']:.0f}시간 전입니다.")
        if bk.get("last_error"):
            out.append(f"최근 백업 실패 ({bk.get('last_error_at')}): {bk['last_error']}")
        if not bk.get("mirror_dir"):
            out.append("백업 미러(BACKUP_MIRROR_DIR)가 설정되지 않았습니다 — 디스크 고장 시 "
                       "데이터와 백업이 함께 사라질 수 있습니다. NAS/외장디스크를 지정하세요.")
        elif bk["last"] and bk["last"].get("mirror_error"):
            out.append(f"백업 미러 복사 실패: {bk['last']['mirror_error']}")
    if disk_free is not None and disk_free < 2 * 1024 ** 3:
        out.append(f"데이터베이스 디스크 여유 공간이 {disk_free / 2**30:.1f} GB 남았습니다.")
    return out


@router.get("/api/system/status")
def system_status(db: Session = Depends(get_db), _=Depends(_admin)):
    path = sqlite_path()
    db_info = {"dialect": engine.dialect.name, "path": str(path) if path else None}
    disk_free = None
    if path is not None and path.exists():
        wal = path.with_name(path.name + "-wal")
        db_info.update(size=path.stat().st_size,
                       wal_size=wal.stat().st_size if wal.exists() else 0)
        disk_free = shutil.disk_usage(path.parent).free
        db_info["disk_free"] = disk_free
    if IS_SQLITE:
        db_info.update({k: db.execute(text(f"PRAGMA {k}")).scalar() for k in
                        ("journal_mode", "synchronous", "foreign_keys")})

    counts = {
        "patients": db.query(func.count(Patient.id)).filter(Patient.deleted_at.is_(None)).scalar(),
        "patients_deleted": db.query(func.count(Patient.id)).filter(Patient.deleted_at.isnot(None)).scalar(),
        "exams": exam_crud.count(db),
        "exams_deleted": db.query(func.count(Exam.id)).filter(Exam.deleted_at.isnot(None)).scalar(),
        "waveforms": db.query(func.count(Waveform.id)).scalar(),
        "measurements": db.query(func.count(Measurement.id)).scalar(),
        "audit_logs": db.query(func.count(AuditLog.id)).scalar(),
    }
    bk = backup.status()
    phi_bad = phi_key_problems(db)
    return {"database": db_info, "counts": counts, "backup": bk,
            "warnings": _warnings(bk, disk_free, phi_bad)}


@router.post("/api/system/integrity")
async def integrity(request: Request, user=Depends(_admin)):
    """Structural integrity check of the live database (PRAGMA quick_check)."""
    result = await run_in_threadpool(quick_check)
    db = SessionLocal()
    try:
        audit_crud.audit(db, user=user, action="system.integrity", detail=result,
                         request=request)
    finally:
        db.close()
    return {"result": result, "ok": result == "ok"}


# -- backups ------------------------------------------------------------------

def _require_backup_support():
    if not backup.supported():
        raise HTTPException(400, "내장 백업은 SQLite 데이터베이스만 지원합니다.")


@router.get("/api/backups")
def list_backups(_=Depends(_admin)):
    _require_backup_support()
    return {"backups": [{k: v for k, v in e.items() if k != "ts"}
                        for e in backup.list_backups()],
            "status": backup.status()}


@router.post("/api/backups", status_code=201)
def create_backup(request: Request, db: Session = Depends(get_db), user=Depends(_admin)):
    _require_backup_support()
    try:
        info = backup.create_backup("manual")
    except backup.BackupBusy as e:
        raise HTTPException(409, str(e), headers={"Retry-After": "5"})
    except backup.BackupError as e:
        raise HTTPException(500, f"백업 실패: {e}")
    audit_crud.audit(db, user=user, action="backup.create", detail=info["name"],
                     request=request)
    return info


@router.get("/api/backups/{name}/download")
def download_backup(name: str, request: Request, db: Session = Depends(get_db),
                    user=Depends(_admin)):
    _require_backup_support()
    try:
        path = backup._resolve(name)
    except backup.BackupError as e:
        raise HTTPException(404, str(e))
    # a backup contains every patient record: always audited
    audit_crud.audit(db, user=user, action="backup.download", detail=name, request=request)
    return FileResponse(path, media_type="application/gzip", filename=name)


@router.post("/api/backups/{name}/verify")
def verify_backup(name: str, request: Request, db: Session = Depends(get_db),
                  user=Depends(_admin)):
    _require_backup_support()
    try:
        result = backup.verify_backup(name)
    except backup.BackupError as e:
        raise HTTPException(400, str(e))
    audit_crud.audit(db, user=user, action="backup.verify",
                     detail=f"{name} ok={result['ok']}", request=request)
    return result


class RestoreRequest(BaseModel):
    confirm: str  # must repeat the backup name


@router.post("/api/backups/{name}/restore")
def restore_backup(name: str, data: RestoreRequest, request: Request,
                   user=Depends(_admin)):
    """Replace the live database with a backup (a pre-restore safety copy of
    the current state is taken first, so the restore can be undone)."""
    _require_backup_support()
    if data.confirm != name:
        raise HTTPException(400, "확인을 위해 백업 이름을 정확히 입력하세요.")
    username = user.username
    try:
        result = backup.restore_backup(name)
    except backup.BackupBusy as e:
        raise HTTPException(409, str(e), headers={"Retry-After": "5"})
    except backup.BackupError as e:
        raise HTTPException(400, f"복원 실패: {e}")
    init_db()  # bring an older backup's schema up to date
    db = SessionLocal()
    try:
        # the restored database may predate this admin's account
        restored_user = audit_crud.get_by_username(db, username)
        audit_crud.audit(db, user=restored_user, action="backup.restore",
                         detail=f"{name} by {username} (safety copy "
                                f"{result['pre_restore_backup']})",
                         request=request)
    finally:
        db.close()
    return result


# -- trash -------------------------------------------------------------------

@router.get("/api/trash")
def list_trash(db: Session = Depends(get_db), _=Depends(_admin)):
    patients = patient_crud.list_deleted(db)
    exams = exam_crud.list_deleted(db)
    return {
        "patients": [{"id": p.id, "mrn": p.mrn, "name": p.name,
                      "deleted_at": p.deleted_at, "deleted_by": p.deleted_by}
                     for p in patients],
        "exams": [{"id": e.id, "patient_id": e.patient_id,
                   "patient_name": e.patient.name if e.patient else None,
                   "test_type": e.test_type, "protocol": e.protocol,
                   "performed_at": e.performed_at,
                   "deleted_at": e.deleted_at, "deleted_by": e.deleted_by}
                  for e in exams],
    }


@router.post("/api/trash/patients/{patient_id}/restore")
def restore_patient(patient_id: int, request: Request, db: Session = Depends(get_db),
                    user=Depends(_admin)):
    if not patient_crud.restore(db, patient_id):
        raise HTTPException(404, "휴지통에 해당 환자가 없습니다.")
    audit_crud.audit(db, user=user, action="patient.restore", entity="patient",
                     entity_id=patient_id, request=request)
    return {"status": "restored"}


@router.post("/api/trash/exams/{exam_id}/restore")
def restore_exam(exam_id: int, request: Request, db: Session = Depends(get_db),
                 user=Depends(_admin)):
    if not exam_crud.restore(db, exam_id):
        raise HTTPException(404, "휴지통에 해당 검사가 없습니다.")
    audit_crud.audit(db, user=user, action="exam.restore", entity="exam",
                     entity_id=exam_id, request=request)
    return {"status": "restored"}
