"""Approved package catalogue and credit-accounting tests."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import catalogue, credits  # noqa: E402
from src.database import CreditBalanceDB, CreditLedgerDB, SubscriptionPlanDB  # noqa: E402
from src.usage_quota import current_period_key, get_units_used  # noqa: E402
from tests.conftest import make_user  # noqa: E402


def _seed_plan(db, package: catalogue.Package) -> SubscriptionPlanDB:
    plan = SubscriptionPlanDB(
        slug=package.slug, name=package.name,
        description=package.description,
        price_pesewas=package.price_pesewas, currency="GHS",
        interval="one_time", duration_days=package.validity_days or 0,
        features=list(package.features), entitlements=package.entitlements(),
        active=package.purchasable, package_kind=package.kind,
        credit_allowance=package.credits,
        credit_validity_days=package.validity_days,
        payment_terms=package.payment_terms,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


class TestCatalogue:
    def test_exact_approved_catalogue(self):
        assert catalogue.FREE.price_pesewas == 0
        assert catalogue.FREE.credits == 2
        assert catalogue.FLEXIBLE_CREDIT_PACK.price_pesewas == 1200
        assert catalogue.FLEXIBLE_CREDIT_PACK.credits == 20
        assert catalogue.FLEXIBLE_CREDIT_PACK.validity_days is None
        assert catalogue.TEACHER_MONTHLY.price_pesewas == 2200
        assert catalogue.TEACHER_MONTHLY.credits == 40
        assert catalogue.TEACHER_MONTHLY.validity_days == 30
        assert catalogue.TEACHER_TERM_PASS.price_pesewas == 5000
        assert catalogue.TEACHER_TERM_PASS.credits == 160
        assert catalogue.TEACHER_TERM_PASS.validity_days == 120
        assert catalogue.ACADEMIC_YEAR_PASS.price_pesewas == 12000
        assert catalogue.ACADEMIC_YEAR_PASS.credits == 480
        assert catalogue.ACADEMIC_YEAR_PASS.validity_days == 365

    def test_purchasable_catalogue_excludes_free_and_legacy(self):
        slugs = [p.slug for p in catalogue.purchasable()]
        assert slugs == [
            "flexible-credit-pack", "teacher-monthly",
            "teacher-term-pass", "academic-year-pass",
        ]
        assert "free" not in slugs
        assert "teacher-annual" not in slugs
        assert "school-monthly" not in slugs

    def test_package_entitlements_are_finite_credits_not_monthly_cap(self):
        ent = catalogue.TEACHER_TERM_PASS.entitlements()
        assert ent["generation_limit"] == 0
        assert ent["credit_allowance"] == 160
        assert ent["credit_validity_days"] == 120


class TestFreeCredits:
    def test_two_free_credits_per_calendar_month(self, db):
        user = make_user(db)
        state = credits.status(db, user.id)
        assert state["free"]["limit"] == 2
        assert state["free"]["remaining"] == 2
        assert state["free"]["period_key"] == current_period_key()

    def test_free_credits_do_not_roll_over(self, db):
        user = make_user(db)
        credits.reserve(db, user.id, 2, "free-1", "scheme", ["A", "B"])
        assert credits.status(db, user.id)["free"]["remaining"] == 0
        previous = credits.status(db, user.id)["free"]["period_key"]
        assert get_units_used(db, user.id, previous) == 2
        # A different (earlier) month has its own zero usage row.
        assert get_units_used(db, user.id, "2000-01") == 0

    def test_third_free_plan_is_refused(self, db):
        user = make_user(db)
        assert credits.reserve(db, user.id, 2, "free-2", "s", ["A", "B"]).allowed
        denied = credits.reserve(db, user.id, 1, "free-3", "s", ["C"])
        assert denied.allowed is False
        assert denied.reason == "insufficient_credits"
        assert get_units_used(db, user.id) == 2


class TestPaidCredits:
    def test_flexible_twenty_never_expire(self, db):
        user = make_user(db)
        plan = _seed_plan(db, catalogue.FLEXIBLE_CREDIT_PACK)
        start = datetime.utcnow() - timedelta(days=5000)
        bal = credits.grant_package(db, user.id, plan, "flex-ref", start)
        assert bal.credits_remaining == 20
        assert bal.expires_at is None
        assert credits.status(db, user.id)["purchased"] == 20

    @pytest.mark.parametrize("package,days", [
        (catalogue.TEACHER_MONTHLY, 30),
        (catalogue.TEACHER_TERM_PASS, 120),
        (catalogue.ACADEMIC_YEAR_PASS, 365),
    ])
    def test_timed_packages_expire_from_activation(self, db, package, days):
        user = make_user(db)
        plan = _seed_plan(db, package)
        start = datetime.utcnow()
        bal = credits.grant_package(db, user.id, plan, f"ref-{package.slug}", start)
        assert bal.credits_remaining == package.credits
        assert bal.expires_at == start + timedelta(days=days)
        assert credits.status(db, user.id)["package"] == package.credits

    def test_expired_package_credits_do_not_grant(self, db):
        user = make_user(db)
        plan = _seed_plan(db, catalogue.TEACHER_MONTHLY)
        credits.grant_package(
            db, user.id, plan, "old", datetime.utcnow() - timedelta(days=31))
        assert credits.status(db, user.id)["package"] == 0

    def test_package_expiry_does_not_consume_flexible_credits(self, db):
        user = make_user(db)
        flex = _seed_plan(db, catalogue.FLEXIBLE_CREDIT_PACK)
        monthly = _seed_plan(db, catalogue.TEACHER_MONTHLY)
        credits.grant_package(db, user.id, flex, "flex")
        credits.grant_package(
            db, user.id, monthly, "monthly", datetime.utcnow() - timedelta(days=31))
        state = credits.status(db, user.id)
        assert state["purchased"] == 20
        assert state["package"] == 0

    def test_spending_order_free_then_soonest_package_then_referral_then_purchased(self, db):
        user = make_user(db)
        flex = _seed_plan(db, catalogue.FLEXIBLE_CREDIT_PACK)
        monthly = _seed_plan(db, catalogue.TEACHER_MONTHLY)
        credits.grant_package(db, user.id, flex, "flex")
        credits.grant_package(db, user.id, monthly, "monthly")
        credits.grant(db, user.id, source="referral", credits=3,
                      grant_key="referral:x", label="Referral bonus")
        # Free first.
        assert credits.reserve(db, user.id, 2, "r1", "s", ["A", "B"]).allowed
        assert credits.status(db, user.id)["free"]["remaining"] == 0
        # Then the package bucket.
        assert credits.reserve(db, user.id, 1, "r2", "s", ["C"]).allowed
        state = credits.status(db, user.id)
        assert state["package"] == 39
        assert state["referral"] == 3
        assert state["purchased"] == 20

    def test_duplicate_reservation_key_does_not_double_charge(self, db):
        user = make_user(db)
        plan = _seed_plan(db, catalogue.FLEXIBLE_CREDIT_PACK)
        credits.grant_package(db, user.id, plan, "flex")
        credits.reserve(db, user.id, 2, "same", "s", ["A", "B"])
        before = credits.status(db, user.id)["purchased"]
        again = credits.reserve(db, user.id, 2, "same", "s", ["A", "B"])
        assert again.allowed
        assert again.charged == 0
        assert credits.status(db, user.id)["purchased"] == before

    def test_release_refunds_the_paid_bucket(self, db):
        user = make_user(db)
        plan = _seed_plan(db, catalogue.FLEXIBLE_CREDIT_PACK)
        credits.grant_package(db, user.id, plan, "flex")
        res = credits.reserve(db, user.id, 3, "rel", "s", ["A", "B", "C"])
        # Two free credits pay for A and B; the pack pays for C.
        assert credits.status(db, user.id)["purchased"] == 19
        released = credits.release(db, res, ["C"])
        assert released == 1
        assert credits.status(db, user.id)["purchased"] == 20

    def test_commit_refunds_unproduced_codes_only(self, db):
        user = make_user(db)
        plan = _seed_plan(db, catalogue.FLEXIBLE_CREDIT_PACK)
        credits.grant_package(db, user.id, plan, "flex")
        res = credits.reserve(db, user.id, 3, "com", "s", ["A", "B", "C"])
        # A and B are free; C is the paid unit and is produced.
        credits.commit(db, res, ["A", "C"])
        assert credits.status(db, user.id)["purchased"] == 19
        # B (free) was not produced and is released.
        assert credits.status(db, user.id)["free"]["remaining"] == 1

    def test_ledger_is_append_only_and_records_source(self, db):
        user = make_user(db)
        plan = _seed_plan(db, catalogue.FLEXIBLE_CREDIT_PACK)
        credits.grant_package(db, user.id, plan, "flex")
        # Exhaust free credits first so the ledger records a paid consume.
        credits.reserve(db, user.id, 2, "led-free", "s", ["A", "B"])
        credits.reserve(db, user.id, 1, "led", "s", ["C"])
        entries = db.query(CreditLedgerDB).filter(
            CreditLedgerDB.user_id == user.id).all()
        assert {e.entry_type for e in entries} == {"grant", "consume"}
        assert all(e.credits != 0 for e in entries)
        assert db.query(CreditBalanceDB).filter(
            CreditBalanceDB.user_id == user.id).count() == 1


class TestMigrationSeeding:
    def test_v041_seeds_approved_catalogue_and_disables_legacy(self, db):
        from src.migrations import v041_commercial_credits_referrals as migration

        legacy = SubscriptionPlanDB(
            slug="teacher-annual", name="Teacher Annual", price_pesewas=48000,
            currency="GHS", interval="annual", duration_days=365, active=True,
        )
        db.add(legacy)
        db.commit()

        migration.engine = db.get_bind()
        migration.up(db)

        rows = {p.slug: p for p in db.query(SubscriptionPlanDB).all()}
        assert rows["flexible-credit-pack"].price_pesewas == 1200
        assert rows["flexible-credit-pack"].credit_allowance == 20
        assert rows["flexible-credit-pack"].active is True
        assert rows["teacher-monthly"].price_pesewas == 2200
        assert rows["teacher-monthly"].credit_allowance == 40
        assert rows["teacher-monthly"].credit_validity_days == 30
        assert rows["teacher-term-pass"].price_pesewas == 5000
        assert rows["teacher-term-pass"].credit_allowance == 160
        assert rows["academic-year-pass"].price_pesewas == 12000
        assert rows["academic-year-pass"].credit_allowance == 480
        assert rows["teacher-annual"].active is False


    def test_v041_preserves_an_existing_teacher_monthly_customer(self, db):
        from src.database import User, UserSubscriptionDB
        from src.migrations import v041_commercial_credits_referrals as migration

        old = SubscriptionPlanDB(
            slug="teacher-monthly", name="Teacher Monthly", price_pesewas=5000,
            currency="GHS", interval="monthly", duration_days=30, active=True)
        db.add(old)
        db.commit()
        user = make_user(db)
        db.add(UserSubscriptionDB(
            user_id=user.id, plan_id=old.id, status="active",
            paid_through=datetime.utcnow() + timedelta(days=10)))
        db.commit()

        migration.engine = db.get_bind()
        migration.up(db)

        legacy = db.query(SubscriptionPlanDB).filter_by(
            slug="teacher-monthly-legacy").one()
        assert legacy.id == old.id
        assert legacy.price_pesewas == 5000
        assert legacy.active is False
        new = db.query(SubscriptionPlanDB).filter_by(slug="teacher-monthly").one()
        assert new.id != old.id
        assert new.price_pesewas == 2200
        sub = db.query(UserSubscriptionDB).filter_by(user_id=user.id).one()
        assert sub.plan_id == legacy.id


    def test_v042_updates_unreferenced_package_prices_in_place(self, db):
        from src.migrations import v042_package_price_update as migration

        term = SubscriptionPlanDB(
            slug="teacher-term-pass", name="Teacher Term Pass",
            price_pesewas=5900, currency="GHS", interval="one_time",
            duration_days=120, credit_allowance=160,
            credit_validity_days=120, active=True)
        year = SubscriptionPlanDB(
            slug="academic-year-pass", name="Academic Year Pass",
            price_pesewas=14900, currency="GHS", interval="one_time",
            duration_days=365, credit_allowance=480,
            credit_validity_days=365, active=True)
        db.add_all([term, year])
        db.commit()
        term_id, year_id = term.id, year.id

        migration.engine = db.get_bind()
        migration.up(db)

        db.expire_all()
        term = db.query(SubscriptionPlanDB).filter_by(slug="teacher-term-pass").one()
        year = db.query(SubscriptionPlanDB).filter_by(slug="academic-year-pass").one()
        assert term.id == term_id and term.price_pesewas == 5000
        assert term.credit_allowance == 160 and term.credit_validity_days == 120
        assert year.id == year_id and year.price_pesewas == 12000
        assert year.credit_allowance == 480 and year.credit_validity_days == 365

    def test_v042_preserves_historical_plan_ids_and_transaction_amounts(self, db):
        from src.database import (
            SubscriptionTransactionDB, UserLicenseDB, UserSubscriptionDB,
        )
        from src.migrations import v042_package_price_update as migration

        term = SubscriptionPlanDB(
            slug="teacher-term-pass", name="Teacher Term Pass",
            price_pesewas=5900, currency="GHS", interval="one_time",
            duration_days=120, credit_allowance=160,
            credit_validity_days=120, active=True)
        year = SubscriptionPlanDB(
            slug="academic-year-pass", name="Academic Year Pass",
            price_pesewas=14900, currency="GHS", interval="one_time",
            duration_days=365, credit_allowance=480,
            credit_validity_days=365, active=True)
        db.add_all([term, year])
        db.commit()
        user = make_user(db)
        tx = SubscriptionTransactionDB(
            reference="HIST-TERM-1", user_id=user.id, plan_id=term.id,
            amount_pesewas=5900, currency="GHS", status="success",
            environment="live", payment_method="bank_transfer")
        sub = UserSubscriptionDB(
            user_id=user.id, plan_id=year.id, status="active")
        db.add_all([tx, sub])
        db.commit()
        term_id, year_id, tx_id = term.id, year.id, tx.id

        migration.engine = db.get_bind()
        migration.up(db)

        db.expire_all()
        legacy_term = db.query(SubscriptionPlanDB).filter_by(
            slug="teacher-term-pass-legacy").one()
        legacy_year = db.query(SubscriptionPlanDB).filter_by(
            slug="academic-year-pass-legacy").one()
        assert legacy_term.id == term_id and legacy_term.price_pesewas == 5900
        assert legacy_year.id == year_id and legacy_year.price_pesewas == 14900
        assert legacy_term.active is False and legacy_year.active is False
        new_term = db.query(SubscriptionPlanDB).filter_by(slug="teacher-term-pass").one()
        new_year = db.query(SubscriptionPlanDB).filter_by(slug="academic-year-pass").one()
        assert new_term.price_pesewas == 5000
        assert new_term.credit_allowance == 160 and new_term.credit_validity_days == 120
        assert new_year.price_pesewas == 12000
        assert new_year.credit_allowance == 480 and new_year.credit_validity_days == 365
        assert new_term.id != term_id and new_year.id != year_id
        tx = db.query(SubscriptionTransactionDB).filter_by(id=tx_id).one()
        assert tx.amount_pesewas == 5900 and tx.plan_id == term_id
        sub = db.query(UserSubscriptionDB).filter_by(user_id=user.id).one()
        assert sub.plan_id == year_id
        # A second run is a no-op for the sellable rows.
        migration.up(db)
        assert db.query(SubscriptionPlanDB).filter_by(
            slug="teacher-term-pass").count() == 1
        assert db.query(SubscriptionPlanDB).filter_by(
            slug="academic-year-pass").count() == 1
