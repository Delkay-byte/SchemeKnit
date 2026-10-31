"""Cloudflare Turnstile server-side verification.

The browser widget only produces a short-lived token. This module is the
authority: it calls the Siteverify endpoint, validates the configured hostname
and action, and records the token digest so a replay cannot authorise a second
action.

When Siteverify is unavailable the protected action fails CLOSED with a safe,
retryable error. A browser callback that merely looks successful is never
trusted.
"""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, Optional

import requests
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import get_settings
from .database import TurnstileTokenDB, generate_id
from .logging_config import get_logger

logger = get_logger()

#: Cloudflare's documented test secrets. They are public and must only be used
#: in local/automated tests — never in production.
TEST_SECRETS = frozenset({
    "1x0000000000000000000000000000000AA",  # always passes
    "2x0000000000000000000000000000000AA",  # always fails
    "3x0000000000000000000000000000000AA",  # token already spent
})

#: Documented test site keys (public). The production site key is separate.
TEST_SITE_KEYS = frozenset({
    "1x00000000000000000000AA",  # visible, always passes
    "2x00000000000000000000AB",  # visible, always blocks
    "1x00000000000000000000BB",  # invisible, always passes
    "3x00000000000000000000FF",  # forces an interactive challenge
})

VALID_ACTIONS = frozenset({"register", "login", "password_reset"})

_TOKEN_MAX_LENGTH = 4096


class TurnstileError(HTTPException):
    """Safe HTTP error carrying a machine code for the frontend widget."""

    def __init__(self, status_code: int, code: str, message: str,
                 retryable: bool = True):
        super().__init__(
            status_code=status_code,
            detail={"code": code, "message": message},
            headers={"Retry-After": "5"} if retryable and status_code >= 500 else None,
        )
        self.code = code


def _settings():
    return get_settings()


def is_enabled() -> bool:
    return bool(getattr(_settings(), "TURNSTILE_ENABLED", False))


def _secret() -> str:
    return (getattr(_settings(), "TURNSTILE_SECRET_KEY", "") or "").strip()


def is_test_secret(secret: Optional[str] = None) -> bool:
    return (secret or _secret()) in TEST_SECRETS


def allowed_hostnames() -> list[str]:
    raw = getattr(_settings(), "TURNSTILE_ALLOWED_HOSTNAMES", "") or ""
    return [h.strip().lower() for h in raw.split(",") if h.strip()]


