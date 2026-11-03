# Post-Release Hardening Acceptance Report

Date: 2026-11-03
Branch: `hardening/post-release-integrity-ux-20261102`
Starting `origin/main`: `da76859a52b9fd153d92e76267056d9e28e3a9b2`
Production code release before this branch: `be7d5c8d54327a58da856e941d05fa41b8d5a6d1`

Status: **implemented and tested locally/PostgreSQL/PostgreSQL 16 browser-E2E;
not migrated or deployed to production.**

## 1. Executive summary

Weekly plans now have an authoritative relational store with a database-enforced
revision check. The hosted JSON read/write path has been removed. Real
PostgreSQL tests with independent connections prove that two writers with the
same revision cannot both succeed. SQLite keeps the same functional CAS
behaviour for desktop/local use.

Production topology and data were inspected read-only: one Render web service,
one process, no background workers, no weekly-plan table, zero weekly-plan rows.
The repository legacy file contains acceptance fixtures only; the production
container file is not inspectable. A minimal, dry-run-first importer exists for
the contingent case where a real legacy file is later retrieved.

Teacher account activation/deactivation now has genuine browser coverage,
including optimistic feedback, rollback, retry, duplicate suppression and
authorization. Responsive/axe/keyboard acceptance covers the critical teacher
and school-admin screens. ESLint 9 flat config is active with a measured
warning baseline. Live Gemini/Groq tests are isolated behind `live_provider`.

## 2. Verified production topology

| Item | Result |
|---|---|
| Render service | `schemeknit-api` (`srv-damsbb1ntn7c73d7eg10`) |
| Instances | 1 |
| Plan | free |
| Start | `cd backend && python -m uvicorn src.main:app --host 0.0.0.0 --port $PORT` |
| Workers | Uvicorn default single worker; no `WEB_CONCURRENCY` |
| Background worker/cron | none registered for SchemeKnit |
| Filesystem | ephemeral; not shared/durable |
| Auto-deploy | no |

Full evidence: `docs/architecture/WEEKLY-PLAN-PERSISTENCE-TOPOLOGY.md`.

## 3. Verified data baseline

| Source | Result |
|---|---|
| Production PostgreSQL | `weekly_class_plans` absent; no weekly-plan table; **0 rows** |
| Other DB representation | none (`pg_tables` only had `weeks`) |
| Repository JSON file | **7 records**, all fixtures (`accept-teacher-0001` ×6, `wp-ux-fixture` ×1) |
| Production JSON file | inaccessible via Render API; ephemeral container path |
| Real teacher/school weekly plans found | none |
| Historical import required | **no verified records**; importer provided only for a future retrieved file |

## 4. PostgreSQL implementation

Schema migration: `backend/src/migrations/v051_weekly_class_plans.py`

Model: `WeeklyPlanDB` in `backend/src/database.py`.
Repository: `backend/src/weekly_plan_store.py`.

- `content` is JSONB on PostgreSQL, JSON on SQLite.
- `revision` is an integer starting at 1 and incremented once per successful
  conditional update.
- Ownership is a real `owner_id` FK; school scope and query columns are indexed.
- Update uses a database CAS:
  `UPDATE ... WHERE id = ? AND owner_id = ? AND revision = ?`.
- `rowcount = 0` ⇒ 409; no write.
- Missing `If-Match` resolves the current revision then still uses CAS.
- Read/list/get/export all use the database; no JSON fallback.
- Database errors return a controlled 503.

`docs/release/WEEKLY-PLAN-POSTGRES-CUTOVER.md` documents the migration,
rehearsal, cutover sequence, rollback and JSON retirement criteria.

## 5. PostgreSQL concurrency results

Real PostgreSQL 16 container, two independent engines/sessions, concurrent
threads:

```text
cd backend
POSTGRES_MIGRATION_TEST_URL=postgresql://... \
  python -m pytest -q tests/test_weekly_plan_postgres.py

4 passed
```

Covered:

- two writers with the same revision → exactly one succeeds, one 409;
- revision increments exactly once (to 2);
- the winner's document is complete, never mixed;
- stale writer cannot overwrite after commit;
- empty schema and owner isolation;
- v051 migration creates the table from a baseline without it.

SQLite tests:

```text
python -m pytest -q tests/test_optimistic_concurrency.py
9 passed (including a threaded two-writer CAS test)
```

## 6. JSON path removal

Search of `backend/src` shows no `_load_store`, `_save_store`, `_PLANS_FILE` or
`weekly_plans.json` read/write in application routes. Only the legacy file and
the importer reference it. Hosted writes/reads use `weekly_plan_store`.

Importer (dry-run by default, non-destructive, idempotent):
`backend/scripts/import_weekly_plans.py`. Tests: 2 passed.

