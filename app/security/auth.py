"""Authentication and role-based access control (RBAC).

Roles and the permissions they grant. Keeping this in one table makes the
access policy auditable at a glance.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db

# All discrete permissions in the system.
PERMISSIONS = {
    "view_patient", "edit_patient", "delete_patient",
    "run_exam", "delete_exam", "view_report",
    "view_phi",         # decrypt/reveal the full national id
    "manage_users",     # create/disable accounts
    "view_audit",       # read the audit log
}

# Role -> granted permissions.
ROLES = {
    "admin": set(PERMISSIONS),  # everything
    "clinician": {
        "view_patient", "edit_patient", "delete_patient",
        "run_exam", "delete_exam", "view_report", "view_phi",
    },
    "technician": {
        "view_patient", "edit_patient", "run_exam", "view_report",
    },  # note: no view_phi
    "viewer": {"view_patient", "view_report"},
}

ROLE_LABELS = {
    "admin": "관리자 (Admin)",
    "clinician": "의사 (Clinician)",
    "technician": "검사기사 (Technician)",
    "viewer": "조회자 (Viewer)",
}


def has_permission(user, permission: str) -> bool:
    if user is None:
        return False
    return permission in ROLES.get(user.role, set())


def current_user(request: Request, db: Session = Depends(get_db)):
    """Return the logged-in User (or None). Never raises."""
    from app.models import User  # local import avoids a cycle at import time

    uid = request.session.get("user_id")
    if not uid:
        return None
    user = db.get(User, uid)
    if user is None or not user.is_active:
        return None
    return user


def require_login(user=Depends(current_user)):
    """Dependency: 401 for API routes when not authenticated."""
    if user is None:
        raise HTTPException(401, "Authentication required")
    return user


def require_permission(permission: str):
    """Dependency factory enforcing a single permission."""
    def _dep(user=Depends(require_login)):
        if not has_permission(user, permission):
            raise HTTPException(403, f"Permission denied: {permission}")
        return user
    return _dep


def optional_user(request: Request) -> Optional[int]:
    """Cheap check (no DB) used by the auth middleware for page gating."""
    return request.session.get("user_id")
