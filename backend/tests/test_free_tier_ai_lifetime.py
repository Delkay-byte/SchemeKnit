"""
Free Tier lifetime AI generation quota tests (§15, §16).

    The Free Tier receives 5 SUCCESSFUL AI generations for the LIFETIME of the
    account. There is NO daily, weekly or monthly reset. Only a successfully
    completed generation consumes an allowance.
"""

from datetime import date, datetime, timedelta

import pytest
from fastapi import HTTPException

from src.database import EntitlementDB, generate_id
from tests.conftest import make_user, make_entitled_teacher
from src.entitlements import (
    FREE_TIER_AI_GENERATIONS,
    ai_entitlement,
    consume_ai_generation,
    require_ai_entitlement,
)


def _make_free_user(db, email="free@test.com"):
    user = make_user(db, role="teacher", email=email)
    user.school_id = None
    user.subscription_type = "individual"
    db.commit()
    ent = EntitlementDB(
        id=generate_id(),
        user_id=user.id,
        edition="free",
        subscription_type="individual",
        generation_limit=3,
        generations_used=0,
        batch_generation=False,
        zip_export=False,
        pdf_export=True,
        custom_template_limit=1,
        history_limit=10,
        ai_enabled=True,
        ai_credits=FREE_TIER_AI_GENERATIONS,
        ai_credits_used=0,
    )
    db.add(ent)
    db.commit()
    return user, ent


class TestFreeTierLifetimeAllowance:
    def test_new_free_account_starts_with_five(self, db):
        user, _ = _make_free_user(db)
        entitled, reason = ai_entitlement(user, db)
        assert entitled
        assert reason == "free_trial"
        from src.entitlements import resolve_entitlement
        resolved = resolve_entitlement(db, user)
        assert resolved["plan_name"] == "Free Tier"
        assert resolved["ai_credits"] == 5
        assert resolved["ai_credits_used"] == 0

    def test_each_successful_generation_decrements_by_one(self, db):
        user, _ = _make_free_user(db)
        expected = [4, 3, 2, 1, 0]
        for remaining in expected:
            assert consume_ai_generation(user, db) == remaining

    def test_fifth_generation_exhausts(self, db):
        user, _ = _make_free_user(db)
        for _ in range(5):
            consume_ai_generation(user, db)
        entitled, reason = ai_entitlement(user, db)
        assert not entitled
        assert reason == "credits_exhausted"

    def test_sixth_generation_is_rejected(self, db):
        user, _ = _make_free_user(db)
        for _ in range(5):
            consume_ai_generation(user, db)
        # A sixth attempt is denied by the server-side gate.
        with pytest.raises(HTTPException) as exc:
            require_ai_entitlement(user, db)
        assert exc.value.status_code == 403

    def test_exhaustion_message(self, db):
        user, _ = _make_free_user(db)
        for _ in range(5):
            consume_ai_generation(user, db)
        with pytest.raises(HTTPException) as exc:
            require_ai_entitlement(user, db)
        assert "You've used all 5 free AI generations included with the Free Tier." in exc.value.detail

    def test_consumption_is_clamped(self, db):
        user, _ = _make_free_user(db)
        for _ in range(5):
            consume_ai_generation(user, db)
        # Further consumption cannot drive the counter below zero.
        assert consume_ai_generation(user, db) == 0
        assert consume_ai_generation(user, db) == 0

    def test_no_reset_across_time(self, db):
        """The allowance never refills — no day/week/month reset."""
        user, ent = _make_free_user(db)
        for _ in range(5):
            consume_ai_generation(user, db)
        # Simulate the passage of time: nothing in the codebase resets usage.
        ent.created_at = datetime.utcnow() - timedelta(days=90)
        db.commit()
        db.expire_all()
        entitled, reason = ai_entitlement(user, db)
        assert not entitled
        assert reason == "credits_exhausted"


class TestIdempotentConsumption:
    def test_duplicate_submission_does_not_double_consume(self, db):
        user, ent = _make_free_user(db)
        first = consume_ai_generation(user, db, request_id="req-1")
        second = consume_ai_generation(user, db, request_id="req-1")
        assert first == 4
        assert second == 4  # unchanged — same successful request
        db.refresh(ent)
        assert ent.ai_credits_used == 1

    def test_distinct_requests_consume_separately(self, db):
        user, ent = _make_free_user(db)
        consume_ai_generation(user, db, request_id="req-1")
        consume_ai_generation(user, db, request_id="req-2")
        db.refresh(ent)
        assert ent.ai_credits_used == 2


class TestEntitlementsNotAffected:
    def test_school_license_is_unlimited(self, db):
        user, _school, _lic = make_entitled_teacher(db, email="school@test.com")
        entitled, reason = ai_entitlement(user, db)
        assert entitled and reason == "school_license"
        # Consumption is a no-op for unlimited entitlements.
        assert consume_ai_generation(user, db) == -1

    def test_paid_pro_with_unlimited_credits(self, db):
        user = make_user(db, role="teacher", email="pro@test.com")
        user.school_id = None
        db.commit()
        ent = EntitlementDB(
            id=generate_id(),
            user_id=user.id,
            edition="teacher",
            ai_enabled=True,
            ai_credits=0,  # 0 = unlimited
            ai_credits_used=0,
        )
        db.add(ent)
        db.commit()
        entitled, reason = ai_entitlement(user, db)
        assert entitled and reason == "paid_entitlement"
        assert consume_ai_generation(user, db) == -1
        db.refresh(ent)
        assert ent.ai_credits_used == 0

    def test_pro_with_finite_credits_not_lifetime_capped(self, db):
        """A paid plan keeps its own allowance, not the free lifetime rule."""
        user = make_user(db, role="teacher", email="pro2@test.com")
        user.school_id = None
        db.commit()
        ent = EntitlementDB(
            id=generate_id(),
            user_id=user.id,
            edition="teacher",
            ai_enabled=True,
            ai_credits=50,
            ai_credits_used=10,
        )
        db.add(ent)
        db.commit()
        entitled, reason = ai_entitlement(user, db)
        assert entitled and reason == "paid_entitlement"


class TestOllamaCannotBypass:
    def test_exhausted_free_user_blocked_for_any_provider(self, db):
        """Ollama is a runtime, not permission. The gate is provider-agnostic."""
        user, _ = _make_free_user(db)
        for _ in range(5):
            consume_ai_generation(user, db)
        # The entitlement check runs BEFORE any provider is constructed.
        with pytest.raises(HTTPException) as exc:
            require_ai_entitlement(user, db)
        assert exc.value.status_code == 403
