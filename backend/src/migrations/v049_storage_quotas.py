"""Migration v049: durable storage quota ledger and counters."""
from sqlalchemy import inspect as sa_inspect, text

MIGRATION_VERSION = "v049_storage_quotas"
MIGRATION_NAME = "Durable storage quota ledger and shared counters"


def _has(db, table: str) -> bool:
    return sa_inspect(db.get_bind()).has_table(table)


def up(db):
    if not _has(db, "storage_ledger"):
        db.execute(text(
            "CREATE TABLE storage_ledger ("
            "id VARCHAR PRIMARY KEY, "
            "owner_id VARCHAR NOT NULL, "
            "object_key VARCHAR NOT NULL UNIQUE, "
            "document_id VARCHAR NULL, "
            "size_bytes BIGINT NOT NULL DEFAULT 0, "
            "file_type VARCHAR NOT NULL DEFAULT '', "
            "state VARCHAR NOT NULL DEFAULT 'reserved', "
            "idempotency_key VARCHAR NULL UNIQUE, "
            "created_at TIMESTAMP NOT NULL, "
            "updated_at TIMESTAMP NOT NULL, "
            "committed_at TIMESTAMP NULL, "
            "deleted_at TIMESTAMP NULL)"
        ))
        db.execute(text(
            "CREATE INDEX ix_storage_ledger_owner "
            "ON storage_ledger (owner_id, state)"
        ))
        db.execute(text(
            "CREATE INDEX ix_storage_ledger_document "
            "ON storage_ledger (document_id)"
        ))

    if not _has(db, "storage_counters"):
        db.execute(text(
            "CREATE TABLE storage_counters ("
            "id VARCHAR PRIMARY KEY, "
            "scope VARCHAR NOT NULL, "
            "key VARCHAR NOT NULL DEFAULT '', "
            "committed_bytes BIGINT NOT NULL DEFAULT 0, "
            "reserved_bytes BIGINT NOT NULL DEFAULT 0, "
            "created_at TIMESTAMP NOT NULL, "
            "updated_at TIMESTAMP NOT NULL, "
            "CONSTRAINT uq_storage_counter_scope UNIQUE (scope, key))"
        ))
    db.commit()


def down(db):
    for table in ("storage_ledger", "storage_counters"):
        if _has(db, table):
            db.execute(text(f"DROP TABLE {table}"))
    db.commit()
