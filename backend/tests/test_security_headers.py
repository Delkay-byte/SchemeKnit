"""Security-header defaults and opt-in HSTS behaviour."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from src.security import SecurityHeadersMiddleware  # noqa: E402


def _app():
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    return app


def test_baseline_headers_and_report_only_csp(monkeypatch):
    from src.config import get_settings
    monkeypatch.setenv("CSP_REPORT_ONLY", "true")
    monkeypatch.setenv("ENABLE_HSTS", "false")
    get_settings.cache_clear()
    try:
        with TestClient(_app()) as client:
            r = client.get("/ping")
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["x-frame-options"] == "SAMEORIGIN"
        assert "content-security-policy-report-only" in r.headers
        assert "content-security-policy" not in r.headers
        assert "strict-transport-security" not in r.headers
        assert "frame-ancestors 'self'" in r.headers[
            "content-security-policy-report-only"]
    finally:
        get_settings.cache_clear()


def test_enforced_csp_and_hsts_opt_in(monkeypatch):
    from src.config import get_settings
    monkeypatch.setenv("CSP_REPORT_ONLY", "false")
    monkeypatch.setenv("ENABLE_HSTS", "true")
    monkeypatch.setenv("DEBUG", "false")
    get_settings.cache_clear()
    try:
        with TestClient(_app()) as client:
            r = client.get("/ping")
        assert "content-security-policy" in r.headers
        assert "content-security-policy-report-only" not in r.headers
        assert r.headers["strict-transport-security"].startswith("max-age=")
    finally:
        get_settings.cache_clear()
