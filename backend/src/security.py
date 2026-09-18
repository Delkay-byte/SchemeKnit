"""
SchemeKnit Security Primitives

Centralized, dependency-free hardening helpers:
- filename sanitization + directory containment (path traversal defense)
- in-memory sliding-window rate limiting for sensitive endpoints
- security headers middleware

Documented limits live here; operational tuning via environment (see .env.example).
"""

import os
import re
import time
from pathlib import Path
from typing import Dict, List, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


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


class RateLimitMiddleware(BaseHTTPMiddleware):
    """429 JSON on exceeded sensitive-route budgets. Localhost exempt (dev/test)."""

    async def dispatch(self, request: Request, call_next):
        try:
            path = request.url.path
            if rate_limiter._rules_for(path):
                client = request.client.host if request.client else "unknown"
                if client not in RATE_LIMIT_EXEMPT_IPS:
                    allowed, info = rate_limiter.is_allowed(client, path)
                    if not allowed:
                        return JSONResponse(
                            status_code=429,
                            content={"error": True,
                                     "detail": "Too many requests. Please wait and try again.",
                                     "status_code": 429},
                            headers={"Retry-After": str(max(info.get("reset", 60), 1))},
                        )
        except Exception:
            # Limiter must fail open: never break legitimate traffic.
            pass
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Baseline headers compatible with the Next.js frontend.

    Note: no Content-Security-Policy here — Next.js dev/inline scripts would
    break; CSP is documented as WARNING in the audit for later tightening.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Cache-Control", "no-store")
        return response
