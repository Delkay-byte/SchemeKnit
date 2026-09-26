# Tab-Isolated Authentication — Implementation & Verification Report

**Date:** 2026-09-26
**Scope:** Every browser tab of the same origin/profile must hold an independent,
server-verified authenticated session. Tab A = User A and Tab B = User B must be able
to coexist simultaneously; login, logout, and refresh in one tab must never change
another tab's identity.
**Verdict:** PASS — proven in a real browser (same context, multiple pages) with
captured API request credentials and server-resolved identities.

---

## A. Root cause: one shared `localStorage` session for the whole origin

Before this change, `frontend/src/lib/auth-context.tsx` persisted the JWT and user
object under the shared origin-wide `localStorage` keys `teachflow_token` /
`teachflow_user` (restore `localStorage.getItem`, login `localStorage.setItem`,
logout `localStorage.removeItem`). `localStorage` is shared by every tab of an
origin, so:

- a brand-new tab auto-attached to whichever identity was last written;
- logging out in one tab logged out every tab;
- logging in as User B in one tab silently overwrote User A's identity everywhere.

`frontend/src/lib/api.ts` had the same shared-storage coupling in its 401 handler.

## B. Fix design: tab-scoped bearer credentials, no shared channel

The backend was already stateless: JWTs are minted per login and validated from the
`Authorization: Bearer` header only — **no cookies, no server session rows, no
refresh-token endpoint, no logout endpoint** (verified in §N). Therefore the only
shared vector was frontend storage. The fix is minimal and architectural:

- Auth identity (JWT + user object) now lives in **`sessionStorage`**, which is
  scoped to a single tab (top-level browsing context) — a new tab starts empty.
- Every request still authenticates via the per-tab JS module's in-memory
  `authToken` (`api.setToken`) → `Authorization: Bearer <tab's JWT>`.
- There is deliberately **no cross-tab sync channel** (no `BroadcastChannel`, no
  `storage` event listeners) for auth: a tab's login/logout only affects that tab.

## C. Code changes (all in `frontend/`)

| File | Change |
|---|---|
| `src/lib/auth-context.tsx` | Restore reads `sessionStorage` only (lines 37–38, explicit comment: legacy `localStorage` tokens are **not** migrated). Login writes `sessionStorage.setItem('teachflow_token'/'teachflow_user')` (51–52). Logout removes both keys from `sessionStorage` (59–60). |
| `src/lib/api.ts` | 401 handler clears **only** this tab's `sessionStorage` keys and redirects only this tab (83–86); never touches `localStorage`. |
| `src/components/change-password.tsx` | Fresh token/user after password change stored in `sessionStorage` (59–60). |
| `e2e/tab-isolated-auth-acceptance.js` | **New** same-context multi-page acceptance (see §J/P). |
| `e2e/phase17-teacher-journey.js` | Legacy helper now reads `sessionStorage` first with `localStorage` fallback (test-only token read). |

No backend files were modified. `git status` shows exactly these 5 files changed.

## D. Backward compatibility / legacy migration

**INTENTIONAL** — a legacy shared `localStorage.teachflow_token` is deliberately
**not** migrated into a fresh tab. A new tab must start unauthenticated and require
an explicit login (verified: §Q). This prevents any silent re-attach of two tabs to
one old shared identity. Users with a pre-upgrade session simply log in once per tab.

## E. What was deliberately NOT changed

- Backend auth (stateless JWT + `pwv` password-version invalidation + role
  dependencies) — untouched, so no security model change and no full-suite impact.
- Non-auth `localStorage` preferences remain `localStorage`:
  `schemeknit.ai_mode` (lessons/generate pages) and the PWA install-prompt
  `DISMISS_KEY` (`src/components/install-prompt.tsx`) — classified NON-AUTH (§V/§W).
- Electron desktop menu sign-out (`desktop-menu-listener.tsx`) — per-window Electron
  IPC message, not cross-tab auth synchronization; kept as-is.

