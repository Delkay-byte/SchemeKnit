"""Notification recovery must cover old gaps, not only the latest 20 rows."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src import email_service, purchase_notifications
from src.database import (
    Base, SubscriptionPlanDB, SubscriptionTransactionDB, generate_id,
)
from tests.conftest import make_user


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setenv("OWNER_ALERT_EMAIL", "owner@test.invalid")
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
    session.add(SubscriptionPlanDB(
        slug="flexible-credit-pack", name="Flexible Credit Pack",
        price_pesewas=1200, currency="GHS", interval="one_time",
        duration_days=0, entitlements={"credit_allowance": 20},
        active=True, package_kind="flexible", credit_allowance=20,
    ))
    session.commit()
    yield session
    session.close()
    engine.dispose()


class FakeEmail:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def send_subscription_notification(self, **kwargs):
        self.calls.append(("customer", kwargs.get("reference")))
        if self.fail:
            return email_service.EmailResult(success=False, message="provider down")
        return email_service.EmailResult(success=True, provider_id="em_customer")

    def send_owner_purchase(self, **kwargs):
        self.calls.append(("owner", kwargs.get("reference")))
        if self.fail:
            return email_service.EmailResult(success=False, message="provider down")
        return email_service.EmailResult(success=True, provider_id="em_owner")


def _successful_tx(db, user, index, days_ago, notifications):
    plan = db.query(SubscriptionPlanDB).one()
    tx = SubscriptionTransactionDB(
        id=generate_id(), reference=f"TFM-recovery-{index:02d}",
        user_id=user.id, plan_id=plan.id, environment="test",
        amount_pesewas=1200, currency="GHS", status="success",
        payment_method="mobile_money", channel="mobile_money",
        paid_at=datetime.utcnow() - timedelta(days=days_ago),
        created_at=datetime.utcnow() - timedelta(days=days_ago),
        payment_details={
            "package_snapshot": {
                "slug": plan.slug, "name": plan.name, "credits": 20,
                "package_kind": "flexible", "duration_days": 0,
            },
            "notifications": notifications,
        },
    )
    db.add(tx)
    return tx


def test_older_failure_outside_latest_20_is_recovered(db, monkeypatch):
    user = make_user(db)
    sent = {"customer": {"status": "sent"}, "owner": {"status": "sent"}}
    old_failed = {
        "customer": {
            "status": "failed", "attempts": 1,
            "attempted_at": (datetime.utcnow() - timedelta(days=30)).isoformat(),
            "error": "provider down",
        },
        "owner": {"status": "sent"},
    }
    # The oldest record is outside the 20 most recent successful purchases.
    for index in range(25):
        days = 60 - index
        _successful_tx(db, user, index, days,
                       old_failed if index == 0 else sent)
    db.commit()

    fake = FakeEmail()
    monkeypatch.setattr(email_service, "get_email", lambda: fake)
    retried = purchase_notifications.retry_pending(
        db, batch_size=4, max_batches=100)
    assert retried == 1
    assert fake.calls == [("customer", "TFM-recovery-00")]

    db.expire_all()
    tx = db.query(SubscriptionTransactionDB).filter_by(
        reference="TFM-recovery-00").one()
    notes = tx.payment_details["notifications"]["customer"]
    assert notes["status"] == "sent"
    assert notes["attempts"] == 2
    assert notes["provider_id"] == "em_customer"


def test_successfully_delivered_notifications_are_never_resent(db, monkeypatch):
    user = make_user(db)
    sent = {"customer": {"status": "sent"}, "owner": {"status": "sent"}}
    _successful_tx(db, user, 1, 5, sent)
    db.commit()
    fake = FakeEmail()
    monkeypatch.setattr(email_service, "get_email", lambda: fake)
    assert purchase_notifications.retry_pending(db) == 0
    assert fake.calls == []


def test_backoff_and_retry_limit_are_respected(db, monkeypatch):
    user = make_user(db)
    just_now = {
        "customer": {
            "status": "failed", "attempts": 1,
            "attempted_at": datetime.utcnow().isoformat(),
        },
        "owner": {"status": "sent"},
    }
    exhausted = {
        "customer": {
            "status": "failed",
            "attempts": purchase_notifications.MAX_NOTIFICATION_ATTEMPTS,
            "attempted_at": (datetime.utcnow() - timedelta(days=30)).isoformat(),
        },
        "owner": {"status": "sent"},
    }
    _successful_tx(db, user, 1, 5, just_now)
    _successful_tx(db, user, 2, 6, exhausted)
    db.commit()
    fake = FakeEmail()
    monkeypatch.setattr(email_service, "get_email", lambda: fake)
    assert purchase_notifications.retry_pending(db) == 0
    assert fake.calls == []


def test_failed_retry_is_recorded_and_retained_for_recovery(db, monkeypatch):
    user = make_user(db)
    due = {
        "customer": {
            "status": "failed", "attempts": 1,
            "attempted_at": (datetime.utcnow() - timedelta(days=2)).isoformat(),
        },
        "owner": {"status": "sent"},
    }
    _successful_tx(db, user, 1, 5, due)
    db.commit()
    fake = FakeEmail(fail=True)
    monkeypatch.setattr(email_service, "get_email", lambda: fake)
    assert purchase_notifications.retry_pending(db) == 1
    db.expire_all()
    tx = db.query(SubscriptionTransactionDB).filter_by(
        reference="TFM-recovery-01").one()
    notes = tx.payment_details["notifications"]["customer"]
    assert notes["status"] == "failed"
    assert notes["attempts"] == 2
    assert notes["error"] == "provider down"
    # Still retained and eligible later (attempts < limit).
    assert notes["status"] != "sent"


def test_repeated_worker_runs_are_idempotent(db, monkeypatch):
    user = make_user(db)
    due = {
        "customer": {
            "status": "failed", "attempts": 1,
            "attempted_at": (datetime.utcnow() - timedelta(days=2)).isoformat(),
        },
        "owner": {"status": "sent"},
    }
    _successful_tx(db, user, 1, 5, due)
    db.commit()
    fake = FakeEmail()
    monkeypatch.setattr(email_service, "get_email", lambda: fake)
    assert purchase_notifications.retry_pending(db) == 1
    assert purchase_notifications.retry_pending(db) == 0
    assert fake.calls == [("customer", "TFM-recovery-01")]
