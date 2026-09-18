# Platform Admin Web Acceptance

Date: 2026-09-16
Scope: Platform Admin web experience only (canonical repo `C:\Users\SAVIOUR\Documents\TeachFlow`).
Teacher workflow, desktop packaging, custom templates, and AI enrichment are out of scope for this run.

## 1. Environment (actual URLs)

| Layer    | URL                                | How started |
|----------|------------------------------------|-------------|
| Frontend | http://localhost:3000              | `npm run dev -- --port 3000` in `frontend/` (Next.js 14.2.3, web target) |
| Backend  | http://127.0.0.1:8000              | `venv/Scripts/python -m uvicorn src.main:app --host 127.0.0.1 --port 8000` in `backend/` |
| Platform Admin UI | http://localhost:3000/platform-admin/ | role-guarded route, `platform_admin` only |
| Health   | http://127.0.0.1:8000/api/health   | `{"status":"healthy","service":"TeachFlow","version":"1.0.3"}` |

Browser: real Chrome (system install) driven via Playwright, headless, screenshots in `/tmp/pa_*.png`.

## 2. Platform Admin account method

ONE supported bootstrap: `backend/src/tools/create_platform_admin.py` (CLI, local filesystem access only).
No role selector on registration, no client-side role assignment, no manual SQLite editing.

Acceptance account created with the tool (`--force`, pre-existing admin untouched):

- Email: `platform.acceptance@bloomcore.com`
- Role: `platform_admin` (verified in login response + DB)
- Pre-existing admin `admin@bloomcore.com` (Kobla Saviour) left untouched; password unknown, not needed.

Supporting acceptance accounts (known passwords, used for isolation matrix):

- `sadmin.accept@accept.edu.gh` / school_admin of Acceptance Test School (via `POST /api/auth/setup-school-admin`)
- `teacher.accept@accept.edu.gh` / teacher of Acceptance Test School (via school-admin `POST /api/auth/register`)

## 3. Pre-existing records (verified, not created this run)

| Record | Key fields | Result |
|---|---|---|
| Awasive M/A Basic School | code AWASIVE-488989, active, license TF-LIC-5Z7H-KPEH, 20 seats, expiry 2027-09-15 | PASS |
| TeachFlow School Annual | GH₵800.00, GHS, 365 days, 20 seats, active | PASS |
| Test School + Test Plan + No License School | isolation fixtures | PASS |

## 4. Test records created this run (via real UI unless noted)

| Record | Method | Key fields |
|---|---|---|
| Acceptance Test School | Platform Admin UI → Create School | code ACCEPT-2026-0916, active |
| Acceptance Annual 2026 | Platform Admin UI → Create Plan | GH₵750.00, 365 days, 15 seats |
| License TF-LIC-MUWR-3KTN | Platform Admin UI → Create License | Acceptance Test School, 10 seats |
| Codes TF-SCH-VQMN-RVJ4-G5CB, TF-SCH-I9YX-PKQI-39NY | UI → Generate Code | `TF-SCH-XXXX-XXXX-XXXX`, secure random |
| Payment MTN-ACC-001 (GH₵750, mtn_momo) | API submit → UI verify | verified |
| Payment GCB-ACC-002 (GH₵800, bank_transfer) | API submit → UI reject | rejected |

## 5. Browser acceptance results

