"""Durable Paystack webhook recovery.

The HTTP webhook endpoint persists the verified event before acknowledging it.
Processing happens in a background task; this module provides the same
idempotent processing path for a bounded one-shot recovery command that a
scheduler can invoke after a worker crash or restart.

Eligible rows are claimed with PostgreSQL ``FOR UPDATE SKIP LOCKED`` and a
short lease. Two workers cannot claim the same row. A crashed worker's lease
expires and the row becomes eligible again. Completed, ignored and exhausted
rows are never retried.
"""

from __future__ import annotations

import argparse
import os
import socket
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from . import paystack
from .database import PaystackWebhookEventDB, SessionLocal
from .logging_config import log_error, log_event

#: Events this application can safely replay. Outgoing-transfer and unknown
#: events are marked ignored rather than retried.
RECOVERABLE_EVENTS = frozenset({
    "charge.success",
    "bank.transfer.rejected",
    "refund.pending",
    "refund.processing",
    "refund.needs-attention",
    "refund.failed",
    "refund.processed",
    # Historical subscription/card events remain processable for old records.
    "subscription.create",
    "subscription.not_renew",
    "subscription.disable",
    "subscription.expiring_cards",
    "invoice.create",
    "invoice.update",
    "invoice.payment_failed",
})

DEFAULT_BATCH_SIZE = 20
DEFAULT_MAX_BATCHES = 5
DEFAULT_MAX_ATTEMPTS = 8
DEFAULT_LEASE_SECONDS = 120
STALE_RECEIVED_SECONDS = 300
BASE_BACKOFF_SECONDS = 30
MAX_BACKOFF_SECONDS = 3600


def backoff_seconds(attempts: int) -> int:
    """Bounded exponential backoff: 30s, 60s, 120s … up to 1h."""
    attempts = max(int(attempts or 1), 1)
    return min(BASE_BACKOFF_SECONDS * (2 ** min(attempts - 1, 10)),
               MAX_BACKOFF_SECONDS)


def sanitize_error(exc: Exception) -> str:
    """A safe error summary: no URLs, payloads, tokens or customer data."""
    return f"{type(exc).__name__}: webhook processing failed"


def _worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def _eligible(now: datetime, max_attempts: int):
    stale_before = now - timedelta(seconds=STALE_RECEIVED_SECONDS)
    return or_(
        and_(
            PaystackWebhookEventDB.status == "received",
            PaystackWebhookEventDB.received_at < stale_before,
            or_(
                PaystackWebhookEventDB.lease_expires_at.is_(None),
                PaystackWebhookEventDB.lease_expires_at < now,
            ),
        ),
        and_(
            PaystackWebhookEventDB.status == "failed",
            PaystackWebhookEventDB.attempts < max_attempts,
            or_(
                PaystackWebhookEventDB.next_retry_at.is_(None),
                PaystackWebhookEventDB.next_retry_at <= now,
            ),
        ),
        and_(
            PaystackWebhookEventDB.status == "processing",
            PaystackWebhookEventDB.lease_expires_at.isnot(None),
            PaystackWebhookEventDB.lease_expires_at < now,
            PaystackWebhookEventDB.attempts < max_attempts,
        ),
    )


def claim_events(
    db: Session,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    worker_id: Optional[str] = None,
    now: Optional[datetime] = None,
) -> list[PaystackWebhookEventDB]:
    """Atomically lease up to ``batch_size`` eligible rows."""
    now = now or datetime.utcnow()
    worker = worker_id or _worker_id()
    query = (
        db.query(PaystackWebhookEventDB)
        .filter(_eligible(now, max_attempts))
        .order_by(PaystackWebhookEventDB.received_at,
                  PaystackWebhookEventDB.id)
        .limit(max(1, int(batch_size)))
    )
    dialect = db.get_bind().dialect.name if db.get_bind() is not None else "sqlite"
    if dialect == "postgresql":
        query = query.with_for_update(skip_locked=True)
    rows = query.all()
    for row in rows:
        row.status = "processing"
        row.lease_owner = worker
        row.lease_expires_at = now + timedelta(seconds=lease_seconds)
        row.last_attempt_at = now
        row.attempts = int(row.attempts or 0) + 1
        row.last_error = ""
    if rows:
        db.commit()
    return rows


