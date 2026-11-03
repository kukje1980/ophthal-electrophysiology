"""Clinical photo API: upload, list, image/thumbnail delivery (authenticated;
role-gated; audited)."""
import os
from datetime import datetime
from typing import List, Optional
from urllib.parse import quote

from cryptography.fernet import InvalidToken
from fastapi import (
    APIRouter, Depends, File, Form, HTTPException, Request, Response,
    UploadFile,
)
from sqlalchemy.orm import Session

from app.config import settings
from app.crud import patient as patient_crud
from app.crud import photo as crud
from app.crud import user as audit_crud
from app.database import get_db
from app.models.photo import EYES, MODALITIES
from app.schemas import PhotoOut, PhotoUpdate
from app.security import require_permission

router = APIRouter(prefix="/api/photos", tags=["photos"])

MAX_FILES = 50
MAX_IDS = 200
_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
        "image/bmp": ".bmp", "image/gif": ".gif"}


def _check_meta(eye: Optional[str], modality: Optional[str]) -> None:
    if eye and eye not in EYES:
        raise HTTPException(400, f"eye must be one of {', '.join(EYES)}")
    if modality and modality not in MODALITIES:
        raise HTTPException(400, f"unknown modality '{modality}'")


def _parse_taken_at(value: Optional[str]) -> Optional[datetime]:
    if not value or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip())
    except ValueError:
        raise HTTPException(400, "taken_at must be an ISO date / datetime")


