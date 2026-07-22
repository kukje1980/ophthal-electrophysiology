"""PHI encryption at rest and masking.

The national id (주민등록번호) and any similarly sensitive value are stored
encrypted with Fernet (AES-128-CBC + HMAC). The plaintext is only ever
decrypted for a user who holds the ``view_phi`` permission, and that access
is written to the audit log by the router.
"""
from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

_PREFIX = "enc:"  # marks an already-encrypted value


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = settings.PHI_ENCRYPTION_KEY
    if not key:
        # Derive a stable key from SECRET_KEY so the demo runs without extra
        # configuration. Production should set PHI_ENCRYPTION_KEY explicitly.
        digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        key = base64.urlsafe_b64encode(digest).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_phi(plaintext: str | None) -> str | None:
    if plaintext is None or plaintext == "":
        return None
    token = _fernet().encrypt(plaintext.encode()).decode()
    return _PREFIX + token


def decrypt_phi(stored: str | None) -> str | None:
    if not stored:
        return None
    if not stored.startswith(_PREFIX):
        return stored  # legacy/plaintext value, return as-is
    try:
        return _fernet().decrypt(stored[len(_PREFIX):].encode()).decode()
    except InvalidToken:
        return None


def mask_rrn(stored: str | None) -> str | None:
    """Return a masked national id (e.g. 680310-1******) from stored cipher."""
    plain = decrypt_phi(stored)
    if not plain:
        return None
    if "-" in plain:
        front, back = plain.split("-", 1)
        keep = back[:1]
        return f"{front}-{keep}{'*' * max(0, len(back) - 1)}"
    # No dash: reveal first 6 chars, mask the rest.
    return plain[:6] + "*" * max(0, len(plain) - 6)
