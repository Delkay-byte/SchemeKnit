# Web Release Candidate Checklist (v1.0.4)

## SECURITY — PASS (with noted WARNINGs)
- Authn (hashing, expiry, disabled, duplicates): PASS (evidence: auth tests + probes)
- Authz/tenancy/IDOR (14 tests + live probes): PASS
- Uploads (traversal/MIME/size/malformed): PASS
- Exports authz + ZIP entries: PASS
- Secrets fail-safe + env separation: PASS (live refusal verified)
- Rate limiting: PASS (unit-tested; localhost-exempt by design)
- Headers/CORS: PASS (CORS env-driven; CSP deferred → WARNING)

## DATABASE — PASS (SQLite + live PostgreSQL)
- SQLite acceptance (all journeys): PASS
- Migration chain v001–v009 portable (inspector-based): PASS (code review + both DBs)
- Live PostgreSQL acceptance: **PASS** — Docker `teachflow-pg-accept` (PG 16.14);
  migrations, 378/378 tests, browser journeys A–F, structural DOCX validation.
  (Conda-forge Windows PG remains environmentally broken; documented, not used.)
- Transactions/atomicity (activation, creation, events): PASS (tests)
- Portability bugs found live and fixed: `is_admin = 1` (v004), `datetime('now')` +
  integer booleans (bootstrap tool). Datetime convention: naive UTC everywhere.

## AUTHENTICATION — PASS (login-failure audit WARNING)
## AUTHORIZATION — PASS
## FILE UPLOADS — PASS
## GENERATION — PASS (dedup, retry, regen semantics tested)
## EXPORTS — PASS (DOCX/XLSX/ZIP verified; PDF converter-limited = known)
## AUDIT — PASS (activation/teacher/license/export events; login-failure logging WARNING)
## OBSERVABILITY — PASS (/health + /ready + JSON logs; WARNING: no CVE sweep, naive datetimes)
## CONFIGURATION — PASS (.env.example current; fail-fast verified)
## BACKUPS — PASS (documented expectations; N/A automated platform)
## BROWSER ACCEPTANCE — PASS (A–E journeys + failure scenarios, evidence captured)
## REGRESSION — PASS (368 backend, tsc clean, structural DOCX green)
## KNOWN LIMITATIONS — documented (ZIP-click env, PDF, orphans, single-worker limiter, PG blocked)

## Version decision
Remains **1.0.4** (backend/frontend/desktop consistent). 1.0.4 reserved for the release
once PostgreSQL is verified or explicitly waived — no arbitrary bump per convention.
