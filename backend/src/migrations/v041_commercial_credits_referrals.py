"""Migration v041: approved commercial catalogue, credits and referrals.

Additive and idempotent. Existing subscription transactions, licences and
entitlements are never modified. The three old catalogue rows remain for
history; the two legacy packages are deactivated for new purchases. The
existing ``teacher-monthly`` row is repriced to the approved Teacher Monthly
package (new purchases only — historical transactions keep their amount).
"""

from __future__ import annotations

import json

from sqlalchemy import text, inspect as sa_inspect

from .. import catalogue
from ..database import Base, engine

MIGRATION_VERSION = "v041_commercial_credits_referrals"
MIGRATION_NAME = "Approved package catalogue, credit ledger and referrals"

_TABLES = (
    "credit_balances",
    "credit_ledger",
    "credit_reservations",
    "referral_codes",
    "referrals",
    "referral_visits",
    "referral_settings",
)

_PLAN_COLUMNS = (
    ("package_kind", "VARCHAR DEFAULT 'timed'"),
    ("credit_allowance", "INTEGER DEFAULT 0"),
    ("credit_validity_days", "INTEGER"),
    ("display_order", "INTEGER DEFAULT 0"),
    ("payment_terms", "VARCHAR DEFAULT 'One-time prepaid payment. No automatic renewal.'"),
)


def _columns(db, table: str) -> list[str]:
    return [c["name"] for c in sa_inspect(engine).get_columns(table)]


def _add_plan_columns(db) -> None:
    if not sa_inspect(engine).has_table("subscription_plans"):
        return
    cols = set(_columns(db, "subscription_plans"))
    for name, ddl in _PLAN_COLUMNS:
        if name not in cols:
            db.execute(text(f"ALTER TABLE subscription_plans ADD COLUMN {name} {ddl}"))
            db.commit()


def _create_tables(db) -> None:
    inspector = sa_inspect(engine)
    for name in _TABLES:
        if inspector.has_table(name):
            continue
        table = Base.metadata.tables.get(name)
        if table is not None:
            table.create(bind=engine, checkfirst=True)
    db.commit()


def _upsert_plan(db, row: dict) -> None:
    from ..database import generate_id

    existing = db.execute(
        text("SELECT id, price_pesewas FROM subscription_plans WHERE slug = :slug"),
        {"slug": row["slug"]},
    ).first()
    # Never silently reprice an existing customer's package. If the live
    # teacher-monthly row still carries the old GH₵50 price, preserve that row
    # (and every subscription/transaction referencing its id) under a legacy
    # slug, then create the approved GH₵22 package as a new row.
    if (existing and row["slug"] == "teacher-monthly"
            and int(existing[1]) != int(row["price_pesewas"])):
        legacy_slug = "teacher-monthly-legacy"
        clash = db.execute(
            text("SELECT 1 FROM subscription_plans WHERE slug = :slug"),
            {"slug": legacy_slug},
        ).first()
        if not clash:
            db.execute(
                text(
                    "UPDATE subscription_plans SET slug = :legacy, "
                    "name = 'Teacher Monthly (Legacy)', active = FALSE "
                    "WHERE id = :id"
                ),
                {"legacy": legacy_slug, "id": existing[0]},
            )
            existing = None
    values = {
        "slug": row["slug"],
        "name": row["name"],
        "desc": row["description"],
        "price": row["price_pesewas"],
        "interval": row["interval"],
        "days": row["duration_days"],
        "features": json.dumps(row["features"]),
        "entitlements": json.dumps(row["entitlements"]),
        "active": bool(row["active"]),
        "kind": row["package_kind"],
        "allowance": row["credit_allowance"],
        "validity": row["credit_validity_days"],
        "order": row["display_order"],
        "terms": row["payment_terms"],
    }
    if existing:
        db.execute(
            text(
                "UPDATE subscription_plans SET name=:name, description=:desc, "
                "price_pesewas=:price, interval=:interval, duration_days=:days, "
                "features=CAST(:features AS JSON), "
                "entitlements=CAST(:entitlements AS JSON), active=:active, "
                "package_kind=:kind, credit_allowance=:allowance, "
                "credit_validity_days=:validity, display_order=:order, "
                "payment_terms=:terms WHERE slug=:slug"
            ),
            values,
        )
        return
    values["id"] = generate_id()
    db.execute(
        text(
            "INSERT INTO subscription_plans "
            "(id, slug, name, description, price_pesewas, currency, interval, "
            "duration_days, features, entitlements, active, package_kind, "
            "credit_allowance, credit_validity_days, display_order, "
            "payment_terms, paystack_test_plan_code, paystack_live_plan_code) "
            "VALUES (:id, :slug, :name, :desc, :price, 'GHS', :interval, :days, "
            "CAST(:features AS JSON), CAST(:entitlements AS JSON), :active, "
            ":kind, :allowance, :validity, "
            ":order, :terms, '', '')"
        ),
        values,
    )


def up(db):
    _add_plan_columns(db)
    _create_tables(db)

    if sa_inspect(engine).has_table("subscription_transactions"):
        cols = set(_columns(db, "subscription_transactions"))
        if "payment_details" not in cols:
            db.execute(text(
                "ALTER TABLE subscription_transactions ADD COLUMN payment_details JSON"))
            db.commit()

    if sa_inspect(engine).has_table("subscription_plans"):
        for row in catalogue.seeds():
            _upsert_plan(db, row)
        # Legacy packages stay for existing customers/history but cannot be
        # purchased again.
        for slug in catalogue.LEGACY_SLUGS:
            db.execute(
                text("UPDATE subscription_plans SET active = FALSE WHERE slug = :slug"),
                {"slug": slug},
            )
        db.commit()


def down(db):
    # Additive only. Re-enable the historical catalogue and hide the new
    # packages; no rows or transactions are deleted.
    if not sa_inspect(engine).has_table("subscription_plans"):
        return
    for slug in catalogue.LEGACY_SLUGS:
        db.execute(
            text("UPDATE subscription_plans SET active = TRUE WHERE slug = :slug"),
            {"slug": slug},
        )
    for slug in (p.slug for p in catalogue.purchasable()):
        db.execute(
            text("UPDATE subscription_plans SET active = FALSE WHERE slug = :slug"),
            {"slug": slug},
        )
    db.commit()
