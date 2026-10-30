"""CORS preflight + registration availability regression tests.

Background: the local web frontend is served on http://localhost:3100 (the
port every browser acceptance journey uses), but backend CORS_ORIGINS only
listed 3000/5173/18235. The signup POST therefore failed its CORS preflight
("Disallowed CORS origin") and the browser surfaced it as a bare
"Failed to fetch" — no request ever reached the registration handler.

These tests pin both the behavior (configured origins pass preflight on the
registration route, unknown origins are rejected) and the configuration
(the documented local dev frontend origin must stay allowed).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.config import get_settings
from src.database import Base, get_db
from src.main import app


@pytest.fixture
def http():
    """TestClient backed by a fresh in-memory SQLite database."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app), db
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()
        engine.dispose()


class TestCorsPreflight:
    @pytest.fixture(scope="class")
    def live_app_client(self):
        """The real application object (with its production middleware stack)."""
        with TestClient(app) as c:
            yield c

    def test_preflight_allowed_for_every_configured_origin(self, live_app_client):
        settings = get_settings()
        assert settings.CORS_ORIGINS, "CORS_ORIGINS must not be empty"
        for origin in settings.CORS_ORIGINS:
            res = live_app_client.options(
                "/api/auth/register/individual",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                },
            )
            assert res.status_code == 200, (origin, res.status_code, res.text)
            assert res.headers["access-control-allow-origin"] == origin

    def test_preflight_rejected_for_unconfigured_origin(self, live_app_client):
        res = live_app_client.options(
            "/api/auth/register/individual",
            headers={
                "Origin": "http://localhost:9999",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert res.status_code == 400
        assert "Disallowed CORS origin" in res.text
        assert "access-control-allow-origin" not in res.headers

    def test_local_frontend_dev_origin_is_configured(self):
        """The regression that caused 'Failed to fetch': the local web
        frontend runs on :3100; if CORS_ORIGINS loses that origin the
        browser can no longer register at all."""
        settings = get_settings()
        assert "http://localhost:3100" in settings.CORS_ORIGINS
        assert "http://127.0.0.1:3100" in settings.CORS_ORIGINS


class TestRegistrationAvailability:
    def test_register_individual_route_is_mounted(self, http):
        client, _ = http
        res = client.post("/api/auth/register/individual", json={})
        # Route exists and validates: empty payload is a validation error,
        # not 404/405.
        assert res.status_code == 422, res.status_code

    def test_register_individual_rejects_weak_password(self, http):
        client, _ = http
        res = client.post("/api/auth/register/individual", json={
            "email": "weakpw@test.com",
            "password": "short",
            "full_name": "Weak PW",
        })
        assert res.status_code == 422, res.text

    def test_register_individual_duplicate_email_is_409(self, http):
        client, _ = http
        payload = {
            "email": "dupindiv@test.com",
            "password": "Secure1!Pass",
            "full_name": "Dup Individual",
        }
        first = client.post("/api/auth/register/individual", json=payload)
        assert first.status_code == 200, first.text
        second = client.post("/api/auth/register/individual", json=payload)
        assert second.status_code == 409
        assert second.json()["detail"] == "Email already registered"

    def test_registered_teacher_can_login(self, http):
        client, _ = http
        payload = {
            "email": "loginflow@test.com",
            "password": "Secure1!Pass",
            "full_name": "Login Flow",
        }
        assert client.post("/api/auth/register/individual", json=payload).status_code == 200
        login = client.post("/api/auth/login",
                            json={"email": payload["email"], "password": payload["password"],
                                  "entry": "teacher"})
        assert login.status_code == 200, login.text
        assert "access_token" in login.json()
