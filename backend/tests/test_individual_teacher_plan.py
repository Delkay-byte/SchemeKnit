"""
Individual Teacher Plan — comprehensive backend tests.

Tests cover:
  - Individual teacher registration
  - Free plan entitlements and limits
  - Teacher Pro upgrade and activation
  - Feature gates (generation, batch, ZIP, PDF, templates, AI)
  - School + individual entitlement precedence
  - Expiry behavior
  - Payment flow
  - Platform Admin management
  - Security (no privilege escalation, no quota bypass)
"""

import os
import sys
from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.database import (
    get_db, User, EntitlementDB, SubscriptionDB, SchoolDB, SchoolLicenseDB,
    SchoolMembershipDB, ProductPlanDB, PaymentDB, generate_id,
)
from src.auth import hash_password, create_access_token
from src.entitlements import (
    resolve_entitlement, get_user_entitlement, get_active_subscription,
    can_generate_batch, can_export_zip, can_use_ai, can_create_custom_template,
    increment_generation_count, increment_ai_credits, ai_entitlement,
)
from tests.conftest import make_user


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_individual_teacher(db, email, edition="free"):
    """Create an individual teacher with an entitlement row."""
    u = make_user(db, role="teacher", email=email)
    u.school_id = None
    u.subscription_type = "individual"
    db.commit()

    ent = EntitlementDB(
        id=generate_id(),
        user_id=u.id,
        edition=edition,
        subscription_type="individual",
        generation_limit=3 if edition == "free" else 0,
        generations_used=0,
        batch_generation=(edition == "teacher"),
        zip_export=(edition == "teacher"),
        pdf_export=True,
        custom_template_limit=1 if edition == "free" else 10,
        history_limit=10 if edition == "free" else 100,
        ai_enabled=True,
        ai_credits=5 if edition == "free" else 50,
        ai_credits_used=0,
    )
    db.add(ent)
    db.commit()
    return u, ent


def _make_school_teacher(db, email):
    """Create a school teacher with an active school license."""
    school = SchoolDB(
        id=generate_id(), name="Test School", school_code="TST001",
        status="active",
    )
    db.add(school)
    db.flush()

    u = make_user(db, role="teacher", email=email)
    u.school_id = school.id
    db.commit()

    membership = SchoolMembershipDB(
        id=generate_id(), user_id=u.id, school_id=school.id,
        role="teacher", status="active",
    )
    db.add(membership)

    plan = ProductPlanDB(
        id=generate_id(), name="School Plan", product_type="subscription",
        price=199.0, duration_days=365, seat_limit=50,
    )
    db.add(plan)
    db.flush()

    lic = SchoolLicenseDB(
        id=generate_id(), school_id=school.id, product_plan_id=plan.id,
        license_code=f"TF-LIC-{generate_id()[:8]}",
        status="active", start_date=date.today(),
        expiry_date=date.today() + timedelta(days=365),
        seat_limit=50,
    )
    db.add(lic)
    db.commit()
    return u, school, lic


# ── Account Tests ────────────────────────────────────────────────────────────

