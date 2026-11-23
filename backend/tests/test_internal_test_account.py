"""Regression tests for the owner-only internal test-account entitlement."""
from __future__ import annotations

from src.entitlements import (
    ai_entitlement,
    consume_ai_generation,
    lesson_quota_status,
    resolve_entitlement,
)


def test_internal_account_is_unlimited_and_labelled(db):
    from tests.conftest import make_user
    user = make_user(db, email="owner-qa@test.test")
    user.is_internal_test_account = True
    db.commit()

    resolved = resolve_entitlement(db, user)
    assert resolved["lesson_quota_unlimited"] is True
    assert resolved["ai_quota_unlimited"] is True
    assert resolved["plan_source"] == "internal_test_account"
    assert resolved["is_internal_test_account"] is True
    assert "billing" in resolved["internal_test_label"].lower()

    quota = lesson_quota_status(db, user, resolved)
    assert quota["unlimited"] is True and quota["internal_test_account"] is True

    assert ai_entitlement(user, db) == (True, "internal_test_account")
    assert consume_ai_generation(user, db, request_id="internal-1") == -1


def test_normal_account_keeps_free_tier_caps(db):
    from tests.conftest import make_user
    user = make_user(db, email="ordinary@test.test")
    resolved = resolve_entitlement(db, user)
    assert resolved["lesson_quota_unlimited"] is False
    assert resolved["is_internal_test_account"] is False
    assert ai_entitlement(user, db)[0] is False


def test_entitlement_is_not_client_assignable():
    """The flag is a DB column, not a request field."""
    from src.routers.generation import LessonConfigRequest
    assert "is_internal_test_account" not in LessonConfigRequest.model_fields


def test_subscription_payload_reports_internal_unlimited(db):
    """The subscription UI must read the unlimited entitlement, not the free
    credit bucket (which remains 2 for historic bookkeeping)."""
    import asyncio
    from src.routers.paystack import my_subscription
    from tests.conftest import make_user

    user = make_user(db, email="owner-plan@test.test")
    user.is_internal_test_account = True
    db.commit()

    body = asyncio.run(my_subscription(user=user, db=db))
    ent = body["entitlement"]
    assert ent["lesson_quota_unlimited"] is True
    assert ent["ai_quota_unlimited"] is True
    assert ent["is_internal_test_account"] is True
    assert ent["batch_generation"] is True
    assert body["credits"]["free"]["limit"] == 2
