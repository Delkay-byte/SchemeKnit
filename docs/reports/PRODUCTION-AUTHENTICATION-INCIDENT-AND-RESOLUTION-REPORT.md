# Production Authentication Incident and Resolution Report

**Incident:** ordinary users and Super Admins see "Your session has expired. Please sign in again." at `https://schemeknit.bloomcoretech.com`
**Date:** 17 November 2026
**Severity:** P0 (authentication blocked)
**Status:** Code fix complete, tested, and committed. Production deployment and authenticated production verification are **BLOCKED** — no Render/Neon credentials and no authorized production accounts were available in this environment.

---

## 1. Summary

Production sign-in failures were reported for both ordinary users and Super Admins. The failed request was reproduced against the live API. The observable defect is confirmed:

- `POST https://schemeknit-api.onrender.com/api/auth/login` returns `401` with `{"error":true,"detail":"Invalid email or password","status_code":401}`.
- The frontend collapsed **every** HTTP 401 into the fixed message `Your session has expired. Please sign in again.` (`frontend/src/lib/error-normalizer.ts`).
- The frontend also cleared the tab session and redirected to `/login` on any 401 that was not `/api/auth/login` or `/api/auth/setup`, including 401s from in-session credential checks (current-password verification, MFA disable, recovery-code regeneration).

So the message shown during login was never a backend session-expiry assertion. It was a misclassified credential rejection.

Three fixes are included:

1. **Truthful 401 classification** (frontend): credential failures show the real, safe message; explicit session outcomes keep the backend wording; opaque token diagnostics stay hidden.
2. **Session preservation on credential failures** (frontend): a wrong current password or wrong MFA credential no longer signs the user out mid-action.
3. **Legacy email compatibility** (backend): accounts stored before email normalization (mixed case, surrounding whitespace) resolve at login instead of being rejected as unknown.

The credential-rejection *cause* for the specific production accounts could not be proven. That requires production credentials or Render/Neon access, which were not available. Section 7 records exactly what is still blocked.

---

## 2. Impact

- Ordinary teachers and Super Admins could not sign in.
- Any failed login attempt produced a misleading security message that instructed users to sign in again, which they had already done.
- Users changing their password or disabling MFA with a wrong current password were signed out of the tab instead of being told the password was wrong.
- No production data, sessions, or customer records were modified by this work.

---

## 3. Evidence

### 3.1 Live production request

```
POST https://schemeknit-api.onrender.com/api/auth/login
Content-Type: application/json

{"email":"<nonexistent probe>","password":"<probe>","entry":"teacher"}
```

Response:

```
HTTP 401
{"error":true,"detail":"Invalid email or password","status_code":401}
```

The UI then displayed:

```
Your session has expired. Please sign in again.
```

### 3.2 Service state at investigation time

| Check | Result |
| --- | --- |
| `GET /api/health` | `200` |
| `GET /api/ready` | `200` (DB + storage reachable) |
| `GET /api/service-status` | `200` |
| `GET /api/auth/setup/status` | `200`, `user_count: 4` |
| `GET /api/auth/registration-policy` | `invite_only` |
| `GET /api/auth/oidc/status` | `{"enabled":false}` |
| Server clock | UTC, matches client expectation |
| CORS / auth headers | correct for the frontend origin |

The deployed backend is at least the 6 November SSO build. Production documentation records deployed commit `7497408` (version `1.0.5`, 12 November 2026), services `schemeknit-api` and `schemeknit-frontend`.

### 3.3 Historical evidence that the same deployment worked

`docs/reports/WAPEF-DOCX-QUALITY-AND-KEYWORD-IMPROVEMENT-REPORT.md` records successful production authentication and acceptance on the same commit. This argues against a permanent design fault and toward a data, configuration, or account-state cause on the production side.

### 3.4 Repository state

- Working tree: `C:\Users\SAVIOUR\Documents\TeachFlow`
- Remote: `https://github.com/Delkay-byte/SchemeKnit.git`
- Base commit: `734f3c7` (`docs: record P4 production acceptance and QA cleanup`), equal to `origin/main`
- No auth-related commits after 12 November 2026
- Unrelated owner work (untracked `docs/infrastructure/benchmarks/`) left untouched