## 7. Teacher activation browser E2E

`frontend/e2e/teacher-activation-admin.js` — **11 passed, 0 failed**.

Verified against the real admin UI and API:

- inactive → active optimistic update and server confirmation;
- active → inactive optimistic update and server confirmation;
- forced 500 restores the previous row state and leaves the server unchanged;
- friendly error + retry repeats the actual operation;
- duplicate click during a pending request produces one PUT;
- teacher cannot open the admin teacher UI or call the toggle endpoint (403);
- licence/payment actions remain outside this optimistic path.

## 8. Responsive acceptance

`frontend/e2e/responsive-accessibility.js` — **84 passed, 0 failed**.

Screens × 320/360/390/768/1024/1280/1440: dashboard, lesson editor, weekly
editor, new weekly plan, scheme review, settings, school overview, teacher
management, school settings, licence management. Also: config modal, draft
banner at 320, reduced-motion skeleton.

Matrix: `docs/qa/RESPONSIVE-ACCEPTANCE-MATRIX.md`.

No global overflow hiding was added. School-admin navigation was changed from
Radix Tabs (invalid `aria-controls`) to semantic links.

## 9. Accessibility acceptance

Tool: axe-core 4.14.0 + Playwright; keyboard suite **5 passed, 0 failed**.

Automated result on tested screens: **no critical or serious violations**.

Fixed:

- muted text 4.34:1 → darker `--muted-foreground`;
- brand text on tinted backgrounds 4.27–4.48:1 → darkened text brand;
- destructive text 3.76:1 → darker `--destructive`;
- invalid `aria-controls` on school-admin nav → semantic nav/links.

Keyboard: dialog focus entry, containment, Escape close, focus restoration,
not-found Tab target and visible focus all pass.

Report: `docs/qa/ACCESSIBILITY-ACCEPTANCE-REPORT.md`.
Not claimed: WCAG certification, real screen-reader walkthrough, authenticated
platform-admin console coverage.

## 10. ESLint

`frontend/eslint.config.mjs` uses Next.js 16 flat config + TypeScript.

```text
cd frontend && npm run lint
0 errors, 364 warnings (exit 0)
```

Warnings are existing `any` and React Hooks v7 compiler-oriented rules; they
remain visible, with a `--max-warnings=380` budget. CI runs lint. Documentation:
`docs/development/LINTING.md`.

## 11. Live provider reliability

Normal CI excludes `live_provider`; live tests remain available in the manual
`live-providers` workflow.

Evidence: focused live runs passed both providers (129 s / 174 s total), with
Gemini dominating latency. No provider source changed in this branch. The
failure is classified as external quota/latency, not application logic; auth
rejection now fails instead of silently skipping. Documentation:
`docs/testing/LIVE-PROVIDER-TESTING.md`.

## 12. Test summary

| Suite | Result |
|---|---|
| Frontend UX unit | 45 passed |
| Dashboard/delete/draft/error E2E | 16 passed |
| Editing/prefill/conflict E2E | 20 passed |
| Teacher activation browser E2E | 11 passed |
| Responsive + axe | 84 passed |
| Keyboard/focus | 5 passed |
| Backend concurrency + migration (SQLite/PG) | 9 + 4 passed |
| Importer | 2 passed |
| Backend deterministic full suite | **3,156 passed, 27 skipped, 2 deselected** (live_provider) in 37:55 |
| Live provider focused runs | both passed (2–3 minutes) |
| TypeScript | pass |
| Frontend lint | 0 errors |
| Production build | pass |

## 13. Exclusions and limitations

| Item | Status / impact |
|---|---|
| Production migration/deploy | **not run**; awaits separate approval |
| Production legacy JSON file | inaccessible; importer + dry-run documented |
| Platform-admin authenticated console | not browser-tested (MFA gate) |
| Screen-reader walkthrough | not performed |
| NSIS installer/offline upgrade | explicitly deferred |
| Desktop Electron runtime | prior acceptance retained; backend SQLite CAS covered |
| Full backend suite | 3,156 passed, 27 skipped, 2 live deselected |
| E2E screenshots | generated on failure only; not committed |
| Warning budget | 364 legacy warnings remain visible; errors fail |

## 14. Release recommendation

The code and database change are **ready for separate production approval**.
No known data-loss or security regression remains in the implemented path.

Before production:

1. Back up the production database.
2. Confirm `weekly_class_plans` absent and zero rows again.
3. Apply v051 through the normal startup migration.
4. If a real legacy JSON file is retrieved, run the importer dry-run first.
5. Run authenticated create/read/update/conflict smoke tests in a safe
   environment.
6. Keep the legacy file until the retirement criteria in the cutover document
   are met.
