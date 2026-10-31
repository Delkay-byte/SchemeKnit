"""Authoritative per-teacher and global storage quota accounting.

The browser's file size and the upload request count are never authoritative.
The route passes the actual number of bytes it read to :func:`reserve`, which
atomically reserves both the teacher's quota and the global production-prefix
cap in shared database counters. A successful object write is committed only
after the scheme row is durable; failure releases the reservation.

The ledger is idempotent by object key and by optional idempotency key, so a
retried upload or a duplicated delete cannot double-count storage.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as _pg_insert
from sqlalchemy.dialects.sqlite import insert as _sqlite_insert
from sqlalchemy.orm import Session

from .config import get_settings
from .database import (
    SchemeDB, StorageCounterDB, StorageLedgerDB, generate_id,
)
from .logging_config import get_logger

logger = get_logger()

MIB = 1024 * 1024
GIB = 1024 * MIB


class StorageQuotaError(Exception):
    """Safe quota error translated to HTTP by the upload route."""

    def __init__(self, status_code: int, code: str, message: str,
                 details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass
class StorageReservation:
    id: str
    owner_id: str
    object_key: str
    size_bytes: int
    file_type: str
    state: str = "reserved"


def human_bytes(value: int) -> str:
    value = max(0, int(value or 0))
    if value >= GIB:
        return f"{value / GIB:.2f} GiB"
    if value >= MIB:
        return f"{value / MIB:.1f} MiB"
    if value >= 1024:
        return f"{value / 1024:.1f} KiB"
    return f"{value} B"


def limits() -> Dict[str, int]:
    s = get_settings()
    legacy_cap = int(getattr(s, "MAX_UPLOAD_SIZE_MB", 50) or 50) * MIB
    file_limit = min(
        int(getattr(s, "STORAGE_MAX_FILE_BYTES", 50 * MIB) or 50 * MIB),
        legacy_cap,
    )
    return {
        "user_quota_bytes": int(
            getattr(s, "STORAGE_USER_QUOTA_BYTES", 500 * MIB) or 500 * MIB),
        "global_quota_bytes": int(
            getattr(s, "STORAGE_GLOBAL_QUOTA_BYTES", 8 * GIB) or 8 * GIB),
        "max_file_bytes": file_limit,
    }


def _dialect(db: Session) -> str:
    bind = db.get_bind()
    return bind.dialect.name if bind is not None else "sqlite"


def _insert_ignore(db: Session, model, values: dict) -> None:
    if _dialect(db) == "postgresql":
        stmt = _pg_insert(model.__table__).values(**values).on_conflict_do_nothing()
    else:
        stmt = _sqlite_insert(model.__table__).values(**values).on_conflict_do_nothing()
    db.execute(stmt)


def _counter(db: Session, scope: str, key: str) -> StorageCounterDB:
    row = db.query(StorageCounterDB).filter(
        StorageCounterDB.scope == scope,
        StorageCounterDB.key == key,
    ).first()
    if row is None:
        _insert_ignore(db, StorageCounterDB, {
            "id": generate_id(), "scope": scope, "key": key,
            "committed_bytes": 0, "reserved_bytes": 0,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        })
        db.flush()
        row = db.query(StorageCounterDB).filter(
            StorageCounterDB.scope == scope,
            StorageCounterDB.key == key,
        ).first()
    return row


def _guarded_add(db: Session, row: StorageCounterDB, amount: int,
                 limit: int) -> bool:
    result = db.execute(
        text(
            "UPDATE storage_counters "
            "SET reserved_bytes = reserved_bytes + :amount, updated_at = :now "
            "WHERE id = :row_id "
            "AND committed_bytes + reserved_bytes + :amount <= :limit"
        ),
        {
            "amount": int(amount), "now": datetime.utcnow(),
            "row_id": row.id, "limit": int(limit),
        },
    )
    return (result.rowcount or 0) == 1


def _usage_error(owner_id: str, size_bytes: int, user_used: int,
                 user_quota: int, global_used: int,
                 global_quota: int) -> StorageQuotaError:
    if user_used + size_bytes > user_quota:
        details = {
            "used_bytes": user_used,
            "quota_bytes": user_quota,
            "remaining_bytes": max(user_quota - user_used, 0),
            "requested_bytes": size_bytes,
        }
        return StorageQuotaError(
            507, "storage_user_quota_exceeded",
            "Your storage is full. Delete a document you no longer need, or "
            "contact support if your storage display appears incorrect.",
            details,
        )
    return StorageQuotaError(
        507, "storage_global_quota_exceeded",
        "SchemeKnit storage is temporarily full. Please try again later, or "
        "contact support if this continues.",
        {
            "used_bytes": global_used,
            "quota_bytes": global_quota,
            "remaining_bytes": max(global_quota - global_used, 0),
            "requested_bytes": size_bytes,
        },
    )


def reserve(
    db: Session,
    owner_id: str,
    *,
    object_key: str,
    size_bytes: int,
    file_type: str = "",
    document_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> StorageReservation:
    """Atomically reserve teacher + global quota for one actual object size."""
    cfg = limits()
    size_bytes = int(size_bytes or 0)
    if size_bytes <= 0:
        raise StorageQuotaError(
            400, "storage_empty_file", "The uploaded file is empty.")
    if size_bytes > cfg["max_file_bytes"]:
        raise StorageQuotaError(
            413, "storage_file_too_large",
            f"This file is larger than the {human_bytes(cfg['max_file_bytes'])} "
            "limit. Reduce the file and try again.",
            {"max_file_bytes": cfg["max_file_bytes"],
             "requested_bytes": size_bytes},
        )

    if idempotency_key:
        existing = db.query(StorageLedgerDB).filter(
            StorageLedgerDB.idempotency_key == idempotency_key).first()
        if existing is not None:
            return StorageReservation(
                id=existing.id, owner_id=existing.owner_id,
                object_key=existing.object_key,
                size_bytes=int(existing.size_bytes or 0),
                file_type=existing.file_type or "", state=existing.state,
            )

    # Legacy objects already physically present are not in the counter yet;
    # the reconciliation command backfills them. New uploads remain strictly
    # bounded even before that one-off backfill.
    try:
        with db.begin_nested():
            user_row = _counter(db, "user", owner_id)
            user_used = int(user_row.committed_bytes or 0) + int(
                user_row.reserved_bytes or 0)
            if not _guarded_add(db, user_row, size_bytes,
                                cfg["user_quota_bytes"]):
                raise _usage_error(
                    owner_id, size_bytes, user_used, cfg["user_quota_bytes"],
                    0, cfg["global_quota_bytes"])

            global_row = _counter(db, "global", "production")
            global_used = int(global_row.committed_bytes or 0) + int(
                global_row.reserved_bytes or 0)
            if not _guarded_add(db, global_row, size_bytes,
                                cfg["global_quota_bytes"]):
                raise _usage_error(
                    owner_id, size_bytes, user_used, cfg["user_quota_bytes"],
                    global_used, cfg["global_quota_bytes"])

            ledger = StorageLedgerDB(
                id=generate_id(),
                owner_id=owner_id,
                object_key=object_key,
                document_id=document_id,
                size_bytes=size_bytes,
                file_type=file_type,
                state="reserved",
                idempotency_key=idempotency_key,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(ledger)
        db.commit()
    except StorageQuotaError:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.error("storage_reservation_failed", error=str(exc)[:200])
        raise StorageQuotaError(
            503, "storage_quota_unavailable",
            "Storage accounting is temporarily unavailable. Please try again.",
        ) from exc

    return StorageReservation(
        id=ledger.id, owner_id=owner_id, object_key=object_key,
        size_bytes=size_bytes, file_type=file_type, state="reserved",
    )


def commit(db: Session, reservation: StorageReservation,
           document_id: Optional[str] = None) -> bool:
    """Move a reserved object to committed. Idempotent."""
    row = db.query(StorageLedgerDB).filter(
        StorageLedgerDB.id == reservation.id).first()
    if row is None:
        return False
    if row.state == "committed":
        return True
    if row.state != "reserved":
        return False

    size = int(row.size_bytes or 0)
    try:
        with db.begin_nested():
            for scope, key in (("user", row.owner_id),
                               ("global", "production")):
                db.execute(
                    text(
                        "UPDATE storage_counters SET "
                        "reserved_bytes = CASE WHEN reserved_bytes >= :size "
                        "THEN reserved_bytes - :size ELSE 0 END, "
                        "committed_bytes = committed_bytes + :size, "
                        "updated_at = :now "
                        "WHERE scope = :scope AND key = :key"
                    ),
                    {
                        "size": size, "now": datetime.utcnow(),
                        "scope": scope, "key": key,
                    },
                )
            row.state = "committed"
            row.committed_at = datetime.utcnow()
            row.updated_at = datetime.utcnow()
            if document_id:
                row.document_id = document_id
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


def release(db: Session, reservation: StorageReservation) -> bool:
    """Release a reservation whose object was never accepted. Idempotent."""
    row = db.query(StorageLedgerDB).filter(
        StorageLedgerDB.id == reservation.id).first()
    if row is None or row.state != "reserved":
        return False
    size = int(row.size_bytes or 0)
    try:
        with db.begin_nested():
            for scope, key in (("user", row.owner_id),
                               ("global", "production")):
                db.execute(
                    text(
                        "UPDATE storage_counters SET "
                        "reserved_bytes = CASE WHEN reserved_bytes >= :size "
                        "THEN reserved_bytes - :size ELSE 0 END, "
                        "updated_at = :now "
                        "WHERE scope = :scope AND key = :key"
                    ),
                    {
                        "size": size, "now": datetime.utcnow(),
                        "scope": scope, "key": key,
                    },
                )
            row.state = "released"
            row.updated_at = datetime.utcnow()
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False


def attach_document(db: Session, object_key: str,
                    document_id: str) -> bool:
    """Link a committed ledger row to its scheme/document id (no commit)."""
    row = db.query(StorageLedgerDB).filter(
        StorageLedgerDB.object_key == object_key).first()
    if row is None:
        return False
    row.document_id = document_id
    row.updated_at = datetime.utcnow()
    return True


def release_object(db: Session, object_key: str) -> bool:
    """Release a committed object exactly once (used by document delete)."""
    if not object_key:
        return False
    row = db.query(StorageLedgerDB).filter(
        StorageLedgerDB.object_key == object_key).first()
    if row is None:
        # Legacy object with no ledger row: nothing was counted for it.
        return False
    if row.state == "deleted":
        return False
    if row.state == "released":
        row.state = "deleted"
        row.deleted_at = datetime.utcnow()
        db.commit()
        return True

    size = int(row.size_bytes or 0)
    try:
        with db.begin_nested():
            for scope, key in (("user", row.owner_id),
                               ("global", "production")):
                db.execute(
                    text(
                        "UPDATE storage_counters SET "
                        "committed_bytes = CASE WHEN committed_bytes >= :size "
                        "THEN committed_bytes - :size ELSE 0 END, "
                        "updated_at = :now "
                        "WHERE scope = :scope AND key = :key"
                    ),
                    {
                        "size": size, "now": datetime.utcnow(),
                        "scope": scope, "key": key,
                    },
                )
            row.state = "deleted"
            row.deleted_at = datetime.utcnow()
            row.updated_at = datetime.utcnow()
        db.commit()
        return True
    except Exception:
        db.rollback()
        logger.error("storage_release_failed", object_key=object_key[:120])
        return False


def usage(db: Session, owner_id: str) -> Dict[str, Any]:
    """Safe usage snapshot for one authenticated teacher."""
    cfg = limits()
    user_row = db.query(StorageCounterDB).filter(
        StorageCounterDB.scope == "user",
        StorageCounterDB.key == owner_id,
    ).first()
    global_row = db.query(StorageCounterDB).filter(
        StorageCounterDB.scope == "global",
        StorageCounterDB.key == "production",
    ).first()
    used = int(user_row.committed_bytes or 0) if user_row else 0
    reserved = int(user_row.reserved_bytes or 0) if user_row else 0
    total = used + reserved
    global_used = (
        int(global_row.committed_bytes or 0)
        + int(global_row.reserved_bytes or 0)
    ) if global_row else 0
    return {
        "used_bytes": used,
        "reserved_bytes": reserved,
        "total_bytes": total,
        "quota_bytes": cfg["user_quota_bytes"],
        "remaining_bytes": max(cfg["user_quota_bytes"] - total, 0),
        "max_file_bytes": cfg["max_file_bytes"],
        "used_human": human_bytes(total),
        "quota_human": human_bytes(cfg["user_quota_bytes"]),
        "remaining_human": human_bytes(
            max(cfg["user_quota_bytes"] - total, 0)),
        "max_file_human": human_bytes(cfg["max_file_bytes"]),
        "global_used_bytes": global_used,
        "global_quota_bytes": cfg["global_quota_bytes"],
        "global_remaining_bytes": max(
            cfg["global_quota_bytes"] - global_used, 0),
    }


def reconcile(
    db: Session,
    storage,
    *,
    prefix: str = "production/",
    dry_run: bool = True,
    delete_orphans: bool = False,
    min_orphan_age_hours: int = 24,
) -> Dict[str, Any]:
    """Compare the ledger with real objects. Never deletes valid documents.

    Safe defaults: report only. Deletion requires ``dry_run=False`` AND
    ``delete_orphans=True``, and an object is deleted only when it is older
    than ``min_orphan_age_hours`` AND no live scheme row references it.
    """
    listed = storage.list_objects(prefix)
    objects = {key: size for key, size, _modified in listed}
    modified_at = {key: modified for key, _size, modified in listed}
    committed = db.query(StorageLedgerDB).filter(
        StorageLedgerDB.state == "committed").all()
    ledger_keys = {row.object_key for row in committed}
    scheme_keys = {
        row.storage_filename for row in db.query(SchemeDB).filter(
            SchemeDB.storage_filename.isnot(None)).all()
        if row.storage_filename
    }

    missing_objects = sorted(
        key for key in ledger_keys if key not in objects)
    orphan_candidates = sorted(
        key for key in objects
        if key not in ledger_keys and key not in scheme_keys)

    # Backfill legacy scheme objects that predate the ledger. They are real,
    # referenced documents, so they are counted rather than deleted.
    legacy = sorted(
        key for key in scheme_keys
        if key.startswith(prefix) and key in objects
        and key not in ledger_keys
    )
    backfilled = 0
    for key in legacy:
        owner = db.query(SchemeDB).filter(
            SchemeDB.storage_filename == key).first()
        if owner is None:
            continue
        existing = db.query(StorageLedgerDB).filter(
            StorageLedgerDB.object_key == key).first()
        if existing is not None:
            continue
        size = int(objects.get(key) or 0)
        if size <= 0:
            continue
        if not dry_run:
            try:
                with db.begin_nested():
                    db.add(StorageLedgerDB(
                        id=generate_id(), owner_id=owner.owner_id,
                        object_key=key, document_id=owner.id,
                        size_bytes=size, file_type="legacy",
                        state="committed", created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                        committed_at=datetime.utcnow(),
                    ))
                    for scope, counter_key in (
                            ("user", owner.owner_id), ("global", "production")):
                        row = _counter(db, scope, counter_key)
                        row.committed_bytes = int(
                            row.committed_bytes or 0) + size
                db.commit()
            except Exception:
                db.rollback()
                continue
        backfilled += 1

    deleted = []
    skipped_young = []
    if delete_orphans and not dry_run:
        cutoff = datetime.utcnow() - timedelta(hours=min_orphan_age_hours)
        for key in orphan_candidates:
            modified = modified_at.get(key)
            live_ref = db.query(SchemeDB).filter(
                SchemeDB.storage_filename == key).count()
            if live_ref:
                continue
            if modified is not None and modified > cutoff:
                skipped_young.append(key)
                continue
            try:
                storage.delete(key)
                deleted.append(key)
            except Exception:
                logger.error("storage_orphan_delete_failed", key=key[:120])

    return {
        "prefix": prefix,
        "dry_run": dry_run,
        "object_count": len(objects),
        "object_bytes": sum(int(v) for v in objects.values()),
        "ledger_committed_count": len(committed),
        "missing_objects": missing_objects,
        "orphan_candidates": orphan_candidates,
        "legacy_backfilled": backfilled,
        "deleted_orphans": deleted,
        "skipped_young_orphans": skipped_young,
    }
