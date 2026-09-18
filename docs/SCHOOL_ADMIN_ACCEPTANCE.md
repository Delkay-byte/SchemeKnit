# School Admin Milestone — Acceptance

Date: 2026-09-16. Canonical repo only. No legacy files touched. No desktop rebuild.

## Architecture
- Roles: `platform_admin` (business plane) / `school_admin` (one school) / `teacher`
  (one school, workflow only). Enforced server-side (`require_platform_admin`,
  `require_admin`, `_require_same_school`, `require_teacher_workflow`,
  `require_valid_license`) + role-aware UI (header + route guards).
- Activation: `ActivationCodeDB` (active/used/revoked, expiry) → `SchoolLicenseDB`
  (pending/active/suspended/expired/cancelled) → `User(school_admin)` + `SchoolMembershipDB`.
  No parallel systems; one migration-free change (no schema change needed).
- Seat rule (single, documented in code + here): **only ACTIVE teachers consume seats**.
  Deactivation frees a seat (data preserved, login disabled); reactivation re-checks the
  limit; creation requires a usable (active, non-expired) license.

## Role boundaries
- Platform Admin: schools/plans/licenses/codes/payments/audit only; 403'd out of the
  teacher workflow; header shows Platform only.
- School Admin (`/school-admin/*`): own dashboard/teachers/settings/license only;
  cross-school user ops 403; platform APIs 403; teacher workflow links hidden.
- Teacher: workflow + templates only; user-management and admin APIs 403; no Admin nav.
- `/admin` is a redirect alias to `/school-admin`; login/header point to `/school-admin`.

## Activation flow
1. Platform Admin creates school → license (seats set, e.g. 3) → generates code
   (`TF-SCH-XXXX-XXXX-XXXX`, secure random).
2. Logged-out `/activate-school`: code → `POST /activation/validate` shows school/plan/
   status/seats/expiry (display only) → create admin (name/email/password ≥8 + confirm).
3. `POST /setup-school-admin` validates + redeems + creates admin + membership + audit
   **atomically** (row lock; single winner). School always derived from the code —
   client `school_id` ignored. Old open endpoint closed (code now required).
4. Success → login → `/school-admin`.

## Seat enforcement
- Server-side on create (`403 seat limit`) and on reactivation; UI shows `used/limit`
  plus a seat-full banner with the rule. Verified: limit 3 → T1/T2/T3 ok, T4 rejected
  with message; deactivation frees, reactivation re-checks.

## License enforcement
- ACTIVE: normal access. SUSPENDED/EXPIRED/missing: teacher workflow 403 and teacher
  creation 403; school admin still views dashboard/teachers/settings/license (read context);
  **no data deleted ever**. Platform Admin suspend/reactivate verified live with data intact.

## Teacher lifecycle
- Create (role/school server-forced + membership + audit) → directory → edit name/email →
  deactivate (login disabled, seat freed) → reactivate (seat re-checked) → password reset.
- Deactivated teachers get 403 on any authenticated use.

## Security isolation
- School Admin A: cross-school toggle/reset/update → 403; user list scoped to own school.
- Teacher: user creation, school-admin and platform APIs → 403; direct-URL guards redirect.
- Activation: invalid 404, expired/used/revoked/suspended-license 403, replay 403,
  short password 422, duplicate email 409. No secrets/hashes in responses.

## API endpoints
- `POST /api/auth/activation/validate` (public, display-only)
- `POST /api/auth/setup-school-admin` (secured: code + atomic redeem + claim)
- `POST /api/auth/users` (create teacher: license + seat gated)
- `PUT /api/auth/users/{id}` (scoped edit) · `PUT /users/{id}/toggle-active` (scoped + seat-gated
  reactivation) · `POST /users/{id}/reset-password` (scoped, min length)
- `GET/PUT /api/auth/my-school`, `GET /api/auth/users` (scoped) — reused.
- Platform: existing school/license/code/audit endpoints reused unchanged.

## Migration details
None required (existing tables covered the model). v008 (export events, prior milestone)
applied in acceptance DB; migrations v001–v008 current.

## Browser acceptance steps (all PASS, real Chrome)
- A: PA login → create Milestone School B → 3-seat license → activate → generate
  `TF-SCH-2T4B-Q8QW-8A6X`. PASS
- B: logged-out `/activate-school` → invalid-code message → valid details (school/plan/
  pending/3 seats/expiry) → create admin → "School Activated". PASS
- C: SA login → `/school-admin` (name/plan/0 teachers/0-of-3/Active/expiry) → empty state →
  create T1 + T2 → directory + seats 2 of 3. PASS
- D: T1 login → teacher dashboard, lessons empty state, templates load, teacher nav
  intact with no Admin/Platform. PASS
- E: teacher→PA/school-admin redirected; SA→PA redirected; SA cross-school toggle 403;
  teacher create-user 403. PASS
- F: T3 → 3-of-3; T4 → rejected with seat-limit message. PASS
- G: code replay → 403 already used. PASS
- Suspend/reactivate cycle via API with teacher + creation probes + data-intact check. PASS

## Test count
- 23 new tests (`tests/test_school_admin.py`: activation ×10, seats ×3, teachers ×6,
  license ×2, roles ×2). Full suite: **312 passed**. TypeScript: clean.

## Known limitations
- One admin claim per activation code (extra admins via Platform Admin).
- `/activate` (desktop-styled) kept working via the secured endpoint; school web flow
  is `/activate-school`.
- ZIP browser-click transfer + PDF engine limits unchanged from prior milestones.
- `setup-school-admin` keeps accepting (and ignoring) a client `school_id` for
  backward compatibility; authority is always the code.
