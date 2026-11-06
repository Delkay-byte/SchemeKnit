"""Platform-admin OIDC SSO router (BloomCore Identity / Control Center).

Mounted under ``/api/auth/oidc``. Entirely feature-flagged: every endpoint
returns 404 while ``PLATFORM_OIDC_ENABLED`` is false, so the local password
(+TOTP) login paths are byte-for-byte unchanged when the feature is off.

Flow (web-only):
  1. ``GET  /start``     — creates the PKCE flow, sets the HttpOnly flow
                           cookie, 303 → IdP authorize URL.
  2. ``GET  /callback``  — validates state/nonce/ID token (JWKS), checks the
                           IdP ``amr`` for a second factor (fail closed), then
                           resolves the Control Center linking status:
                             - ``none``    → 403 denial page, no session
                             - ``pending`` → 303 to the link-confirmation page
                               (local platform-admin password proof)
                             - ``verified``→ native session minted, 303 to the
                               SPA completion route (token in the fragment).
  3. ``POST /confirm``   — completes the pending-link flow: verifies the
                           existing local password, writes the link row, sends
                           the HMAC-signed proof to the Control Center, mints
                           the native session.

Every step emits a structured security log; user-attributed steps also emit a
platform audit row. ``/start`` and ``/callback`` reuse the login_security
progressive-cooldown primitives (keyed by source IP, since no account exists
yet), and ``/confirm`` keys failures on the resolved account exactly like the
regular login does.
"""

from __future__ import annotations

import secrets
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import (
    create_user_token, create_session_record, verify_password,
)
from ..config import get_settings
from ..database import (
    get_db, generate_id, User,
    PlatformAuditLogDB, PlatformAdminOidcLinkDB,
)
from .. import oidc_client
from ..oidc_client import (
    FLOW_COOKIE_NAME, OidcError, amr_from_claims, amr_has_second_factor,
    build_authorization_url, decode_flow, encode_flow, error_page_html,
    exchange_code, new_flow, sign_attempt_token, validate_id_token,
    verify_attempt_token,
)
from ..logging_config import log_security, alert_security
from ..login_security import (
    account_key, check_lockout, clear_failures, record_failure,
)
from ..security import client_ip
from ..validation import normalize_email
from .auth import _dummy_password_check

router = APIRouter()

#: Local SPA routes involved in the flow.
CONFIRM_PAGE_PATH = "/login/platform-admin/sso/confirm"
COMPLETE_PAGE_PATH = "/login/platform-admin/sso/complete"

#: Lifetime of the confirm stage (also the attempt-token TTL).
CONFIRM_TTL_SECONDS = 300


class OidcConfirmRequest(BaseModel):
    attempt: str
    password: str


def _enabled() -> bool:
    return bool(get_settings().PLATFORM_OIDC_ENABLED)


def _frontend_base() -> str:
    return (get_settings().PUBLIC_WEB_URL or "http://localhost:3000").rstrip("/")


def _redirect_uri() -> str:
    return (get_settings().API_BASE_URL or "").rstrip("/") + "/api/auth/oidc/callback"


def _cookie_secure() -> bool:
    """Secure-cookie flag: on unless a local dev/desktop profile is running."""
    settings = get_settings()
    return not (settings.DEBUG or settings.DESKTOP_MODE)


def _set_flow_cookie(resp: Response, flow: dict, max_age: int) -> None:
    resp.set_cookie(
        FLOW_COOKIE_NAME,
        encode_flow(flow),
        max_age=max_age,
        path="/api/auth/oidc",
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(),
    )


def _clear_flow_cookie(resp: Response) -> None:
    resp.delete_cookie(
        FLOW_COOKIE_NAME,
        path="/api/auth/oidc",
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(),
    )


def _audit(db: Session, actor_id: str, actor_role: str, action: str,
           target_type: str = "user", target_id: str = "",
           details: Optional[dict] = None) -> None:
    """Platform audit row for user-attributed SSO events."""
    db.add(PlatformAuditLogDB(
        id=generate_id(),
        actor_id=actor_id,
        actor_role=actor_role,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details or {},
    ))


def _rate_bucket(request: Optional[Request]) -> str:
    return f"oidc:{client_ip(request) if request is not None else 'unknown'}"


