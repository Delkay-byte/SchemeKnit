"""Legacy weekly-plan JSON importer (dry-run by default).

The hosted application no longer reads the JSON store. This script exists only
if a legacy file still contains real records; it validates ownership, reports
invalid/duplicate records and never deletes or rewrites the source file.

Usage (run from backend/, with DATABASE_URL set):
    python scripts/import_weekly_plans.py --file teachflow_data/weekly_plans.json
    python scripts/import_weekly_plans.py --file ... --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.database import SessionLocal, User, WeeklyPlanDB  # noqa: E402
from src.models import WeeklyClassPlan  # noqa: E402
from src.weekly_plan_store import create_row  # noqa: E402


def run(path: Path, apply: bool) -> int:
    store = json.loads(path.read_text(encoding="utf-8"))
    records = store.get("plans") or []
    summary = {
        "dry_run": not apply,
        "source": str(path),
        "source_records": len(records),
        "valid": 0,
        "invalid": 0,
        "already_present": 0,
        "imported": 0,
        "invalid_records": [],
    }
    db = SessionLocal()
    try:
        for index, record in enumerate(records):
            plan_id = str(record.get("id") or "")
            owner_id = str(record.get("owner_id") or "")
            problem = None
            plan = None
            if not plan_id or not owner_id:
                problem = "missing id or owner_id"
            elif not db.query(User).filter(User.id == owner_id).first():
                problem = "owner does not exist in this database"
            else:
                try:
                    plan = WeeklyClassPlan.model_validate(record.get("plan") or {})
                except Exception as exc:  # malformed legacy payload
                    problem = f"invalid plan document: {type(exc).__name__}"

            if problem:
                summary["invalid"] += 1
                summary["invalid_records"].append(
                    {"index": index, "id": plan_id, "reason": problem})
                continue

            summary["valid"] += 1
            existing = db.query(WeeklyPlanDB).filter(
                WeeklyPlanDB.id == plan_id).first()
            if existing:
                summary["already_present"] += 1
                continue
            if apply:
                create_row(
                    db, owner_id=owner_id, plan=plan,
                    school_id=record.get("school_id"),
                )
                summary["imported"] += 1

        print(json.dumps(summary, indent=2))
        return 0 if summary["invalid"] == 0 else 1
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--file", default="teachflow_data/weekly_plans.json",
        help="legacy JSON file (never modified)",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="write valid records; default is a read-only dry run",
    )
    args = parser.parse_args()
    raise SystemExit(run(Path(args.file), args.apply))