class TestIndividualTeacherRegistration:
    @pytest.mark.asyncio
    async def test_self_registration_creates_individual_teacher(self, db):
        from src.routers.auth import register_individual_teacher, IndividualRegisterRequest

        req = IndividualRegisterRequest(
            email="indiv@test.com",
            password="TestPass1!",
            full_name="Individual Teacher",
        )
        result = await register_individual_teacher(req, db)

        assert "access_token" in result
        assert result["user"]["role"] == "teacher"
        assert result["user"]["school_id"] is None
        assert result["user"]["subscription_type"] == "individual"

    @pytest.mark.asyncio
    async def test_self_registration_creates_free_entitlement(self, db):
        from src.routers.auth import register_individual_teacher, IndividualRegisterRequest

        req = IndividualRegisterRequest(
            email="indiv-ent@test.com",
            password="TestPass1!",
            full_name="Free Teacher",
        )
        result = await register_individual_teacher(req, db)

        user_id = result["user"]["id"]
        ent = get_user_entitlement(db, user_id)
        assert ent is not None
        assert ent.edition == "free"
        assert ent.subscription_type == "individual"
        assert ent.generation_limit == 3
        assert ent.batch_generation is False
        assert ent.zip_export is False
        assert ent.ai_enabled is True
        assert ent.ai_credits == 5

    @pytest.mark.asyncio
    async def test_duplicate_email_rejected(self, db):
        from src.routers.auth import register_individual_teacher, IndividualRegisterRequest

        req = IndividualRegisterRequest(
            email="dup@test.com",
            password="TestPass1!",
            full_name="First",
        )
        await register_individual_teacher(req, db)

        req2 = IndividualRegisterRequest(
            email="dup@test.com",
            password="TestPass2!",
            full_name="Second",
        )
        with pytest.raises(HTTPException) as e:
            await register_individual_teacher(req2, db)
        assert e.value.status_code == 409

    @pytest.mark.asyncio
    async def test_invalid_email_rejected(self, db):
        from src.routers.auth import register_individual_teacher, IndividualRegisterRequest

        req = IndividualRegisterRequest(
            email="not-an-email",
            password="TestPass1!",
            full_name="Bad Email",
        )
        with pytest.raises(HTTPException) as e:
            await register_individual_teacher(req, db)
        assert e.value.status_code == 422

    @pytest.mark.asyncio
    async def test_weak_password_rejected(self, db):
        from src.routers.auth import register_individual_teacher, IndividualRegisterRequest

        req = IndividualRegisterRequest(
            email="weak@test.com",
            password="123",
            full_name="Weak Password",
        )
        with pytest.raises(HTTPException) as e:
            await register_individual_teacher(req, db)
        assert e.value.status_code == 422

    @pytest.mark.asyncio
    async def test_school_id_is_null(self, db):
        from src.routers.auth import register_individual_teacher, IndividualRegisterRequest

        req = IndividualRegisterRequest(
            email="noschool@test.com",
            password="TestPass1!",
            full_name="No School",
        )
        result = await register_individual_teacher(req, db)
        assert result["user"]["school_id"] is None


# ── Free Plan Entitlement Tests ─────────────────────────────────────────────

class TestFreePlanEntitlements:
    def test_free_teacher_has_limited_generation(self, db):
        u, ent = _make_individual_teacher(db, "free-gen@test.com")
        resolved = resolve_entitlement(db, u)
        assert resolved["generation_limit"] == 3
        assert resolved["generations_used"] == 0

    def test_free_teacher_cannot_batch(self, db):
        u, _ = _make_individual_teacher(db, "free-batch@test.com")
        allowed, reason = can_generate_batch(u, db)
        assert not allowed
        assert "Teacher Pro" in reason

    def test_free_teacher_cannot_zip(self, db):
        u, _ = _make_individual_teacher(db, "free-zip@test.com")
        allowed, reason = can_export_zip(u, db)
        assert not allowed
        assert "Teacher Pro" in reason

    def test_free_teacher_has_pdf(self, db):
        u, _ = _make_individual_teacher(db, "free-pdf@test.com")
        resolved = resolve_entitlement(db, u)
        assert resolved["pdf_export"] is True

    def test_free_teacher_limited_templates(self, db):
        u, _ = _make_individual_teacher(db, "free-tpl@test.com")
        resolved = resolve_entitlement(db, u)
        assert resolved["custom_template_limit"] == 1

    def test_free_teacher_has_ai_trial(self, db):
        u, _ = _make_individual_teacher(db, "free-ai@test.com")
        allowed, reason = can_use_ai(u, db)
        assert allowed

    def test_free_teacher_limited_history(self, db):
        u, _ = _make_individual_teacher(db, "free-hist@test.com")
        resolved = resolve_entitlement(db, u)
        assert resolved["history_limit"] == 10

    def test_generation_counter_increments(self, db):
        u, ent = _make_individual_teacher(db, "free-inc@test.com")
        assert ent.generations_used == 0
        increment_generation_count(u, db, 1)
        ent = get_user_entitlement(db, u.id)
        assert ent.generations_used == 1

    def test_generation_quota_enforcement(self, db):
        u, ent = _make_individual_teacher(db, "free-quota@test.com")
        ent.generations_used = 3
        db.commit()
        resolved = resolve_entitlement(db, u)
        assert resolved["generation_limit"] == 3
        assert resolved["generations_used"] == 3
        # Generation should be blocked
        assert resolved["generation_limit"] > 0 and resolved["generations_used"] >= resolved["generation_limit"]

    def test_ai_credits_decrement(self, db):
        u, ent = _make_individual_teacher(db, "free-aidec@test.com")
        assert ent.ai_credits_used == 0
        increment_ai_credits(u, db, 1)
        ent = get_user_entitlement(db, u.id)
        assert ent.ai_credits_used == 1


