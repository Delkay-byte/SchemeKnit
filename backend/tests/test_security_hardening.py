"""
Production hardening tests: path traversal, rate limiting, config fail-safe,
upload validation.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.security import (
    sanitize_filename,
    safe_join,
    RateLimiter,
    RateLimitMiddleware,
    rate_limiter,
    RATE_LIMITS,
)
from src.config import Settings


class TestSanitizeFilename:
    def test_plain_name_kept(self):
        assert sanitize_filename("lesson plan.docx") == "lesson_plan.docx"

    def test_unicode_preserved_safely(self):
        out = sanitize_filename("Kwame Asante Week 2.docx")
        assert out.endswith(".docx") and ".." not in out and "/" not in out

    @pytest.mark.parametrize("evil", [
        "../evil.docx", "..\\evil.docx", "../../etc/passwd",
        "/abs/path.docx", "C:\\Windows\\evil.docx", "C:/evil.docx",
        "\\\\server\\share.docx", "~/.bashrc", ".", "..", "", "   ",
        "....//evil.docx", "sub/dir/file.docx",
    ])
    def test_traversal_rejected(self, evil):
        with pytest.raises(ValueError):
            sanitize_filename(evil)

    def test_null_byte_rejected(self):
        with pytest.raises(ValueError):
            sanitize_filename("a\x00.docx")

    def test_browser_full_path_rejected(self):
        # Strict policy: client must send a plain basename (modern browsers do).
        with pytest.raises(ValueError):
            sanitize_filename("C:\\fakepath\\sample.docx")

    def test_long_name_truncated_with_extension(self):
        long_name = "a" * 200 + ".docx"
        out = sanitize_filename(long_name)
        assert len(out) <= 120 and out.endswith(".docx")


class TestSafeJoin:
    def test_inside_root_ok(self, tmp_path):
        p = safe_join(str(tmp_path), "abc_sample.docx")
        assert p.startswith(str(tmp_path))

    def test_escape_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            safe_join(str(tmp_path), "..", "evil.docx")

    def test_absolute_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            safe_join(str(tmp_path), "/etc/passwd")


class TestRateLimiter:
    def test_allows_under_limit(self):
        rl = RateLimiter([("/api/auth/login", 3, 60)])
        assert all(rl.is_allowed("1.2.3.4", "/api/auth/login", now=1000.0 + i)[0]
                   for i in range(3))

    def test_blocks_over_limit(self):
        rl = RateLimiter([("/api/auth/login", 2, 60)])
        rl.is_allowed("1.2.3.4", "/api/auth/login", now=1000.0)
        rl.is_allowed("1.2.3.4", "/api/auth/login", now=1001.0)
        allowed, info = rl.is_allowed("1.2.3.4", "/api/auth/login", now=1002.0)
        assert allowed is False
        assert info["remaining"] == 0

    def test_window_slides(self):
        rl = RateLimiter([("/api/auth/login", 1, 60)])
        assert rl.is_allowed("1.2.3.4", "/api/auth/login", now=1000.0)[0] is True
        assert rl.is_allowed("1.2.3.4", "/api/auth/login", now=1001.0)[0] is False
        assert rl.is_allowed("1.2.3.4", "/api/auth/login", now=1070.0)[0] is True

    def test_per_client_isolation(self):
        rl = RateLimiter([("/api/auth/login", 1, 60)])
        assert rl.is_allowed("1.1.1.1", "/api/auth/login", now=1000.0)[0] is True
        assert rl.is_allowed("2.2.2.2", "/api/auth/login", now=1000.0)[0] is True

    def test_unlisted_paths_unlimited(self):
        rl = RateLimiter([("/api/auth/login", 1, 60)])
        for i in range(50):
            assert rl.is_allowed("1.2.3.4", "/api/lessons", now=1000.0 + i)[0] is True

    def test_prefix_matching(self):
        rl = RateLimiter([("/api/generation/", 1, 60)])
        assert rl.is_allowed("9.9.9.9", "/api/generation/abc/export/zip", now=5.0)[0] is True
        assert rl.is_allowed("9.9.9.9", "/api/generation/abc/export/zip", now=6.0)[0] is False


class TestBudgetPolicyAndCorsOn429:
    """Production acceptance regression: the workspace journey's status
    polling exhausted the /api/generation/ 30-per-60s budget mid-flight, and
    because RateLimitMiddleware sat outside CORSMiddleware the 429 arrived
    without Access-Control-Allow-Origin — the browser hid it as an opaque
    network error, the workspace lost its scheme-status response and fell
    back to the generate form. Reads must bypass budgets, mutations must
    stay limited, and a 429 must be JS-readable."""

    @staticmethod
    def _app():
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware

        app = FastAPI()
        # Production order (main.py): RateLimit registered first, so CORS
        # wraps it and decorates its 429 responses.
        app.add_middleware(RateLimitMiddleware)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["https://schemeknit-frontend.onrender.com"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @app.get("/api/generation/preview")
        async def preview_get():
            return {"ok": True}

        @app.post("/api/generation/preview")
        async def preview_post():
            return {"ok": True}

        @app.get("/api/generation/downloads/{token}")
        async def download(token: str):
            return {"bytes": 1}

        return app

    @staticmethod
    def _exhaust(bucket_host: str):
        budget = max(m for p, m, _w in RATE_LIMITS if p == "/api/generation/")
        for _ in range(budget + 1):
            rate_limiter.is_allowed(bucket_host, "/api/generation/x")

    def test_reads_bypass_an_exhausted_budget(self):
        from fastapi.testclient import TestClient

        rate_limiter.reset()
        try:
            client = TestClient(self._app())
            # TestClient's host is "testclient" — deliberately not a
            # localhost-exempt IP, so budgets apply as in production.
            self._exhaust("testclient")
            assert client.get("/api/generation/preview").status_code == 200
            assert client.get("/api/generation/downloads/sometoken").status_code == 200
            # ...and reads must not have consumed budget: mutations still 429.
            assert client.post("/api/generation/preview").status_code == 429
        finally:
            rate_limiter.reset()

    def test_mutations_stay_budgeted(self):
        from fastapi.testclient import TestClient

        rate_limiter.reset()
        try:
            client = TestClient(self._app())
            assert client.post("/api/generation/preview").status_code == 200
            self._exhaust("testclient")
            assert client.post("/api/generation/preview").status_code == 429
        finally:
            rate_limiter.reset()

    def test_429_carries_cors_headers(self):
        from fastapi.testclient import TestClient

        rate_limiter.reset()
        try:
            client = TestClient(self._app())
            self._exhaust("testclient")
            r = client.post(
                "/api/generation/preview",
                headers={"Origin": "https://schemeknit-frontend.onrender.com"},
            )
            assert r.status_code == 429
            assert r.headers.get("access-control-allow-origin") == \
                "https://schemeknit-frontend.onrender.com"
            assert "Too many requests" in r.json()["detail"]
        finally:
            rate_limiter.reset()

    def test_production_registers_rate_limit_inside_cors(self):
        # The mirror app above only proves Starlette semantics; this pins the
        # real wiring in main.py. user_middleware is outermost-first
        # (Starlette prepends on add_middleware), so CORS must appear before
        # RateLimit — otherwise the limiter's 429s bypass CORS and lose
        # Access-Control-Allow-Origin.
        from src.main import app

        order = [m.cls.__name__ for m in app.user_middleware]
        assert "RateLimitMiddleware" in order, order
        assert "CORSMiddleware" in order, order
        assert order.index("CORSMiddleware") < order.index("RateLimitMiddleware"), order


class TestConfigFailSafe:
    def test_debug_allows_defaults(self):
        s = Settings(DEBUG=True)
        s.validate_production()  # must not raise

    def test_production_rejects_default_secrets(self):
        s = Settings(DEBUG=False, SECRET_KEY="CHANGE-ME-IN-PRODUCTION",
                     JWT_SECRET_KEY="CHANGE-ME-IN-PRODUCTION")
        with pytest.raises(RuntimeError):
            s.validate_production()

    def test_production_accepts_real_secrets(self):
        s = Settings(
            DEBUG=False,
            SECRET_KEY="x" * 32,
            JWT_SECRET_KEY="y" * 32,
            DATABASE_URL="postgresql://user:pass@host:5432/schemeknit",
            PUBLIC_WEB_URL="https://app.schemeknit.com",
            API_BASE_URL="https://api.schemeknit.com",
            CORS_ORIGINS=["https://app.schemeknit.com"],
            RESEND_API_KEY="re_test_key",
            EMAIL_FROM="notify@schemeknit.com",
            STORAGE_BACKEND="s3",
            S3_BUCKET="schemeknit",
            S3_ACCESS_KEY="ak",
            S3_SECRET_KEY="sk",
        )
        s.validate_production()  # must not raise


class TestSampleUploadValidation:
    def _file(self, name, content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"):
        from types import SimpleNamespace
        return SimpleNamespace(filename=name, content_type=content_type)

    def test_valid_name_accepted(self):
        from src.routers.templates import _validated_sample_filename
        assert _validated_sample_filename(self._file("My Sample.docx")) == "My_Sample.docx"

    def test_wrong_extension_rejected(self):
        from fastapi import HTTPException
        from src.routers.templates import _validated_sample_filename
        with pytest.raises(HTTPException) as e:
            _validated_sample_filename(self._file("evil.pdf", "application/pdf"))
        assert e.value.status_code == 400

    def test_bad_mime_rejected(self):
        from fastapi import HTTPException
        from src.routers.templates import _validated_sample_filename
        with pytest.raises(HTTPException) as e:
            _validated_sample_filename(self._file("x.docx", "application/x-msdownload"))
        assert e.value.status_code == 400

    def test_traversal_name_rejected(self):
        from fastapi import HTTPException
        from src.routers.templates import _validated_sample_filename
        with pytest.raises(HTTPException) as e:
            _validated_sample_filename(self._file("../../evil.docx"))
        assert e.value.status_code == 400
