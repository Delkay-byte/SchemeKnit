# Production Operations

## Environments
DEVELOPMENT (SQLite, `DEBUG=true`, localhost) · TEST (in-memory/ephemeral) ·
ACCEPTANCE (isolated SQLite file or PostgreSQL) · PRODUCTION (PostgreSQL, `DEBUG=false`).
Configure via environment variables (see `backend/.env.example`); never commit `.env`.

## Startup
1. Set `DATABASE_URL`, `SECRET_KEY`, `JWT_SECRET_KEY`, `CORS_ORIGINS` (exact frontend origin).
2. Backend: `uvicorn src.main:app --host 0.0.0.0 --port 8000` from `backend/`.
   Startup runs `init_db()` + the full migration chain, then refuses to serve if
   production secrets are defaults (fail-fast, exit non-zero).
3. Frontend (web target): `NEXT_PUBLIC_API_URL=https://api.example.com`,
   `NEXT_PUBLIC_BUILD_TARGET=web`, `npm run build && npm run start`.
4. Verify `GET /api/health` (liveness) and `GET /api/ready` (DB reachable, 503 otherwise).

## Database migration
Automatic on boot (`run_all_migrations`, idempotent, recorded in `teachflow_migrations`).
PostgreSQL path: `DATABASE_URL=postgresql+psycopg://USER:PASS@HOST:5432/DB`
(requires `psycopg[binary]`, already in requirements). Migrations are dialect-portable
(inspector-based); verify on a staging copy first. SQLite→PostgreSQL data moves are
dump/load operations, not covered by the migration chain.

## Backup / restore
- SQLite: stop writes (or checkpoint), copy the `.db` file + `uploads/` + `exports/`;
  restore by replacing files. Nightly copies + 7-day retention is the baseline expectation.
- PostgreSQL: `pg_dump -Fc` nightly + WAL archiving per recovery objectives; restore with
  `pg_restore`; test restores quarterly. Uploaded/exported files live on disk (`UPLOAD_DIR`,
  `EXPORT_DIR`) and must be snapshotted alongside the database.
- Rollback: migrations are forward-only (`down()` is a no-op by SQLite convention);
  roll back by restoring the pre-release backup, never by partial downgrade.

## Logs / health / troubleshooting
- JSON logs (`LOG_LEVEL`); security/audit events in `platform_audit_logs` (server-side only).
- Health: `/api/health`; readiness: `/api/ready` (503 = not servable).
- Common: 401 → re-login (expired token); 403 → role/license boundary (do not retry blindly);
  429 → back off per `Retry-After`; 422 → fix the submitted payload; export 500 on PDF =
  converter gap (DOCX/XLSX/ZIP unaffected).

## Release process
1. Freeze web source; run full backend suite + `tsc --noEmit` + structural DOCX validation.
2. Complete browser acceptance on the acceptance database.
3. Align versions (backend `APP_VERSION`, frontend `package.json`, desktop `package.json`).
4. Record status in `docs/WEB_RELEASE_CANDIDATE_CHECKLIST.md`. Desktop packages only
   from a frozen, accepted web release — never during hardening.
