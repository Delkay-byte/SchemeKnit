"""Independent lifecycle tests for flexible packs and timed packages.

These prove that expiring a timed package never destroys a flexible credit
pack, and that legacy shared-licence records keep working.
"""
import asyncio
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src import credits, paystack
from src.database import (
    Base, CreditBalanceDB, CreditLedgerDB, EntitlementDB,
    PurchaseEntitlementDB, SubscriptionPlanDB, SubscriptionTransactionDB,
    UserLicenseDB, UserSubscriptionDB, generate_id,
)
from src.routers import auth as auth_router
from tests.conftest import make_user

SECRET = "sk_test_entitlement_secret"
PUBLIC = "pk_test_entitlement_public"


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setenv("PAYSTACK_ENABLED", "true")
    monkeypatch.setenv("PAYSTACK_MODE", "test")
    monkeypatch.setenv("PAYSTACK_SECRET_KEY", SECRET)
    monkeypatch.setenv("NEXT_PUBLIC_PAYSTACK_PUBLIC_KEY", PUBLIC)
    monkeypatch.setenv("PAYSTACK_CURRENCY", "GHS")
    try:
        from src.config import get_settings
        get_settings.cache_clear()
    except Exception:
        pass
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    for slug, name, price, days, allowance, kind in (
        ("flexible-credit-pack", "Flexible Credit Pack", 1200, 0, 20, "flexible"),
        ("teacher-monthly", "Teacher Monthly", 2200, 30, 40, "timed"),
    ):
        session.add(SubscriptionPlanDB(
            slug=slug, name=name, price_pesewas=price, currency="GHS",
            interval="one_time", duration_days=days,
            features=["Lesson-plan credits"],
            entitlements={"generation_limit": 0, "ai_enabled": True,
                          "credit_allowance": allowance},
            active=True, package_kind=kind, credit_allowance=allowance,
            credit_validity_days=days or None,
        ))
    session.commit()
    yield session
    session.close()
    engine.dispose()


def _new_tx(db, user, slug, reference, paid_at=None, method="mobile_money"):
    plan = db.query(SubscriptionPlanDB).filter_by(slug=slug).one()
    tx = SubscriptionTransactionDB(
        reference=reference, user_id=user.id, plan_id=plan.id,
        environment="test", amount_pesewas=plan.price_pesewas,
        currency="GHS", status="pending", payment_method=method,
        provider="vod" if method == "mobile_money" else "",
        payment_details={"package_snapshot": paystack.package_snapshot(plan)},
    )
    db.add(tx)
    db.commit()
    return tx, plan


def _payload(tx, plan, user, paid_at=None):
    return {
        "status": "success",
        "amount": int(plan.price_pesewas),
        "currency": "GHS",
        "reference": tx.reference,
        "id": 6730146887,
        "channel": tx.payment_method,
        "paid_at": (paid_at or datetime.utcnow()).isoformat(),
        "customer": {"email": user.email, "customer_code": "CUS_ENT"},
        "metadata": {
            "user_id": user.id, "plan_id": plan.id, "environment": "test",
        },
    }


def _buy(db, user, slug, reference, paid_at=None):
    tx, plan = _new_tx(db, user, slug, reference, paid_at=paid_at)
    paystack.activate_paid_transaction(db, tx, _payload(tx, plan, user, paid_at))
    db.expire_all()
    return db.query(SubscriptionTransactionDB).filter_by(reference=reference).one()


def test_flexible_pack_has_no_expiry_and_grants_credits(db):
    user = make_user(db)
    tx = _buy(db, user, "flexible-credit-pack", "TFM-flex-only")
    ent = db.query(PurchaseEntitlementDB).filter_by(reference=tx.reference).one()
    assert ent.kind == "flexible"
    assert ent.expires_at is None
    assert ent.status == "active"
    assert credits.status(db, user.id)["purchased"] == 20
    assert paystack.fulfilment_state(db, tx) == "activated"


def test_dashboard_exposes_activated_licences_with_canonical_names_and_credits(db):
    """Platform Admin sees the authoritative entitlement, not just payment."""
    from src.routers.platform_admin import platform_dashboard

    admin = make_user(db, role="platform_admin")
    user = make_user(db)

    # A historical/local label must not leak into the admin display.
    plan = db.query(SubscriptionPlanDB).filter_by(slug="teacher-monthly").one()
    plan.name = "Kyerɛkyerɛni — Individual Teacher (Monthly)"
    db.commit()

    timed = _buy(db, user, "teacher-monthly", "TFM-dashboard-timed")
    flexible = _buy(db, user, "flexible-credit-pack", "TFM-dashboard-flex")
    dashboard = asyncio.run(platform_dashboard(user=admin, db=db))
    rows = {row["reference"]: row for row in dashboard["recent_entitlements"]}

    timed_row = rows[timed.reference]
    assert timed_row["package_name"] == "Teacher Monthly"
    assert timed_row["entitlement_status"] == "active"
    assert timed_row["licence_status"] == "active"
    assert timed_row["payment_status"] == "success"
    assert timed_row["fulfilment_status"] == "activated"
    assert timed_row["credits_granted"] == 40
    assert timed_row["credits_remaining"] == 40
    assert timed_row["credits_used"] == 0
    assert timed_row["expires_at"] is not None

    flex_row = rows[flexible.reference]
    assert flex_row["package_name"] == "Flexible Credit Pack"
    assert flex_row["kind"] == "flexible"
    # A flexible pack has no expiry, even when a timed licence exists.
    assert flex_row["expires_at"] is None
    assert flex_row["credits_granted"] == 20
    assert dashboard["entitlement_counts"]["active"] == 2
    assert dashboard["capabilities"]["standard_generation"] is True


