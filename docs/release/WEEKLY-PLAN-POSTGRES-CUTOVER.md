# Weekly-Plan PostgreSQL Cutover

Date: 2026-11-02
Branch: `hardening/post-release-integrity-ux-20261102`
Status: **implemented and tested locally/PostgreSQL; production migration NOT run**

## 1. Verified current data state

| Source | Verified result |
|---|---|
| Production PostgreSQL | `weekly_class_plans` absent; no weekly-plan table; zero records |
| Repository JSON file | 7 records, all acceptance fixtures (`accept-teacher-0001`, `wp-ux-fixture`) |
| Production JSON file | not inspectable through Render API; container filesystem is ephemeral |
| Real teacher/school weekly plans found | none |

Production `DATABASE_URL` was used once read-only to inspect table existence and
counts; the value was never printed, logged or written to disk.

## 2. Current storage mechanism (before this branch)

`backend/src/routers/weekly_plans.py` read/wrote
`backend/teachflow_data/weekly_plans.json` under a Python `threading.Lock`.
The lock only protected one process; Render restarts could lose the file.

## 3. New schema

Migration: `backend/src/migrations/v051_weekly_class_plans.py`

```sql
CREATE TABLE weekly_class_plans (
  id VARCHAR PRIMARY KEY,
  owner_id VARCHAR NOT NULL REFERENCES users(id),
  school_id VARCHAR REFERENCES schools(id),
  class_level VARCHAR NOT NULL DEFAULT '',
  week_number INTEGER NOT NULL DEFAULT 0,
  term VARCHAR NOT NULL DEFAULT '',
  academic_year VARCHAR NOT NULL DEFAULT '',
  template_id VARCHAR NOT NULL DEFAULT '',
  content JSONB NOT NULL,          -- JSON on SQLite
  revision INTEGER NOT NULL DEFAULT 1,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Indexes: owner, (owner, updated_at), school. The model is `WeeklyPlanDB`; the
repository is `backend/src/weekly_plan_store.py`.

## 4. Concurrency

`update_row()` performs a single conditional UPDATE:

```sql
UPDATE weekly_class_plans
SET content = :content, revision = revision + 1, updated_at = :now
WHERE id = :id AND owner_id = :owner AND revision = :expected;
```

- `rowcount == 1` → success, new revision returned.
- `rowcount == 0` → 409, no write.
- A second update after an overwrite pre-check still needs the latest revision.

Real PostgreSQL tests use two independent engines/sessions and concurrent
threads; exactly one writer succeeds. SQLite tests use the same predicate and
serialized writes. No JSON fallback exists in the routes.

## 5. Migration plan

1. Back up the production database using the existing provider backup process.
2. Record `SELECT to_regclass('public.weekly_class_plans')` and confirm absent.
3. Deploy code that understands both no-table and table-present states? The
   model creates the table on startup in this repository; the explicit migration
   records v051. Either path is additive.
4. Run the normal startup migration (`run_all_migrations`), which applies
   `v051_weekly_class_plans` if the table is not already present.
5. Confirm the table exists, is empty, and has the indexes.
6. Verify create/read/list/update through a disposable test teacher account in
   a non-production environment before customer use.

No destructive step and no data backfill are required for the verified
zero-record baseline.

## 6. Legacy JSON handling

- The hosted routes no longer read or write the JSON file.
- The repository JSON file is retained unchanged.
- If a production file is later retrieved and contains real records, run:

```bash
cd backend
python scripts/import_weekly_plans.py --file <retrieved.json>          # dry run
python scripts/import_weekly_plans.py --file <retrieved.json> --apply  # after review
```

The importer validates owner existence and plan shape, reports invalid records,
skips ids already present (idempotent) and never deletes or rewrites the source.
It does not import the known fixture owners because those users do not exist in
production.

Do not delete the file until:
- the database count matches the validated real-record count;
- create/update/read/export have been exercised against the database;
- one full release has run without JSON reads.

## 7. Rehearsal results

- PostgreSQL 16 disposable container (`postgres:16-alpine`).
- `test_postgres_migrations.py`: 6 passed.
- `test_weekly_plan_postgres.py`: 3 passed (two connections, stale overwrite,
  empty schema/ownership).
- SQLite: `test_optimistic_concurrency.py` weekly tests pass, including stale
  revision rejection and 503 database-failure handling.
- Importer: dry-run, apply, idempotent re-apply and invalid-owner tests pass.

## 8. Failure handling and rollback

- Database/transaction error → HTTP 503 `Weekly plans are temporarily
  unavailable`; no JSON fallback.
- Stale revision → HTTP 409 with the existing conflict UI.
- Rollback of application code is safe while the table is empty; the table is
  additive. Do not drop it in production without a verified backup.
- The legacy file is preserved as a fallback artifact only for manual recovery;
  the application does not read it.

## 9. Post-cutover verification

- Production `weekly_class_plans` exists and is empty at cutover.
- Authenticated create → read → update → export in staging.
- Two concurrent updates with the same revision: one 200, one 409.
- No JSON file creation in the hosted process working directory after writes.
- Cloud logs show no weekly-plan database errors.

## 10. Retirement criteria for JSON

Retire the file only after the database has been authoritative for one full
release, the import (if any) is reconciled, and no operational runbook depends
on it. Deletion requires separate approval; this branch does not delete it.
