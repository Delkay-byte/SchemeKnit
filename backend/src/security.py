"""
SchemeKnit Security Primitives

Centralized, dependency-free hardening helpers:
- filename sanitization + directory containment (path traversal defense)
- in-memory sliding-window rate limiting for sensitive endpoints
- security headers middleware

Documented limits live here; operational tuning via environment (see .env.example).
"""

import ipaddress
import logging
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Tuple

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


def _trusted_proxy(host: str) -> bool:
    settings = get_settings()
    if not settings.TRUST_PROXY_HEADERS:
        return False
    raw = (settings.TRUSTED_PROXY_CIDRS or "").strip()
    if not raw:
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if address in ipaddress.ip_network(part, strict=False):
                return True
        except ValueError:
            continue
    return False


def client_ip(request: Request) -> str:
    """Return the rate-limit key for the request's client address.

    Forwarding headers are trusted ONLY when the direct peer is inside the
    configured trusted-proxy CIDRs. Otherwise a forged X-Forwarded-For is
    ignored and the direct socket address is used. When enabled, the first
    address in X-Forwarded-For is treated as the original client; this must be
    verified against the actual Render proxy topology before enabling.
    """
    direct = request.client.host if request.client else "unknown"
    if not _trusted_proxy(direct):
        return direct
    forwarded = request.headers.get("x-forwarded-for", "")
    first = forwarded.split(",")[0].strip() if forwarded else ""
    return first or direct


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
                if client not in RATE_LIMIT_EXEMPT_IPS:
                    allowed, info = limiter.is_allowed(client, path)
                    if not allowed:
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
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
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
