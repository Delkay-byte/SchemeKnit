"""Credit consumption through generation semantics and concurrency guards."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import catalogue, credits  # noqa: E402
from src.database import SubscriptionPlanDB  # noqa: E402
from tests.conftest import make_user  # noqa: E402


def _plan(db, package=catalogue.FLEXIBLE_CREDIT_PACK):
    plan = SubscriptionPlanDB(
        slug=package.slug, name=package.name, price_pesewas=package.price_pesewas,
        currency="GHS", interval="one_time",
        duration_days=package.validity_days or 0, active=True,
        package_kind=package.kind, credit_allowance=package.credits,
        credit_validity_days=package.validity_days,
        entitlements=package.entitlements(),
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def test_multiple_indicators_in_one_week_consume_separate_credits(db):
    """One scheme week with 4 indicators reserves 4 credits, not one."""
    user = make_user(db)
    plan = _plan(db)
    credits.grant_package(db, user.id, plan, "flex")
    res = credits.reserve(
        db, user.id, 4, "same-week", "scheme-1",
        ["B7.1.1.1.1", "B7.1.1.1.2", "B7.1.1.1.3", "B7.1.1.1.4"],
    )
    assert res.allowed and res.charged == 4
    # Two free + two purchased (free is spent first).
    assert credits.status(db, user.id)["free"]["remaining"] == 0
    assert credits.status(db, user.id)["purchased"] == 18


def test_failed_generation_releases_its_credits(db):
    user = make_user(db)
    plan = _plan(db)
    credits.grant_package(db, user.id, plan, "flex")
    res = credits.reserve(db, user.id, 3, "will-fail", "s", ["A", "B", "C"])
    assert credits.status(db, user.id)["total"] == 19  # 20 + 2 free - 3 held
    credits.release(db, res)
    assert credits.status(db, user.id)["total"] == 22  # 20 + 2 free


def test_duplicate_generation_request_does_not_double_deduct(db):
    user = make_user(db)
    plan = _plan(db)
    credits.grant_package(db, user.id, plan, "flex")
    credits.reserve(db, user.id, 2, "dup", "s", ["A", "B"])
    before = credits.status(db, user.id)
    replay = credits.reserve(db, user.id, 2, "dup", "s", ["A", "B"])
    after = credits.status(db, user.id)
    assert replay.charged == 0
    assert after["total"] == before["total"]


def test_concurrent_reservations_cannot_overspend(db):
    """The second guarded reservation fails instead of overdrawing."""
    user = make_user(db)
    plan = _plan(db)
    credits.grant_package(db, user.id, plan, "flex")
    # Drain the free allowance, then leave exactly one paid credit.
    credits.reserve(db, user.id, 2, "free", "s", ["A", "B"])
    credits.reserve(db, user.id, 19, "drain", "s", [f"D{i}" for i in range(19)])
    assert credits.status(db, user.id)["total"] == 1

    first = credits.reserve(db, user.id, 1, "race-1", "s", ["X"])
    second = credits.reserve(db, user.id, 1, "race-2", "s", ["Y"])
    assert first.allowed is True
    assert second.allowed is False
    assert credits.status(db, user.id)["total"] == 0


def test_expired_package_balance_is_not_spendable(db):
    user = make_user(db)
    plan = _plan(db, catalogue.TEACHER_MONTHLY)
    credits.grant_package(
        db, user.id, plan, "old", datetime.utcnow() - timedelta(days=31))
    res = credits.reserve(db, user.id, 3, "expired", "s", ["A", "B", "C"])
    # Only the 2 free credits are available.
    assert res.allowed is False
    assert res.available == 2


def test_paid_package_is_finite_credits_not_unlimited_monthly(db):
    from src.database import EntitlementDB
    from src.entitlements import resolve_entitlement, lesson_quota_status

    user = make_user(db)
    plan = _plan(db)
    credits.grant_package(db, user.id, plan, "flex")
    db.add(EntitlementDB(
        user_id=user.id, edition="teacher", source="paystack",
        status="active", generation_limit=0, ai_enabled=True))
    db.commit()

    resolved = resolve_entitlement(db, user)
    assert resolved["lesson_quota_unlimited"] is False
    status = lesson_quota_status(db, user, resolved)
    assert status["enforced"] is True
    assert status["remaining"] == 22  # 2 free + 20 purchased


def test_legacy_unlimited_account_generates_without_credits(db):
    from fastapi.testclient import TestClient
    from src.database import EntitlementDB
    from tests.test_quota_enforcement_journey import _app, _config, _scheme

    user = make_user(db)
    db.add(EntitlementDB(
        user_id=user.id, edition="teacher", source="admin",
        status="active", generation_limit=0))
    db.commit()
    scheme = _scheme(db, user.id, weeks=3)
    with TestClient(_app(db, user)) as client:
        resp = client.post(
            f"/api/generation/{scheme.id}/generate",
            json=_config(scheme.id).model_dump(mode="json"))
    assert resp.status_code == 200, resp.text
    from src.database import CreditBalanceDB
    assert db.query(CreditBalanceDB).count() == 0
