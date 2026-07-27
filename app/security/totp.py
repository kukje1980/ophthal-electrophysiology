"""Time-based one-time password (TOTP, RFC 6238) — standard library only.

Used for optional two-factor authentication. Secrets are base32 strings
compatible with Google Authenticator / Authy and stored encrypted at rest.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct
import time
from urllib.parse import quote

_PERIOD = 30
_DIGITS = 6


def generate_secret(length: int = 20) -> str:
    return base64.b32encode(os.urandom(length)).decode().rstrip("=")


def _hotp(secret_b32: str, counter: int) -> str:
    pad = "=" * ((8 - len(secret_b32) % 8) % 8)
    key = base64.b32decode(secret_b32 + pad, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code % (10 ** _DIGITS)).zfill(_DIGITS)


def verify(secret: str, code: str, window: int = 1, t: float | None = None) -> bool:
    if not secret or not code:
        return False
    code = code.strip().replace(" ", "")
    if not code.isdigit():
        return False
    now = int(t if t is not None else time.time())
    counter = now // _PERIOD
    for w in range(-window, window + 1):
        if hmac.compare_digest(_hotp(secret, counter + w), code.zfill(_DIGITS)):
            return True
    return False


def provisioning_uri(secret: str, account: str,
                     issuer: str = "ISCEV ERG-VEP") -> str:
    label = quote(f"{issuer}:{account}")
    return (f"otpauth://totp/{label}?secret={secret}"
            f"&issuer={quote(issuer)}&digits={_DIGITS}&period={_PERIOD}")


def qr_svg(uri: str) -> str | None:
    """Return an inline SVG QR code for the provisioning URI, or None if the
    optional ``qrcode`` package is unavailable (UI then falls back to the
    secret for manual entry)."""
    try:
        import io

        import qrcode
        import qrcode.image.svg

        img = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage,
                          box_size=9, border=2)
        buf = io.BytesIO()
        img.save(buf)
        return buf.getvalue().decode()
    except Exception:
        return None
