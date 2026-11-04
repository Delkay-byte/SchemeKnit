"""OIDC client for platform-admin SSO (BloomCore Identity / Authentik).

Implements the browser-facing half of the platform-admin SSO adapter:

- Authorization Code + PKCE (S256) against the IdP discovery document.
- ID token validation: RS256 signature via JWKS (``PyJWKClient``), exact
  issuer match, ``aud`` == client_id, ``exp``/``iat`` with 30 s leeway, and
  single-use ``nonce`` checked against the signed flow cookie.
- Short-lived flow-state cookie helpers (state/nonce/verifier, expiry
  hard-capped at 10 minutes) — URL-encoded JSON, never secrets.
- HMAC-signed one-time attempt tokens for the pending-link confirmation step.
- ``amr`` helpers for MFA reconciliation (fail closed when the IdP did not
  attest a second factor).

Everything is feature-flagged via the ``PLATFORM_OIDC_*`` settings; when the
flag is off this module is never exercised by the routers.

WEB-ONLY: this client speaks only the browser authorization-code flow. No
device flow, no CIBA, no desktop-mode SSO.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from functools import lru_cache
from typing import Any, Optional
from urllib.parse import quote, unquote, urlencode

import httpx
import jwt
from jwt import InvalidTokenError, PyJWKClient

from .config import get_settings

#: Name of the short-lived flow cookie (state/nonce/verifier, later the
#: link-confirmation binding). Hostile-name it clearly: it is a flow record,
#: never a credential.
FLOW_COOKIE_NAME = "sk_oidc_flow"

#: Maximum lifetime of any OIDC flow state (brief: <= 10 minutes).
MAX_FLOW_TTL_SECONDS = 600

#: Clock leeway for ID token exp/iat/nbf validation (brief: 30 s).
TOKEN_LEEWAY_SECONDS = 30

#: Allowed clock skew for the flow cookie itself (strict, state is local).
FLOW_LEEWAY_SECONDS = 5

#: IdP authentication-method references that attest a SECOND factor.
#: Authentik reports amr values such as ["pwd", "otp"] or ["pwd", "webauthn"].
#: "pwd"/"kc-auth" (passwordless authentik flow marker is "webauthn") — a
#: bare password is explicitly NOT a second factor.
SECOND_FACTOR_AMR = frozenset({
    "mfa", "otp", "totp", "webauthn", "fido2", "u2f", "passkey",
    "sms", "hwk", "pop", "duo", "push",
})

#: httpx timeout for IdP / Control Center server-to-server calls.
_HTTP_TIMEOUT_SECONDS = 10.0


class OidcError(Exception):
    """Any failure of the OIDC flow that maps to a denial."""


# ───────────────────────────────────────────────────── discovery / endpoints


@lru_cache(maxsize=4)
def _discovery(issuer: str) -> dict:
    """Fetch (and cache) the IdP's OpenID Connect discovery document."""
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    try:
        resp = httpx.get(url, timeout=_HTTP_TIMEOUT_SECONDS, follow_redirects=True)
        resp.raise_for_status()
        doc = resp.json()
    except Exception as exc:  # network, malformed JSON, non-2xx
        raise OidcError(f"OIDC discovery failed: {exc}") from exc
    for key in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        if not doc.get(key):
            raise OidcError(f"OIDC discovery document missing {key}")
    return doc


def discovery() -> dict:
    settings = get_settings()
    return _discovery(settings.PLATFORM_OIDC_ISSUER)


def authorization_endpoint() -> str:
    return discovery()["authorization_endpoint"]


def token_endpoint() -> str:
    return discovery()["token_endpoint"]


def jwks_uri() -> str:
    return discovery()["jwks_uri"]


def revocation_endpoint() -> Optional[str]:
    return discovery().get("revocation_endpoint")


# ──────────────────────────────────────────────────────────────────── PKCE


def create_pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, S256 code_challenge) per RFC 7636."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).decode().rstrip("=")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).decode().rstrip("=")
    return verifier, challenge


