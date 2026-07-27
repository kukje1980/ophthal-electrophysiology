"""Security layer: password hashing, PHI encryption, authentication and RBAC."""
from app.security.passwords import hash_password, verify_password
from app.security.crypto import decrypt_phi, encrypt_phi, mask_rrn
from app.security import totp
from app.security.auth import (
    PERMISSIONS,
    ROLES,
    current_user,
    has_permission,
    require_login,
    require_permission,
)

__all__ = [
    "hash_password",
    "verify_password",
    "encrypt_phi",
    "decrypt_phi",
    "mask_rrn",
    "totp",
    "PERMISSIONS",
    "ROLES",
    "current_user",
    "has_permission",
    "require_login",
    "require_permission",
]
