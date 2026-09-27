"""
Migration v027: monthly AI generation ledger.

The Free Tier AI allowance becomes 5 AI generations per CALENDAR MONTH
(real-use remediation PART 16-19) instead of a lifetime count. The monthly
ledger mirrors usage_periods: one row per (user, "ai_calendar_month",
"YYYY-MM"), created lazily, with a guarded atomic increment in ai_quota.py.
A new calendar month reads a new row, so usage resets automatically — no cron
and no manual reset. Existing lifetime counters (entitlements.ai_credits_used)
remain in place for paid plans and are simply no longer the Free Tier gate.
"""

from sqlalchemy import text, inspect as sa_inspect
from ..database import engine

MIGRATION_VERSION = "v027_monthly_ai_quota"
MIGRATION_NAME = "Monthly AI generation quota ledger"


def up(db):
    """Create the ai_generation_periods table (additive; no data migration)."""
    inspector = sa_inspect(engine)
    if inspector.has_table("ai_generation_periods"):
        return
    db.execute(text(
        """
        CREATE TABLE ai_generation_periods (
            id VARCHAR PRIMARY KEY,
            user_id VARCHAR NOT NULL REFERENCES users (id),
            period_type VARCHAR NOT NULL,
            period_key VARCHAR NOT NULL,
            units_used INTEGER,
            created_at TIMESTAMP,
            updated_at TIMESTAMP,
            CONSTRAINT uq_ai_generation_period
                UNIQUE (user_id, period_type, period_key)
        )
        """
    ))
    db.execute(text(
        "CREATE INDEX ix_ai_generation_periods_user "
        "ON ai_generation_periods (user_id)"
    ))
    db.commit()


def down(db):
    """Drop the ledger (quota reverts to the lifetime counters)."""
    inspector = sa_inspect(engine)
    if inspector.has_table("ai_generation_periods"):
        db.execute(text("DROP TABLE ai_generation_periods"))
        db.commit()