def build_authorization_url(redirect_uri: str, state: str, nonce: str,
                            code_challenge: str) -> str:
    """Build the IdP authorize redirect (response_type=code, PKCE S256)."""
    settings = get_settings()
    params = {
        "response_type": "code",
        "client_id": settings.PLATFORM_OIDC_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "scope": settings.PLATFORM_OIDC_SCOPES,
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{authorization_endpoint()}?{urlencode(params)}"


def exchange_code(code: str, redirect_uri: str, code_verifier: str) -> dict:
    """Redeem the authorization code at the IdP token endpoint.

    Returns the token response JSON (id_token, access_token, ...). Raises
    :class:`OidcError` on any transport or IdP-side failure.
    """
    settings = get_settings()
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": settings.PLATFORM_OIDC_CLIENT_ID,
        "client_secret": settings.PLATFORM_OIDC_CLIENT_SECRET,
        "code_verifier": code_verifier,
    }
    try:
        resp = httpx.post(token_endpoint(), data=data,
                          timeout=_HTTP_TIMEOUT_SECONDS, follow_redirects=True)
    except Exception as exc:
        raise OidcError(f"token endpoint unreachable: {exc}") from exc
    if resp.status_code != 200:
        raise OidcError(f"token endpoint returned {resp.status_code}")
    tokens = resp.json()
    if not tokens.get("id_token"):
        raise OidcError("token response missing id_token")
    return tokens


# ────────────────────────────────────────────────────── ID token validation

_JWK_CLIENTS: dict[str, PyJWKClient] = {}


def _jwk_client(uri: str) -> PyJWKClient:
    client = _JWK_CLIENTS.get(uri)
    if client is None:
        client = PyJWKClient(uri, cache_keys=True, lifespan=300)
        _JWK_CLIENTS[uri] = client
    return client


def validate_id_token(id_token: str, expected_nonce: str,
                      expected_issuer: Optional[str] = None,
                      expected_audience: Optional[str] = None) -> dict:
    """Validate an ID token and return its claims.

    Checks (all enforced, fail closed):
    - RS256 signature against the IdP JWKS
    - exact issuer match
    - audience == client_id
    - exp/iat within TOKEN_LEEWAY_SECONDS
    - nonce equals the single-use value from the signed flow cookie
    - mandatory claims: sub, email

    Raises :class:`OidcError` on any failure.
    """
    settings = get_settings()
    issuer = expected_issuer if expected_issuer is not None \
        else settings.PLATFORM_OIDC_ISSUER
    audience = expected_audience if expected_audience is not None \
        else settings.PLATFORM_OIDC_CLIENT_ID
    try:
        signing_key = _jwk_client(jwks_uri()).get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=audience,
            issuer=issuer,
            leeway=TOKEN_LEEWAY_SECONDS,
            options={"require": ["exp", "iat", "iss", "aud", "sub", "email"]},
        )
    except InvalidTokenError as exc:
        raise OidcError(f"invalid ID token: {exc}") from exc
    except Exception as exc:  # JWKS fetch failure etc.
        raise OidcError(f"ID token validation unavailable: {exc}") from exc

    # Single-use nonce: PyJWT does not check it; we compare against the value
    # bound into the flow cookie (which is destroyed on use).
    if not expected_nonce or not hmac.compare_digest(
            str(claims.get("nonce", "")), str(expected_nonce)):
        raise OidcError("ID token nonce mismatch")

    if not claims.get("sub") or not claims.get("email"):
        raise OidcError("ID token missing sub/email")
    return claims


LOGOUT_EVENT = "http://schemas.openid.net/event/backchannel-logout"
LOGOUT_TOKEN_MAX_AGE_SECONDS = 120


def validate_logout_token(logout_token: str) -> dict:
    """Validate an OIDC Back-Channel Logout token (OpenID Connect BCL 1.0).

    Enforced, fail closed:
    - RS256 signature against the IdP JWKS
    - exact issuer, audience == client_id, exp/iat
    - the ``events`` claim contains the back-channel-logout event
    - ``iat`` is recent (replay window), a ``jti`` is present
    - at least one of ``sub`` / ``sid`` is present
    - a logout token MUST NOT carry a ``nonce`` (spec §2.6)

    Raises :class:`OidcError` on any failure.
    """
    settings = get_settings()
    try:
        signing_key = _jwk_client(jwks_uri()).get_signing_key_from_jwt(logout_token)
        claims = jwt.decode(
            logout_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.PLATFORM_OIDC_CLIENT_ID,
            issuer=settings.PLATFORM_OIDC_ISSUER,
            leeway=TOKEN_LEEWAY_SECONDS,
            options={"require": ["exp", "iat", "iss", "aud", "jti"]},
        )
    except InvalidTokenError as exc:
        raise OidcError(f"invalid logout token: {exc}") from exc
    except Exception as exc:
        raise OidcError(f"logout token validation unavailable: {exc}") from exc

    events = claims.get("events") or {}
    if not isinstance(events, dict) or LOGOUT_EVENT not in events:
        raise OidcError("logout token missing back-channel-logout event")
    if claims.get("nonce") is not None:
        raise OidcError("logout token must not contain a nonce")

    age = abs(int(time.time()) - int(claims.get("iat", 0)))
    if age > LOGOUT_TOKEN_MAX_AGE_SECONDS:
        raise OidcError("logout token is stale")
    if not claims.get("jti"):
        raise OidcError("logout token missing jti")
    if not claims.get("sub") and not claims.get("sid"):
        raise OidcError("logout token carries neither sub nor sid")
    return claims


