"""Durable webhook recovery, retry, and refund lifecycle tests."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import credits, paystack, webhook_sweeper  # noqa: E402
from src.database import (  # noqa: E402
    CreditBalanceDB, PaystackWebhookEventDB, SubscriptionPlanDB,
    SubscriptionTransactionDB, UserLicenseDB,
)
from tests.conftest import make_user  # noqa: E402


@pytest.fixture(autouse=True)
def _paystack_test_env(monkeypatch):
    monkeypatch.setenv("PAYSTACK_SECRET_KEY", "sk_test_sweeper")
    monkeypatch.setenv("NEXT_PUBLIC_PAYSTACK_PUBLIC_KEY", "pk_test_sweeper")
    monkeypatch.setenv("PAYSTACK_CURRENCY", "GHS")
    monkeypatch.setenv("PAYSTACK_MODE", "test")
    monkeypatch.setenv("PAYSTACK_ENABLED", "true")


def _record(db, event, data, *, status="received", received_at=None,
            attempts=0, next_retry_at=None):
    raw = json.dumps({"event": event, "data": data}).encode()
    row, fresh = paystack.record_webhook(db, event, data, raw)
    assert fresh
    row.status = status
    row.received_at = received_at or datetime.utcnow()
    row.attempts = attempts
    row.next_retry_at = next_retry_at
    db.commit()
    return row


def _plan(db):
    plan = SubscriptionPlanDB(
        slug="teacher-term-pass", name="Teacher Term Pass",
        price_pesewas=5000, currency="GHS", interval="one_time",
        duration_days=120, active=True, package_kind="timed",
        credit_allowance=160, credit_validity_days=120,
        entitlements={"generation_limit": 0, "credit_allowance": 160},
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def _purchase(db, reference="SWEEP-1"):
    user = make_user(db)
    plan = _plan(db)
    tx = SubscriptionTransactionDB(
        reference=reference, user_id=user.id, plan_id=plan.id,
        amount_pesewas=5000, currency="GHS", status="success",
        environment="test", payment_method="bank_transfer",
        channel="bank_transfer",
    )
    db.add(tx)
    db.commit()
    credits.grant_package(db, user.id, plan, reference)
    return user, plan, tx


def test_backoff_is_bounded_exponential():
    assert webhook_sweeper.backoff_seconds(1) == 30
    assert webhook_sweeper.backoff_seconds(2) == 60
    assert webhook_sweeper.backoff_seconds(3) == 120
    assert webhook_sweeper.backoff_seconds(12) == 3600


def test_stale_received_event_is_claimed_and_processed(db):
    data = {"reference": "BANK-1", "status": "failed"}
    row = _record(
        db, "bank.transfer.rejected", data,
        received_at=datetime.utcnow() - timedelta(minutes=10),
    )
    claimed = webhook_sweeper.claim_events(db, batch_size=5, worker_id="test")
    assert [r.id for r in claimed] == [row.id]
    db.refresh(row)
    assert row.status == "processing"
    assert row.attempts == 1
    assert row.lease_owner == "test"


def test_fresh_received_event_is_not_swept(db):
    _record(db, "bank.transfer.rejected", {"reference": "BANK-2"})
    assert webhook_sweeper.claim_events(db, batch_size=5) == []


def test_failed_event_ready_for_retry_is_claimed(db):
    row = _record(
        db, "bank.transfer.rejected", {"reference": "BANK-3"},
        status="failed",
        next_retry_at=datetime.utcnow() - timedelta(seconds=1),
        attempts=1,
    )
    claimed = webhook_sweeper.claim_events(db, batch_size=5)
    assert [r.id for r in claimed] == [row.id]


def test_failed_event_before_retry_time_is_skipped(db):
    _record(
        db, "bank.transfer.rejected", {"reference": "BANK-4"},
        status="failed",
        next_retry_at=datetime.utcnow() + timedelta(minutes=5),
        attempts=1,
    )
    assert webhook_sweeper.claim_events(db, batch_size=5) == []


def test_completed_and_ignored_events_are_skipped(db):
    _record(db, "bank.transfer.rejected", {"reference": "BANK-5"},
            status="processed")
    _record(db, "bank.transfer.rejected", {"reference": "BANK-6"},
            status="ignored")
    assert webhook_sweeper.claim_events(db, batch_size=5) == []


def test_expired_processing_lease_is_reclaimed(db):
    row = _record(
        db, "bank.transfer.rejected", {"reference": "BANK-7"},
        status="processing", attempts=1,
    )
    row.lease_owner = "dead-worker"
    row.lease_expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    claimed = webhook_sweeper.claim_events(db, batch_size=5, worker_id="alive")
    assert [r.id for r in claimed] == [row.id]
    db.refresh(row)
    assert row.lease_owner == "alive"


def test_max_attempts_marks_terminal_and_is_not_reclaimed(db):
    row = _record(
        db, "bank.transfer.rejected", {"reference": "BANK-8"},
        status="failed", attempts=8, next_retry_at=None,
    )
    assert webhook_sweeper.claim_events(db, batch_size=5, max_attempts=8) == []
    assert webhook_sweeper.process_event(db, row.id) == "exhausted"
    db.refresh(row)
    assert row.status == "exhausted"
    assert row.next_retry_at is None


def test_unknown_event_is_ignored_not_retried(db):
    row = _record(
        db, "transfer.success", {"reference": "OUT-1"},
        received_at=datetime.utcnow() - timedelta(minutes=10),
    )
    counts = webhook_sweeper.sweep_once(db, batch_size=5)
    assert counts["ignored"] == 1
    db.refresh(row)
    assert row.status == "ignored"
    assert webhook_sweeper.claim_events(db, batch_size=5) == []


def test_duplicate_delivery_is_not_reprocessed(db):
    data = {"reference": "BANK-9"}
    first = _record(
        db, "bank.transfer.rejected", data,
        received_at=datetime.utcnow() - timedelta(minutes=10),
    )
    raw = json.dumps({"event": "bank.transfer.rejected", "data": data}).encode()
    duplicate, fresh = paystack.record_webhook(
        db, "bank.transfer.rejected", data, raw)
    assert fresh is False and duplicate.id == first.id
    assert webhook_sweeper.process_event(db, first.id) == "processed"
    assert webhook_sweeper.claim_events(db, batch_size=5) == []


def test_refund_pending_processing_failed_do_not_reverse(db):
    user, _plan_row, _tx = _purchase(db, "SWEEP-REFUND-1")
    for i, event in enumerate(("refund.pending", "refund.processing",
                               "refund.failed")):
        _record(
            db, event,
            {"transaction_reference": "SWEEP-REFUND-1",
             "refund_reference": f"RFD-{i}", "status": event.split(".")[-1]},
            received_at=datetime.utcnow() - timedelta(minutes=10),
        )
    counts = webhook_sweeper.sweep_once(db, batch_size=10)
    assert counts["processed"] == 3
    assert credits.status(db, user.id)["package"] == 160


def test_refund_processed_reverses_once_and_is_duplicate_safe(db):
    user, _plan_row, _tx = _purchase(db, "SWEEP-REFUND-2")
    row = _record(
        db, "refund.processed",
        {"transaction_reference": "SWEEP-REFUND-2",
         "refund_reference": "RFD-2", "status": "processed"},
        received_at=datetime.utcnow() - timedelta(minutes=10),
    )
    assert webhook_sweeper.process_event(db, row.id) == "processed"
    assert credits.status(db, user.id)["package"] == 0
    tx = db.query(SubscriptionTransactionDB).filter_by(
        reference="SWEEP-REFUND-2").one()
    assert tx.status == "reversed"
    assert webhook_sweeper.process_event(db, row.id) == "processed"
    assert credits.status(db, user.id)["package"] == 0
    assert db.query(CreditBalanceDB).one().credits_remaining == 0


def test_charge_success_grants_once_through_sweeper(db, monkeypatch):
    user = make_user(db)
    plan = _plan(db)
    tx = SubscriptionTransactionDB(
        reference="SWEEP-PAY-1", user_id=user.id, plan_id=plan.id,
        amount_pesewas=5000, currency="GHS", status="pending",
        environment="test", payment_method="bank_transfer",
    )
    db.add(tx)
    db.commit()
    payload = {
        "status": "success", "amount": 5000, "currency": "GHS",
        "reference": "SWEEP-PAY-1", "id": 6001, "channel": "bank_transfer",
        "customer": {"email": user.email},
    }
    monkeypatch.setattr(paystack, "verify", lambda ref: dict(payload))
    row = _record(
        db, "charge.success",
        {"reference": "SWEEP-PAY-1", "id": 6001, "status": "success",
         "amount": 5000, "currency": "GHS",
         "customer": {"email": user.email}},
        received_at=datetime.utcnow() - timedelta(minutes=10),
    )
    assert webhook_sweeper.process_event(db, row.id) == "processed"
    assert credits.status(db, user.id)["package"] == 160
    assert db.query(UserLicenseDB).count() == 1
    # Replaying the same ledger row cannot grant again.
    assert webhook_sweeper.process_event(db, row.id) == "processed"
    assert credits.status(db, user.id)["package"] == 160
    assert db.query(UserLicenseDB).count() == 1