---

## 4. Root cause

### 4.1 Confirmed defect: 401 was treated as one condition

`frontend/src/lib/error-normalizer.ts` mapped every 401 to a single fixed string:

```ts
if (status === 401) {
  return { ...base, category: 'auth', message: FRIENDLY_MESSAGES.auth, ... }
}
```

The backend uses 401 for at least four different outcomes:

| Backend outcome | Endpoint | Safe user meaning |
| --- | --- | --- |
| `Invalid email or password` | `/api/auth/login` | credentials rejected |
| `Invalid credentials` / `Current password is incorrect` | change password, MFA disable/regenerate | submitted credential wrong, session still valid |
| `Your session has expired…`, `This session has ended…`, `You have signed out…` | any authenticated endpoint | session genuinely over |
| `Invalid or expired token`, `Not authenticated` | token parsing/authentication | session invalid |

Only the last two are "your session expired". Collapsing all four produced the reported P0 message during login.

`frontend/src/lib/api.ts` compounded it: any 401 outside `/api/auth/login` and `/api/auth/setup` cleared `sessionStorage` and redirected to `/login`. That turned a wrong current password into an unexpected sign-out.

### 4.2 Contributing risk: legacy email rows

Login compares `User.email == normalize_email(req.email)`. Rows written before normalization (mixed case, leading/trailing spaces) never match. This is a plausible cause of `Invalid email or password` for otherwise valid accounts, but it is **not proven** for the four production users.

### 4.3 Not the cause

- Token lifetime and clock skew: the failure occurs before any token is issued.
- CSRF: the API uses bearer tokens, and the login request reached the handler.
- Role/entry boundary: it returns the same generic 401 by design, so it cannot be distinguished from a bad password in the response (correctly so).
- CORS: preflight and headers were correct.

---

## 5. Changes

### 5.1 `frontend/src/lib/auth-401.ts` (new)

Single, testable rule for what a 401 means:

- `CREDENTIAL_401_ENDPOINTS`: `/api/auth/login`, `/api/auth/setup`, `/api/auth/change-password`, `/api/auth/mfa/disable`, `/api/auth/mfa/recovery/regenerate`, `/api/auth/reset-token/validate`, `/api/auth/confirm-password-reset`.
- `isCredential401(endpoint, failureCode)`: true for those endpoints, and for any endpoint whose backend code is `invalid_credentials`.

### 5.2 `frontend/src/lib/api.ts`

- Parses the error body before deciding anything.
- Clears the tab session and redirects only when the 401 is **not** a credential failure.
- Preserves the session for in-session credential checks.
- 403 handling, CSRF behaviour, tab-scoped `sessionStorage`, and redirect targets are unchanged.

### 5.3 `frontend/src/lib/error-normalizer.ts`

- 401 with a credential detail → `category: 'validation'`, message is the backend detail (for example `Invalid email or password`, `Current password is incorrect`).
- 401 with an explicit session outcome → `category: 'auth'`, backend wording preserved (expired, ended, signed out, inactivity).
- 401 with an opaque token detail or no detail → unchanged friendly session message; raw diagnostics never rendered.
- Detail is still bounded and filtered by the existing `safeDetail` / `INTERNAL_MARKERS` guards.

### 5.4 `backend/src/routers/auth.py`

- Added `_find_user_for_login()`:
  - exact indexed match first (`User.email == lookup`);
  - fallback `lower(trim(User.email)) == lookup` only when the exact match misses.
- Login uses the helper. No other lookup path, permission, or role check changed.
- Password verification, lockout, Turnstile escalation, MFA, entry/role matching, session creation, and audit logging are untouched.

### 5.5 Tests

- `backend/tests/test_auth_login_session_p0.py` (new, 6 tests):
  - ordinary teacher login, three consecutive authorized calls;
  - platform-admin login, repeated authorized calls, platform-admin API allowed, teacher workflow denied;
  - wrong password → generic 401, no token;
  - unknown account → same generic 401;
  - legacy mixed-case/whitespace stored email logs in;
  - logout revokes the shared session.