## F. Test design constraints (as mandated)

`frontend/e2e/tab-isolated-auth-acceptance.js` uses **ONE `chromium.launch`,
ONE `browser.newContext()`, SAME origin, multiple `context.newPage()` pages** —
never separate contexts for the primary test. It captures every API request each
page makes (`page.on('request')` → `authorization` + `cookie` headers) and asserts
identities via **actual API responses** (`GET /api/auth/me` executed from inside
each tab with that tab's own token, plus a Node-side cross-check with the captured
token) — never by displayed UI text alone.

Accounts (safe acceptance fixtures, roles verified live before the run):

| Tab | Account | Role | Server user id |
|---|---|---|---|
| A | `accept.teacher@schemeknit.test` | teacher | `accept-teacher-0001` |
| B | `accept.sa@schemeknit.test` | school_admin | `accept-sa-0001` |
| C | `accept.pa@schemeknit.test` | platform_admin | `accept-pa-0001` |

## G. Security posture (no weakening)

See §W for the verified checklist. The only credential held client-side remains the
signed JWT (same as before this change); it moved from origin-shared storage to
tab-scoped storage, which strictly reduces exposure (any same-origin script or tab
can no longer read another tab's token).

## H. Environment

- Frontend: fresh `npm run build` (exit 0) served by `next start -p 3003`.
- Backend: `127.0.0.1:8000` (`/api/health` 200, version 1.0.5) — unchanged this phase.
- CORS-excluded origin `http://localhost:3999` used only for hero/auth-role
  setup-state reproduction (documented pre-existing condition).

## I. Backend session architecture (documented per requirement)

| Aspect | Mechanism |
|---|---|
| **LOGIN** | `POST /api/auth/login` verifies bcrypt password → returns `{access_token, user}` (JWT signed with `JWT_SECRET_KEY`, claims `sub/email/role/pwv`, `exp` = `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`). No cookie is set; no server session row is created. |
| **REQUEST** | `HTTPBearer` extracts `Authorization: Bearer …` → `jwt.decode` (signature + expiry) → user id lookup in DB → `is_active` + `pwv` checks (`backend/src/auth.py`). |
| **LOGOUT** | No server endpoint exists; logout = this tab drops its token (`sessionStorage` + in-memory). Nothing server-side to invalidate a shared cookie because none exists. |
| **REFRESH** | No refresh endpoint and no refresh cookie; a new login mints a new token for that tab only. |
| **EXPIRATION** | `exp` claim → `decode_token` raises 401; stale token cleared only in the tab that received the 401 (`api.ts` handler). Password change bumps `pwv`, invalidating older tokens server-wide (unchanged). |
| **TAB ISOLATION** | Identity lives in per-tab `sessionStorage` + per-page in-memory module state. Tab B can only send a credential it physically holds; sharing would require a shared cookie or storage/sync channel — neither exists (§N, §V). |

## J. Acceptance coverage (43 checks)

Same-context sequence executed: A login → B fresh/protected-URL unauthenticated →
B login → dual identity → API identity both tabs → reloads → **A logout (B stays
authenticated immediately after)** → A re-login → C new tab (no inheritance:
landing + protected URL) → C platform-admin login → three identities coexist →
Node-side API cross-check → server-side role ladder → corrupt A's token (A alone
logged out) → request-capture evidence → final storage audit → zero page errors.

## K. Known limitations

- A logged-out tab's JWT remains cryptographically valid server-side until `exp`
  (inherent to stateless JWT; identical to the pre-change architecture — logout was
  never server-side). Holding the token elsewhere (e.g., copied out) would still
  work until expiry; that risk is unchanged by this work.
- Per-tab wall-clock session expiry is not directly controllable from e2e; covered
  by invalid-token rejection (§U) and backend expiry tests.

## L. Regression results (all green)