def test_timed_package_has_its_own_expiry(db):
    user = make_user(db)
    tx = _buy(db, user, "teacher-monthly", "TFM-timed-only")
    ent = db.query(PurchaseEntitlementDB).filter_by(reference=tx.reference).one()
    assert ent.kind == "timed"
    assert ent.expires_at is not None
    assert timedelta(days=29) < ent.expires_at - datetime.utcnow() \
        < timedelta(days=31)
    assert credits.status(db, user.id)["package"] == 40


def test_flexible_pack_bought_while_timed_is_active_keeps_both(db):
    user = make_user(db)
    timed = _buy(db, user, "teacher-monthly", "TFM-both-timed")
    flex = _buy(db, user, "flexible-credit-pack", "TFM-both-flex")
    entitlements = db.query(PurchaseEntitlementDB).filter_by(
        user_id=user.id).all()
    assert {e.reference for e in entitlements} == {timed.reference, flex.reference}
    state = credits.status(db, user.id)
    assert state["package"] == 40
    assert state["purchased"] == 20
    assert paystack.fulfilment_state(db, flex) == "activated"
    assert paystack.fulfilment_state(db, timed) == "activated"


def test_timed_expiry_keeps_flexible_credits_and_licence(db):
    user = make_user(db)
    old = datetime.utcnow() - timedelta(days=45)
    timed = _buy(db, user, "teacher-monthly", "TFM-old-timed", paid_at=old)
    flex = _buy(db, user, "flexible-credit-pack", "TFM-live-flex")

    paystack.expire_overdue(db)
    db.expire_all()

    timed_ent = db.query(PurchaseEntitlementDB).filter_by(
        reference=timed.reference).one()
    flex_ent = db.query(PurchaseEntitlementDB).filter_by(
        reference=flex.reference).one()
    assert timed_ent.status == "expired"
    assert flex_ent.status == "active"
    assert flex_ent.expires_at is None

    # The flexible purchase remains fulfilled and its credits are untouched.
    assert paystack.fulfilment_state(db, flex) == "activated"
    state = credits.status(db, user.id)
    assert state["purchased"] == 20
    assert state["package"] == 0

    lic = db.query(UserLicenseDB).filter_by(user_id=user.id).one()
    ent = db.query(EntitlementDB).filter_by(user_id=user.id).one()
    assert lic.status == "active"
    assert lic.expires_at is None
    assert ent.status == "active"
    assert ent.expires_at is None


def test_partially_consumed_flexible_credits_are_reported(db):
    user = make_user(db)
    _buy(db, user, "flexible-credit-pack", "TFM-partial")
    result = credits.reserve(
        db, user.id, 5, "partial-reservation", scheme_id="scheme-1",
        codes=["a", "b", "c", "d", "e"])
    assert result.allowed
    state = credits.status(db, user.id)
    assert state["purchased"] == 17
    pack = state["purchased_packages"][0]
    assert pack["granted"] == 20
    assert pack["used"] == 3
    assert pack["remaining"] == 17
    assert pack["expires_at"] is None


def test_two_flexible_packs_are_independent_buckets(db):
    user = make_user(db)
    _buy(db, user, "flexible-credit-pack", "TFM-pack-a")
    _buy(db, user, "flexible-credit-pack", "TFM-pack-b")
    assert db.query(PurchaseEntitlementDB).filter_by(
        user_id=user.id, kind="flexible").count() == 2
    assert db.query(CreditBalanceDB).filter_by(
        user_id=user.id, source="purchased").count() == 2
    assert credits.status(db, user.id)["purchased"] == 40


def test_renewing_timed_package_extends_from_current_period(db):
    user = make_user(db)
    first = _buy(db, user, "teacher-monthly", "TFM-renew-1")
    second = _buy(db, user, "teacher-monthly", "TFM-renew-2")
    sub = db.query(UserSubscriptionDB).filter_by(user_id=user.id).one()
    assert timedelta(days=59) < sub.paid_through - datetime.utcnow() \
        < timedelta(days=61)
    rows = db.query(PurchaseEntitlementDB).filter_by(
        user_id=user.id, kind="timed").all()
    assert {r.reference for r in rows} == {first.reference, second.reference}
    assert credits.status(db, user.id)["package"] == 80