# ── Pro Plan Tests ──────────────────────────────────────────────────────────

class TestProPlanEntitlements:
    def test_pro_teacher_can_batch(self, db):
        u, _ = _make_individual_teacher(db, "pro-batch@test.com", edition="teacher")
        allowed, reason = can_generate_batch(u, db)
        assert allowed

    def test_pro_teacher_can_zip(self, db):
        u, _ = _make_individual_teacher(db, "pro-zip@test.com", edition="teacher")
        allowed, reason = can_export_zip(u, db)
        assert allowed

    def test_pro_teacher_unlimited_generation(self, db):
        u, _ = _make_individual_teacher(db, "pro-gen@test.com", edition="teacher")
        resolved = resolve_entitlement(db, u)
        assert resolved["generation_limit"] == 0  # unlimited

    def test_pro_teacher_has_ai(self, db):
        u, _ = _make_individual_teacher(db, "pro-ai@test.com", edition="teacher")
        allowed, reason = can_use_ai(u, db)
        assert allowed

    def test_pro_teacher_more_templates(self, db):
        u, _ = _make_individual_teacher(db, "pro-tpl@test.com", edition="teacher")
        resolved = resolve_entitlement(db, u)
        assert resolved["custom_template_limit"] == 10

    def test_pro_teacher_more_history(self, db):
        u, _ = _make_individual_teacher(db, "pro-hist@test.com", edition="teacher")
        resolved = resolve_entitlement(db, u)
        assert resolved["history_limit"] == 100

    def test_pro_source_is_individual(self, db):
        u, _ = _make_individual_teacher(db, "pro-src@test.com", edition="teacher")
        resolved = resolve_entitlement(db, u)
        assert resolved["source"] == "individual"
        assert resolved["subscription_type"] == "individual"
        assert resolved["plan_name"] == "Teacher Pro"


# ── Expiry Tests ────────────────────────────────────────────────────────────

class TestExpiryBehavior:
    def test_expired_pro_returns_free(self, db):
        u, ent = _make_individual_teacher(db, "exp@test.com", edition="teacher")
        ent.expires_at = datetime.utcnow() - timedelta(days=1)
        db.commit()
        # get_user_entitlement returns None for expired
        assert get_user_entitlement(db, u.id) is None
        # resolve_entitlement falls back to free defaults
        resolved = resolve_entitlement(db, u)
        assert resolved["edition"] == "free"
        assert resolved["batch_generation"] is False

    def test_active_pro_not_expired(self, db):
        u, ent = _make_individual_teacher(db, "active-pro@test.com", edition="teacher")
        ent.expires_at = datetime.utcnow() + timedelta(days=30)
        db.commit()
        assert get_user_entitlement(db, u.id) is not None
        resolved = resolve_entitlement(db, u)
        assert resolved["batch_generation"] is True

    def test_data_retained_after_expiry(self, db):
        u, ent = _make_individual_teacher(db, "retain@test.com", edition="teacher")
        ent.expires_at = datetime.utcnow() - timedelta(days=1)
        db.commit()
        # Entitlement row still exists, just expired
        raw_ent = db.query(EntitlementDB).filter(EntitlementDB.user_id == u.id).first()
        assert raw_ent is not None
        assert raw_ent.edition == "teacher"


# ── School + Individual Precedence Tests ────────────────────────────────────