def process_event(
    db: Session,
    event_id: str,
    *,
    worker_id: Optional[str] = None,
    fallback_data: Optional[dict] = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    now: Optional[datetime] = None,
) -> str:
    """Process one event idempotently; return the terminal row status."""
    now = now or datetime.utcnow()
    row = db.query(PaystackWebhookEventDB).filter(
        PaystackWebhookEventDB.id == event_id).first()
    if row is None:
        return "missing"
    if row.status in ("processed", "ignored", "exhausted"):
        return row.status

    if row.status == "failed" and int(row.attempts or 0) >= max_attempts:
        row.status = "exhausted"
        row.next_retry_at = None
        row.lease_owner = ""
        row.lease_expires_at = None
        db.commit()
        return "exhausted"

    if row.status in ("received", "failed"):
        row.status = "processing"
        row.lease_owner = worker_id or _worker_id()
        row.lease_expires_at = now + timedelta(seconds=lease_seconds)
        row.last_attempt_at = now
        row.attempts = int(row.attempts or 0) + 1
        db.commit()

    event_type = str(row.event_type or "")
    payload = row.payload_json if isinstance(row.payload_json, dict) else None
    if payload is None and isinstance(fallback_data, dict):
        payload = fallback_data

    if event_type not in RECOVERABLE_EVENTS:
        row.status = "ignored"
        row.last_error = "unsupported_event"
        row.lease_owner = ""
        row.lease_expires_at = None
        row.next_retry_at = None
        db.commit()
        log_event("paystack_webhook_ignored", event_type=event_type,
                  reference=row.reference or "", event_id=row.id)
        return "ignored"

    if payload is None:
        row.status = "exhausted"
        row.last_error = "payload_unavailable"
        row.lease_owner = ""
        row.lease_expires_at = None
        row.next_retry_at = None
        db.commit()
        log_error("paystack_webhook_exhausted", error="payload unavailable",
                  event_type=event_type, reference=row.reference or "",
                  event_id=row.id)
        return "exhausted"

    try:
        paystack.handle_webhook(db, event_type, payload)
        row = db.query(PaystackWebhookEventDB).filter(
            PaystackWebhookEventDB.id == event_id).first()
        if row is None:
            return "missing"
        row.status = "processed"
        row.processed_at = datetime.utcnow()
        row.last_attempt_at = datetime.utcnow()
        row.last_error = ""
        row.next_retry_at = None
        row.lease_owner = ""
        row.lease_expires_at = None
        db.commit()
        log_event("paystack_webhook_processed", event_type=event_type,
                  reference=row.reference or "", event_id=row.id,
                  attempts=row.attempts)
        return "processed"
    except Exception as exc:
        db.rollback()
        row = db.query(PaystackWebhookEventDB).filter(
            PaystackWebhookEventDB.id == event_id).first()
        if row is None:
            return "missing"
        attempts = int(row.attempts or 0)
        row.last_attempt_at = datetime.utcnow()
        row.lease_owner = ""
        row.lease_expires_at = None
        row.last_error = sanitize_error(exc)[:300]
        if attempts >= max_attempts:
            row.status = "exhausted"
            row.next_retry_at = None
        else:
            row.status = "failed"
            row.next_retry_at = datetime.utcnow() + timedelta(
                seconds=backoff_seconds(attempts))
        db.commit()
        log_error("paystack_webhook_failed", error=row.last_error,
                  event_type=event_type, reference=row.reference or "",
                  event_id=row.id, attempts=attempts)
        return row.status


def sweep_once(
    db: Optional[Session] = None,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_batches: int = DEFAULT_MAX_BATCHES,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    worker_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Run one bounded recovery cycle and return only aggregate counts."""
    own_session = db is None
    session = db or SessionLocal()
    worker = worker_id or _worker_id()
    counts = {"claimed": 0, "processed": 0, "failed": 0,
              "ignored": 0, "exhausted": 0, "missing": 0}
    try:
        for _ in range(max(1, int(max_batches))):
            rows = claim_events(
                session, batch_size=batch_size, max_attempts=max_attempts,
                lease_seconds=lease_seconds, worker_id=worker,
            )
            if not rows:
                break
            for row in rows:
                counts["claimed"] += 1
                status = process_event(
                    session, row.id, worker_id=worker,
                    max_attempts=max_attempts, lease_seconds=lease_seconds,
                )
                if status in counts:
                    counts[status] += 1
        return counts
    finally:
        if own_session:
            session.close()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run one bounded Paystack webhook recovery cycle.")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--max-batches", type=int, default=DEFAULT_MAX_BATCHES)
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    parser.add_argument("--lease-seconds", type=int,
                        default=DEFAULT_LEASE_SECONDS)
    args = parser.parse_args(argv)
    counts = sweep_once(
        batch_size=max(1, args.batch_size),
        max_batches=max(1, args.max_batches),
        max_attempts=max(1, args.max_attempts),
        lease_seconds=max(10, args.lease_seconds),
    )
    print("webhook_sweeper " + " ".join(
        f"{key}={value}" for key, value in counts.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
