"""
Entitlement lifecycle, admin PRO workflow, and download-token persistence.

Covers the production remediation requirements:

  ENTITLEMENT
    * a new/existing teacher with no entitlement resolves to FREE;
    * the plan is SERVER-authoritative — no client field can promote a user;
    * an admin can activate and revoke PRO; an expired/revoked plan resolves
      back to FREE;
    * the admin endpoints are gated by require_platform_admin (checked through
      the real FastAPI dependency chain, not just by convention).

  DOWNLOADS
    * the one-time token is PERSISTED (so a multi-worker deployment works),
      user-bound, expiring and single-use;
    * at least one test exercises the REAL HTTP route and the returned binary
      body (DOCX/PDF signatures), not a mocked response.
"""

import asyncio
import inspect
from datetime import datetime, timedelta
from urllib.parse import unquote

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.database import (
    DownloadTokenDB, EntitlementDB, ProductPlanDB, get_db, generate_id,
)
from src.auth import create_access_token, get_optional_user, require_platform_admin
from src.entitlements import (
    PLAN_FREE,
    PLAN_PRO,
    PLAN_STATUS_EXPIRED,
    PLAN_STATUS_REVOKED,
    activate_pro_entitlement,
    get_user_entitlement,
    resolve_entitlement,
    revoke_pro_entitlement,
)
from src.routers import generation as gen_router
from src.routers.platform_admin import (
    ActivateIndividualRequest,
    ExtendIndividualRequest,
    RevokeIndividualRequest,
    activate_individual_teacher,
    extend_individual_teacher,
    revoke_individual_teacher,
)
from tests.conftest import make_user

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF_MIME = "application/pdf"