def _parse_ids(value: str) -> List[int]:
    try:
        ids = [int(x) for x in value.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(400, "ids must be a comma-separated list of integers")
    if len(ids) > MAX_IDS:
        raise HTTPException(400, f"at most {MAX_IDS} ids")
    return ids


def _get_or_404(db: Session, photo_id: int):
    obj = crud.get(db, photo_id)
    if not obj:
        raise HTTPException(404, "Photo not found")
    return obj


@router.get("/options")
def photo_options(_=Depends(require_permission("view_photo"))):
    """Modality and eye choices for upload / filter forms."""
    return {
        "modalities": [{"key": k, "label": v} for k, v in MODALITIES.items()],
        "eyes": list(EYES),
        "max_mb": settings.PHOTO_MAX_MB,
    }


@router.get("", response_model=List[PhotoOut])
def list_photos(patient_id: Optional[int] = None, q: Optional[str] = None,
                modality: Optional[str] = None, eye: Optional[str] = None,
                ids: Optional[str] = None, limit: int = 1000, offset: int = 0,
                db: Session = Depends(get_db),
                _=Depends(require_permission("view_photo"))):
    return crud.list_photos(
        db, patient_id=patient_id, q=q, modality=modality, eye=eye,
        ids=_parse_ids(ids) if ids is not None else None,
        limit=max(1, min(limit, 5000)), offset=max(0, offset),
    )


@router.post("", response_model=List[PhotoOut], status_code=201)
def upload_photos(request: Request,
                  patient_id: int = Form(...),
                  files: List[UploadFile] = File(...),
                  eye: Optional[str] = Form(None),
                  modality: Optional[str] = Form(None),
                  taken_at: Optional[str] = Form(None),
                  note: Optional[str] = Form(None),
                  source_id: Optional[int] = Form(None),
                  db: Session = Depends(get_db),
                  user=Depends(require_permission("upload_photo"))):
    """Upload one or more images for a patient. ``source_id`` marks the upload
    as an edited copy of an existing photo (saved from the viewer)."""
    eye, modality = eye or None, modality or None
    _check_meta(eye, modality)
    if not patient_crud.get(db, patient_id):
        raise HTTPException(404, "Patient not found")
    if source_id is not None:
        src = crud.get(db, source_id)
        if not src or src.patient_id != patient_id:
            raise HTTPException(400, "source_id must be a photo of the same patient")
    if not files or len(files) > MAX_FILES:
        raise HTTPException(400, f"send 1–{MAX_FILES} files")

    limit = settings.PHOTO_MAX_MB * 1024 * 1024
    payload = []
    for f in files:
        raw = f.file.read(limit + 1)
        if len(raw) > limit:
            raise HTTPException(413, f"{f.filename}: larger than {settings.PHOTO_MAX_MB} MB")
        payload.append((f.filename or "image", raw))

    try:
        photos = crud.create_many(
            db, patient_id, payload, eye=eye, modality=modality,
            taken_at=_parse_taken_at(taken_at), note=(note or None),
            source_id=source_id, uploaded_by=user.username,
        )
    except crud.PhotoError as e:
        raise HTTPException(400, str(e))
    for p in photos:
        audit_crud.audit(
            db, user=user, action="photo.edit_save" if source_id else "photo.upload",
            entity="photo", entity_id=p.id,
            detail=f"patient {patient_id}" + (f", from #{source_id}" if source_id else ""),
            request=request,
        )
    return photos


@router.get("/{photo_id}", response_model=PhotoOut)
def get_photo(photo_id: int, db: Session = Depends(get_db),
              _=Depends(require_permission("view_photo"))):
    return _get_or_404(db, photo_id)


@router.get("/{photo_id}/image")
def photo_image(photo_id: int, request: Request, download: bool = False,
                db: Session = Depends(get_db),
                user=Depends(require_permission("view_photo"))):
    """The full-resolution image (decrypted). Every fetch is audited."""
    obj = _get_or_404(db, photo_id)
    try:
        data = crud.read_image(obj)
    except (FileNotFoundError, InvalidToken):
        raise HTTPException(410, "Image file is missing or unreadable")
    audit_crud.audit(db, user=user,
                     action="photo.download" if download else "photo.view",
                     entity="photo", entity_id=photo_id,
                     detail=f"patient {obj.patient_id}", request=request)
    headers = {"Cache-Control": "private, no-store"}
    if download:
        ext = _EXT.get(obj.content_type, "")
        stem = os.path.splitext(obj.original_name or "")[0] or f"photo-{obj.id}"
        headers["Content-Disposition"] = (
            f"attachment; filename=\"photo-{obj.id}{ext}\"; "
            f"filename*=UTF-8''{quote(stem + ext)}"
        )
    return Response(data, media_type=obj.content_type, headers=headers)


@router.get("/{photo_id}/thumb")
def photo_thumb(photo_id: int, db: Session = Depends(get_db),
                _=Depends(require_permission("view_photo"))):
    obj = _get_or_404(db, photo_id)
    try:
        data = crud.read_thumb(obj)
    except (FileNotFoundError, InvalidToken):
        raise HTTPException(410, "Thumbnail is missing or unreadable")
    return Response(data, media_type="image/jpeg",
                    headers={"Cache-Control": "private, max-age=3600"})


@router.put("/{photo_id}", response_model=PhotoOut)
def update_photo(photo_id: int, data: PhotoUpdate, request: Request,
                 db: Session = Depends(get_db),
                 user=Depends(require_permission("upload_photo"))):
    _check_meta(data.eye, data.modality)
    obj = crud.update(db, photo_id, data)
    if not obj:
        raise HTTPException(404, "Photo not found")
    audit_crud.audit(db, user=user, action="photo.update", entity="photo",
                     entity_id=photo_id,
                     detail=",".join(data.model_dump(exclude_unset=True).keys()),
                     request=request)
    return obj


@router.delete("/{photo_id}", status_code=204)
def delete_photo(photo_id: int, request: Request, db: Session = Depends(get_db),
                 user=Depends(require_permission("delete_photo"))):
    if not crud.delete(db, photo_id):
        raise HTTPException(404, "Photo not found")
    audit_crud.audit(db, user=user, action="photo.delete", entity="photo",
                     entity_id=photo_id, request=request)
