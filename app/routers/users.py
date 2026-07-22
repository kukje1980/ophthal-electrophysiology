"""User administration API (admin only)."""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.crud import user as crud
from app.database import get_db
from app.schemas.user import UserCreate, UserOut, UserUpdate
from app.security import ROLES, require_permission

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=List[UserOut])
def list_users(db: Session = Depends(get_db),
               _=Depends(require_permission("manage_users"))):
    return crud.list_all(db)


@router.post("", response_model=UserOut, status_code=201)
def create_user(data: UserCreate, request: Request, db: Session = Depends(get_db),
                admin=Depends(require_permission("manage_users"))):
    if data.role not in ROLES:
        raise HTTPException(400, f"Unknown role: {data.role}")
    try:
        user = crud.create(db, data)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"Username '{data.username}' already exists")
    crud.audit(db, user=admin, action="user.create", entity="user",
               entity_id=user.id, detail=f"{user.username} ({user.role})",
               request=request)
    return user


@router.put("/{user_id}", response_model=UserOut)
def update_user(user_id: int, data: UserUpdate, request: Request,
                db: Session = Depends(get_db),
                admin=Depends(require_permission("manage_users"))):
    if data.role is not None and data.role not in ROLES:
        raise HTTPException(400, f"Unknown role: {data.role}")
    user = crud.update(db, user_id, data)
    if not user:
        raise HTTPException(404, "User not found")
    crud.audit(db, user=admin, action="user.update", entity="user",
               entity_id=user.id, detail=str(data.model_dump(exclude_unset=True)),
               request=request)
    return user