| Gate | Result |
|---|---|
| `npx tsc --noEmit` | exit 0 |
| `npm run build` | exit 0 |
| `app-ui-acceptance` | 53/0 |
| `app-chrome-acceptance` | 72/0 |
| `app-surfaces-acceptance` | 109/0 |
| `login-grid-acceptance` | 476/0 |
| `deep-journey-acceptance` | 21/0 |
| `download-acceptance bundled` | 14/14 |
| `app-closure-acceptance` | 94/0 |
| `hero-v3-acceptance` (at `:3999`) | 151/0 |
| `auth-role-design-acceptance` (at `:3999`) | 131/0 |
| **`tab-isolated-auth-acceptance` (new)** | **43/43** |
| Backend auth tests (`test_authorization`, `test_authorization_idor`, `test_auth_lifecycle`) | 66 passed (backend source unchanged; full suite not required) |

---

## M. Build-artifact verification — PASS

- Pre-clean stale auth (`localStorage…teachflow_token`) found **exclusively** in
  regenerable, **git-untracked** outputs: `frontend/.next` (14 files) and
  `desktop/release/win-unpacked/resources/frontend/_next` (18 files).
  Zero matches in `frontend/src`, `backend/src`, or any tracked file.
- Clean rebuild executed: stopped `:3003` → removed `frontend/.next` → `npm run
  build` (exit 0) → restarted `:3003` → re-searched:
  - `localStorage…teachflow_token` in new `.next`: **0**
  - `sessionStorage…teachflow_*` in new `.next`: **14**
  - old-auth matches in source (`frontend/src` + `backend/src`): **0**
- `desktop/release/win-unpacked` is a stale local Electron package (untracked;
  regenerated by the desktop packaging build at next release) — **INTENTIONAL**,
  documented, and not served by the web app. The desktop app's renderer source is
  `frontend/src`, which is clean; the next package build embeds the new auth code.

## N. Cookie audit — PASS

| # | Question | Answer |
|---|---|---|
| A | Does login set an auth cookie? | **No.** `POST /api/auth/login` returns JSON only. `set_cookie`/`cookies=`/`HttpOnly`/`SameSite` grep across all backend source (excluding venv) and tests: **0 hits**. |
| B | Does the browser send a cookie on API requests? | **No.** Captured every API request in the acceptance run: requests carrying a `Cookie` header = **0**. |
| C | Does backend auth prioritize a cookie? | **No.** `HTTPBearer` reads only the `Authorization` header (`backend/src/auth.py`); no cookie path exists. |
| D | Refresh-token cookie? | **No.** No refresh endpoint at all. |
| E | Shared session cookie? | **No.** No cookies of any kind are set. |
| F | Middleware/read-session using cookies? | **No.** Frontend has no `middleware.ts`; no `document.cookie` anywhere in `frontend/src`; backend middleware is CORS/rate-limit only. |
| G | Does logout invalidate a shared cookie? | **N/A — INTENTIONAL:** logout is client-side per-tab token drop; there is no shared cookie to invalidate. |

`CORSMiddleware(allow_credentials=True)` is set, but `allow_credentials` only
matters when cookies exist — none are issued, so no shared credential can ride along.

## O. Request authentication mechanism — PASS

- Per-tab: login → `sessionStorage.teachflow_token` (tab-scoped) →
  `api.setToken()` (per-page in-memory) → every `fetch` sends
  `Authorization: Bearer <this tab's JWT>`.
- Captured evidence across the run: authenticated API requests all carried
  `Authorization: Bearer …`; Tab A's bearer set and Tab B's bearer set are
  **disjoint** (distinct JWTs, different `sub` claims); 0 requests carried cookies.
- Server-side, each token resolves to its own user (§R).

## P. Same-browser-context results — PASS (43/43)

- A = teacher (`/dashboard`), B = school admin (`/school-admin`), C = platform
  admin (`/platform-admin`) authenticated **simultaneously** in one context/origin.
