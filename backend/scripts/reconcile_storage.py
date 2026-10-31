"""Bounded storage reconciliation for the production R2 prefix.

Default is READ-ONLY. It reports:
  * ledger objects missing from the bucket,
  * bucket objects with no ledger and no live scheme reference (orphans),
  * legacy scheme objects that need ledger backfill (counted, not deleted).

Deletion requires BOTH flags:
    python -m scripts.reconcile_storage --delete-orphans --no-dry-run

An object is only deleted when it is not referenced by any live scheme row and
is older than ``--min-age-hours`` (default 24). Valid teacher documents are
never deleted by a dry run.

Run from the backend directory with the same STORAGE_* environment as the
service. No secret is printed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database import SessionLocal  # noqa: E402
from src.logging_config import setup_logging  # noqa: E402
from src.storage import get_storage  # noqa: E402
from src.storage_quota import reconcile  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", default="production/")
    parser.add_argument("--delete-orphans", action="store_true")
    parser.add_argument(
        "--no-dry-run", action="store_true",
        help="Apply changes. Without this, nothing is written or deleted.")
    parser.add_argument("--min-age-hours", type=int, default=24)
    args = parser.parse_args()

    setup_logging()
    db = SessionLocal()
    try:
        report = reconcile(
            db,
            get_storage(),
            prefix=args.prefix,
            dry_run=not args.no_dry_run,
            delete_orphans=bool(args.delete_orphans),
            min_orphan_age_hours=max(1, int(args.min_age_hours)),
        )
    finally:
        db.close()
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