def _token_hash(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def validate_siteverify_payload(
    payload: Dict[str, Any],
    *,
    expected_action: str,
    hostnames: Iterable[str],
    allow_test_hostname: bool = False,
) -> None:
    """Validate one Siteverify response. Raises ``TurnstileError`` on failure.

    Split from the network call so hostname/action rules are directly testable.
    """
    if not isinstance(payload, dict) or payload.get("success") is not True:
        codes = payload.get("error-codes") if isinstance(payload, dict) else None
        logger.warning("turnstile_siteverify_rejected", codes=str(codes)[:200])
        raise TurnstileError(
            400, "turnstile_invalid",
            "Bot verification failed. Please complete the challenge again.",
            retryable=False,
        )

    action = str(payload.get("action") or "")
    if action != expected_action:
        logger.warning(
            "turnstile_action_mismatch",
            expected=expected_action, received=action[:40],
        )
        raise TurnstileError(
            400, "turnstile_action_mismatch",
            "Bot verification was issued for a different action. Please retry.",
            retryable=False,
        )

    hostname = str(payload.get("hostname") or "").strip().lower()
    allowed = {h for h in hostnames if h}
    if allow_test_hostname and is_test_secret():
        return
    if not hostname or hostname not in allowed:
        logger.warning(
            "turnstile_hostname_mismatch", received=hostname[:120],
        )
        raise TurnstileError(
            400, "turnstile_hostname_mismatch",
            "Bot verification was issued for a different site. Please retry "
            "from the SchemeKnit sign-in page.",
            retryable=False,
        )


def _siteverify(token: str, action: str, remote_ip: Optional[str]) -> Dict[str, Any]:
    secret = _secret()
    if not secret:
        # Enabled but unconfigured: fail closed, never bypass.
        logger.error("turnstile_secret_missing")
        raise TurnstileError(
            503, "turnstile_unavailable",
            "Bot verification is temporarily unavailable. Please try again "
            "in a moment.",
        )

    idempotency_key = hashlib.sha256(
        f"{action}:{token}".encode("utf-8")).hexdigest()[:32]
    data = {
        "secret": secret,
        "response": token,
        "idempotency_key": idempotency_key,
    }
    if remote_ip:
        data["remoteip"] = remote_ip

    timeout = float(
        getattr(_settings(), "TURNSTILE_TIMEOUT_SECONDS", 5.0) or 5.0)
    last_error: Optional[Exception] = None
    # One bounded retry with the same idempotency key. No unbounded loop.
    for attempt in range(2):
        try:
            response = requests.post(
                getattr(
                    _settings(), "TURNSTILE_VERIFY_URL",
                    "https://challenges.cloudflare.com/turnstile/v0/siteverify",
                ),
                data=data,
                timeout=(min(2.0, timeout), timeout),
            )
            if response.status_code >= 500:
                last_error = RuntimeError(f"siteverify_http_{response.status_code}")
                if attempt == 0:
                    time.sleep(0.25)
                    continue
                break
            return response.json()
        except Exception as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(0.25)
                continue
            break

    logger.error(
        "turnstile_siteverify_unavailable", error=str(last_error)[:200])
    raise TurnstileError(
        503, "turnstile_unavailable",
        "Bot verification is temporarily unavailable. Please try again in a "
        "moment.",
    )


def verify_token(
    db: Session,
    token: str,
    *,
    action: str,
    remote_ip: Optional[str] = None,
) -> Dict[str, Any]:
    """Verify and consume ONE Turnstile token for ``action``.

    Raises ``TurnstileError`` for missing/invalid/expired/replayed tokens, a
    wrong action, a wrong hostname, or Siteverify unavailability. On success
    the token digest is recorded atomically, so a duplicate submission cannot
    reuse it.
    """
    if action not in VALID_ACTIONS:
        raise TurnstileError(
            500, "turnstile_misconfigured",
            "Bot verification is not configured correctly.", retryable=False)

    token = (token or "").strip()
    if not token:
        raise TurnstileError(
            428, "turnstile_required",
            "Please complete the bot-verification challenge before continuing.",
        )
    if len(token) > _TOKEN_MAX_LENGTH:
        raise TurnstileError(
            400, "turnstile_invalid",
            "Bot verification failed. Please complete the challenge again.",
            retryable=False,
        )

    payload = _siteverify(token, action, remote_ip)
    validate_siteverify_payload(
        payload, expected_action=action, hostnames=allowed_hostnames())

    digest = _token_hash(token)
    now = datetime.utcnow()
    db.add(TurnstileTokenDB(
        id=generate_id(),
        token_hash=digest,
        action=action,
        hostname=str(payload.get("hostname") or "")[:255],
        # Cloudflare tokens live five minutes. This row only needs to outlive
        # the token, so an hour of replay memory is more than sufficient.
        expires_at=now + timedelta(hours=1),
        created_at=now,
    ))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.warning("turnstile_token_replay", action=action)
        raise TurnstileError(
            400, "turnstile_replay",
            "This verification has already been used. Please complete the "
            "challenge again.",
            retryable=False,
        )

    # Opportunistic cleanup of expired digest rows. Never blocks the request.
    try:
        db.query(TurnstileTokenDB).filter(
            TurnstileTokenDB.expires_at < now).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()

    return payload


def require_turnstile(
    db: Session,
    token: str,
    *,
    action: str,
    remote_ip: Optional[str] = None,
) -> None:
    """Enforce Turnstile when enabled; no-op in local/disabled builds."""
    if not is_enabled():
        return
    verify_token(db, token, action=action, remote_ip=remote_ip)


def turnstile_public_config() -> Dict[str, Any]:
    """Safe public configuration for health/feature checks (no secret)."""
    return {
        "enabled": is_enabled(),
        "site_key": (getattr(_settings(), "TURNSTILE_SITE_KEY", "") or "").strip()
        if is_enabled() else "",
        "actions": sorted(VALID_ACTIONS),
    }
