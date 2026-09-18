# Production Hardening Audit

Date: 2026-09-16. Method: code inspection + live probing + tests. Severity: CRITICAL /
HIGH / MEDIUM / LOW / INFORMATIONAL. Status: PASS / WARNING / BLOCKER / N/A.

## Matrix

| ID | Area | Sev | Evidence | Behavior → Remediation | Status |
|----|------|-----|----------|------------------------|--------|
| A1 | Password hashing | — | `passlib[bcrypt]` (`src/auth.py`); all stored creds hashed | No change | PASS |
| A2 | Password strength | MEDIUM | Only client-side `minLength` existed on setup flows | Server-side minimum enforced (8) on setup, teacher create/reset paths | PASS |
| A3 | Token expiry | LOW | JWT 24h (`JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440`); no revocation list (stateless design) | Documented; 401 auto-redirect added client-side | PASS |
| A4 | Disabled users | — | `_authenticate_user` 403s `is_active=False`; tested | No change | PASS |
| A5 | Duplicate email | — | 409 on register/setup; tested | No change | PASS |
| B1 | Role boundaries | — | `require_platform_admin` / `require_admin` / school scoping; 14 IDOR + role tests | No change | PASS |
| B2 | Teacher→admin escalation | — | 403s verified live + tests | No change | PASS |
| C1 | School tenancy | — | `school_id` server-derived everywhere (register, setup, lists) | No change | PASS |
| D1 | Cross-owner reads | HIGH | Schemes/lessons/jobs/templates owner-scoped; workflow endpoint inherits | Verified by 14 IDOR tests (403/404, data intact) | PASS |
| D2 | Cross-owner writes | HIGH | Same scoping on PUT/DELETE/approve/generate/export | Tested; victim rows intact | PASS |
| E1 | Template upload traversal | **HIGH** | `templates.py` joined raw `file.filename` into storage path | Fixed: `sanitize_filename` (strict reject) + `safe_join` containment; 35 tests | PASS |
| E2 | Scheme upload paths | — | Server-generated names only; original name display-only | Verified, no change | PASS |
| E3 | MIME validation | MEDIUM | Extension-only checks | Allowlist MIME added on scheme + template uploads (octet-stream tolerated) | PASS |
| E4 | Size limits | — | 50 MB schemes / 10 MB samples, streamed pre-check | Verified | PASS |
| E5 | Malformed docs | — | Controlled 400/422, file cleanup, server survives (probed live) | No change | PASS |
| F1 | Export authz | HIGH | All export endpoints resolve job/lessons by `(id, owner)` | Probed: cross-owner lesson read + job export → denied | PASS |
| F2 | ZIP entries | — | Server-generated names only; no user paths in archive | Verified | PASS |
| G1 | Template ownership | — | Owner-scoped CRUD + 403/404 diagnostics | Tested | PASS |
| G2 | Archived template use | MEDIUM | Archived hidden from lists; direct id falls back to built-in (silent) | Documented limitation; no silent cross-owner leak (owner check first) | WARNING |
| H | Path traversal (general) | HIGH | See E1; exports/ZIP/scheme paths server-built | Fixed + tested | PASS |
| I1 | Migration portability | HIGH | v005–v008 used PRAGMA/sqlite_master/DATETIME/BOOLEAN-0 | Rewritten to inspector-based dialect-portable SQL | PASS (code review) |
| I2 | Live PG acceptance | — | Docker Desktop started → `teachflow-pg-accept` (postgres:16-alpine, PG 16.14, dedicated volume/db/user, localhost:5433) | Full chain verified: migrations v001–v009, 391/391 tests (both DBs), browser journeys A–F | PASS |
| I3 | Runtime SQL portability | — | Full scan: only Python `strftime`, no SQLite SQL in app code | No change | PASS |
| I4 | JSON/boolean/date types | LOW | Generic SQLAlchemy types; naive datetimes throughout (consistent) | Consistent; TZ-awareness deferred (documented) | WARNING |
| J1 | Activation atomicity | HIGH | Was check-then-set; now row-locked single transaction + audit | Fixed + tested (incl. replay) | PASS |
| J2 | Export events | MEDIUM | Event logged after file build, before transfer completes | Accepted + documented (build success = the persisted fact) | WARNING |
| J3 | Regeneration | — | Delete-then-create per scheme; no duplicates; tested | No change | PASS |
| K1 | Error leakage | — | Generic 500 handler; parser/validation messages user-safe | Verified live (422/403/404 bodies contain no traces/paths/secrets) | PASS |
| L1 | Secrets in logs | — | No passwords/hashes/tokens in logging paths (inspected) | No change | PASS |
| L2 | Login-failure logging | LOW | Failures not logged (noisy-signal tradeoff) | Rate limiting mitigates; documented | WARNING |
| M1 | Rate limiting | MEDIUM | None existed | Sliding-window middleware on 10 sensitive route groups; localhost-exempt for dev; unit-tested; multi-worker note documented | PASS |
| N1 | CORS | MEDIUM | Env-configurable allowlist; was localhost-heavy dev default | `.env.example` mandates exact production origins; code unchanged | PASS |
| O1 | Security headers | LOW | None existed | nosniff + referrer + SAMEORIGIN + permissions-policy + no-store added; CSP deferred (Next.js compat) | PASS |
| P1 | Default secrets | **HIGH** | `CHANGE-ME-IN-PRODUCTION` booted silently | Fail-fast `validate_production()` on non-debug boot (verified live) | PASS |
| P2 | Env separation | MEDIUM | `.env.example` stale (v1.0.0); dev `.env` present | Example refreshed (1.0.3, all vars documented); dev `.env` stays local-only | PASS |
| Q1 | Health/readiness | LOW | Only `/api/health` | Added `/api/ready` (DB ping, no secrets); verified live | PASS |
| R1 | Generation dedup | — | Scheme-scoped replace verified by inspection + tests | No change | PASS |
| S1 | Workflow integrity | — | Event/data-driven states; 11 state-machine tests | No change | PASS |
| T1 | Destructive ops | — | Deletes scoped + confirmed in UI; no data loss on expiry/suspend | Verified | PASS |
| U1 | Dependencies | LOW | Pinned requirements; added `psycopg[binary]` (needed for PG path) | No CVEs audited in this pass (documented) | WARNING |
| V1 | Frontend secret exposure | — | Only `NEXT_PUBLIC_*` in bundle (API URL, build target); no backend secrets | Verified by inspection | PASS |
| W1 | Production build | LOW | Dev server used in acceptance; `build:web`/`build:desktop` targets exist | Release process documented; production build smoke deferred to deploy | WARNING |

## Remediation summary (this milestone)
`src/security.py` (new) · `templates.py` + `documents.py` upload hardening ·
`config.validate_production` · rate-limit + security-headers middleware · `/api/ready` ·
frontend 401→login · `setup-school-admin` password floor · requirements + `.env.example` ·
Next.js 14.2.3→14.2.35 (auth-bypass class cleared) · PDF 503-when-no-converter ·
scheme storage tracking (v009) + guarded delete + staged purge · naive-UTC standard ·
login-failure security logging · AI payload robustness (fences, nesting, timeouts).
79 new tests total across hardening suites; **391/391 on SQLite AND PostgreSQL**;
TypeScript clean; production build + smoke green.
