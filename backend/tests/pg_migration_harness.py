"""
PostgreSQL migration harness for Phase 16.6 (v021 + v022).

Run as a subprocess with DATABASE_URL pointing at a SCRATCH PostgreSQL
database (never production). Exercises the real migration runner against
PostgreSQL to prove:

  1. The pre-fix SQL (BOOLEAN ... DEFAULT 0) fails with DatatypeMismatch —
     reproducing the Render production error.
  2. The fixed migrations apply cleanly through run_all_migrations().
  3. week_ending_derived exists, is BOOLEAN, defaults to FALSE, existing
     rows read false, and TRUE can still be stored.
  4. v022's lesson_plans columns (DATE + BOOLEAN DEFAULT FALSE) apply.
  5. Re-running migrations is a no-op (idempotent / retry-safe).

Exit code 0 = all assertions passed. Prints a JSON summary on stdout.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path


def main() -> int:
    backend_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(backend_dir))

    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgres"):
        print(json.dumps({"ok": False, "error": "DATABASE_URL must be postgresql"}))
        return 2
    # Local environment ships psycopg v3 only; normalise bare postgresql://.
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
        os.environ["DATABASE_URL"] = url

    from sqlalchemy import Boolean, Date, text, inspect as sa_inspect

    from src.database import Base, engine, SessionLocal, generate_id
    from src.migration_runner import (
        MigrationRecord,
        ensure_migration_table,
        run_all_migrations,
    )

    summary = {"dialect": engine.dialect.name, "steps": []}
    if engine.dialect.name != "postgresql":
        print(json.dumps({"ok": False, "error": f"expected postgresql, got {engine.dialect.name}"}))
        return 2

    # ── 1. Baseline: current schema, then roll weeks/lesson_plans back to
    #       their pre-v021/v022 shape (what production looked like today). ──
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    with engine.begin() as conn:
        # Scratch-DB superuser: allow orphan seed rows without FK parents.
        conn.execute(text("SET session_replication_role = replica"))
        conn.execute(text(
            "INSERT INTO weeks (id, scheme_id, week_number, week_type, "
            "start_date, end_date, week_ending_derived) "
            "VALUES ('w1', 's1', 4, 'instruction', '2026-01-26', '2026-01-30', TRUE)"
        ))
        conn.execute(text(
            "INSERT INTO lesson_plans (id, job_id, owner_id, scheme_id, "
            "week_number, lesson_sequence, class_level, subject, "
            "week_ending, week_ending_derived) "
            "VALUES ('lp1', 'j1', 'u1', 's1', 4, 1, 'Basic 8', 'Science', "
            "'2026-01-30', FALSE)"
        ))
        conn.execute(text("ALTER TABLE weeks DROP COLUMN week_ending_derived"))
        conn.execute(text("ALTER TABLE lesson_plans DROP COLUMN week_ending"))
        conn.execute(text("ALTER TABLE lesson_plans DROP COLUMN week_ending_derived"))
    summary["steps"].append("pre_v021_schema_ready")

    # ── 2. Prove the old SQL reproduces the Render failure. ──
    old_sql_error = None
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE weeks ADD COLUMN week_ending_derived "
                "BOOLEAN NOT NULL DEFAULT 0"
            ))
        print(json.dumps({"ok": False, "error": "old SQL unexpectedly succeeded on PostgreSQL",
                          "summary": summary}))
        return 1
    except Exception as exc:  # noqa: BLE001 — harness asserts on message
        old_sql_error = str(exc)
    summary["old_sql_error"] = old_sql_error[:240]
    if "DatatypeMismatch" not in old_sql_error and \
       "default expression is of type integer" not in old_sql_error:
        print(json.dumps({"ok": False, "error": "old SQL failed with unexpected error",
                          "summary": summary}))
        return 1
    summary["steps"].append("old_sql_reproduced_render_failure")

    # ── 3. Simulate production bookkeeping: v001–v020 already applied. ──
    mig_dir = backend_dir / "src" / "migrations"
    stems = sorted(f.stem for f in mig_dir.glob("v*.py"))
    pre_applied = [s for s in stems if not (s.startswith("v021") or s.startswith("v022"))]
    ensure_migration_table()
    db = SessionLocal()
    try:
        for stem in pre_applied:
            db.add(MigrationRecord(
                id=generate_id(), version=stem, name=stem,
                applied_at=datetime.utcnow(),
            ))
        db.commit()
    finally:
        db.close()
    summary["pre_recorded"] = len(pre_applied)

    # ── 4. Run the real migration runner with the fixed SQL. ──
    results = run_all_migrations()
    applied = [v for v, _n, _s in results]
    summary["applied"] = applied
    if "v021_week_ending_derived" not in applied:
        summary["error"] = "v021 was not applied"
        print(json.dumps({"ok": False, "summary": summary}))
        return 1
    if "v022_lesson_week_ending" not in applied:
        summary["error"] = "v022 was not applied"
        print(json.dumps({"ok": False, "summary": summary}))
        return 1
    summary["steps"].append("v021_v022_applied")

    # ── 5. Column-level assertions. ──
    insp = sa_inspect(engine)
    week_cols = {c["name"]: c for c in insp.get_columns("weeks")}
    if "week_ending_derived" not in week_cols:
        summary["error"] = "weeks.week_ending_derived missing"
        print(json.dumps({"ok": False, "summary": summary}))
        return 1
    if not isinstance(week_cols["week_ending_derived"]["type"], Boolean):
        summary["error"] = (
            "weeks.week_ending_derived type is "
            f"{week_cols['week_ending_derived']['type']!r}, expected Boolean"
        )
        print(json.dumps({"ok": False, "summary": summary}))
        return 1

    lp_cols = {c["name"]: c for c in insp.get_columns("lesson_plans")}
    for name, expected in (("week_ending", Date), ("week_ending_derived", Boolean)):
        if name not in lp_cols or not isinstance(lp_cols[name]["type"], expected):
            summary["error"] = (
                f"lesson_plans.{name} missing or wrong type: "
                f"{lp_cols.get(name, {}).get('type')!r}"
            )
            print(json.dumps({"ok": False, "summary": summary}))
            return 1

    with engine.connect() as conn:
        week_default = conn.execute(text(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_name = 'weeks' AND column_name = 'week_ending_derived'"
        )).scalar()
        lp_default = conn.execute(text(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_name = 'lesson_plans' AND column_name = 'week_ending_derived'"
        )).scalar()
        existing_week = conn.execute(text(
            "SELECT week_ending_derived FROM weeks WHERE id = 'w1'"
        )).scalar()
        existing_lp = conn.execute(text(
            "SELECT week_ending_derived FROM lesson_plans WHERE id = 'lp1'"
        )).scalar()
        # Existing rows must be false (column did not exist pre-migration).
        if existing_week is not False or existing_lp is not False:
            summary["error"] = (
                f"existing rows not false: weeks={existing_week!r} "
                f"lesson_plans={existing_lp!r}"
            )
            print(json.dumps({"ok": False, "summary": summary}))
            return 1
        # TRUE must still be storable — field stays a real boolean.
    with engine.begin() as conn:
        conn.execute(text(
            "UPDATE weeks SET week_ending_derived = TRUE WHERE id = 'w1'"
        ))
        conn.execute(text(
            "UPDATE lesson_plans SET week_ending_derived = TRUE, "
            "week_ending = '2026-01-30' WHERE id = 'lp1'"
        ))
    with engine.connect() as conn:
        if conn.execute(text(
            "SELECT week_ending_derived FROM weeks WHERE id = 'w1'"
        )).scalar() is not True:
            summary["error"] = "could not store TRUE in weeks.week_ending_derived"
            print(json.dumps({"ok": False, "summary": summary}))
            return 1
        if conn.execute(text(
            "SELECT week_ending_derived FROM lesson_plans WHERE id = 'lp1'"
        )).scalar() is not True:
            summary["error"] = "could not store TRUE in lesson_plans.week_ending_derived"
            print(json.dumps({"ok": False, "summary": summary}))
            return 1

    summary["week_default"] = week_default
    summary["lesson_default"] = lp_default
    for label, default in (("weeks", week_default), ("lesson_plans", lp_default)):
        norm = (default or "").strip().lower().replace(" ", "")
        if norm not in ("false", "0::boolean"):
            summary["error"] = f"{label}.week_ending_derived default is {default!r}, expected false"
            print(json.dumps({"ok": False, "summary": summary}))
            return 1
    summary["steps"].append("column_assertions_passed")

    # ── 6. Idempotency: a second run must be a no-op. ──
    second = run_all_migrations()
    if second:
        summary["error"] = f"second run applied migrations again: {second}"
        print(json.dumps({"ok": False, "summary": summary}))
        return 1
    summary["steps"].append("idempotent_rerun")

    print(json.dumps({"ok": True, "summary": summary}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
