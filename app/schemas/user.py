"""User and audit schemas."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class UserCreate(BaseModel):
    username: str = Field(..., max_length=64)
    password: str = Field(..., min_length=6, max_length=128)
    full_name: Optional[str] = Field(None, max_length=128)
    role: str = Field("viewer", max_length=16)


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, max_length=128)
    role: Optional[str] = Field(None, max_length=16)
    is_active: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=6, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: Optional[str] = None
    role: str
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6, max_length=128)


class TotpEnable(BaseModel):
    code: str = Field(..., min_length=6, max_length=8)


class TotpDisable(BaseModel):
    current_password: str


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    at: datetime
    username: Optional[str] = None
    action: str
    entity: Optional[str] = None
    entity_id: Optional[int] = None
    detail: Optional[str] = None
    ip: Optional[str] = None
