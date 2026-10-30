"""Referral attribution, reward and reversal tests."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import catalogue, credits, referrals  # noqa: E402
from src.database import (  # noqa: E402
    CreditBalanceDB, ReferralDB, SubscriptionPlanDB, SubscriptionTransactionDB,
)
from tests.conftest import make_user  # noqa: E402


def _plan(db):
    plan = SubscriptionPlanDB(
        slug="flexible-credit-pack", name="Flexible Credit Pack",
        price_pesewas=1200, currency="GHS", interval="one_time",
        duration_days=0, active=True, package_kind="flexible",
        credit_allowance=20, credit_validity_days=None,
        entitlements=catalogue.FLEXIBLE_CREDIT_PACK.entitlements(),
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def _tx(db, user, plan, reference="TX-1", status="pending"):
    tx = SubscriptionTransactionDB(
        reference=reference, user_id=user.id, plan_id=plan.id,
        amount_pesewas=1200, currency="GHS", status=status,
        environment="test", payment_method="mobile_money",
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


class TestAttribution:
    def test_unique_code_per_account(self, db):
        a = make_user(db, email="a@test.com")
        b = make_user(db, email="b@test.com")
        ca = referrals.ensure_code(db, a)
        cb = referrals.ensure_code(db, b)
        assert ca.code != cb.code
        assert referrals.ensure_code(db, a).code == ca.code

    def test_attribution_is_single_and_repeat_safe(self, db):
        referrer = make_user(db, email="ref@test.com")
        referred = make_user(db, email="new@test.com")
        code = referrals.ensure_code(db, referrer).code

        row = referrals.attribute(db, referred, code)
        assert row.referrer_id == referrer.id
        assert row.status == "registered"
        # A second call never changes the referrer.
        other = make_user(db, email="other@test.com")
        other_code = referrals.ensure_code(db, other).code
        again = referrals.attribute(db, referred, other_code)
        assert again.referrer_id == referrer.id

    def test_self_referral_rejected(self, db):
        user = make_user(db, email="self@test.com")
        code = referrals.ensure_code(db, user).code
        assert referrals.attribute(db, user, code) is None

    def test_unknown_code_ignored(self, db):
        user = make_user(db)
        assert referrals.attribute(db, user, "NOPE") is None

    def test_registration_alone_grants_no_reward(self, db):
        referrer = make_user(db, email="ref2@test.com")
        referred = make_user(db, email="new2@test.com")
        referrals.attribute(db, referred, referrals.ensure_code(db, referrer).code)
        assert credits.status(db, referrer.id)["referral"] == 0
        assert credits.status(db, referred.id)["referral"] == 0


class TestRewards:
    def test_pending_payment_grants_no_reward(self, db):
        referrer = make_user(db, email="ref3@test.com")
        referred = make_user(db, email="new3@test.com")
        plan = _plan(db)
        referrals.attribute(db, referred, referrals.ensure_code(db, referrer).code)
        tx = _tx(db, referred, plan, status="pending")
        referrals.qualify(db, referred, tx)
        assert credits.status(db, referrer.id)["referral"] == 0

    def test_first_successful_purchase_grants_five_and_three_once(self, db):
        referrer = make_user(db, email="ref4@test.com")
        referred = make_user(db, email="new4@test.com")
        plan = _plan(db)
        referrals.attribute(db, referred, referrals.ensure_code(db, referrer).code)
        tx = _tx(db, referred, plan, status="success")
        referrals.qualify(db, referred, tx)

        assert credits.status(db, referrer.id)["referral"] == 5
        assert credits.status(db, referred.id)["referral"] == 3
        row = db.query(ReferralDB).filter(
            ReferralDB.referred_id == referred.id).one()
        assert row.status == "rewarded"
        assert row.qualifying_reference == tx.reference
        assert row.referrer_credits == 5
        assert row.referred_credits == 3
        assert row.rewarded_at is not None

        # Duplicate webhook / repeated qualification pays nothing more.
        referrals.qualify(db, referred, tx)
        assert credits.status(db, referrer.id)["referral"] == 5
        assert credits.status(db, referred.id)["referral"] == 3

    def test_second_purchase_is_not_qualifying(self, db):
        referrer = make_user(db, email="ref5@test.com")
        referred = make_user(db, email="new5@test.com")
        plan = _plan(db)
        referrals.attribute(db, referred, referrals.ensure_code(db, referrer).code)
        _tx(db, referred, plan, reference="TX-OLD", status="success")
        tx2 = _tx(db, referred, plan, reference="TX-NEW", status="success")
        referrals.qualify(db, referred, tx2)
        assert credits.status(db, referrer.id)["referral"] == 0
        row = db.query(ReferralDB).filter(
            ReferralDB.referred_id == referred.id).one()
        assert row.status == "ineligible"

    def test_five_rewarded_referrals_per_academic_term(self, db):
        referrer = make_user(db, email="ref6@test.com")
        plan = _plan(db)
        code = referrals.ensure_code(db, referrer).code
        for i in range(6):
            referred = make_user(db, email=f"new6-{i}@test.com")
            referrals.attribute(db, referred, code)
            tx = _tx(db, referred, plan, reference=f"TX-6-{i}", status="success")
            referrals.qualify(db, referred, tx)
        assert credits.status(db, referrer.id)["referral"] == 25
        last = db.query(ReferralDB).filter(
            ReferralDB.referred_id == referred.id).one()
        assert last.status == "limit_reached"
        cfg = referrals.settings(db)
        cfg.term_limit = 6
        db.commit()
        # Raising the limit does not retroactively pay the refused referral.
        assert credits.status(db, referrer.id)["referral"] == 25

    def test_refunded_payment_reverses_unused_rewards_safely(self, db):
        referrer = make_user(db, email="ref7@test.com")
        referred = make_user(db, email="new7@test.com")
        plan = _plan(db)
        referrals.attribute(db, referred, referrals.ensure_code(db, referrer).code)
        tx = _tx(db, referred, plan, reference="TX-REV", status="success")
        credits.grant_package(db, referred.id, plan, tx.reference)
        referrals.qualify(db, referred, tx)

        # Spend some of the referred teacher's 3 reward credits (after free).
        credits.reserve(db, referred.id, 2, "free-drain", "s", ["A", "B"])
        credits.reserve(db, referred.id, 2, "spend-reward", "s", ["C", "D"])
        assert credits.status(db, referred.id)["referral"] == 1

        referrals.reverse_for_transaction(db, tx, "refunded")
        assert credits.status(db, referred.id)["referral"] == 0
        assert credits.status(db, referrer.id)["referral"] == 0
        for bal in db.query(CreditBalanceDB).all():
            assert bal.credits_remaining >= 0
        row = db.query(ReferralDB).filter(
            ReferralDB.referred_id == referred.id).one()
        assert row.status == "reversed"
        assert row.reversal_reason == "refunded"

    def test_history_and_balance_are_consistent(self, db):
        referrer = make_user(db, email="ref8@test.com")
        referred = make_user(db, email="new8@test.com")
        plan = _plan(db)
        referrals.attribute(db, referred, referrals.ensure_code(db, referrer).code)
        referrals.track_visit(db, referrals.ensure_code(db, referrer).code)
        tx = _tx(db, referred, plan, status="success")
        referrals.qualify(db, referred, tx)
        stats = referrals.stats(db, referrer)
        assert stats["invited"] == 1
        assert stats["registered"] == 1
        assert stats["qualifying"] == 1
        assert stats["credits_earned"] == 5
        assert stats["credits_balance"] == 5
        assert stats["history"][0]["status"] == "rewarded"
        assert "5 bonus credits" in stats["language"]
