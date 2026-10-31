"""Migration v047: AI provider spend accounting and budget counters.

Creates the shared provider-usage ledger, atomic spend/concurrency counters and
reservation table used by ``src/ai_spend.py``. Non-destructive: existing tables
and data are untouched.
"""
from sqlalchemy import inspect as sa_inspect, text

MIGRATION_VERSION = "v047_ai_provider_spend"
MIGRATION_NAME = "AI provider spend accounting and budget controls"


def _has(db, table: str) -> bool:
    return sa_inspect(db.get_bind()).has_table(table)


def up(db):
    if not _has(db, "ai_provider_usage"):
        db.execute(text(
            "CREATE TABLE ai_provider_usage ("
            "id VARCHAR PRIMARY KEY, "
            "attempt_id VARCHAR NOT NULL UNIQUE, "
            "reservation_id VARCHAR NULL, "
            "user_id VARCHAR NULL, "
            "request_id VARCHAR NULL, "
            "provider VARCHAR NOT NULL DEFAULT '', "
            "model VARCHAR NOT NULL DEFAULT '', "
            "input_tokens INTEGER NOT NULL DEFAULT 0, "
            "cached_input_tokens INTEGER NOT NULL DEFAULT 0, "
            "output_tokens INTEGER NOT NULL DEFAULT 0, "
            "total_tokens INTEGER NOT NULL DEFAULT 0, "
            "usage_source VARCHAR NOT NULL DEFAULT 'actual', "
            "pricing_version VARCHAR NOT NULL DEFAULT '', "
            "cost_micros BIGINT NOT NULL DEFAULT 0, "
            "cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0, "
            "outcome VARCHAR NOT NULL DEFAULT 'success', "
            "created_at TIMESTAMP NOT NULL)"
        ))
        db.execute(text(
            "CREATE INDEX ix_ai_provider_usage_user "
            "ON ai_provider_usage (user_id)"
        ))
        db.execute(text(
            "CREATE INDEX ix_ai_provider_usage_request "
            "ON ai_provider_usage (request_id)"
        ))
        db.execute(text(
            "CREATE INDEX ix_ai_provider_usage_created "
            "ON ai_provider_usage (created_at)"
        ))

    if not _has(db, "ai_spend_counters"):
        db.execute(text(
            "CREATE TABLE ai_spend_counters ("
            "id VARCHAR PRIMARY KEY, "
            "scope VARCHAR NOT NULL, "
            "period_key VARCHAR NOT NULL DEFAULT '', "
            "provider VARCHAR NOT NULL DEFAULT '', "
            "reserved_micros BIGINT NOT NULL DEFAULT 0, "
            "spent_micros BIGINT NOT NULL DEFAULT 0, "
            "active_requests INTEGER NOT NULL DEFAULT 0, "
            "expires_at TIMESTAMP NULL, "
            "warning_sent BOOLEAN NOT NULL DEFAULT FALSE, "
            "created_at TIMESTAMP NOT NULL, "
            "updated_at TIMESTAMP NOT NULL, "
            "CONSTRAINT uq_ai_spend_counter_scope "
            "UNIQUE (scope, period_key, provider))"
        ))

    if not _has(db, "ai_spend_reservations"):
        db.execute(text(
            "CREATE TABLE ai_spend_reservations ("
            "id VARCHAR PRIMARY KEY, "
            "attempt_id VARCHAR NOT NULL UNIQUE, "
            "user_id VARCHAR NULL, "
            "request_id VARCHAR NULL, "
            "provider VARCHAR NOT NULL DEFAULT '', "
            "model VARCHAR NOT NULL DEFAULT '', "
            "estimated_micros BIGINT NOT NULL DEFAULT 0, "
            "settled_micros BIGINT NOT NULL DEFAULT 0, "
            "status VARCHAR NOT NULL DEFAULT 'held', "
            "scopes JSON NULL, "
            "created_at TIMESTAMP NOT NULL, "
            "updated_at TIMESTAMP NOT NULL)"
        ))
        db.execute(text(
            "CREATE INDEX ix_ai_spend_reservations_status "
            "ON ai_spend_reservations (status)"
        ))
    db.commit()


def down(db):
    for table in (
        "ai_spend_reservations", "ai_spend_counters", "ai_provider_usage",
    ):
        if _has(db, table):
            db.execute(text(f"DROP TABLE {table}"))
    db.commit()