- Reload A keeps teacher; reload B keeps school admin.
- A logout → A alone lands on `/login` with its storage cleared while an immediate
  B API call returns **200 as `accept-sa-0001`**; A re-login leaves B intact.
- Zero uncaught page errors across all three tabs.

## Q. New-tab inheritance results — PASS

- With A authenticated, a genuinely new `context.newPage()` opening `/` starts with
  **empty `sessionStorage`** (no token/user) — no inheritance.
- Direct navigation of a new page to protected `/dashboard` ends at `/login`
  unauthenticated — no inherited identity.
- After explicit login, C became platform admin while A and B kept their identities
  (three coexisting sessions).

## R. API data-isolation results — PASS

- In-tab `GET /api/auth/me` (using that tab's own token): A → `200 accept-teacher-0001`,
  B → `200 accept-sa-0001`, C → `200 accept-pa-0001` (also after every reload).
- Node-side cross-check with the captured per-tab tokens returned the same
  distinct ids/emails — server-resolved, not UI-asserted.

## S. Logout-isolation results — PASS

Hard requirement met: right after A's logout, B's authenticated API call succeeded
(`200`, `accept-sa-0001`), B's token remained present, and B's page was untouched —
no 401, no 403, no redirect.

## T. Role-isolation results — PASS (server-side, nothing loosened)

| Endpoint | Teacher (A) | School admin (B) | Platform admin (C) |
|---|---|---|---|
| `GET /api/platform-admin/dashboard` | 403 | 403 | 200 |
| `GET /api/auth/users` | 403 | 200 | (not asserted) |

Role boundaries verified against the live backend with each tab's own bearer token.

## U. Session-expiration results — PASS (with INTENTIONAL note)

- Corrupting **only Tab A's** stored token caused A's next API call to fail → A
  alone was logged out (storage cleared, redirected to `/login`), while B and C
  continued to resolve `200` with their identities — invalid-session rejection is
  tab-isolated.
- **INTENTIONAL:** wall-clock JWT expiry is a server config
  (`JWT_ACCESS_TOKEN_EXPIRE_MINUTES`) not directly expirable per tab from e2e;
  expiry rejection is covered by `decode_token` 401 handling and backend tests.
  Password-change invalidation (`pwv`) remains server-wide by design (unchanged).

## V. Cross-tab broadcast audit — PASS

- Source grep across `frontend/src`: `BroadcastChannel` = 0, `window.addEventListener("storage"` = 0, `document.cookie` = 0, logout-broadcast/global-auth-store patterns = 0.
- Behavioral proof: A's login did **not** log B in (B was unauthenticated before its
  own login), and A's logout did **not** log B/C out (§S).
- Unrelated cross-tab/local functionality intentionally untouched: non-auth
  `localStorage` preferences (`schemeknit.ai_mode`, PWA dismiss) and the Electron
  per-window IPC menu listener.

## W. Security verification — PASS

- **No passwords in `sessionStorage`** — only the signed access token and the
  non-secret user object (id/email/name/role); no password, hash, or backend secret
  anywhere in frontend storage.
- **Backend stays authoritative:** user id/role come from the verified JWT
  (`jwt.decode` with server secret) + DB lookup; the frontend never supplies an
  identity header that is trusted on its own.
- **Role checks remain server-side** (`require_admin`, `require_platform_admin`,
  etc.) — re-proven live in §T with zero loosening.
- **Logout/invalid/expired sessions rejected:** logout drops only the owning tab's
  token; tampered/invalid tokens are rejected 401 (§U) and cleared only in the
  failing tab.
- **Tradeoff documented:** the bearer JWT is held in tab-scoped `sessionStorage`
  (per-tab, not origin-shared). This is strictly narrower than the previous
  origin-shared `localStorage`; architecture deliberately unchanged otherwise —
  no switch to cookies/sessions (which would *introduce* a shared credential).
