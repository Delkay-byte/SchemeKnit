"""
Migration v017: AI lifetime usage idempotency ledger.

The Free Tier AI allowance is a LIFETIME count of successful generations held on
EntitlementDB (ai_credits / ai_credits_used). This table only records which
successful generation requests have already consumed an allowance so a duplicate
submission cannot double-consume. It is not a second quota system.
"""

from sqlalchemy import text, inspect as sa_inspect
from ..database import engine

MIGRATION_VERSION = "v017_ai_lifetime_usage"
MIGRATION_NAME = "AI lifetime usage idempotency ledger"


def up(db):
    inspector = sa_inspect(engine)
    if inspector.has_table("ai_usage_events"):
        return
    db.execute(text(
        """
        CREATE TABLE ai_usage_events (
            id VARCHAR PRIMARY KEY,
            user_id VARCHAR NOT NULL,
            request_id VARCHAR,
            consumed BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP,
            UNIQUE (user_id, request_id)
        )
        """
    ))
    db.execute(text(
        "CREATE INDEX ix_ai_usage_events_user ON ai_usage_events (user_id)"
    ))
    db.commit()


def down(db):
    """SQLite-friendly teardown."""
    db.execute(text("DROP TABLE IF EXISTS ai_usage_events"))
    db.commit()
