"""
SchemeKnit Security Primitives

Centralized, dependency-free hardening helpers:
- filename sanitization + directory containment (path traversal defense)
- in-memory sliding-window rate limiting for sensitive endpoints
- security headers middleware

Documented limits live here; operational tuning via environment (see .env.example).
"""

import hashlib
import hmac
import ipaddress
import logging
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .config import get_settings
from .database import RateLimitCounterDB, SessionLocal, generate_id

logger = logging.getLogger("security")


# ── Filename / path safety ────────────────────────────────────────────────────

_SAFE_CHARS_RE = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_filename(filename: str, max_len: int = 120) -> str:
    """Return a filesystem-safe basename for a user-supplied filename.

    Raises ValueError on traversal sequences, absolute paths, UNC paths,
    empty names, or names that sanitize to nothing.
    """
    if not filename or not isinstance(filename, str):
        raise ValueError("Filename is required")
    if "\x00" in filename:
        raise ValueError("Invalid filename")
    raw = filename.strip()
    # Reject traversal sequences, separators, and absolute/UNC/drive-qualified
    # paths outright: only a plain basename is ever acceptable from the client.
    if (not raw or ".." in raw or "/" in raw or "\\" in raw
            or re.match(r"^[A-Za-z]:", raw) or raw.startswith("~")
            or raw.startswith(".")):
        raise ValueError("Invalid filename")
    base = raw
    safe = _SAFE_CHARS_RE.sub("_", base)
    safe = re.sub(r"_+", "_", safe).strip("._")
    if not safe:
        raise ValueError("Invalid filename")
    # Preserve extension (truncate stem, not suffix)
    if len(safe) > max_len:
        stem, dot, ext = safe.rpartition(".")
        if dot and len(ext) <= 10:
            safe = stem[: max_len - len(ext) - 1] + dot + ext
        else:
            safe = safe[:max_len]
    return safe


def safe_join(root: str, *names: str) -> str:
    """Join names under root and verify containment (symlink-aware).

    Raises ValueError if the resolved path escapes root.
    """
    root_path = Path(root).resolve()
    target = root_path.joinpath(*names).resolve()
    try:
        target.relative_to(root_path)
    except ValueError:
        raise ValueError("Path escapes storage root")
    return str(target)


# ── Rate limiting ─────────────────────────────────────────────────────────────
# Sliding window, per client IP + route group. In-memory: single-worker safe;
# multi-worker deployments should front with a reverse-proxy limiter (documented).

# (path prefix, max requests, window seconds)
RATE_LIMITS: List[Tuple[str, int, int]] = [
    ("/api/auth/login", 20, 60),
    ("/api/auth/setup", 10, 300),
    ("/api/auth/activation/validate", 30, 300),
    ("/api/auth/setup-school-admin", 10, 300),
    ("/api/auth/users/", 30, 60),          # password reset / initiate-reset
    ("/api/auth/setup-platform-admin", 5, 300),   # bootstrap (very strict)
    ("/api/auth/change-password", 10, 60),
    ("/api/auth/confirm-password-reset", 10, 300),
    ("/api/auth/reset-token/validate", 20, 300),
    ("/api/platform-admin/activate", 30, 300),
    ("/api/documents/upload", 10, 300),
    ("/api/templates/analyze", 10, 300),
    ("/api/templates/upload", 10, 300),
    ("/api/generation/", 30, 60),
]

RATE_LIMIT_EXEMPT_IPS = {"127.0.0.1", "::1", "localhost"}


def _rate_limit_exempt(address: str) -> bool:
    """Exempt loopback only in local/debug mode.

    Production must never exempt a real peer merely because a proxy or
    sidecar presents it as localhost.
    """
    try:
        if get_settings().DEBUG:
            return address in RATE_LIMIT_EXEMPT_IPS
    except Exception:
        pass
    return False

