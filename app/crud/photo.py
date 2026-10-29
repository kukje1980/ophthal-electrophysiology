"""Clinical photo storage and CRUD.

Image bytes are written under ``PHOTO_DIR`` encrypted with the PHI Fernet key
and named by a random storage key, so neither file names nor file contents
reveal patient data on disk. Each image also gets a small JPEG thumbnail for
the gallery. Browser-displayable formats (JPEG / PNG / WebP / BMP / GIF) are
kept exactly as uploaded; anything else Pillow can decode (e.g. the TIFF a
fundus camera exports) is converted to lossless PNG so the viewer can show it.
"""
import io
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageOps
from sqlalchemy import event, func, or_
from sqlalchemy.orm import Session, contains_eager, object_session

from app.config import settings
from app.models import Patient, Photo
from app.schemas import PhotoUpdate
from app.security import decrypt_bytes, encrypt_bytes

# Pillow format -> MIME type, for formats browsers display natively.
WEB_FORMATS = {
    "JPEG": "image/jpeg", "MPO": "image/jpeg", "PNG": "image/png",
    "WEBP": "image/webp", "BMP": "image/bmp", "GIF": "image/gif",
}
THUMB_SIZE = (360, 360)
MAX_PIXELS = 100_000_000  # refuse decompression bombs

_EXIF_DATETIME_ORIGINAL = 0x9003
_EXIF_DATETIME = 0x0132
_EXIF_IFD = 0x8769


class PhotoError(ValueError):
    """The uploaded file is not a usable image."""


@dataclass
class Prepared:
    data: bytes          # bytes to store (original, or PNG conversion)
    thumb: bytes         # JPEG thumbnail
    content_type: str
    width: int           # display size (EXIF orientation applied)
    height: int
    taken_at: Optional[datetime]  # from EXIF, when present


def _to_8bit(img: Image.Image) -> Image.Image:
    """Reduce high-bit-depth images (16-bit / float TIFF) to 8-bit grey."""
    if img.mode in ("I;16", "I;16B", "I;16L", "I;16N", "I", "F"):
        arr = np.asarray(img, dtype=np.float32)
        top = float(arr.max()) or 1.0
        arr = np.clip(arr * (255.0 / top), 0, 255).astype(np.uint8)
        return Image.fromarray(arr, "L")
    if img.mode not in ("1", "L", "LA", "P", "RGB", "RGBA"):
        return img.convert("RGB")
    return img


def _exif_taken_at(img: Image.Image) -> Optional[datetime]:
    try:
        exif = img.getexif()
        raw = exif.get_ifd(_EXIF_IFD).get(_EXIF_DATETIME_ORIGINAL) \
            or exif.get(_EXIF_DATETIME)
        return datetime.strptime(str(raw).strip(), "%Y:%m:%d %H:%M:%S") \
            if raw else None
    except Exception:
        return None


def _thumbnail(img: Image.Image) -> bytes:
    thumb = _to_8bit(img).copy()
    thumb.thumbnail(THUMB_SIZE)
    if thumb.mode in ("RGBA", "LA", "P"):
        rgba = thumb.convert("RGBA")
        thumb = Image.new("RGB", rgba.size, (0, 0, 0))  # photos sit on black
        thumb.paste(rgba, mask=rgba.getchannel("A"))
    else:
        thumb = thumb.convert("RGB")
    buf = io.BytesIO()
    thumb.save(buf, "JPEG", quality=82)
    return buf.getvalue()


def prepare_image(raw: bytes) -> Prepared:
    """Validate an upload and derive what is stored for it."""
    try:
        img = Image.open(io.BytesIO(raw))
        fmt = img.format
        if img.size[0] * img.size[1] > MAX_PIXELS:
            raise PhotoError("이미지 해상도가 너무 큽니다")
        img.load()
    except PhotoError:
        raise
    except Exception as e:  # unidentified, truncated, decompression bomb ...
        raise PhotoError("이미지 파일을 읽을 수 없습니다") from e

    shown = ImageOps.exif_transpose(img)  # browsers honour EXIF orientation
    if fmt in WEB_FORMATS:
        data, content_type = raw, WEB_FORMATS[fmt]
    else:
        buf = io.BytesIO()
        _to_8bit(shown).save(buf, "PNG")
        data, content_type = buf.getvalue(), "image/png"
    return Prepared(
        data=data, thumb=_thumbnail(shown), content_type=content_type,
        width=shown.size[0], height=shown.size[1],
        taken_at=_exif_taken_at(img),
    )


# -- encrypted file store ---------------------------------------------------

def _path(key: str, kind: str) -> str:
    """kind: "img" or "thumb". Files are sharded by the key's first byte."""
    return os.path.join(settings.PHOTO_DIR, key[:2], f"{key}.{kind}")