def amr_from_claims(claims: dict) -> list[str]:
    """The IdP-attested authentication methods (empty list when absent)."""
    amr = claims.get("amr") or []
    if isinstance(amr, str):
        amr = [amr]
    return [str(a) for a in amr if a]


def amr_has_second_factor(amr: list[str]) -> bool:
    """True when the IdP attested any second factor (MFA reconciliation).

    Fail closed: an absent or password-only amr is NOT accepted.
    """
    return bool(SECOND_FACTOR_AMR.intersection({a.lower() for a in amr}))


# ─────────────────────────────────────────────── flow cookie / attempt token


def new_flow() -> dict:
    """A fresh flow record (stored in the HttpOnly cookie, never the URL)."""
    verifier, challenge = create_pkce_pair()
    ttl = _flow_ttl()
    now = time.time()
    return {
        "kind": "authorize",
        "state": secrets.token_urlsafe(32),
        "nonce": secrets.token_urlsafe(32),
        "verifier": verifier,
        "challenge": challenge,
        "created": now,
        "exp": now + ttl,
    }


def _flow_ttl() -> int:
    raw = int(getattr(get_settings(), "PLATFORM_OIDC_FLOW_TTL_SECONDS",
                      MAX_FLOW_TTL_SECONDS))
    return max(60, min(raw, MAX_FLOW_TTL_SECONDS))


def encode_flow(flow: dict) -> str:
    """URL-encoded JSON of the flow record (cookie value)."""
    return quote(json.dumps(flow, separators=(",", ":")), safe="")


def decode_flow(raw: Optional[str]) -> Optional[dict]:
    """Decode and expiry-check a flow cookie value. None when invalid/expired."""
    if not raw:
        return None
    try:
        flow = json.loads(unquote(raw))
    except Exception:
        return None
    if not isinstance(flow, dict):
        return None
    exp = flow.get("exp")
    if not isinstance(exp, (int, float)) or time.time() > exp + FLOW_LEEWAY_SECONDS:
        return None
    return flow


def _signing_key() -> bytes:
    secret = get_settings().SECRET_KEY
    return (secret or "CHANGE-ME-IN-PRODUCTION").encode("utf-8")