# Safe methods are never budgeted. The workspace legitimately fires dozens of
# reads a minute (scheme status polling while lessons render, per-reload
# status + options + provenance fetches), so counting them against the same
# per-minute budget as generate/upload made a normal production journey trip
# 429 mid-flight — and a throttled read was invisible to the client (the
# workspace just failed to restore and fell back to the generate form).
# Budgets guard what mutates: generate, preview, exports, uploads, auth.
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class RateLimiter:
    """Minimal sliding-window limiter. hits: {(key): [timestamps]}."""

    def __init__(self, limits: List[Tuple[str, int, int]] = None):
        self.limits = limits if limits is not None else RATE_LIMITS
        self.hits: Dict[str, List[float]] = {}

    def _rules_for(self, path: str):
        return [(p, m, w) for (p, m, w) in self.limits if path.startswith(p)]

    def is_allowed(self, key: str, path: str, now: float = None) -> Tuple[bool, dict]:
        """Check + record. Returns (allowed, {limit, remaining, reset})."""
        now = now if now is not None else time.time()
        rules = self._rules_for(path)
        if not rules:
            return True, {}
        allowed, info = True, {}
        for prefix, maximum, window in rules:
            bucket = f"{key}|{prefix}"
            stamps = [t for t in self.hits.get(bucket, []) if now - t < window]
            if len(stamps) >= maximum:
                allowed = False
                info = {"limit": maximum, "remaining": 0,
                        "reset": int(max(stamps)) + window - int(now)}
            else:
                stamps.append(now)
                if allowed:
                    info = {"limit": maximum, "remaining": maximum - len(stamps),
                            "reset": window}
            self.hits[bucket] = stamps
        return allowed, info

    def is_allowed_for(self, key: str, prefix: str, maximum: int,
                       window: int, now: float = None) -> Tuple[bool, dict]:
        """Explicit budget, used for authenticated-user limits."""
        now = now if now is not None else time.time()
        bucket = f"{key}|{prefix}"
        stamps = [t for t in self.hits.get(bucket, []) if now - t < window]
        if len(stamps) >= maximum:
            return False, {
                "limit": maximum, "remaining": 0,
                "reset": int(max(stamps)) + window - int(now),
            }
        stamps.append(now)
        self.hits[bucket] = stamps
        return True, {
            "limit": maximum, "remaining": maximum - len(stamps),
            "reset": window,
        }

    def reset(self):
        self.hits.clear()


rate_limiter = RateLimiter()


