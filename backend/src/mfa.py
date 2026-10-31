"""TOTP and recovery-code helpers for privileged-account MFA.

Uses only the Python standard library for TOTP (RFC 6238) and the existing
Passlib bcrypt context for recovery-code hashes. Secrets are never logged.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from typing import Iterable, Optional
from urllib.parse import quote

from .auth import hash_password, verify_password

DIGITS = 6
STEP_SECONDS = 30
ISSUER = "SchemeKnit"


def generate_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _key(secret: str) -> bytes:
    padded = secret.strip().upper()
    padded += "=" * ((8 - len(padded) % 8) % 8)
    return base64.b32decode(padded)


def step_at(now: Optional[float] = None) -> int:
    return int((now if now is not None else time.time()) // STEP_SECONDS)


def totp(secret: str, step: Optional[int] = None) -> str:
    counter = step if step is not None else step_at()
    digest = hmac.new(
        _key(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code % (10 ** DIGITS)).zfill(DIGITS)


def verify_totp(secret: str, code: str, now: Optional[float] = None,
                window: int = 1) -> Optional[int]:
    """Return the matched timestep, or None. No secret is logged."""
    text = "".join(ch for ch in str(code or "") if ch.isdigit())
    if len(text) != DIGITS or not secret:
        return None
    current = step_at(now)
    for offset in range(-window, window + 1):
        candidate = current + offset
        if hmac.compare_digest(totp(secret, candidate), text):
            return candidate
    return None


def provisioning_uri(secret: str, account: str) -> str:
    label = quote(f"{ISSUER}:{account}", safe="")
    return (
        f"otpauth://totp/{label}?secret={secret}"
        f"&issuer={quote(ISSUER)}&algorithm=SHA1&digits={DIGITS}"
        f"&period={STEP_SECONDS}"
    )


def generate_recovery_codes(count: int = 8) -> list[str]:
    return [secrets.token_hex(5).upper() for _ in range(count)]


def hash_recovery_codes(codes: Iterable[str]) -> list[str]:
    return [hash_password(code) for code in codes]


def verify_recovery_code(code: str, hashes: Iterable[str]) -> Optional[int]:
    text = str(code or "").strip().upper()
    if not text:
        return None
    for index, stored in enumerate(list(hashes or [])):
        try:
            if verify_password(text, stored):
                return index
        except Exception:
            continue
    return None
