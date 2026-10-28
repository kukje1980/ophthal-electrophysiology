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

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.config import settings

_PREFIX = "enc:"  # marks an already-encrypted value


def _derived_key() -> bytes:
    digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return base64.urlsafe_b64encode(digest)


@lru_cache(maxsize=1)
def _fernet() -> MultiFernet:
    """Encrypt with the first key, decrypt with any of them.

    PHI_ENCRYPTION_KEY may list several comma-separated keys (newest first)
    for key rotation. Without it a key is derived from SECRET_KEY so the demo
    runs out of the box. The derived key is always kept as a decrypt-only
    fallback, so configuring PHI_ENCRYPTION_KEY after records already exist
    never makes those records unreadable.
    """
    keys = [k.strip() for k in settings.PHI_ENCRYPTION_KEY.split(",") if k.strip()]
    fernets = [Fernet(k.encode()) for k in keys]
    fernets.append(Fernet(_derived_key()))
    return MultiFernet(fernets)


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


def phi_key_problems(db, sample: int = 200) -> int:
    """How many of (up to ``sample``) encrypted national ids fail to decrypt —
    non-zero means the encryption key changed and records are unreadable."""
    from app.models import Patient

    rows = (db.query(Patient.national_id)
            .filter(Patient.national_id.like(_PREFIX + "%"))
            .limit(sample).all())
    return sum(1 for (value,) in rows if decrypt_phi(value) is None)