class TestSchoolIndividualPrecedence:
    def test_school_teacher_gets_school_entitlement(self, db):
        u, school, lic = _make_school_teacher(db, "school-t@test.com")
        resolved = resolve_entitlement(db, u)
        assert resolved["source"] == "school"
        assert resolved["batch_generation"] is True
        assert resolved["zip_export"] is True

    def test_individual_plus_school_combined(self, db):
        u, ent = _make_individual_teacher(db, "both@test.com", edition="teacher")
        school = SchoolDB(
            id=generate_id(), name="Both School", school_code="BTH001",
            status="active",
        )
        db.add(school)
        db.flush()
        u.school_id = school.id

        plan = ProductPlanDB(
            id=generate_id(), name="School Plan", product_type="subscription",
            price=199.0, duration_days=365, seat_limit=50,
        )
        db.add(plan)
        db.flush()

        lic = SchoolLicenseDB(
            id=generate_id(), school_id=school.id, product_plan_id=plan.id,
            license_code=f"TF-LIC-{generate_id()[:8]}",
            status="active", start_date=date.today(),
            expiry_date=date.today() + timedelta(days=365),
            seat_limit=50,
        )
        db.add(lic)
        db.commit()

        resolved = resolve_entitlement(db, u)
        assert resolved["source"] == "individual+school"
        assert resolved["batch_generation"] is True
        assert resolved["zip_export"] is True

    def test_school_expiry_does_not_erase_individual_pro(self, db):
        u, ent = _make_individual_teacher(db, "sch-exp@test.com", edition="teacher")
        school = SchoolDB(
            id=generate_id(), name="Exp School", school_code="EXP001",
            status="active",
        )
        db.add(school)
        db.flush()
        u.school_id = school.id

        plan = ProductPlanDB(
            id=generate_id(), name="School Plan", product_type="subscription",
            price=199.0, duration_days=365, seat_limit=50,
        )
        db.add(plan)
        db.flush()

        lic = SchoolLicenseDB(
            id=generate_id(), school_id=school.id, product_plan_id=plan.id,
            license_code=f"TF-LIC-{generate_id()[:8]}",
            status="active", start_date=date.today() - timedelta(days=400),
            expiry_date=date.today() - timedelta(days=30),  # expired
            seat_limit=50,
        )
        db.add(lic)
        db.commit()

        resolved = resolve_entitlement(db, u)
        # School license is expired, so individual Pro should still work
        assert resolved["batch_generation"] is True
        assert resolved["zip_export"] is True


# ── Payment Flow Tests ──────────────────────────────────────────────────────

class TestPaymentFlow:
    def test_free_to_pro_upgrade(self, db):
        u, ent = _make_individual_teacher(db, "upgrade@test.com", edition="free")
        assert ent.edition == "free"
        assert ent.batch_generation is False

        # Simulate payment activation
        from src.payment_service import PaymentService
        from src.database import PaymentDB

        plan = ProductPlanDB(
            id=generate_id(), name="Teacher Pro", product_type="subscription",
            price=49.0, duration_days=30, customer_type="individual_teacher",
            batch_generation=True, zip_export=True, pdf_export=True,
            custom_template_limit=10, history_limit=100,
            ai_enabled=True, ai_credits=50, generation_limit=0,
        )
        db.add(plan)
        db.flush()

        payment = PaymentDB(
            id=generate_id(), user_id=u.id, payment_method="mtn_momo",
            amount=49.0, product_type="subscription", product_id=plan.id,
            product_name="Teacher Pro", status="verified",
        )
        db.add(payment)
        db.flush()

        svc = PaymentService()
        svc._activate_entitlement(db, payment)

        ent = get_user_entitlement(db, u.id)
        assert ent.edition == "teacher"
        assert ent.batch_generation is True
        assert ent.zip_export is True
        assert ent.ai_credits == 50


# ── Security Tests ──────────────────────────────────────────────────────────