- `frontend/tests/ux/auth-401.test.ts` (new, 5 tests): credential endpoints vs session endpoints, backend code precedence, query strings.
- `frontend/tests/ux/error-normalizer.test.ts`: 4 new 401 regression tests (credential message, wrong current password, explicit session wording, opaque token detail).
- `frontend/package.json`: `test:ux` now includes the new test file.

---

## 6. Verification performed

| Check | Command | Result |
| --- | --- | --- |
| New backend regression suite | `python -m pytest tests/test_auth_login_session_p0.py -q` | 6 passed |
| Auth/session/release regression | `python -m pytest tests/test_auth_entry_boundary.py tests/test_auth_lifecycle.py tests/test_session_lifecycle.py tests/test_release_boundaries.py -q` | 79 passed |
| New + existing frontend UX tests | `node --test tests/ux/auth-401.test.ts tests/ux/error-normalizer.test.ts` | 26 passed |
| TypeScript | `npx tsc --noEmit -p tsconfig.json` | clean |
| ESLint (changed files) | `npx eslint src/lib/api.ts src/lib/auth-401.ts src/lib/error-normalizer.ts tests/ux/auth-401.test.ts tests/ux/error-normalizer.test.ts` | 0 errors (pre-existing `any` warnings only) |
| Production web build | `npm run build:web` | compile, TypeScript, and all 49 static pages succeeded; the process then exits 1 on the Next.js security advisory check (see 8.2) |

### 6.1 Security properties preserved

- No password, cookie, token, session ID, or secret is logged.
- No token lifetime was extended.
- No session validation was disabled.
- No protected route was made public.
- No bypass account was added.
- Role, tenant, license, and platform-admin checks are unchanged.
- CSRF, rate limiting, lockout, MFA, and session revocation are unchanged.
- Only tab-scoped `sessionStorage` is touched, and only for genuine session failures.

---

## 7. Deployment and production verification

### 7.1 Deployment

**BLOCKED.** This environment has no Render API key, no Render dashboard session, and no repository deploy workflow (`.github/workflows` contains no deployment job). Production cannot be updated from here.

Deployment commit: `01b149b` (`fix: classify 401s truthfully and stop signing out on credential errors`) on branch `fix/auth-401-session-classification`, pushed to `origin`. Pull request: https://github.com/Delkay-byte/SchemeKnit/pull/11. It is not on `main` and not deployed.

### 7.2 Production verification

**BLOCKED.** No authorized production account credentials were available. Documented QA accounts were removed earlier, and registration is `invite_only`, so no test identity could be created without touching customer data.

### 7.3 Operator steps to close the incident

1. Deploy the backend and frontend from the fix commit.
2. Confirm health: `/api/health`, `/api/ready`, `/api/service-status`.
3. Sign in as an existing ordinary teacher and confirm `/api/auth/me` returns 200 and the dashboard loads.
4. Sign in as the Super Admin through `/login/platform-admin` and confirm `/api/platform-admin/dashboard` returns 200.
5. Confirm a wrong password on `/login` now shows `Invalid email or password`, not the session-expired message.
6. Confirm a wrong current password in Settings does **not** redirect to `/login`.
7. If a valid account still gets `Invalid email or password`, check the stored `users.email` and `role` for that account in Neon, and check `/api/auth/login` failures in Render logs. The response body cannot distinguish bad password, role/entry mismatch, and MFA failure by design.

---

## 8. Follow-ups

1. **Next.js security advisory.** `next@16.4.3` is flagged by the build-time advisory check. Upgrade in a separate change; it is unrelated to this incident.
2. **Backend structured auth codes.** The frontend now classifies correctly using endpoint and detail. Adding a stable `code` to auth errors (`invalid_credentials`, `session_expired`, …) would remove the endpoint allowlist as a dependency. This is a contract change and should ship with its own tests.
3. **Login diagnostics.** Add a non-sensitive failure reason to server logs only (`bad_credentials`, `entry_mismatch`, `mfa_failed`) and to the security audit trail. Never expose the reason to the client; the generic response is intentional.
4. **Session UX.** Tab-scoped sessions mean a new browser tab requires a fresh sign-in. That is by design (`1143f1c`), but the login copy should state it if users report it as a fault.

---

## 9. Rollback

Revert the fix commit. No schema migration and no data migration are included, so rollback is code-only. The legacy email fallback is read-only and safe to keep.
