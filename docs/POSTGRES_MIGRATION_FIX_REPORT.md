# Postgres Migration Fix Report — Phase 16.6

**Date:** 2026-09-23
**Commit:** `28aa91e` — `fix: make Phase 16.6 boolean migration PostgreSQL-safe`

## A. Render failure

Render backend build succeeded, but the application exited with status 3 during
startup migrations:

```
psycopg.errors.DatatypeMismatch:
column "week_ending_derived" is of type boolean
but default expression is of type integer

ALTER TABLE weeks
ADD COLUMN week_ending_derived BOOLEAN NOT NULL DEFAULT 0
```

## B. Root cause

Migration `v021_week_ending_derived` issued `BOOLEAN NOT NULL DEFAULT 0`.
SQLite accepts an integer literal for a boolean default; PostgreSQL does not —
it requires a boolean expression (`FALSE`). The migration runner executes
`up()` **before** writing the `teachflow_migrations` record, so the failure
aborted startup before anything was recorded (no partial bookkeeping, no data
modified; the failed statement rolled back).

## C. V021 correction

```sql
ALTER TABLE weeks
ADD COLUMN week_ending_derived BOOLEAN NOT NULL DEFAULT FALSE
```

- Column remains `BOOLEAN NOT NULL` (not made nullable).
- Existing rows receive `FALSE` (derived dates are opt-in via the parser).
- `DEFAULT FALSE` is portable: PostgreSQL and SQLite (≥ 3.23) both accept it.
- The migration keeps its column-existence guard, so a retry after failure —
  or a record-without-column edge case — cannot double-add the column.

Retry safety: because `apply_migration()` records success only after `up()`
returns, production (where v021 failed) will simply re-run the corrected
migration on the next startup, then apply v022.

## D. V022 audit/result

`v022_lesson_week_ending` contained the same defect
(`week_ending_derived BOOLEAN NOT NULL DEFAULT 0`) and would have been the
next startup failure. Corrected to `DEFAULT FALSE`. Its `week_ending DATE`
column is PostgreSQL-safe. v022 does not depend on v021's column, but is
ordered after it by the runner's sorted-file ordering; with v021 fixed both
apply in sequence.

Full-migration audit for `BOOLEAN … DEFAULT 0/1`:

| Migration | Status |
|---|---|
| v003, v006, v016 | already `DEFAULT FALSE` |
| v017 | already `DEFAULT TRUE` |
| **v013** | 7× `BOOLEAN DEFAULT 0` → **fixed to `DEFAULT FALSE`** (guarded column-adds; already recorded in production, so no production re-run; protects fresh/SQLite/PG restores) |
| **v021** | **fixed** (production failure) |
| **v022** | **fixed** (latent, same phase) |

A static regression test now fails the suite if any migration reintroduces
`BOOLEAN … DEFAULT 0/1`.

## E. PostgreSQL test result

Added (no new dependencies; reuses repo's existing `teachflow-pg-accept`
Docker PostgreSQL 16 container and the `psycopg` v3 driver already in
`requirements.txt`):

- `backend/tests/test_postgres_migrations.py` — static audit (always runs) +
  live harness (runs when `POSTGRES_MIGRATION_TEST_URL` or
  `TEACHFLOW_TEST_DATABASE_URL` is a postgres URL; skips otherwise).
- `backend/tests/pg_migration_harness.py` — production-like scenario against
  real PostgreSQL in scratch DB `smk_mig_scratch`:

1. Builds current schema, seeds a week + lesson row, drops the three
   Phase 16.6 columns (pre-v021 shape).
2. Executes the **old** SQL → reproduces the exact Render
   `DatatypeMismatch` error (proves root cause).
3. Pre-records v001–v020 applied (mirrors production bookkeeping), runs the
   real `run_all_migrations()`.
4. Asserts: v021 + v022 applied; `weeks.week_ending_derived` is BOOLEAN;
   `column_default = false`; existing rows read `false`; `TRUE` stores and
   reads back; `lesson_plans.week_ending` is DATE, `week_ending_derived`
   BOOLEAN default false; second run is a no-op (idempotent).

**Result: 3 passed** (static ×2 + live PostgreSQL harness).

## F. SQLite regression result

Migration modules and corrected DDL run unchanged on SQLite. Local SQLite
startup path executed (`run_all_migrations` applied pending v021/v022 +
uvicorn FastAPI startup): `/api/health` **200**, `/api/service-status` **200**.
No dialect-specific branch was needed; `DEFAULT FALSE` is portable.

## G. Full test result

| Suite | Result |
|---|---|
| Backend pytest (with live PG harness enabled) | **1209 passed, 10 skipped, 0 failed** (baseline 1206 + 3 new) |
| Frontend `npx tsc --noEmit` | **PASS** |
| Frontend `npm run build` | **PASS** |
| Backend import/startup (SQLite) | **PASS** (health 200, service-status 200) |

Section A–E, Phase 16.6 Section F–T, and Phase 17 tests are included in the
full pytest run above (no failures, no skips added to existing tests).

## H. Render deployment result

- Pushed `28aa91e` to `origin/main`.
- `https://schemeknit-api.onrender.com/api/health` → **200**
  `{"status":"healthy","service":"SchemeKnit","version":"1.0.5"}`
- `https://schemeknit-api.onrender.com/api/service-status` → **200**
  `{"status":"healthy","maintenance":{"active":false},…}`
- Health polled 12+ consecutive times across ~3 minutes: **stable 200** —
  the exit-3 crash loop is not occurring; the backend process stays up.
- **Caveat (same as Phases 14–17):** `/api/health` does not expose the commit
  SHA, and this environment has no Render dashboard/API access, so the live
  build's exact SHA is *unverified*. Owner should confirm in the Render
  dashboard that a deploy of `28aa91e` completed and migrations v021/v022
  appear applied (or trigger a manual redeploy).

## I. Remaining concerns

1. **Deploy SHA not observable** — recommend exposing a short commit hash in
   `/api/health` (already noted as optional in prior phase reports).
2. **v013 DDL fixed retroactively** — production already recorded v013, so the
   change only protects other environments; no production re-application.
3. Local full-suite runs default to SQLite; the live PG harness runs only
   when `POSTGRES_MIGRATION_TEST_URL` is set (CI/acceptance should set it).
4. No destructive SQL, no data loss, no production reset performed.