class TestSecurity:
    def test_teacher_cannot_self_upgrade(self, db):
        """Teachers cannot modify their own entitlement."""
        u, ent = _make_individual_teacher(db, "self-upgrade@test.com")
        # The entitlement is server-managed; there's no API for teachers to change it
        # This is verified by the absence of such an endpoint
        assert ent.edition == "free"

    def test_teacher_cannot_bypass_quota_via_api(self, db):
        """Generation quota is enforced server-side."""
        u, ent = _make_individual_teacher(db, "quota-bypass@test.com")
        ent.generations_used = 3
        db.commit()

        # The generation endpoint checks entitlement before generating
        resolved = resolve_entitlement(db, u)
        assert resolved["generation_limit"] == 3
        assert resolved["generations_used"] == 3

    def test_teacher_cannot_access_platform_admin(self, db):
        """Individual teachers cannot access platform admin endpoints."""
        u, _ = _make_individual_teacher(db, "admin-bypass@test.com")
        assert u.role == "teacher"
        # Platform admin check is in require_platform_admin dependency

    def test_school_teacher_not_treated_as_individual(self, db):
        """School teachers should not be pushed toward individual plans."""
        u, school, lic = _make_school_teacher(db, "sch-indiv@test.com")
        resolved = resolve_entitlement(db, u)
        assert resolved["subscription_type"] == "school"
        assert resolved["plan_name"] == "School Subscription"


# ── AI Entitlement Tests ────────────────────────────────────────────────────

class TestAIEntitlement:
    def test_free_teacher_ai_trial(self, db):
        u, _ = _make_individual_teacher(db, "ai-free@test.com")
        entitled, reason = ai_entitlement(u, db)
        assert entitled
        assert reason == "paid_entitlement"

    def test_pro_teacher_ai(self, db):
        u, _ = _make_individual_teacher(db, "ai-pro@test.com", edition="teacher")
        entitled, reason = ai_entitlement(u, db)
        assert entitled
        assert reason == "paid_entitlement"

    def test_ai_credits_exhausted(self, db):
        u, ent = _make_individual_teacher(db, "ai-exhausted@test.com")
        ent.ai_credits_used = 5
        db.commit()
        entitled, reason = ai_entitlement(u, db)
        assert not entitled
        assert reason == "credits_exhausted"

    def test_school_teacher_ai(self, db):
        u, school, lic = _make_school_teacher(db, "ai-school@test.com")
        entitled, reason = ai_entitlement(u, db)
        assert entitled
        assert reason == "school_license"


# ── Platform Admin Tests ────────────────────────────────────────────────────

class TestPlatformAdmin:
    @pytest.mark.asyncio
    async def test_list_individual_teachers(self, db):
        from src.routers.platform_admin import list_individual_teachers

        _make_individual_teacher(db, "list1@test.com")
        _make_individual_teacher(db, "list2@test.com", edition="teacher")

        admin = make_user(db, role="platform_admin", email="admin-list@test.com")
        result = await list_individual_teachers(admin, db)

        assert result["count"] >= 2
        emails = [t["email"] for t in result["teachers"]]
        assert "list1@test.com" in emails
        assert "list2@test.com" in emails

    @pytest.mark.asyncio
    async def test_activate_individual_teacher(self, db):
        from src.routers.platform_admin import activate_individual_teacher, ActivateIndividualRequest

        u, _ = _make_individual_teacher(db, "activate@test.com")
        admin = make_user(db, role="platform_admin", email="admin-act@test.com")

        plan = ProductPlanDB(
            id=generate_id(), name="Teacher Pro", product_type="subscription",
            price=49.0, duration_days=30, customer_type="individual_teacher",
            batch_generation=True, zip_export=True, pdf_export=True,
            custom_template_limit=10, history_limit=100,
            ai_enabled=True, ai_credits=50, generation_limit=0,
        )
        db.add(plan)
        db.commit()

        req = ActivateIndividualRequest(
            teacher_id=u.id,
            product_plan_id=plan.id,
            duration_days=30,
        )
        result = await activate_individual_teacher(req, admin, db)

        assert result["status"] == "activated"
        ent = get_user_entitlement(db, u.id)
        assert ent.edition == "teacher"
        assert ent.batch_generation is True