def test_repeated_fulfilment_does_not_duplicate_entitlement_or_credits(db):
    user = make_user(db)
    tx, plan = _new_tx(db, user, "flexible-credit-pack", "TFM-repeat")
    payload = _payload(tx, plan, user)
    for _ in range(4):
        paystack.activate_paid_transaction(db, tx, payload)
        db.expire_all()
        tx = db.query(SubscriptionTransactionDB).filter_by(
            reference="TFM-repeat").one()
    assert db.query(PurchaseEntitlementDB).filter_by(
        reference="TFM-repeat").count() == 1
    assert db.query(CreditBalanceDB).filter_by(
        grant_key="package:TFM-repeat").count() == 1
    assert db.query(CreditLedgerDB).filter_by(
        idempotency_key="grant:package:TFM-repeat").count() == 1
    assert credits.status(db, user.id)["purchased"] == 20


def test_legacy_success_without_entitlement_row_stays_fulfilled(db):
    user = make_user(db)
    plan = db.query(SubscriptionPlanDB).filter_by(
        slug="flexible-credit-pack").one()
    tx = SubscriptionTransactionDB(
        id=generate_id(), reference="TFM-legacy", user_id=user.id,
        plan_id=plan.id, environment="test", amount_pesewas=1200,
        currency="GHS", status="success", payment_method="mobile_money",
        paid_at=datetime.utcnow() - timedelta(days=90),
        payment_details={"package_snapshot": paystack.package_snapshot(plan)},
    )
    db.add(tx)
    db.add(UserLicenseDB(
        id=generate_id(), user_id=user.id, plan_id=plan.id,
        licence_key="TF-LEGACY", key_hash=paystack._hash_key("TF-LEGACY"),
        status="active", issued_at=datetime.utcnow(),
    ))
    db.add(CreditBalanceDB(
        id=generate_id(), user_id=user.id, source="purchased",
        package_slug=plan.slug, label=plan.name, credits_granted=20,
        credits_remaining=20, grant_key=f"package:{tx.reference}",
        reference=tx.reference, status="active",
    ))
    db.commit()
    assert db.query(PurchaseEntitlementDB).count() == 0
    assert paystack.fulfilment_state(db, tx) == "activated"


def test_dashboard_prefers_live_flexible_pack_after_timed_expiry(db):
    user = make_user(db)
    old = datetime.utcnow() - timedelta(days=45)
    _buy(db, user, "teacher-monthly", "TFM-dash-timed", paid_at=old)
    flex = _buy(db, user, "flexible-credit-pack", "TFM-dash-flex")
    paystack.expire_overdue(db)
    db.expire_all()
    user = db.query(type(user)).filter_by(id=user.id).one()

    resolved = asyncio.run(auth_router.get_my_plan(user=user, db=db))
    package = resolved["active_package"]
    assert package is not None
    assert package["reference"] == flex.reference
    assert package["kind"] == "flexible"
    assert package["credits_granted"] == 20
    assert package["credits_remaining"] == 20
    assert package["expires_at"] is None
    assert package["fulfilment_status"] == "activated"


def test_v054_migration_backfills_legacy_success_purchase(db):
    import importlib.util
    from pathlib import Path
    import sys
    from src import migrations as migration_module
    from sqlalchemy import text

    user = make_user(db)
    plan = db.query(SubscriptionPlanDB).filter_by(
        slug="flexible-credit-pack").one()
    tx = SubscriptionTransactionDB(
        id=generate_id(), reference="TFM-migrated-legacy", user_id=user.id,
        plan_id=plan.id, environment="live", amount_pesewas=1200,
        currency="GHS", status="success", payment_method="mobile_money",
        paid_at=datetime.utcnow() - timedelta(days=10),
        payment_details={},
    )
    db.add(tx)
    db.add(UserLicenseDB(
        id=generate_id(), user_id=user.id, plan_id=plan.id,
        licence_key="TF-MIGRATED", key_hash=paystack._hash_key("TF-MIGRATED"),
        status="active", issued_at=datetime.utcnow(),
    ))
    db.commit()
    db.execute(text("DROP TABLE purchase_entitlements"))
    db.commit()

    engine = db.get_bind()
    path = (Path(migration_module.__file__).parent
            / "v054_purchase_entitlements.py")
    spec = importlib.util.spec_from_file_location("v054_test", path)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "src.migrations"
    sys.modules["src.migrations"] = migration_module
    spec.loader.exec_module(mod)
    mod.engine = engine
    mod.up(db)
    db.expire_all()

    row = db.query(PurchaseEntitlementDB).filter_by(
        reference="TFM-migrated-legacy").one()
    assert row.id == "pe:TFM-migrated-legacy"
    assert row.kind == "flexible"
    assert row.expires_at is None
    assert row.status == "active"
    assert row.package_slug == "flexible-credit-pack"
    assert row.licence_id is not None
