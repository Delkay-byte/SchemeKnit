"""Migration v043: durable webhook recovery fields.

Additive only. Stores the verified event payload and the leasing/backoff
metadata required by the one-shot sweeper. Existing rows remain valid; rows
that predate the payload column are terminal and will not be replayed.
"""

from sqlalchemy import text, inspect as sa_inspect

from ..database import engine

MIGRATION_VERSION = "v043_webhook_recovery"
MIGRATION_NAME = "Durable webhook recovery leasing and payload ledger"

_COLUMNS = (
    ("payload_json", "JSON"),
    ("last_attempt_at", "TIMESTAMP"),
    ("next_retry_at", "TIMESTAMP"),
    ("lease_owner", "VARCHAR DEFAULT ''"),
    ("lease_expires_at", "TIMESTAMP"),
)


def up(db):
    if not sa_inspect(engine).has_table("paystack_webhook_events"):
        return
    cols = {c["name"] for c in sa_inspect(engine).get_columns(
        "paystack_webhook_events")}
    for name, ddl in _COLUMNS:
        if name not in cols:
            db.execute(text(
                f"ALTER TABLE paystack_webhook_events ADD COLUMN {name} {ddl}"))
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_paystack_webhook_retry "
        "ON paystack_webhook_events (status, next_retry_at)"))
    db.commit()


def down(db):
    # Additive columns are retained on rollback so no audit data is lost.
    pass
