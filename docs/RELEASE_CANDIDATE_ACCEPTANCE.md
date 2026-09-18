# Release Candidate Acceptance

Version under test: 1.0.4 (backend/frontend/desktop consistent).
Environment (SQLite): frontend http://localhost:3000, backend http://127.0.0.1:8000,
acceptance SQLite DB.
Environment (PostgreSQL): frontend http://localhost:3001, backend http://127.0.0.1:8001,
`teachflow-pg-accept` container (postgres:16-alpine, dedicated volume/db/user).
PostgreSQL: **VERIFIED LIVE** — migrations v001–v009, 378/378 tests, full browser
journeys A–F (platform, school, teacher+workflow, org/custom templates, exports,
security incl. suspend/reactivate and replay). Conda-forge Windows PG remains broken;
Docker path is the supported one.

## Browser journeys (real Chrome, all PASS)
- A. Platform Admin: login → metrics (GH₵) → schools/plans/licenses/codes/payments/audit;
  nav role-pure; prior full commercial cycle still green.
- B. School Admin: activation-code onboarding (invalid message → details → claim →
  success) → dashboard (plan/seats/expiry) → teachers/settings/license pages;
  empty states, seat banner, confirmations verified.
- C. Teacher: login → dashboard stepper (5 ✓ persisted across refresh + fresh login) →
  review → lessons → edit/save (Saved badge, DB-persisted) → custom template option →
  DOCX download (valid file) → workflow persistence.
- D. Security probes: teacher→PA/school-admin redirected; SA→PA redirected;
  cross-owner lesson read + job export denied (404); cross-school user ops 403;
  suspended license blocks workflow + creation with data intact; reactivation restores.
- E. Failures: expired session → login redirect (new); wrong-extension message;
  malformed DOCX → controlled 422, server alive; replay activation → 403;
  seat-full → 403 + UI message.

## Tests / TypeScript
- Backend: **368 passed** (312 baseline + 35 security + 14 IDOR + 7 workflow-regression).
- TypeScript: clean. Structural DOCX validation: green (prior milestone, untouched code paths).

## Environment / version
- Frontend/Backend/Desktop: 1.0.4. Migrations v001–v008 applied on acceptance DB.
- No desktop rebuild performed. No legacy files touched.

## Known limitations (carried, unchanged)
ZIP browser-click transfer on this machine; PDF converter gap; scheme-file orphans on
delete; login failures not audit-logged; CSP deferred; naive datetimes; no CVE sweep;
in-memory rate limiter is single-worker (proxy limiting required multi-worker).