def _enforce_lockout(db: Session, request: Optional[Request]) -> None:
    retry_after = check_lockout(db, _rate_bucket(request))
    if retry_after:
        log_security("oidc_flow_locked", bucket=account_key(_rate_bucket(request)),
                     retry_after=retry_after)
        raise HTTPException(
            status_code=429,
            detail="Too many sign-in attempts. Please wait before trying again.",
            headers={"Retry-After": str(retry_after)},
        )


def _str_or_none(value) -> str | None:
    """Coerce a JWT claim to a non-empty string, else None."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _mint_session(db: Session, user: User, amr: list[str],
                  idp_sub: str | None = None,
                  idp_sid: str | None = None) -> str:
    """Issue a NATIVE SchemeKnit session via the existing primitives.

    The IdP-attested ``amr`` rides on the token so the platform-admin MFA gate
    can reconcile central MFA/passkey evidence with the local TOTP gate.

    Provenance (Phase 1.1): an SSO-minted session records the immutable
    Authentik subject and the OIDC ``sid`` so central logout and IdP
    back-channel logout can revoke exactly these sessions — and never the same
    administrator's local password sessions.
    """
    jti = secrets.token_hex(16)
    token = create_user_token(user, jti=jti, amr=amr)
    create_session_record(
        db, user.id, jti,
        auth_source="sso" if idp_sub else "local",
        idp_sub=idp_sub,
        idp_sid=idp_sid,
    )
    return token


def _deny_response(status_code: int, title: str, message: str) -> HTMLResponse:
    """Denial page that ALWAYS clears the (single-use) flow cookie."""
    resp = HTMLResponse(error_page_html(title, message), status_code=status_code)
    _clear_flow_cookie(resp)
    return resp


# ──────────────────────────────────────────────────────────────── endpoints


@router.get("/status")
async def oidc_status():
    """Public feature probe for the login page. No secrets, no session data."""
    return {"enabled": _enabled()}


@router.get("/start")
async def oidc_start(request: Request, db: Session = Depends(get_db)):
    """Start the platform-admin OIDC flow (web-only, no session required).

    Sets the short-lived HttpOnly flow cookie (state/nonce/PKCE verifier,
    expiry hard-capped at 10 minutes) and 303-redirects to the IdP.
    """
    if not _enabled():
        raise HTTPException(status_code=404, detail="Not found")
    _enforce_lockout(db, request)

    settings = get_settings()
    flow = new_flow()
    authorize_url = build_authorization_url(
        _redirect_uri(), flow["state"], flow["nonce"], flow["challenge"])
    log_security("oidc_flow_started")

    resp = RedirectResponse(authorize_url, status_code=303)
    _set_flow_cookie(resp, flow, oidc_client._flow_ttl())
    return resp


@router.get("/callback")
async def oidc_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    error_description: str = "",
    db: Session = Depends(get_db),
):
    """IdP redirect target. The flow cookie is cleared on EVERY outcome."""
    if not _enabled():
        raise HTTPException(status_code=404, detail="Not found")
    _enforce_lockout(db, request)

    try:
        return _handle_callback(db, request, code, state, error, error_description)
    except HTTPException as exc:
        if exc.status_code == 429:
            # Cooldown keeps its structured JSON shape + Retry-After header.
            raise
        log_security("oidc_callback_failed",
                     status=exc.status_code,
                     reason=str(exc.detail)[:120])
        record_failure(db, _rate_bucket(request))
        return _deny_response(
            exc.status_code,
            "Sign-in failed",
            str(exc.detail),
        )
    except OidcError as exc:
        log_security("oidc_callback_failed", reason=str(exc)[:120])
        record_failure(db, _rate_bucket(request))
        return _deny_response(
            502,
            "Sign-in failed",
            "The identity provider could not be contacted. Please try again.",
        )


def _handle_callback(db: Session, request: Request, code: str, state: str,
                     error: str, error_description: str) -> Response:
    # Single use, regardless of outcome below: the cookie is destroyed first.
    raw_cookie = request.cookies.get(FLOW_COOKIE_NAME)
    flow = decode_flow(raw_cookie)
    if flow is None or flow.get("kind") != "authorize":
        raise HTTPException(status_code=400,
                            detail="Sign-in flow expired. Please start again.")
    if error:
        raise HTTPException(
            status_code=403,
            detail=f"The identity provider refused the sign-in"
                   f"{f': {error_description}' if error_description else '.'}")

    # Constant-time state comparison: binds the callback to the browser flow.
    if not state or not secrets.compare_digest(
            str(flow.get("state", "")), str(state)):
        raise HTTPException(status_code=400,
                            detail="Invalid sign-in state. Please start again.")
    if not code:
        raise HTTPException(status_code=400,
                            detail="Missing authorization code.")

    tokens = exchange_code(code, _redirect_uri(), flow.get("verifier", ""))
    claims = validate_id_token(tokens["id_token"], flow.get("nonce", ""))

    # MFA reconciliation — fail closed. A password-only IdP session must not
    # reach platform-admin surfaces, exactly like an unenrolled local admin.
    amr = amr_from_claims(claims)
    if not amr_has_second_factor(amr):
        log_security("oidc_mfa_not_attested",
                     amr=",".join(amr) if amr else "absent")
        raise HTTPException(
            status_code=403,
            detail="Multi-factor authentication is required for SchemeKnit "
                   "administration. Sign in at the identity provider with "
                   "your second factor.",
        )

    idp_email = normalize_email(str(claims["email"])) or str(claims["email"])
    idp_sub = str(claims["sub"])

    resolve = oidc_client.resolve_linking(idp_email)
    status = str(resolve.get("status", "none"))

    if status == "verified":
        user, deny = _user_for_verified_link(db, idp_sub, idp_email, amr)
        if deny is not None:
            return deny
        token = _mint_session(db, user, amr, idp_sub=idp_sub,
                              idp_sid=_str_or_none(claims.get("sid")))
        _audit(db, user.id, user.role, "platform_admin_oidc_login", "user",
               user.id, {"amr": amr, "issuer": get_settings().PLATFORM_OIDC_ISSUER})
        db.commit()
        log_security("oidc_login_success", user_id=user.id)
        # Token travels in the URL FRAGMENT (never a query param): fragments
        # are not sent to servers, not logged by proxies, and the completion
        # page strips it from the address bar immediately.
        resp = RedirectResponse(
            f"{_frontend_base()}{COMPLETE_PAGE_PATH}#token={token}",
            status_code=303)
        _clear_flow_cookie(resp)
        return resp

    if status == "pending":
        identity_sub = str(resolve.get("identity_sub") or "")
        identity_email = str(resolve.get("email") or "")
        if not identity_sub:
            raise HTTPException(
                status_code=502,
                detail="The central directory returned an incomplete linking "
                       "record.")
        confirm_id = secrets.token_urlsafe(16)
        attempt = sign_attempt_token({
            "kind": "oidc-link-confirm",
            "confirm_id": confirm_id,
            "sub": idp_sub,
            "email": idp_email,
            "identity_sub": identity_sub,
            "identity_email": identity_email,
            "amr": amr,
        }, ttl_seconds=CONFIRM_TTL_SECONDS)
        log_security("oidc_link_confirm_started", account=account_key(idp_email))
        confirm_flow = {
            "kind": "confirm",
            "confirm_id": confirm_id,
            "exp": time.time() + CONFIRM_TTL_SECONDS,
        }
        resp = RedirectResponse(
            f"{_frontend_base()}{CONFIRM_PAGE_PATH}?attempt={attempt}",
            status_code=303)
        _set_flow_cookie(resp, confirm_flow, CONFIRM_TTL_SECONDS)
        return resp

    # status == "none" (or anything unrecognised) — fail closed. No session,
    # full audit trail, clear denial message.
    log_security("oidc_identity_not_authorised",
                 account=account_key(idp_email), idp_status=status)
    raise HTTPException(
        status_code=403,
        detail="This identity is not authorised for SchemeKnit administration.",
    )


def _user_for_verified_link(db: Session, idp_sub: str, idp_email: str,
                            amr: list[str]):
    """Resolve the local platform-admin user for a verified CC association.

    Returns (user, None) on success or (None, deny_response) on denial.
    Fail closed: a verified central association without a matching local link
    row (e.g. after a database restore) falls back to the pending flow —
    the admin re-proves the local password once and the link row is rebuilt.
    """
    settings = get_settings()
    link = db.query(PlatformAdminOidcLinkDB).filter(
        PlatformAdminOidcLinkDB.issuer == settings.PLATFORM_OIDC_ISSUER,
        PlatformAdminOidcLinkDB.idp_sub == idp_sub,
    ).first()
    if link is None:
        # Self-healing fallback: downgrade to the local-credential-proof path.
        log_security("oidc_link_row_missing", account=account_key(idp_email))
        confirm_id = secrets.token_urlsafe(16)
        attempt = sign_attempt_token({
            "kind": "oidc-link-confirm",
            "confirm_id": confirm_id,
            "sub": idp_sub,
            "email": idp_email,
            "identity_sub": idp_sub,
            "identity_email": idp_email,
            "amr": amr,
        }, ttl_seconds=CONFIRM_TTL_SECONDS)
        confirm_flow = {
            "kind": "confirm",
            "confirm_id": confirm_id,
            "exp": time.time() + CONFIRM_TTL_SECONDS,
        }
        resp = RedirectResponse(
            f"{_frontend_base()}{CONFIRM_PAGE_PATH}?attempt={attempt}",
            status_code=303)
        _set_flow_cookie(resp, confirm_flow, CONFIRM_TTL_SECONDS)
        return None, resp

    user = db.query(User).filter(User.id == link.user_id).first()
    if user is None:
        log_security("oidc_link_user_missing", idp_sub_digest=account_key(idp_sub))
        raise HTTPException(
            status_code=403,
            detail="This identity is not authorised for SchemeKnit administration.")
    if user.role != "platform_admin" or not user.is_active:
        _audit(db, user.id, getattr(user, "role", "") or "unknown",
               "platform_admin_oidc_login_denied", "user", user.id,
               {"reason": "role_or_active"})
        db.commit()
        log_security("oidc_login_denied", user_id=user.id, reason="role_or_active")
        raise HTTPException(
            status_code=403,
            detail="This identity is not authorised for SchemeKnit administration.")
    return user, None


@router.post("/confirm")
async def oidc_confirm(
    req: OidcConfirmRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Complete the pending link with the EXISTING local platform-admin password.

    The one-time attempt token (URL) must be paired with the confirm cookie
    (browser), making replay of the URL alone useless. On success the caller
    receives the standard login response shape and the cookie is cleared.
    """
    if not _enabled():
        raise HTTPException(status_code=404, detail="Not found")

    attempt = verify_attempt_token(req.attempt)
    if attempt is None or attempt.get("kind") != "oidc-link-confirm":
        raise HTTPException(status_code=400,
                            detail="This confirmation link has expired. "
                                   "Please sign in again.")
    account = str(attempt.get("email") or "")

    # Account-scoped progressive cooldown, exactly like the password login.
    retry_after = check_lockout(db, account)
    if retry_after:
        raise HTTPException(
            status_code=429,
            detail="Too many sign-in attempts. Please wait before trying again.",
            headers={"Retry-After": str(retry_after)},
        )

    # The attempt token must be paired with the confirm flow cookie issued at
    # the callback: single-use binding, cleared on success.
    flow = decode_flow(request.cookies.get(FLOW_COOKIE_NAME))
    if (flow is None or flow.get("kind") != "confirm"
            or not str(flow.get("confirm_id", ""))
            or not secrets.compare_digest(str(flow.get("confirm_id", "")),
                                          str(attempt.get("confirm_id", "")))):
        raise HTTPException(status_code=403,
                            detail="Confirmation session expired. "
                                   "Please sign in again.")

    user = db.query(User).filter(User.email == account).first() if account else None
    if not user or user.role != "platform_admin":
        # Timing-equalised generic failure; no account-existence oracle.
        _dummy_password_check(req.password)
        record_failure(db, account or _rate_bucket(request))
        log_security("oidc_link_confirm_failed", reason="unknown_account")
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        _audit(db, user.id, user.role, "platform_admin_oidc_link_denied",
               "user", user.id, {"reason": "inactive"})
        db.commit()
        log_security("oidc_link_confirm_failed", user_id=user.id,
                     reason="inactive")
        raise HTTPException(status_code=403,
                            detail="This identity is not authorised for "
                                   "SchemeKnit administration.")

    if not verify_password(req.password, user.hashed_password):
        cooldown = record_failure(db, account)
        if cooldown:
            alert_security("account_cooldown", account=account_key(account),
                           cooldown_seconds=cooldown)
            raise HTTPException(
                status_code=429,
                detail="Too many sign-in attempts. Please wait before trying again.",
                headers={"Retry-After": str(cooldown)},
            )
        _audit(db, user.id, user.role, "platform_admin_oidc_link_denied",
               "user", user.id, {"reason": "bad_password"})
        db.commit()
        log_security("oidc_link_confirm_failed", user_id=user.id,
                     reason="bad_password")
        raise HTTPException(status_code=401, detail="Invalid email or password")

    clear_failures(db, account)

    # Re-resolve server-side: the central association must still exist and
    # must still point at the same identity the callback authenticated.
    try:
        resolve = oidc_client.resolve_linking(account)
    except OidcError:
        raise HTTPException(
            status_code=502,
            detail="The central directory is unavailable. Try again shortly.")
    if str(resolve.get("status", "none")) not in ("pending", "verified"):
        log_security("oidc_identity_not_authorised",
                     account=account_key(account),
                     idp_status=str(resolve.get("status")))
        raise HTTPException(
            status_code=403,
            detail="This identity is not authorised for SchemeKnit administration.")
    if str(resolve.get("identity_sub") or "") != str(attempt.get("identity_sub") or ""):
        log_security("oidc_link_identity_mismatch", user_id=user.id)
        raise HTTPException(
            status_code=403,
            detail="This identity is not authorised for SchemeKnit administration.")

    settings = get_settings()
    idp_sub = str(attempt["sub"])
    existing_link = db.query(PlatformAdminOidcLinkDB).filter(
        PlatformAdminOidcLinkDB.idp_sub == idp_sub).first()
    if existing_link is not None and existing_link.user_id != user.id:
        _audit(db, user.id, user.role, "platform_admin_oidc_link_denied",
               "user", user.id, {"reason": "sub_already_linked"})
        db.commit()
        log_security("oidc_link_conflict", user_id=user.id)
        raise HTTPException(
            status_code=409,
            detail="This identity is already linked to another account.")
    created_link = False
    if existing_link is None:
        db.add(PlatformAdminOidcLinkDB(
            id=generate_id(),
            user_id=user.id,
            issuer=settings.PLATFORM_OIDC_ISSUER,
            idp_sub=idp_sub,
            linked_via="local_credential_proof",
            created_by=user.email,
        ))
        created_link = True
        db.flush()

    # Signed proof to the Control Center (HMAC-SHA256, per-product key never
    # leaves this host). On failure the local link row is rolled back so the
    # two systems never disagree about the association.
    try:
        oidc_client.confirm_linking(
            str(attempt.get("identity_sub") or ""),
            str(attempt.get("identity_email") or ""),
            account,
        )
    except OidcError as exc:
        if created_link:
            db.rollback()
        log_security("oidc_link_confirm_failed", user_id=user.id,
                     reason=f"cc_confirm:{exc}")
        raise HTTPException(
            status_code=502,
            detail="The central directory rejected the link confirmation. "
                   "Try again shortly.")

    _audit(db, user.id, user.role, "platform_admin_oidc_link_created",
           "user", user.id, {"via": "local_credential_proof", "issuer": settings.PLATFORM_OIDC_ISSUER})
    amr = attempt.get("amr") or []
    token = _mint_session(
        db, user, amr if isinstance(amr, list) else [],
        idp_sub=_str_or_none(attempt.get("sub")),
        idp_sid=_str_or_none(attempt.get("sid")),
    )
    _audit(db, user.id, user.role, "platform_admin_oidc_login", "user",
           user.id, {"amr": amr, "via": "link_confirm"})
    db.commit()
    log_security("oidc_login_success", user_id=user.id, via="link_confirm")

    _clear_flow_cookie(response)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "school_name": user.school_name,
            "is_admin": user.is_admin,
            "is_active": user.is_active,
            "role": user.role,
            "school_id": user.school_id,
            "subscription_type": getattr(user, "subscription_type", None),
            "mfa_enabled": bool(getattr(user, "mfa_enabled", False)),
        },
        "mfa_enrollment_required": bool(
            user.role == "platform_admin" and not user.mfa_enabled),
    }
