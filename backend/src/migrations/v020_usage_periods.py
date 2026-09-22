"""
Migration v020: Calendar-period lesson-plan usage quota.

Replaces the old LIFETIME generation counter semantics with a calendar-period
usage model. Two tables are added:

  usage_periods
    Aggregate units used per (user, period_type, period_key). The active period
    is derived from the SERVER clock (period_key = "YYYY-MM" for a calendar
    month), so January usage never affects February and no cron job is needed
    to reset the allowance.

  usage_units
    One row per consumed lesson plan, uniquely keyed by
    (user, period, kind, key) where key = "<scheme_id>:<indicator_code>".
    This makes the quota idempotent: a duplicate request, or a regeneration of
    the same indicator in the same month, cannot double-consume.

The legacy ``entitlements.generations_used`` column is left in place (harmless)
but is no longer the enforcement source of truth.
"""

from sqlalchemy import text, inspect as sa_inspect
from ..database import engine

MIGRATION_VERSION = "v020_usage_periods"
MIGRATION_NAME = "Calendar-period lesson-plan usage quota"


def up(db):
    inspector = sa_inspect(engine)

    if not inspector.has_table("usage_periods"):
        db.execute(text(
            """
            CREATE TABLE usage_periods (
                id VARCHAR PRIMARY KEY,
                user_id VARCHAR NOT NULL REFERENCES users(id),
                period_type VARCHAR NOT NULL,
                period_key VARCHAR NOT NULL,
                units_used INTEGER DEFAULT 0,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                UNIQUE (user_id, period_type, period_key)
            )
            """
        ))
        db.execute(text(
            "CREATE INDEX ix_usage_periods_user ON usage_periods (user_id)"
        ))

    if not inspector.has_table("usage_units"):
        db.execute(text(
            """
            CREATE TABLE usage_units (
                id VARCHAR PRIMARY KEY,
                user_id VARCHAR NOT NULL REFERENCES users(id),
                period_type VARCHAR NOT NULL,
                period_key VARCHAR NOT NULL,
                unit_kind VARCHAR NOT NULL,
                unit_key VARCHAR NOT NULL,
                scheme_id VARCHAR,
                created_at TIMESTAMP,
                UNIQUE (user_id, period_type, period_key, unit_kind, unit_key)
            )
            """
        ))
        db.execute(text(
            "CREATE INDEX ix_usage_units_period "
            "ON usage_units (user_id, period_type, period_key)"
        ))

    db.commit()


def down(db):
    """SQLite-friendly teardown."""
    db.execute(text("DROP TABLE IF EXISTS usage_units"))
    db.execute(text("DROP TABLE IF EXISTS usage_periods"))
    db.commit()
