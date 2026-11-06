"""Migration v054: independent purchased-entitlement lifecycle.

A flexible credit pack has no expiry. A time-limited package does. Previously
both shared the single per-user ``user_licenses`` row, so expiring a timed
subscription could mark an unrelated flexible purchase as unfulfilled.

``purchase_entitlements`` gives every verified transaction its own row keyed by
the immutable payment reference. Existing data is left untouched: legacy
transactions keep working through the compatibility path in
``paystack.fulfilment_state`` and the next reconciliation/repair creates the
matching row. No column is dropped and no credit balance is modified.
"""

from datetime import datetime, timedelta

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text

from ..database import (
    PurchaseEntitlementDB, SubscriptionPlanDB, SubscriptionTransactionDB,
    UserLicenseDB, engine,
)

MIGRATION_VERSION = "v054_purchase_entitlements"
MIGRATION_NAME = "Independent purchased-entitlement lifecycle"

def up(db):
    inspector = sa_inspect(engine)
    if not inspector.has_table("purchase_entitlements"):
        db.execute(text(
            """
            CREATE TABLE purchase_entitlements (
                id VARCHAR PRIMARY KEY,
                user_id VARCHAR NOT NULL,
                reference VARCHAR NOT NULL,
                plan_id VARCHAR,
                package_slug VARCHAR DEFAULT '',
                package_name VARCHAR DEFAULT '',
                kind VARCHAR NOT NULL DEFAULT 'timed',
                status VARCHAR NOT NULL DEFAULT 'active',
                starts_at TIMESTAMP,
                expires_at TIMESTAMP,
                licence_id VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        ))
    db.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_purchase_entitlements_reference "
        "ON purchase_entitlements (reference)"
    ))
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_purchase_entitlement_user_status "
        "ON purchase_entitlements (user_id, status)"
    ))

    # Backfill existing successful purchases. This preserves every historical
    # entitlement and gives legacy flexible packs an independent lifecycle
    # immediately, without waiting for a new webhook or reconciliation.
    existing = {row[0] for row in db.execute(text(
        "SELECT reference FROM purchase_entitlements"))}
    licences = {row[0]: row[1] for row in db.execute(text(
        "SELECT user_id, id FROM user_licenses"))}
    plans = {plan.id: plan for plan in db.query(SubscriptionPlanDB).all()}
    transactions = (db.query(SubscriptionTransactionDB)
                    .filter(SubscriptionTransactionDB.status == "success")
                    .all())
    for tx in transactions:
        if tx.reference in existing:
            continue
        plan = plans.get(tx.plan_id)
        details = tx.payment_details if isinstance(tx.payment_details, dict) else {}
        snapshot = details.get("package_snapshot") if isinstance(
            details.get("package_snapshot"), dict) else {}
        kind = (snapshot.get("package_kind")
                or (getattr(plan, "package_kind", "") if plan else "")
                or "timed")
        paid_at = tx.paid_at or tx.created_at or datetime.utcnow()
        expires_at = None
        if kind == "timed":
            days = int(snapshot.get("duration_days")
                       or (getattr(plan, "duration_days", 0) if plan else 0)
                       or 0)
            if days:
                expires_at = paid_at + timedelta(days=days)
        db.add(PurchaseEntitlementDB(
            id=f"pe:{tx.reference}",
            user_id=tx.user_id,
            reference=tx.reference,
            plan_id=tx.plan_id,
            package_slug=(snapshot.get("slug")
                          or (getattr(plan, "slug", "") if plan else "")),
            package_name=(snapshot.get("name")
                          or (getattr(plan, "name", "") if plan else "")),
            kind=kind,
            status=("expired" if expires_at and expires_at < datetime.utcnow()
                    else "active"),
            starts_at=paid_at,
            expires_at=expires_at,
            licence_id=licences.get(tx.user_id),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        ))
    db.commit()


def down(db):
    # Forward-only: dropping the separation would re-introduce the shared
    # expiry defect and could make a valid flexible purchase look unfulfilled.
    return
