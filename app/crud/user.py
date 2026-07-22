"""User CRUD and the audit-log helper."""
from typing import List, Optional

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditLog, User
from app.schemas.user import UserCreate, UserUpdate
from app.security import hash_password


def get_by_username(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == username).first()


def get(db: Session, user_id: int) -> Optional[User]:
    return db.get(User, user_id)


def list_all(db: Session) -> List[User]:
    return db.query(User).order_by(User.created_at.desc()).all()


def count(db: Session) -> int:
    return db.query(User).count()


def create(db: Session, data: UserCreate) -> User:
    obj = User(
        username=data.username,
        full_name=data.full_name,
        role=data.role,
        password_hash=hash_password(data.password),
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def update(db: Session, user_id: int, data: UserUpdate) -> Optional[User]:
    obj = db.get(User, user_id)
    if not obj:
        return None
    fields = data.model_dump(exclude_unset=True)
    if "password" in fields:
        pw = fields.pop("password")
        if pw:
            obj.password_hash = hash_password(pw)
    for k, v in fields.items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


def audit(db: Session, *, user=None, action: str, entity: str = None,
          entity_id: int = None, detail: str = None,
          request: Request = None) -> None:
    """Append one entry to the audit log (best-effort, never raises)."""
    try:
        ip = None
        if request is not None and request.client:
            ip = request.client.host
        db.add(AuditLog(
            user_id=getattr(user, "id", None),
            username=getattr(user, "username", None),
            action=action, entity=entity, entity_id=entity_id,
            detail=detail, ip=ip,
        ))
        db.commit()
    except Exception:
        db.rollback()


def list_audit(db: Session, limit: int = 200) -> List[AuditLog]:
    return db.query(AuditLog).order_by(AuditLog.at.desc()).limit(limit).all()