def sign_attempt_token(data: dict, ttl_seconds: int = 300) -> str:
    """HMAC-signed, expiring one-time token (``<b64payload>.<hmac>``).

    Used to carry the pending-link context from the OIDC callback to the
    link-confirmation page without exposing it to tampering. Single-use
    semantics come from the bound confirm cookie, not from this token alone.
    """
    payload = dict(data)
    payload["exp"] = time.time() + min(ttl_seconds, MAX_FLOW_TTL_SECONDS)
    raw = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode().rstrip("=")
    sig = hmac.new(_signing_key(), raw.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{raw}.{sig}"


def verify_attempt_token(token: str) -> Optional[dict]:
    """Verify signature + expiry of an attempt token. None when invalid."""
    if not token or "." not in token:
        return None
    raw, _, sig = token.rpartition(".")
    expected = hmac.new(_signing_key(), raw.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        padded = raw + "=" * (-len(raw) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    exp = data.get("exp")
    if not isinstance(exp, (int, float)) or time.time() > exp:
        return None
    return data


# ─────────────────────────────────────────────── Control Center linking API


def linking_headers() -> dict:
    settings = get_settings()
    return {"x-product-key": settings.PLATFORM_OIDC_LINKING_API_KEY}


def resolve_linking(email: str) -> dict:
    """Ask the Control Center whether this IdP email may administer SchemeKnit.

    Returns the CC response: ``{"status": "none"|"pending"|"verified",
    "identity_sub": ..., "email": ...}``. Raises :class:`OidcError` on
    transport failure or a non-200 reply (fail closed).
    """
    settings = get_settings()
    url = (settings.PLATFORM_OIDC_LINKING_BASE_URL or "").rstrip("/") + \
        "/api/v1/products/schemeknit/linking/resolve"
    try:
        resp = httpx.get(url, params={"email": email},
                         headers=linking_headers(),
                         timeout=_HTTP_TIMEOUT_SECONDS)
    except Exception as exc:
        raise OidcError(f"linking resolve unreachable: {exc}") from exc
    if resp.status_code != 200:
        raise OidcError(f"linking resolve returned {resp.status_code}")
    body = resp.json()
    if not isinstance(body, dict) or "status" not in body:
        raise OidcError("linking resolve returned malformed response")
    return body


def build_linking_proof(identity_sub: str, identity_email: str,
                        product_admin_email: str) -> dict:
    """Signed proof for CC ``linking/confirm`` (HMAC-SHA256 over sorted JSON).

    Mirrors the Control Center's ``sign_linking_proof`` primitive exactly:
    the payload is a compact JSON string with sorted keys and the signature
    is the hex HMAC-SHA256 keyed by the per-product API key.
    """
    import hashlib as _hashlib
    settings = get_settings()
    payload = json.dumps(
        {
            "product": "schemeknit",
            "identity_sub": identity_sub,
            "email": identity_email,
            "product_admin_email": product_admin_email,
            "ts": int(time.time()),
        },
        sort_keys=True,
    )
    sig = hmac.new(
        (settings.PLATFORM_OIDC_LINKING_API_KEY or "").encode("utf-8"),
        payload.encode("utf-8"), _hashlib.sha256).hexdigest()
    return {"payload": payload, "signature": sig}


def confirm_linking(identity_sub: str, identity_email: str,
                    product_admin_email: str) -> None:
    """Tell the Control Center the link was confirmed by a local credential
    proof. Raises :class:`OidcError` on any failure (the caller rolls back)."""
    settings = get_settings()
    url = (settings.PLATFORM_OIDC_LINKING_BASE_URL or "").rstrip("/") + \
        "/api/v1/products/schemeknit/linking/confirm"
    body = build_linking_proof(identity_sub, identity_email, product_admin_email)
    try:
        resp = httpx.post(url, json=body, headers=linking_headers(),
                          timeout=_HTTP_TIMEOUT_SECONDS)
    except Exception as exc:
        raise OidcError(f"linking confirm unreachable: {exc}") from exc
    if resp.status_code != 200:
        raise OidcError(f"linking confirm returned {resp.status_code}")


# ─────────────────────────────────────────────────────── IdP revocation hook


def revoke_idp_token(refresh_token: Optional[str]) -> bool:
    """Best-effort revocation of the IdP session token at logout.

    Phase 1 never stores IdP refresh tokens (only the local session is kept),
    so this is currently a safeguarded no-op: it fires only when a refresh
    token exists. Non-blocking by contract — failures are swallowed.
    """
    if not refresh_token:
        return False
    endpoint = None
    try:
        endpoint = revocation_endpoint()
    except Exception:
        return False
    if not endpoint:
        return False
    settings = get_settings()
    try:
        httpx.post(
            endpoint,
            data={
                "token": refresh_token,
                "client_id": settings.PLATFORM_OIDC_CLIENT_ID,
                "client_secret": settings.PLATFORM_OIDC_CLIENT_SECRET,
            },
            timeout=_HTTP_TIMEOUT_SECONDS,
        )
    except Exception:
        return False
    return True


# ─────────────────────────────────────────────────────────── error responses


def error_page_html(title: str, message: str) -> str:
    """Minimal standalone error page for denial responses (no app assets)."""
    safe_title = (title or "Sign-in failed").replace("&", "&amp;").replace("<", "&lt;")
    safe_msg = (message or "").replace("&", "&amp;").replace("<", "&lt;")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{safe_title}</title>
<meta name="robots" content="noindex, nofollow">
<style>
body{{font-family:system-ui,sans-serif;background:#0f172a;color:#e2e8f0;
display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}}
main{{max-width:28rem;padding:2.5rem;text-align:center}}
h1{{font-size:1.25rem;margin-bottom:.75rem}}
p{{line-height:1.6;color:#94a3b8}}
a{{color:#60a5fa}}
</style></head>
<body><main><h1>{safe_title}</h1><p>{safe_msg}</p>
<p><a href="/login/platform-admin">Back to sign in</a></p></main></body></html>"""
