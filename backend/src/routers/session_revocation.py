"""Central session revocation and IdP back-channel logout.

Two distinct mechanisms (ADR-0004), both scoped to SSO-derived sessions of one
immutable Authentik subject — a product administrator's local password sessions
are never touched by either path:

1. ``POST /api/v1/platform/sessions/revoke``
   The Control Center ends its own session and asks this product to drop the
   SSO sessions it caused. The message is HMAC-SHA256 signed with the shared
   per-product key; the Control Center is NOT the identity provider, so this is
   an internal protocol and never presented as OIDC.

2. ``POST /api/auth/oidc/backchannel-logout``
   Standard OIDC Back-Channel Logout: Authentik POSTs a signed ``logout_token``
   when its own session ends. Validated against the IdP JWKS, issuer, audience,
   events claim, freshness and jti; matched on ``sid`` (exact) or ``sub``.

Neither endpoint requires the Control Center at runtime, so ordinary product
operation stays independent of Control Center availability.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import OidcRevocationEventDB, UserSessionDB, get_db
from ..oidc_client import OidcError, validate_logout_token

logger = logging.getLogger(__name__)

router = APIRouter(tags=["session-revocation"])

REVOCATION_ISSUER = "bloomcore-control-center"
REVOCATION_MAX_AGE_SECONDS = 300


def _sso_enabled() -> bool:
    """The SSO feature flag gates every SSO surface, including revocation.

    With SSO disabled this deployment has no SSO sessions to revoke, so the
    receivers must not exist at all — an unreachable endpoint is a smaller
    surface than a validating one (same rule the login/start endpoint follows).
    """
    from ..config import get_settings

    return bool(getattr(get_settings(), "PLATFORM_OIDC_ENABLED", False))


def _log_security(event: str, **fields) -> None:
    logger.warning(json.dumps({"event": event, **fields}, default=str))


def _audit_revocation(db: Session, *, subject: str | None, reason: str,
                      revoked: int, source: str) -> None:
    """Append a platform audit row for the revocation (never secrets)."""
    from ..database import PlatformAuditLogDB, generate_id

    db.add(PlatformAuditLogDB(
        id=generate_id(),
        actor_id="",
        actor_role="system",
        action="platform.sso_session_revoked",
        target_type="platform_admin",
        target_id=subject or "",
        details={"source": source, "reason": reason, "revoked": revoked},
    ))
    db.commit()


def _seen(db: Session, event_id: str, source: str) -> bool:
    existing = db.get(OidcRevocationEventDB, event_id)
    if existing is not None:
        return True
    db.add(OidcRevocationEventDB(event_id=event_id, source=source,
                                 received_at=datetime.utcnow()))
    return False


def _revoke_sso_sessions(db: Session, *, idp_sub: str | None,
                         idp_sid: str | None,
                         scope: str = "identity_sessions") -> int:
    """Revoke SSO-derived sessions for exactly this identity/session.

    Matching rules (narrowest first):
      * ``idp_sid`` present -> that exact session;
      * otherwise every SSO session whose ``idp_sub`` matches.

    ``auth_source = 'sso'`` is required, so local password sessions of the same
    administrator keep working. Rows with NULL provenance (pre-v053) are never
    targeted by a subject-wide revocation.
    """
    now = datetime.utcnow()
    query = db.query(UserSessionDB).filter(UserSessionDB.revoked_at.is_(None))
    if scope == "session" and idp_sid:
        query = query.filter(UserSessionDB.idp_sid == idp_sid)
        if idp_sub:
            query = query.filter(UserSessionDB.idp_sub == idp_sub)
        query = query.filter(
            or_(UserSessionDB.auth_source == "sso",
                UserSessionDB.auth_source.is_(None))
        )
    elif idp_sub:
        query = query.filter(UserSessionDB.idp_sub == idp_sub,
                             UserSessionDB.auth_source == "sso")
    else:
        return 0

    rows = query.all()
    for row in rows:
        row.revoked_at = now
    db.commit()
    return len(rows)


# ─────────────────────────────────────── 1. Control Center-initiated revocation
@router.post("/api/v1/platform/sessions/revoke")
async def revoke_from_control_center(
    request: Request,
    db: Session = Depends(get_db),
    x_bloomcore_event: Optional[str] = Header(default=None),
    x_bloomcore_signature: Optional[str] = Header(default=None),
) -> dict:
    if not _sso_enabled():
        raise HTTPException(status_code=404, detail="Not Found")

    raw = await request.body()
    if not raw or not x_bloomcore_signature or not x_bloomcore_event:
        raise HTTPException(status_code=400, detail="missing revocation message")

    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="malformed revocation message")

    from ..config import get_settings
    settings = get_settings()
    key = (getattr(settings, "PLATFORM_OIDC_LINKING_API_KEY", "") or "").strip()
    if not key:
        _log_security("revocation_misconfigured", reason="no_api_key")
        raise HTTPException(status_code=503, detail="revocation not configured")

    expected = hmac.new(key.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, x_bloomcore_signature):
        _log_security("revocation_rejected", reason="bad_signature")
        raise HTTPException(status_code=401, detail="invalid signature")

    if body.get("iss") != REVOCATION_ISSUER:
        _log_security("revocation_rejected", reason="bad_issuer")
        raise HTTPException(status_code=401, detail="invalid issuer")
    # The audience is the Control Center's product slug (e.g. "schemeknit"),
    # not the OIDC client id — see ADR-0004. Keep it configurable so a rename
    # in the registry cannot silently widen the accepted audience.
    expected_aud = (getattr(settings, "PLATFORM_REVOCATION_AUDIENCE", "")
                    or "schemeknit").strip()
    if body.get("aud") != expected_aud:
        _log_security("revocation_rejected", reason="bad_audience",
                      aud=body.get("aud"), expected=expected_aud)
        raise HTTPException(status_code=401, detail="invalid audience")
    if body.get("event_id") != x_bloomcore_event:
        _log_security("revocation_rejected", reason="event_header_mismatch")
        raise HTTPException(status_code=400, detail="event id mismatch")

    age = abs(int(time.time()) - int(body.get("iat", 0)))
    if age > REVOCATION_MAX_AGE_SECONDS:
        _log_security("revocation_rejected", reason="stale", age=age)
        raise HTTPException(status_code=401, detail="stale revocation message")

    identity_sub = str(body.get("identity_sub") or "").strip()
    if not identity_sub:
        raise HTTPException(status_code=400, detail="missing identity_sub")

    if _seen(db, str(body["event_id"]), "control_center"):
        db.commit()
        _log_security("revocation_duplicate", event_id=body["event_id"])
        return {"status": "already_applied", "revoked": 0}

    try:
        # The event row and the revocation commit together: a failure here rolls
        # back both, so the Control Center's retry can still apply it. Recording
        # the id first would turn a failed revocation into a silent no-op.
        revoked = _revoke_sso_sessions(
            db,
            idp_sub=identity_sub,
            idp_sid=body.get("idp_sid"),
            scope=str(body.get("scope") or "identity_sessions"),
        )
    except IntegrityError:
        # Concurrent duplicate delivery won the unique constraint.
        db.rollback()
        _log_security("revocation_duplicate", event_id=body["event_id"])
        return {"status": "already_applied", "revoked": 0}
    except Exception:
        db.rollback()
        _log_security("revocation_apply_failed", event_id=body["event_id"])
        raise HTTPException(status_code=500, detail="revocation failed")
    _log_security("revocation_applied", source="control_center",
                  revoked=revoked, reason=body.get("reason"))
    _audit_revocation(db, subject=identity_sub, reason=str(body.get("reason")),
                      revoked=revoked, source="control_center")
    return {"status": "revoked", "revoked": revoked}


# ─────────────────────────────────────────── 2. OIDC back-channel logout (IdP)
@router.post("/api/auth/oidc/backchannel-logout")
async def backchannel_logout(
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    if not _sso_enabled():
        raise HTTPException(status_code=404, detail="Not Found")

    form = await request.form()
    logout_token = str(form.get("logout_token") or "")
    if not logout_token:
        raise HTTPException(status_code=400, detail="missing logout_token")

    try:
        claims = validate_logout_token(logout_token)
    except OidcError as exc:
        _log_security("backchannel_logout_rejected", reason=str(exc)[:120])
        raise HTTPException(status_code=400, detail="invalid logout token")

    jti = str(claims["jti"])
    if _seen(db, jti, "idp"):
        db.commit()
        return {"status": "already_applied"}

    try:
        revoked = _revoke_sso_sessions(
            db,
            idp_sub=str(claims["sub"]) if claims.get("sub") else None,
            idp_sid=str(claims["sid"]) if claims.get("sid") else None,
        )
    except IntegrityError:
        db.rollback()
        return {"status": "already_applied"}
    except Exception:
        db.rollback()
        _log_security("backchannel_logout_apply_failed", jti=jti)
        raise HTTPException(status_code=500, detail="revocation failed")
    _log_security("backchannel_logout_applied", revoked=revoked,
                  has_sid=bool(claims.get("sid")))
    _audit_revocation(db, subject=str(claims.get("sub") or ""), reason="idp_logout",
                      revoked=revoked, source="idp")
    # 200 for a valid token even when nothing matched (idempotent, per spec).
    return {"status": "revoked", "revoked": revoked}