def _file_session(tmp_path):
    """A file-backed SQLite session safe to share with the TestClient thread."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from src.database import Base

    engine = create_engine(
        f"sqlite:///{tmp_path / 'download_tokens.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _make_individual_plan(db, name="Teacher Pro", duration_days=30, ai_credits=50):
    plan = ProductPlanDB(
        id=generate_id(), name=name, product_type="subscription", price=49.0,
        currency="GHS", duration_days=duration_days, seat_limit=0,
        customer_type="individual_teacher", generation_limit=0,
        batch_generation=True, zip_export=True, pdf_export=True,
        custom_template_limit=10, history_limit=100, ai_enabled=True,
        ai_credits=ai_credits,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


class TestFreeDefault:
    def test_new_teacher_resolves_to_free(self, db):
        u = make_user(db, role="teacher", email="free-new@t.test")
        res = resolve_entitlement(db, u)
        assert res["plan"] == PLAN_FREE
        assert res["status"] == "active"
        assert res["plan_source"] == "free"
        assert res["source"] == "free"  # legacy key unchanged
        assert res["lesson_quota_limit"] == 5

    def test_user_with_no_row_but_subscription_flag_is_still_free(self, db):
        """A client-visible flag must never confer PRO on its own."""
        u = make_user(db, role="teacher", email="free-flag@t.test")
        u.subscription_type = "individual"  # spoofed/leftover value
        db.commit()
        res = resolve_entitlement(db, u)
        assert res["plan"] == PLAN_FREE
        assert get_user_entitlement(db, u.id) is None

    def test_entitlement_has_no_client_input_path(self):
        """resolve_entitlement reads the DB only — it accepts no request data."""
        params = list(inspect.signature(resolve_entitlement).parameters)
        assert params == ["db", "user"]


class TestAdminActivation:
    def test_admin_activates_pro(self, db):
        u = make_user(db, role="teacher", email="pro-grant@t.test")
        admin = make_user(db, role="platform_admin", email="pa-grant@t.test")
        plan = _make_individual_plan(db)

        res = asyncio.run(activate_individual_teacher(
            ActivateIndividualRequest(teacher_id=u.id, product_plan_id=plan.id,
                                      duration_days=30),
            admin, db))
        assert res["status"] == "activated"

        resolved = resolve_entitlement(db, u)
        assert resolved["plan"] == PLAN_PRO
        assert resolved["status"] == "active"
        assert resolved["plan_source"] == "admin"
        # The admin actor and timestamp are recorded for audit.
        assert resolved["activated_by"] == admin.id
        assert resolved["activated_at"] is not None
        assert resolved["expires_at"] is not None

    def test_revoke_returns_teacher_to_free(self, db):
        u = make_user(db, role="teacher", email="pro-revoke@t.test")
        admin = make_user(db, role="platform_admin", email="pa-revoke@t.test")
        plan = _make_individual_plan(db)
        asyncio.run(activate_individual_teacher(
            ActivateIndividualRequest(teacher_id=u.id, product_plan_id=plan.id),
            admin, db))

        res = asyncio.run(revoke_individual_teacher(
            u.id, RevokeIndividualRequest(reason="chargeback"), admin, db))
        assert res["plan"] == "FREE"

        resolved = resolve_entitlement(db, u)
        assert resolved["plan"] == PLAN_FREE
        assert resolved["status"] == PLAN_STATUS_REVOKED
        assert resolved["revoked_by"] == admin.id
        assert resolved["revoked_at"] is not None
        # Capabilities are gone, not merely relabelled.
        assert resolved["zip_export"] is False
        assert resolved["batch_generation"] is False
        assert get_user_entitlement(db, u.id) is None

    def test_reactivating_a_revoked_plan_clears_the_revocation(self, db):
        u = make_user(db, role="teacher", email="pro-reactivate@t.test")
        admin = make_user(db, role="platform_admin", email="pa-reactivate@t.test")
        plan = _make_individual_plan(db)
        activate_pro_entitlement(db, u, admin, plan=plan)
        revoke_pro_entitlement(db, u, admin, reason="x")
        db.commit()

        activate_pro_entitlement(db, u, admin, plan=plan)
        db.commit()
        resolved = resolve_entitlement(db, u)
        assert resolved["plan"] == PLAN_PRO
        assert resolved["status"] == "active"
        assert resolved["revoked_by"] is None

    def test_expired_pro_resolves_to_free(self, db):
        u = make_user(db, role="teacher", email="pro-expired@t.test")
        admin = make_user(db, role="platform_admin", email="pa-expired@t.test")
        ent = EntitlementDB(
            id=generate_id(), user_id=u.id, edition="teacher",
            subscription_type="individual", status="active",
            expires_at=datetime.utcnow() - timedelta(days=1),
        )
        db.add(ent)
        db.commit()

        assert get_user_entitlement(db, u.id) is None
        resolved = resolve_entitlement(db, u)
        assert resolved["plan"] == PLAN_FREE
        assert resolved["status"] == PLAN_STATUS_EXPIRED
        assert resolved["zip_export"] is False

    def test_extend_pushes_the_expiry_out(self, db):
        u = make_user(db, role="teacher", email="pro-extend@t.test")
        admin = make_user(db, role="platform_admin", email="pa-extend@t.test")
        plan = _make_individual_plan(db, duration_days=10)
        activate_pro_entitlement(db, u, admin, plan=plan)
        db.commit()
        before = resolve_entitlement(db, u)["expires_at"]

        asyncio.run(extend_individual_teacher(
            u.id, ExtendIndividualRequest(duration_days=30), admin, db))
        after = resolve_entitlement(db, u)["expires_at"]
        assert after > before

    def test_admin_endpoints_require_platform_admin(self):
        def deps_of(endpoint):
            return [
                p.default.dependency
                for p in inspect.signature(endpoint).parameters.values()
                if p.default is not inspect.Parameter.empty
                and hasattr(p.default, "dependency")
            ]

        for endpoint in (activate_individual_teacher, revoke_individual_teacher,
                         extend_individual_teacher):
            assert require_platform_admin in deps_of(endpoint), (
                f"{endpoint.__name__} must be platform-admin gated")

    def test_teacher_is_rejected_by_the_admin_dependency(self, db):
        teacher = make_user(db, role="teacher", email="not-admin@t.test")
        token = create_access_token({"sub": teacher.id, "email": teacher.email})

        async def _call():
            return await require_platform_admin(
                credentials=type("C", (), {"credentials": token})(), db=db)

        with pytest.raises(HTTPException) as e:
            asyncio.run(_call())
        assert e.value.status_code == 403


class TestDownloadTokenPersistence:
    def _issue(self, db, user, filename="Lesson_Plans_X.docx", media="x", body=b"PK"):
        import tempfile
        from pathlib import Path
        d = Path(tempfile.mkdtemp())
        f = d / filename
        f.write_bytes(body)
        token = gen_router._issue_download_token(db, user.id, "job-1", f, media, filename)
        return token, f

    def test_token_row_is_persisted(self, db):
        u = make_user(db, role="teacher", email="tok-persist@t.test")
        token, _f = self._issue(db, u)
        row = db.query(DownloadTokenDB).filter(DownloadTokenDB.token == token).first()
        assert row is not None
        assert row.user_id == u.id
        assert row.used_at is None

    def test_token_is_single_use(self, db):
        u = make_user(db, role="teacher", email="tok-once@t.test")
        token, _f = self._issue(db, u)
        first = gen_router._consume_download_token(db, token)
        assert first is not None
        assert gen_router._consume_download_token(db, token) is None

    def test_token_is_user_bound(self, db):
        u = make_user(db, role="teacher", email="tok-mine@t.test")
        other = make_user(db, role="teacher", email="tok-theirs@t.test")
        token, _f = self._issue(db, u)
        assert gen_router._consume_download_token(db, token, other.id) is None

    def test_expired_token_is_rejected(self, db):
        u = make_user(db, role="teacher", email="tok-exp@t.test")
        token, _f = self._issue(db, u)
        row = db.query(DownloadTokenDB).filter(DownloadTokenDB.token == token).first()
        row.expires_at = datetime.utcnow() - timedelta(minutes=1)
        db.commit()
        assert gen_router._consume_download_token(db, token) is None

    def test_download_http_returns_real_bytes_and_is_single_use(self, tmp_path):
        """The REAL HTTP route, not a mocked response: a valid PDF body must be
        delivered with the right headers exactly once.

        Uses a file-backed DB because TestClient serves the request on another
        thread, and SQLite ``:memory:`` is one database per connection.
        """
        db = _file_session(tmp_path)
        try:
            u = make_user(db, role="teacher", email="tok-http@t.test")
            payload = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\ntrailer\n%%EOF\n"
            token, _f = self._issue(db, u, filename="Lesson_Plans_Science.pdf",
                                    media=PDF_MIME, body=payload)

            from src.main import app

            app.dependency_overrides[get_db] = lambda: db
            app.dependency_overrides[get_optional_user] = lambda: None
            try:
                client = TestClient(app)
                r = client.get(f"/api/generation/downloads/{token}")
                assert r.status_code == 200
                assert r.headers["content-type"].startswith(PDF_MIME)
                assert r.headers["content-disposition"].startswith("attachment;")
                assert r.content.startswith(b"%PDF-")
                assert r.content == payload

                r2 = client.get(f"/api/generation/downloads/{token}")
                assert r2.status_code == 404
            finally:
                app.dependency_overrides.clear()
        finally:
            db.close()

    def test_download_http_rejects_a_foreign_bearer(self, tmp_path):
        """When an authenticated identity IS supplied it must match the issuer."""
        db = _file_session(tmp_path)
        try:
            u = make_user(db, role="teacher", email="tok-owner@t.test")
            other = make_user(db, role="teacher", email="tok-intruder@t.test")
            token, _f = self._issue(
                db, u, filename="x.docx", media=DOCX_MIME, body=b"PK\x03\x04")

            from src.main import app

            app.dependency_overrides[get_db] = lambda: db
            app.dependency_overrides[get_optional_user] = lambda: other
            try:
                client = TestClient(app)
                r = client.get(f"/api/generation/downloads/{token}")
                assert r.status_code == 404
            finally:
                app.dependency_overrides.clear()
        finally:
            db.close()