class DbRateLimiter:
    """Fixed-window limiter backed by the shared application database."""

    _cleanup_after = 200
    _calls = 0

    def __init__(self, session_factory=None):
        self._session_factory = session_factory or SessionLocal

    def _allowed_for_rule(self, db, key: str, prefix: str, maximum: int,
                          window: int, now: float) -> Tuple[bool, dict]:
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        table = RateLimitCounterDB.__table__
        window_start = int(now // window) * window
        bucket_key = f"{key}|{prefix}"
        values = {
            "id": generate_id(), "bucket_key": bucket_key,
            "window_start": window_start, "count": 1,
        }
        dialect = db.get_bind().dialect.name if db.get_bind() is not None else "sqlite"
        make = pg_insert if dialect == "postgresql" else sqlite_insert
        stmt = make(table).values(**values).on_conflict_do_update(
            index_elements=["bucket_key", "window_start"],
            set_={"count": table.c.count + 1},
        ).returning(table.c.count)
        count = int(db.execute(stmt).scalar() or 0)
        db.commit()
        reset = max(1, window_start + window - int(now))
        if count > maximum:
            return False, {"limit": maximum, "remaining": 0, "reset": reset}
        return True, {
            "limit": maximum, "remaining": max(maximum - count, 0),
            "reset": reset,
        }

    def is_allowed(self, key: str, path: str, now: float = None) -> Tuple[bool, dict]:
        now = now if now is not None else time.time()
        rules = rate_limiter._rules_for(path)
        if not rules:
            return True, {}
        db = self._session_factory()
        try:
            allowed, info = True, {}
            for prefix, maximum, window in rules:
                ok, rule_info = self._allowed_for_rule(
                    db, key, prefix, maximum, window, now)
                if not ok:
                    return False, rule_info
                if allowed:
                    info = rule_info
            self._calls += 1
            if self._calls % self._cleanup_after == 0:
                cutoff = int(now) - 86400
                db.query(RateLimitCounterDB).filter(
                    RateLimitCounterDB.window_start < cutoff
                ).delete(synchronize_session=False)
                db.commit()
            return allowed, info
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def is_allowed_for(self, key: str, prefix: str, maximum: int,
                       window: int, now: float = None) -> Tuple[bool, dict]:
        """Explicit shared budget, used for authenticated-user limits."""
        now = now if now is not None else time.time()
        db = self._session_factory()
        try:
            return self._allowed_for_rule(
                db, key, prefix, maximum, window, now)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


#: Forwarded-header parsing bounds. A legitimate proxy chain is tiny; anything
#: larger is treated as malformed and falls back to the direct peer.
MAX_XFF_HEADER_FIELDS = 8
MAX_XFF_TOTAL_CHARS = 2048
MAX_XFF_HOPS = 32
MAX_XFF_VALUE_CHARS = 128


def _normalize_ip(value: str) -> Optional[str]:
    """Return a canonical IPv4/IPv6 string, or None when the value is unsafe.

    Handles bracketed IPv6 with a port, IPv4 with a port, and IPv4-mapped IPv6
    (``::ffff:192.0.2.1`` -> ``192.0.2.1``). Never guesses.
    """
    raw = str(value or "").strip().strip('"')
    if not raw or len(raw) > MAX_XFF_VALUE_CHARS:
        return None
    address = raw
    if raw.startswith("["):
        end = raw.find("]")
        if end < 0:
            return None
        address = raw[1:end]
        suffix = raw[end + 1:]
        if suffix and (not suffix.startswith(":") or not suffix[1:].isdigit()):
            return None
    elif raw.count(":") == 1 and "." in raw:
        host, port = raw.rsplit(":", 1)
        if not port.isdigit():
            return None
        address = host
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return None
    if isinstance(parsed, ipaddress.IPv6Address) and parsed.ipv4_mapped:
        return str(parsed.ipv4_mapped)
    return str(parsed)


def _trusted_proxy(host: str) -> bool:
    """True only when the direct peer is in the explicit proxy allowlist."""
    settings = get_settings()
    if not settings.TRUST_PROXY_HEADERS:
        return False
    raw = (settings.TRUSTED_PROXY_CIDRS or "").strip()
    if not raw:
        return False
    normalized = _normalize_ip(host)
    if normalized is None:
        return False
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            network = ipaddress.ip_network(part, strict=False)
        except ValueError:
            # Startup validation rejects this; fail closed if a runtime
            # mutation or test monkeypatch bypassed it.
            continue
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        if address in network:
            return True
    return False


def _forwarded_chain(request: Request) -> Optional[List[str]]:
    """Parse all X-Forwarded-For fields into left-to-right hops.

    Returns None for a missing, empty, malformed or oversized chain. The
    ``Forwarded`` (RFC 7239) header is deliberately not used: Render's managed
    ingress is not documented to maintain it, so accepting it would add an
    unverified trust path.
    """
    try:
        values = request.headers.getlist("x-forwarded-for")
    except Exception:
        return None
    if not values:
        return None
    if len(values) > MAX_XFF_HEADER_FIELDS:
        return None
    if sum(len(v) for v in values) > MAX_XFF_TOTAL_CHARS:
        return None

    chain: List[str] = []
    for raw in values:
        if len(raw) > MAX_XFF_TOTAL_CHARS:
            return None
        for part in raw.split(","):
            if len(chain) >= MAX_XFF_HOPS:
                return None
            normalized = _normalize_ip(part)
            if normalized is None:
                return None
            chain.append(normalized)
    return chain or None


def client_ip(request: Request) -> str:
    """Return the security-relevant client address, never a spoofed leftmost hop.

    Forwarded headers are ignored unless the direct socket peer is explicitly
    in ``TRUSTED_PROXY_CIDRS``. For a trusted chain, walk right-to-left and
    return the first hop that is not itself a trusted proxy. A malformed or
    oversized chain fails closed to the direct peer.
    """
    raw_direct = request.client.host if request.client else "unknown"
    # A real socket peer is always an IP. Keep a non-IP sentinel (tests,
    # embedded servers) as-is so all such requests share one bounded bucket
    # instead of collapsing to a value that bypasses the caller's bucket key.
    direct = _normalize_ip(raw_direct) or str(raw_direct or "unknown")
    if not _trusted_proxy(direct):
        return direct

    forwarded = _forwarded_chain(request)
    if not forwarded:
        return direct

    # Rightmost entry is nearest the application; skip only verified proxies.
    for candidate in reversed(forwarded + [direct]):
        if _trusted_proxy(candidate):
            continue
        return candidate
    # Every supplied hop is itself a trusted proxy. There is no verified
    # client address in the chain, so fail closed to the direct peer.
    return direct


def client_key(address: str) -> str:
    """Privacy-safe, stable rate-limit/log key for a client address."""
    settings = get_settings()
    raw = (getattr(settings, "SECURITY_HMAC_KEY", "") or "").strip()
    key = raw.encode("utf-8") if raw else (
        getattr(settings, "SECRET_KEY", "") or "schemeKnit-local-security"
    ).encode("utf-8")
    return hmac.new(
        key, f"client-ip:{address}".encode("utf-8"), hashlib.sha256
    ).hexdigest()


#: Per-authenticated-user budgets for expensive/mutating operations. These are
#: independent of the source IP, so rotating X-Forwarded-For or switching
#: networks cannot create a fresh budget for the same account.
AUTHENTICATED_BUDGETS = {
    "upload": (10, 900),
    "generate": (20, 600),
    "resume": (10, 600),
    "export": (30, 600),
}


def enforce_authenticated_budget(user_id: str, action: str) -> None:
    """Fail-closed per-user budget for an expensive operation.

    Uses the same shared limiter backend as the IP middleware. A storage
    failure returns 503 rather than allowing the operation; a legitimate
    request never depends on an unverified forwarded IP.
    """
    maximum, window = AUTHENTICATED_BUDGETS[action]
    limiter = get_rate_limiter()
    checker = getattr(limiter, "is_allowed_for", None)
    if checker is None:
        return
    key = client_key(f"user:{user_id}")
    try:
        allowed, info = checker(key, f"user:{action}", maximum, window)
    except Exception:
        logger.error("authenticated_budget_store_unavailable action=%s", action)
        raise HTTPException(
            status_code=503,
            detail="Security controls are temporarily unavailable. "
                   "Please try again shortly.",
            headers={"Retry-After": "30"},
        )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many requests for this account. Please wait and try again.",
            headers={"Retry-After": str(max(info.get("reset", 60), 1))},
        )


