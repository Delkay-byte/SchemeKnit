"""Per-account failed-login tracking and progressive cooldown.

The counter is keyed by an HMAC of the normalized account identifier, not the
plaintext email. Counters are account-scoped so an attacker cannot evade them by
changing IP address. The cooldown is bounded (never permanent) and short enough
to limit lockout-denial-of-service; account recovery remains available.

The table is additive (migration v044). No password or token is stored here.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import get_settings
from .database import LoginFailureDB


def _now() -> datetime:
    return datetime.utcnow()


def _settings():
    return get_settings()


def _hmac_key() -> bytes:
    s = _settings()
    raw = (getattr(s, "SECURITY_HMAC_KEY", "") or "").strip()
    if raw:
        return raw.encode("utf-8")
    # Local/development fallback only. Production should set a dedicated key.
    return (getattr(s, "SECRET_KEY", "") or "schemeKnit-local-security").encode(
        "utf-8")


def account_key(identifier: str) -> str:
    """Opaque, stable HMAC for one normalized account identifier."""
    normalized = (identifier or "").strip().lower()
    return hmac.new(
        _hmac_key(), normalized.encode("utf-8"), hashlib.sha256).hexdigest()


def _steps() -> list[int]:
    raw = (getattr(_settings(), "LOGIN_LOCKOUT_STEPS", "") or "1,5,15,30,60")
    try:
        return [int(p.strip()) for p in raw.split(",") if p.strip()]
    except ValueError:
        return [1, 5, 15, 30, 60]


def _window_minutes() -> int:
    return max(1, int(getattr(_settings(), "LOGIN_FAILURE_WINDOW_MINUTES", 15)))


def _max_failures() -> int:
    return max(1, int(getattr(_settings(), "LOGIN_MAX_FAILURES", 5)))


def _track_hours() -> int:
    return max(1, int(getattr(_settings(), "LOGIN_LOCKOUT_TRACK_HOURS", 24)))


def _get_or_create(db: Session, key: str) -> LoginFailureDB:
    row = (
        db.query(LoginFailureDB)
        .filter(LoginFailureDB.account_key == key)
        .with_for_update()
        .first()
    )
    if row is not None:
        return row
    row = LoginFailureDB(
        account_key=key, failed_count=0, window_started_at=_now(),
        lockout_count=0,
    )
    db.add(row)
    try:
        db.flush()
        return row
    except IntegrityError:
        db.rollback()
        row = (
            db.query(LoginFailureDB)
            .filter(LoginFailureDB.account_key == key)
            .with_for_update()
            .first()
        )
        if row is None:
            raise
        return row


def check_lockout(db: Session, identifier: str,
                  now: Optional[datetime] = None) -> int:
    """Return remaining cooldown seconds, or 0 when not locked."""
    now = now or _now()
    row = (
        db.query(LoginFailureDB)
        .filter(LoginFailureDB.account_key == account_key(identifier))
        .first()
    )
    if row is None or row.lockout_until is None:
        return 0
    if row.lockout_until <= now:
        return 0
    return max(1, int((row.lockout_until - now).total_seconds()) + 1)


def record_failure(db: Session, identifier: str,
                   now: Optional[datetime] = None) -> int:
    """Record one failed password attempt.

    Returns the new cooldown in seconds when this failure triggered it, else 0.
    The rolling failure window resets after the configured minutes, but the
    escalation history remains until the 24-hour tracking window expires.
    """
    now = now or _now()
    key = account_key(identifier)
    row = _get_or_create(db, key)

    if row.lockout_until and row.lockout_until > now:
        # Already locked: do not inflate counters on every blocked request.
        db.commit()
        return max(1, int((row.lockout_until - now).total_seconds()) + 1)

    window = timedelta(minutes=_window_minutes())
    if row.window_started_at is None or now - row.window_started_at >= window:
        row.failed_count = 0
        row.window_started_at = now

    row.failed_count = int(row.failed_count or 0) + 1
    row.last_failed_at = now

    cooldown = 0
    if row.failed_count >= _max_failures():
        track = timedelta(hours=_track_hours())
        if (row.last_lockout_at is None
                or now - row.last_lockout_at > track):
            row.lockout_count = 0
        row.lockout_count = int(row.lockout_count or 0) + 1
        steps = _steps() or [1]
        idx = min(row.lockout_count - 1, len(steps) - 1)
        cooldown = int(steps[idx]) * 60
        row.lockout_until = now + timedelta(seconds=cooldown)
        row.last_lockout_at = now
        row.failed_count = 0
        row.window_started_at = now

    row.updated_at = now
    db.commit()
    return cooldown


def clear_failures(db: Session, identifier: str) -> None:
    """Clear failure and escalation state after successful authentication."""
    key = account_key(identifier)
    row = (
        db.query(LoginFailureDB)
        .filter(LoginFailureDB.account_key == key)
        .first()
    )
    if row is not None:
        db.delete(row)
        db.commit()
