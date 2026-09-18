"""
Production UI safety gates (milestone: Production UI Polish + PWA).

These lock the rules that keep development/acceptance tooling out of a
production deployment:

  1. The demo commercial-data reset must 403 whenever DEBUG is off, even for a
     platform admin supplying the correct confirmation phrase.
  2. It must still work in a development (DEBUG on) environment, so the gate
     is a production guard, not a removed feature.
  3. A non-admin can never reach it, regardless of environment.
"""

import asyncio

import pytest
from fastapi import HTTPException

from src.config import Settings
from src.routers.platform_admin import ResetDemoRequest, reset_demo_data
from tests.conftest import make_user, make_school, make_product_plan, make_license


def _run(req, user, db, debug: bool):
    """Invoke the async route with settings.DEBUG forced to `debug`."""
    import src.routers.platform_admin as pa

    original = pa.get_settings
    pa.get_settings = lambda: Settings(DEBUG=debug)
    try:
        return asyncio.run(reset_demo_data(req, user, db))
    finally:
        pa.get_settings = original


def test_demo_reset_blocked_in_production(db):
    """DEBUG off + platform admin + correct phrase -> 403, data untouched."""
    school = make_school(db, name="Prod School")
    plan = make_product_plan(db)
    make_license(db, school.id, plan.id, status="active")
    admin = make_user(db, role="platform_admin", is_admin=True)

    req = ResetDemoRequest(confirm="RESET DEMO COMMERCIAL DATA")
    with pytest.raises(HTTPException) as exc:
        _run(req, admin, db, debug=False)

    assert exc.value.status_code == 403
    # Nothing was removed.
    from src.database import SchoolDB
    assert db.query(SchoolDB).count() == 1


def test_demo_reset_allowed_in_development(db):
    """DEBUG on + platform admin -> proceeds and removes commercial data."""
    school = make_school(db, name="Demo School")
    plan = make_product_plan(db)
    make_license(db, school.id, plan.id, status="active")
    admin = make_user(db, role="platform_admin", is_admin=True)

    req = ResetDemoRequest(confirm="RESET DEMO COMMERCIAL DATA")
    result = _run(req, admin, db, debug=True)

    assert result["message"] == "Demo commercial data reset"
    assert result["removed"]["schools"] == 1
    assert result["removed"]["school_licenses"] == 1


def test_demo_reset_wrong_confirmation_rejected(db):
    """A wrong confirmation phrase is rejected in either environment."""
    admin = make_user(db, role="platform_admin", is_admin=True)
    req = ResetDemoRequest(confirm="nope")
    with pytest.raises(HTTPException) as exc:
        _run(req, admin, db, debug=True)
    assert exc.value.status_code == 400


def test_demo_reset_requires_platform_admin_dependency():
    """The route is wired with require_platform_admin, so a teacher can never
    reach the body — authorization is not left to the client."""
    from src.routers import platform_admin

    route = next(
        r for r in platform_admin.router.routes
        if getattr(r, "path", None) == "/reset-demo-data"
    )
    names = []
    stack = list(route.dependant.dependencies or [])
    while stack:
        dep = stack.pop()
        call = getattr(dep, "call", None)
        name = getattr(call, "__name__", None) or type(call).__name__
        if name:
            names.append(name)
        stack.extend(dep.dependencies or [])
    assert "require_platform_admin" in names, (
        "reset-demo-data must depend on require_platform_admin"
    )


def test_production_settings_reject_default_secrets():
    """Non-DEBUG boot must refuse the CHANGE-ME default secrets."""
    s = Settings(DEBUG=False, SECRET_KEY="CHANGE-ME-IN-PRODUCTION",
                 JWT_SECRET_KEY="CHANGE-ME-IN-PRODUCTION")
    with pytest.raises(RuntimeError):
        s.validate_production()


def test_production_settings_accept_real_secrets():
    """Real secrets boot cleanly in production mode."""
    s = Settings(
        DEBUG=False,
        SECRET_KEY="a-real-secret",
        JWT_SECRET_KEY="a-real-jwt-secret",
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