def get_rate_limiter():
    backend = (getattr(get_settings(), "RATE_LIMIT_BACKEND", "db") or "db").lower()
    return DbRateLimiter() if backend == "db" else rate_limiter


_HIGH_RISK_PREFIXES = (
    "/api/auth/", "/api/documents/", "/api/templates/",
    "/api/generation/", "/api/paystack/",
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """429 JSON on exceeded sensitive-route budgets.

    Safe methods bypass budgets (SAFE_METHODS), localhost stays exempt
    (dev/test), and the middleware is registered inside CORSMiddleware so a
    429 reaches JS with its headers intact (see main.py).
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if request.method in SAFE_METHODS:
            return await call_next(request)
        try:
            limiter = get_rate_limiter()
            if rate_limiter._rules_for(path):
                client = client_ip(request)
                if not _rate_limit_exempt(client):
                    # Hash the address before it reaches the shared counter
                    # table or security logs: the limiter only needs a stable
                    # bucket, not the raw client IP.
                    limiter_key = client_key(client)
                    allowed, info = limiter.is_allowed(limiter_key, path)
                    if not allowed:
                        try:
                            from .logging_config import alert_security
                            alert_security(
                                "rate_limit_exceeded", severity="warning",
                                path=path, client=limiter_key)
                        except Exception:
                            pass
                        return JSONResponse(
                            status_code=429,
                            content={"error": True,
                                     "detail": "Too many requests. Please wait and try again.",
                                     "status_code": 429},
                            headers={"Retry-After": str(max(info.get("reset", 60), 1))},
                        )
        except Exception as exc:
            # Never silently make a high-risk endpoint unrestricted when the
            # shared limiter store is down. Low-risk routes keep working and
            # the failure is logged for operations.
            logger.error("rate_limit_store_unavailable path=%s error=%s",
                         path, type(exc).__name__)
            if path.startswith(_HIGH_RISK_PREFIXES):
                return JSONResponse(
                    status_code=503,
                    content={
                        "error": True,
                        "detail": "Security controls are temporarily unavailable. "
                                  "Please try again shortly.",
                        "status_code": 503,
                    },
                    headers={"Retry-After": "30"},
                )
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Baseline headers compatible with the Next.js frontend.

    CSP starts in report-only mode by default so a staging deployment can
    collect violations before enforcement. HSTS is opt-in and must only be
    enabled on a verified HTTPS domain.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        settings = get_settings()
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Cache-Control", "no-store")
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self' https:; "
            "frame-ancestors 'self'; "
            "base-uri 'self'; "
            "object-src 'none'"
        )
        header = ("Content-Security-Policy-Report-Only"
                  if getattr(settings, "CSP_REPORT_ONLY", True)
                  else "Content-Security-Policy")
        response.headers.setdefault(header, csp)
        if getattr(settings, "ENABLE_HSTS", False) and not settings.DEBUG:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000",
            )
        return response