def _write(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(encrypt_bytes(data))
    os.replace(tmp, path)


def _read(path: str) -> bytes:
    with open(path, "rb") as f:
        return decrypt_bytes(f.read())


def _remove_files(key: str) -> None:
    for kind in ("img", "thumb"):
        try:
            os.remove(_path(key, kind))
        except FileNotFoundError:
            pass


def read_image(photo: Photo) -> bytes:
    return _read(_path(photo.storage_key, "img"))


def read_thumb(photo: Photo) -> bytes:
    return _read(_path(photo.storage_key, "thumb"))


# Files of deleted rows (incl. a patient-delete cascade) are removed only once
# the delete commits, so a rolled-back transaction never loses an image.
_PENDING = "photo_files_pending_removal"


@event.listens_for(Photo, "after_delete")
def _queue_file_removal(mapper, connection, target):
    session = object_session(target)
    if session is not None:
        session.info.setdefault(_PENDING, set()).add(target.storage_key)


@event.listens_for(Session, "after_commit")
def _remove_deleted_files(session):
    for key in session.info.pop(_PENDING, ()):
        _remove_files(key)


@event.listens_for(Session, "after_rollback")
def _keep_files(session):
    session.info.pop(_PENDING, None)


# -- CRUD -------------------------------------------------------------------

def _title_from(filename: str) -> Optional[str]:
    stem = os.path.splitext(os.path.basename(filename or ""))[0].strip()
    return stem[:128] or None


def create_many(db: Session, patient_id: int,
                files: Sequence[Tuple[str, bytes]], *,
                eye: Optional[str] = None, modality: Optional[str] = None,
                taken_at: Optional[datetime] = None, note: Optional[str] = None,
                source_id: Optional[int] = None,
                uploaded_by: Optional[str] = None) -> List[Photo]:
    """Store a batch of uploads for one patient, all or nothing.
    Raises PhotoError (prefixed with the file name) for an unusable file."""
    created, keys = [], []
    try:
        for name, raw in files:
            try:
                prep = prepare_image(raw)
            except PhotoError as e:
                raise PhotoError(f"{name}: {e}") from e
            key = uuid.uuid4().hex
            keys.append(key)
            _write(_path(key, "img"), prep.data)
            _write(_path(key, "thumb"), prep.thumb)
            obj = Photo(
                patient_id=patient_id, eye=eye, modality=modality,
                taken_at=taken_at or prep.taken_at, title=_title_from(name),
                note=note, original_name=(name or "")[:256] or None,
                content_type=prep.content_type, width=prep.width,
                height=prep.height, size_bytes=len(prep.data),
                storage_key=key, source_id=source_id, uploaded_by=uploaded_by,
            )
            db.add(obj)
            created.append(obj)
        db.commit()
    except Exception:
        db.rollback()
        for key in keys:
            _remove_files(key)
        raise
    for obj in created:
        db.refresh(obj)
    return created


def get(db: Session, photo_id: int) -> Optional[Photo]:
    return db.get(Photo, photo_id)


def list_photos(db: Session, *, patient_id: Optional[int] = None,
                q: Optional[str] = None, modality: Optional[str] = None,
                eye: Optional[str] = None, ids: Optional[List[int]] = None,
                limit: int = 1000, offset: int = 0) -> List[Photo]:
    """Newest first (by acquisition date, else upload date). With ``ids`` the
    rows come back in the order the ids were given."""
    query = (
        db.query(Photo)
        .join(Patient, Photo.patient_id == Patient.id)
        .options(contains_eager(Photo.patient))
    )
    if ids is not None:
        rows = query.filter(Photo.id.in_(ids)).all()
        by_id = {p.id: p for p in rows}
        return [by_id[i] for i in dict.fromkeys(ids) if i in by_id]
    if patient_id is not None:
        query = query.filter(Photo.patient_id == patient_id)
    if modality:
        query = query.filter(Photo.modality == modality)
    if eye:
        query = query.filter(Photo.eye == eye)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Patient.name.ilike(like), Patient.mrn.ilike(like),
            Photo.title.ilike(like), Photo.note.ilike(like),
        ))
    return (
        query.order_by(func.coalesce(Photo.taken_at, Photo.created_at).desc(),
                       Photo.id.desc())
        .offset(offset).limit(limit).all()
    )


def count(db: Session) -> int:
    return db.query(Photo).count()


def update(db: Session, photo_id: int, data: PhotoUpdate) -> Optional[Photo]:
    obj = db.get(Photo, photo_id)
    if not obj:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    db.commit()
    db.refresh(obj)
    return obj


def delete(db: Session, photo_id: int) -> bool:
    obj = db.get(Photo, photo_id)
    if not obj:
        return False
    db.delete(obj)
    db.commit()
    return True
