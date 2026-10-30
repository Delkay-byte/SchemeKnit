"""Migration v042: approved Term Pass and Academic Year Pass prices.

Additive. Only ``teacher-term-pass`` (GH₵50 / 5,000 pesewas) and
``academic-year-pass`` (GH₵120 / 12,000 pesewas) change. Credits and validity
remain 160/120 days and 480/365 days.

Historical-data rule: a plan row that has ever been referenced by a
subscription, licence or transaction is preserved under a ``*-legacy`` slug and
deactivated for new purchases; a new catalogue row is created for checkout.
A row with no references (for example a fresh install) is updated in place.
No transaction, subscription, licence, entitlement or credit row is deleted or
rewritten.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session  # noqa: F401

from ..database import (
    SubscriptionPlanDB, SubscriptionTransactionDB, UserLicenseDB,
    UserSubscriptionDB, generate_id,
)

MIGRATION_VERSION = "v042_package_price_update"
MIGRATION_NAME = "Teacher Term Pass and Academic Year Pass price update"

_UPDATES = {
    "teacher-term-pass": {
        "name": "Teacher Term Pass",
        "price_pesewas": 5000,
        "credit_allowance": 160,
        "credit_validity_days": 120,
        "duration_days": 120,
        "display_order": 3,
        "description": "One hundred and sixty lesson-plan credits for a school term.",
        "features": [
            "160 indicator-level lesson plans",
            "Available for 120 days",
            "Full batch generation within your credits",
            "No automatic renewal",
        ],
        "entitlements": {
            "generation_limit": 0,
            "batch_generation": True,
            "zip_export": True,
            "pdf_export": True,
            "ai_enabled": True,
            "ai_credits": 0,
            "credit_allowance": 160,
            "credit_validity_days": 120,
            "package_kind": "timed",
        },
    },
    "academic-year-pass": {
        "name": "Academic Year Pass",
        "price_pesewas": 12000,
        "credit_allowance": 480,
        "credit_validity_days": 365,
        "duration_days": 365,
        "display_order": 4,
        "description": "Four hundred and eighty lesson-plan credits for a full academic year.",
        "features": [
            "480 indicator-level lesson plans",
            "Available for 365 days",
            "Full batch generation within your credits",
            "No automatic renewal",
        ],
        "entitlements": {
            "generation_limit": 0,
            "batch_generation": True,
            "zip_export": True,
            "pdf_export": True,
            "ai_enabled": True,
            "ai_credits": 0,
            "credit_allowance": 480,
            "credit_validity_days": 365,
            "package_kind": "timed",
        },
    },
}


def _referenced(db, plan_id: str) -> bool:
    for model in (UserSubscriptionDB, UserLicenseDB, SubscriptionTransactionDB):
        if db.query(model.id).filter(model.plan_id == plan_id).first() is not None:
            return True
    return False


def _apply(row: SubscriptionPlanDB, spec: dict) -> None:
    row.name = spec["name"]
    row.price_pesewas = spec["price_pesewas"]
    row.credit_allowance = spec["credit_allowance"]
    row.credit_validity_days = spec["credit_validity_days"]
    row.duration_days = spec["duration_days"]
    row.display_order = spec["display_order"]
    row.description = spec["description"]
    row.features = list(spec["features"])
    row.entitlements = dict(spec["entitlements"])
    row.currency = "GHS"
    row.interval = "one_time"
    row.package_kind = "timed"
    row.payment_terms = "One-time prepaid payment. No automatic renewal."
    row.active = True
    row.updated_at = datetime.utcnow()


def _create(db, slug: str, spec: dict) -> SubscriptionPlanDB:
    row = SubscriptionPlanDB(
        id=generate_id(), slug=slug,
        name=spec["name"], description=spec["description"],
        price_pesewas=spec["price_pesewas"], currency="GHS",
        interval="one_time", duration_days=spec["duration_days"],
        features=list(spec["features"]),
        entitlements=dict(spec["entitlements"]), active=True,
        package_kind="timed",
        credit_allowance=spec["credit_allowance"],
        credit_validity_days=spec["credit_validity_days"],
        display_order=spec["display_order"],
        payment_terms="One-time prepaid payment. No automatic renewal.",
    )
    db.add(row)
    db.flush()
    return row


def up(db):
    for slug, spec in _UPDATES.items():
        row = db.query(SubscriptionPlanDB).filter(
            SubscriptionPlanDB.slug == slug).first()
        legacy_slug = f"{slug}-legacy"
        legacy = db.query(SubscriptionPlanDB).filter(
            SubscriptionPlanDB.slug == legacy_slug).first()

        if row is None:
            if legacy is None:
                _create(db, slug, spec)
            else:
                # A prior partial run already preserved the old row; create the
                # new sellable row if it is missing.
                _create(db, slug, spec)
            continue

        if (row.price_pesewas == spec["price_pesewas"]
                and row.credit_allowance == spec["credit_allowance"]
                and row.credit_validity_days == spec["credit_validity_days"]):
            _apply(row, spec)  # idempotent: keep the row current and active
            continue

        if _referenced(db, row.id):
            if legacy is None:
                row.slug = legacy_slug
                row.name = f"{spec['name']} (Legacy)"
                row.active = False
                row.updated_at = datetime.utcnow()
                db.flush()
            else:
                # Preserve the referenced row but remove it from the sellable
                # slug; the legacy row already owns the legacy slug.
                row.active = False
                row.slug = f"{slug}-legacy-{row.id[:8]}"
                row.name = f"{spec['name']} (Legacy)"
                db.flush()
            _create(db, slug, spec)
        else:
            # No historical reference: safe to update the existing record.
            _apply(row, spec)
    db.commit()


def down(db):
    """Best-effort rollback: restore old prices for rows that still exist.

    Rows created by ``up`` may already have purchases by the time a rollback is
    requested, so they are deactivated rather than deleted, and preserved
    legacy rows are re-activated.
    """
    old_prices = {"teacher-term-pass": 5900, "academic-year-pass": 14900}
    for slug, old_price in old_prices.items():
        legacy = db.query(SubscriptionPlanDB).filter(
            SubscriptionPlanDB.slug == f"{slug}-legacy").first()
        if legacy is not None:
            legacy.active = True
            legacy.price_pesewas = old_price
        row = db.query(SubscriptionPlanDB).filter(
            SubscriptionPlanDB.slug == slug).first()
        if row is not None:
            row.active = False
            row.price_pesewas = old_price
    db.commit()