| # | Action | Expected | Actual | Result |
|---|---|---|---|---|
| 1 | Login (acceptance admin) | redirect to `/platform-admin/` | redirected, dashboard rendered | PASS |
| 2 | Dashboard metrics | real numbers, GH₵, no `$`, no mocks | 3 schools, 2 licenses, 0 expiring/expired, 8 teachers, 17 seats avail, 0 pending, GH₵ 0.00 → GH₵ 750.00 after verify | PASS |
| 3 | Tabs | Dashboard/Schools/Licenses/Plans/Payments/Activations/Audit, all render | all render; no teacher-workflow tabs | PASS |
| 4 | Schools list | Awasive visible + teacher counts + license status | shown | PASS |
| 5 | School detail modal | contact + licence + teachers/admins | shown | PASS |
| 6 | Create school (UI) | appears in list | listed | PASS |
| 7 | Plans list | TeachFlow School Annual GH₵800 | shown | PASS |
| 8 | Create plan (UI) | appears in list | listed | PASS |
| 9 | Licenses list | codes, seats used/limit, expiry | shown (e.g. 2/20 Awasive, 5/5 Test) | PASS |
| 10 | Create license (UI) | school+plan selectable, license created pending | **school dropdown was EMPTY — bug found and fixed** (licenses tab never fetched schools); after fix, created OK | PASS (after fix) |
| 11 | Generate activation code (UI) | `TF-SCH-XXXX-XXXX-XXXX`, status unused | TF-SCH-VQMN-RVJ4-G5CB, unused | PASS |
| 12 | Copy code (UI) | Copied feedback | shown | PASS |
| 13 | License activate (pending→active) | status flips, Suspend appears | confirmed | PASS |
| 14 | License suspend (active→suspended) | status flips, Activate appears | confirmed | PASS |
| 15 | License reactivate + renew | back to active | confirmed | PASS |
| 16 | Revoke code (UI) | status revoked | confirmed on activations tab | PASS |
| 17 | Payments list | payer, method, amount GH₵, product, status | both test payments shown | PASS |
| 18 | Verify payment (UI) | status verified, revenue updates | verified; dashboard GH₵ 750.00 | PASS |
| 19 | Reject payment (UI) | status rejected | rejected | PASS |
| 20 | Audit log | school/license/payment/activation entries | all present | PASS |
| 21 | Seat usage | computed from memberships | 1/10 acceptance, 2/20 Awasive, 5/5 Test | PASS |
| 22 | PA header nav | Platform only, no teacher links | **leak found and fixed** (Upload/Lesson Plans/Templates were shown); after fix nav = "Platform" | PASS (after fix) |
| 23 | School-admin login | lands on `/admin`, blocked from `/platform-admin` | redirected to `/dashboard` | PASS |
| 24 | Teacher login | lands on `/dashboard`, blocked from `/platform-admin` + `/admin` | both redirected | PASS |

## 6. API authorization matrix (live server)

| # | Request | Expected | Actual |
|---|---|---|---|
| 1 | teacher → `GET /api/platform-admin/dashboard` | 403 | 403 PASS |
| 2 | teacher → `GET /api/platform-admin/schools/{other-school}` | 403 | 403 PASS |
| 3 | school_admin → `GET /api/platform-admin/dashboard` | 403 | 403 PASS |
| 4 | school_admin → `GET /api/auth/users` | only own school | 2/2 acceptance users PASS |
| 5 | platform_admin → `POST /api/documents/upload` | 403 (workflow lock) | 403 PASS |
| 6 | no token → `GET /api/platform-admin/dashboard` | 401 | 401 PASS |

## 7. Code changes made this run

1. `frontend/src/app/platform-admin/page.tsx` — licenses tab now also fetches schools, so the Create License school dropdown is populated. (Was a dead-end flow: empty dropdown, silent no-op.)
2. `frontend/src/components/header.tsx` — role-aware nav: `platform_admin` sees only the Platform link (logo routes to `/platform-admin`); teacher/school-admin nav unchanged.

Verification after changes: `npx tsc --noEmit` clean, backend `pytest tests/` **253 passed**, full browser re-run green.

## 8. Console / API issues observed

- One 404 resource on first login-page load (favicon.ico; harmless, no app impact).
- `passlib`/`bcrypt` version warning (`__about__` AttributeError, "trapped") when running the bootstrap CLI — cosmetic; hashing and login verified working.
- `POST /api/auth/setup-school-admin` is a **public, unauthenticated** endpoint that creates a `school_admin` for any `school_id` with no activation-code check (docstring claims "code is the credential" but no code is verified). Flagged for the production-security phase; not changed in this task.

## 9. Known gaps (not blocking this gate)

- No Content Packs or Settings tabs in the Platform Admin UI (backend CRUD exists at `/api/content-packs`; settings router covers school-level settings). Per navigation rules they are omitted rather than shown as dead tabs.
- Payment submit in this run used the API (teacher UI submit is teacher-workflow scope, out of this task).
- Desktop activation of generated codes is deferred per plan (§23) — codes verified server-side (generate/list/revoke/statuses).

## 10. Version

Single source: `1.0.3` in `backend/src/config.py` (`APP_VERSION`), `frontend/package.json`, `desktop/package.json`, login page title, `/api/health`. No stale `1.0.0`/`1.0.1` labels in source.

## Verdict

**THE PLATFORM ADMIN WEB EXPERIENCE IS DEMONSTRABLY USABLE.** Login → dashboard → create school → create plan → create license → generate/copy/revoke code → verify/reject payment → audit, all performed in a real browser against real backend data, with role separation enforced (UI + 403s) and two real bugs found and fixed.
