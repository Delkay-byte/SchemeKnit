# BATCH 4 — APP CONSISTENCY, CLEANUP & CLOSURE REPORT

Final batch of the SchemeKnit UI program. Repository-wide consistency pass over
the authenticated application: visual system, navigation/route integrity,
states, forms, tables, responsive behavior, accessibility, dead/duplicate UI,
and microcopy — plus a new closure gate, full regression, and sign-off.
**After Batch 4 the application UI system is CLOSED (no Batch 5).**

## A. Mandate and constraints honored

- No redesign: no new visual language, no landing/auth changes, no replacement
  of approved systems (Batch 1–3 artifacts untouched except documented fixes).
- No business logic / API contract / schema / permission / auth / generation /
  billing / curriculum changes. One backend change was made because it was
  UI-blocking (see section E) — a pure route-declaration reorder with zero API
  contract change.
- Existing gate assertions were never weakened; every previously green gate is
  green again after the changes.
- Findings were classified A (fix now) / B (intentional) / C (out of scope)
  before editing; exclusions are documented in section L.
- Screenshots and gate output directories were never staged or committed.

## B. Findings classification (inventory → decisions)

| # | Finding | Class | Disposition |
|---|---------|-------|-------------|
| 1 | `/upgrade` had no entry point anywhere (dashboard sentence was plain text) | A | Dashboard Free Tier note now links to `/upgrade` |
| 2 | Upgrade CTA "Contact School Admin" pointed at `/login/school-admin` (a login screen) | A | CTA row → `View Plans & Payments` → `/payments` + `Maybe Later` → `/dashboard` |
| 3 | `(app)` route group had no auth guard (7 pages unguarded vs 3 self-guarded) | A | Uniform gate added to `(app)/layout.tsx` (school-admin pattern) |
| 4 | `Licence` / `No active licence` on platform-admin school detail | A | → `License` / `No active license` |
| 5 | Quota notice on generate was a hand-rolled blue box | A | → shared `Banner tone="info"` (keeps `data-quota-banner`) |
| 6 | Allocation statuses were ad-hoc colored spans | A | → `StatusPill` (Scheduled=success, Carried forward=info, Needs review=warning) |
| 7 | Generate lesson-review labels not associated with their inputs | A | `htmlFor`/`id` added + focus ring on the dense text inputs |
| 8 | Change-password labels not associated (3) | A | `htmlFor`/`id` added |
| 9 | Payments silent load failure (`console.error` only) | A | Fatal error → early-return `Banner tone="danger"` + `Try Again` retry |
| 10 | Payments `Your Name *` manual asterisk instead of `Field required` | A | `Field label="Your Name" required` |
| 11 | Upload accents `from-amber-400 to-orange-400` / `from-green-500 to-emerald-500` off-palette | A | → solid `bg-amber-400` (warning) / `bg-green-500` (success) per license-page precedent |
| 12 | License page inactive notice hand-rolled amber box | A | → shared `Banner tone="warning"` |
| 13 | `PasswordInput` base used legacy `px-3 py-2 border rounded-md` (mismatched field height on settings) | A | Base aligned to shared `Input` primitive via `cn()` (auth overrides unchanged) |
| 14 | Templates sample-file dropzone not keyboard accessible | A | `role="button"`, `tabIndex`, `aria-label`, Enter/Space handler + focus ring |
| 15 | `GET /api/payments/plans` shadowed by `/{payment_id}` (404 "Payment not found") | A | Backend route reorder (section E) |
| 16 | `/admin` legacy alias (redirect + standard spinner) | B | Kept — behaves consistently, no entry links to it, bookmark-friendly |
| 17 | Platform-admin orange stat numbers (Expiring soon / Expired) | B | Kept — semantic warning colors |
| 18 | Payments status icon + StatusPill pairing | B | Kept — intentional emphasis |
| 19 | Generate allocation micro-table & templates wizard mapping table are raw `<table>` | B | Kept — dense nested tables inside `overflow-x-auto` wrappers |
| 20 | Header `user.is_admin \|\| role==='school_admin'` legacy condition | B | Kept — harmless post-v004-migration; still correct for old rows |
| 21 | Uniform full-page loaders (`h-12 border-b-2 border-primary`) | B/keep | Kept — the consistent pattern (verified uniform across all pages) |
| 22 | Empty-state copy varies between pages | B | Kept — surface-appropriate wording, all rich/illustrated |
| 23 | Landing page ad-hoc chips, landing/auth copy variants | C | Out of scope (public/auth surfaces closed in Batches 1–2) |
| 24 | Legal pages (`/data-retention`, `/license-subscription`) raw content tables | C | Out of scope — static legal documents in `LegalPageLayout` |
| 25 | `setup`/`signup`/`reset-password` spinner accents (violet etc.) | C | Out of scope — Batch 1–2 auth theme |
| 26 | Comment-only legacy mentions (`FREE TEACHER` in dashboard comment, server-message comment) | B | Left — not user-visible |

## C. Teacher application surfaces (fixes)

- `dashboard/page.tsx` — Free Tier allowance note: "Upgrade to Teacher Pro" is
  now a real link to `/upgrade` (closes the orphan-route finding).
- `upgrade/page.tsx` — CTA card routes to `/payments` (individual subscription
  path) and keeps the dashboard exit; the login-screen CTA is gone. The
  already-pro branch (visible for the acceptance Teacher Pro account) is
  unchanged.
- `payments/page.tsx` — load failures render an early-return danger banner with
  a working `Try Again` retry (`data-payments-error`); `Your Name` uses
  `Field required`.
- `generate/[id]/page.tsx` — quota notice via `Banner tone="info"`, allocation
  statuses via `StatusPill`, lesson-review label/input association + focus
  rings.
- `upload/page.tsx` — multi-subject (warning) and success accents normalized to
  palette solids.
- `templates/page.tsx` — sample-file dropzone keyboard accessible.
- `settings` benefits from `change-password.tsx` label fixes and the
  `PasswordInput` primitive alignment (fields now match `Input` exactly).

## D. Administration surfaces (fixes)

- `(app)/layout.tsx` — uniform auth gate: while the session restores show the
  standard loader (never a blank screen); logged-out visitors are sent to
  `/login`. Logged-in access to every `(app)` route is unchanged, so all
  authenticated gates behave as before.
- `(platform-admin)/platform-admin/page.tsx` — `License` spelling fixed in the
  school-detail license block.
- `(school-admin)/school-admin/license/page.tsx` — inactive-license notice via
  shared `Banner tone="warning"`.

## E. Backend fix (UI-blocking)

- `backend/src/routers/payments.py`: `GET /plans` was declared **after**
  `GET /{payment_id}`, so FastAPI's declaration-order matching routed
  `/api/payments/plans` into `get_payment("plans")` → **404 "Payment not
  found"**. The plans list had never been reachable; the payments page could
  never render plan cards or open the purchase flow (older gates only tolerated
  its absence).
- Fix: moved the `/plans` handler **above** the `/{payment_id}` catch-all with
  a comment documenting the ordering constraint. No schema, auth, or response
  shape change; `/config` and `/history` were already declared before the
  catch-all; `/admin/*` paths are multi-segment and unaffected.
- Verified: `GET /api/payments/plans` → 200 with seeded plans; the payments
  page now renders all plan cards and the purchase form flow.

## F. Shared primitives usage after Batch 4

- `Banner` — quota notice (info), inactive license (warning), payments load
  error (danger), settings/template errors (pre-existing).
- `StatusPill` — allocation statuses now match the dashboard/lessons/platform
  convention.
- `Field` — payments submit form fully on `Field`/`htmlFor` with `required`.
- `Input` primitive — `PasswordInput` base now inherits its exact styling via
  `cn()`; auth call-site overrides unaffected.
- Label association is complete across the authenticated app: every `<label>`
  either carries `htmlFor` or wraps its control (runtime-audited by the
  closure gate).

## G. DOM markers used by the closure gate

- New: `data-payments-error` (payments load-error banner + retry).
- Existing reused: `data-app-header`, `data-page-header`, `data-upgrade-cta`,
  `data-already-pro`, `data-plan-card`, `data-submit-payment`,
  `data-quota-banner`, `data-app-mobile-nav` anchors, plus `role="tablist"`
  surfaces on both admin consoles.

## H. New gate: `frontend/e2e/app-closure-acceptance.js` (93 checks)

Coverage areas (deterministic, reuses the standard auth helpers):

- **A** entry routes + logged-out guard on `(app)` (`/dashboard`, `/upload` →
  `/login`)
- **B** header parity, primary nav routes, settings entry, aria-current
- **C** workflow route reachability with PageHeaders + lesson detail
- **D** every header nav href live; `/admin` legacy alias resolves
  role-appropriately
- **E** upgrade ↔ payments wiring (static pins + branch-aware runtime) and the
  deterministic payments error state (route-abort → banner → retry clears)
- **F** label association runtime audits + static change-password pin
- **G** static hygiene: no `confirm()`, no raw `<select>/<textarea>`
- **H** payment history table or empty state; platform data tables
- **I** school-admin 4-tab subnav, Add Teacher dialog focus/Escape
- **J** platform-admin 9 tabs, PageHeader, no `Licence` on screen
- **K** deterministic error/empty states (payments abort flow)
- **L** overflow @1440/@1024/@390 across the full teacher surface + admins
- **M** mobile nav open/close with links
- **N** accessible button names + single `h1` per page
- **O** static pins for every Batch 4 fix (upgrade link, CTA hrefs, Banner
  conversions, License spelling, upload accents, PasswordInput primitive,
  `(app)` gate)
- **P** zero page errors across the whole run

Result: **93 pass, 0 fail** (runs in ~1.5 min; teacher-account branch notes are
logged as explicit skips, never as passes).

## I. Full regression (all green, this session)

| Gate | Result | Notes |
|------|--------|-------|
| app-ui | 53 / 0 | +3 vs Batch 3 (payments surfaces now reachable) |
| app-chrome | 72 / 0 | unchanged |
| app-surfaces | 109 / 0 | +4 (plan cards + submit form activate) |
| login-grid | 476 / 0 | unchanged |
| deep-journey | 21 / 0 | unchanged |
| download (bundled) | 14 / 14 | unchanged |
| **app-closure (new)** | **93 / 0** | Batch 4 closure gate |
| hero (backend DOWN) | 151 / 0 | unchanged |
| auth-role (backend DOWN) | 131 / 0 | unchanged |
| `npx tsc --noEmit` | clean | |
| `npm run build` | exit 0 | |
| overflow 390/430/768/1024/1440 | none | capture pass across 3 roles × 14 routes |

## J. Screenshots and overflow

- 42 screenshots captured into `frontend/e2e/app-closure-acceptance/`
  (untracked, per policy): 3 roles × routes × {1440, 1024, 390}.
- Visually inspected: payments (plan cards render after section E fix),
  upgrade (already-pro branch), settings (password fields match Input
  primitive), generate, license, platform-admin, upload, mobile dashboard —
  all consistent with the approved system.
- Overflow: **none** at 390/430/768/1024/1440 on every captured route.

## K. Static checks and code health

- No `confirm()`/`prompt()`/`alert()` calls, no raw `<select>/<textarea>`
  (case-sensitive), no TODO/coming-soon notices, no duplicate headers, no
  unused components, no dead hrefs/push targets (re-verified this batch).
- `npx tsc --noEmit` clean; production build green; no debug console output
  added (`console.error` only in failure paths).
- `frontend/tsconfig.tsbuildinfo` restored to the committed state after builds.

## L. Explicit exclusions (deliberate, class C)

- Landing page and auth screens (closed in Batches 1–2): their chips, copy
  variants, and themed spinners were left untouched.
- Legal pages (`/data-retention`, `/license-subscription`): static document
  content inside `LegalPageLayout` — out of app-UI scope.
- Comment-only legacy wording (e.g. old "FREE TEACHER" reference in a
  dashboard comment) — not user-visible.
- Server-owned error strings surfaced verbatim by the API.

## M. Environment and acceptance data notes

- Acceptance teacher is on **Teacher Pro** (`/api/auth/my-plan`), so the
  upgrade page renders its already-pro branch and the dashboard Free Tier note
  is hidden at runtime; both free-branch changes are pinned by static checks
  and verified in source.
- Product plans were always seeded in the database but unreachable until
  section E; the payments page now renders Acceptance/Free/Teacher Pro plan
  cards and the purchase flow is exercised by the closure gate.
- Backend restarted with the standard CORS set; frontend served from
  `.next` build on `:3003`; hero/auth-role ran backend-down per their
  contracts, then the backend was restored.
- Known external limitation unchanged: system Chrome reports non-uvicorn 204s
  for ZIP token navigations — download acceptance runs its `bundled` channel
  (14/14).

## N. Bug fixes and repairs during Batch 4

- Backend `/api/payments/plans` route shadowing (section E) — the one
  substantive defect found, discovered by the new gate's deterministic
  payments error flow.
- Closure-gate calibration (gate-side, not app-side): trailing-slash URL
  normalization for the `/admin` alias wait, prefix selectors for
  `/settings/` hrefs, auth-gated render waits (settings/upgrade), branch-aware
  upgrade assertions (Pro account), and a post-retry wait before the history
  check.

## O. Explicit non-changes

- No route added/removed/renamed; `/admin` alias retained.
- No visual restyle of any Batch 1–3 surface; changes are primitive adoption,
  palette-consistent accents, and text/microcopy only.
- Header, PageHeader, Tabs, ConfirmDialog, Table, StatusPill, Banner, Field,
  blueprint background: definitions untouched (only call-site adoption).
- No gate assertions weakened; no tests skipped (branch skips are logged
  explicitly in gate output).

## P. Commits (Batch 4)

1. `fix(app-ui): final consistency and route cleanup` — 11 frontend source
   files + `backend/src/routers/payments.py` (route-order fix).
2. `test(app-ui): add batch 4 closure acceptance` —
   `frontend/e2e/app-closure-acceptance.js`.
3. `docs(app-ui): add batch 4 final report` — this document.

Pushed to `origin/main`; `git rev-parse HEAD` == `git rev-parse origin/main`.

## Q. Verification commands

```bash
# frontend (after build; server on :3003)
node e2e/app-ui-acceptance.js http://localhost:3003
node e2e/app-chrome-acceptance.js http://localhost:3003
node e2e/app-surfaces-acceptance.js http://localhost:3003
node e2e/login-grid-acceptance.js http://localhost:3003
node e2e/deep-journey-acceptance.js http://localhost:3003
node e2e/app-closure-acceptance.js http://localhost:3003   # Batch 4 closure gate

# download (bundled channel)
TF_WEB_URL=http://localhost:3003 \
TF_TEACHER_EMAIL=accept.teacher@schemeknit.test \
TF_TEACHER_PASSWORD='Accept#2026' \
TF_SCHEME_ID=b28921de-1a7b-40af-879c-ebb358a598e2 \
node e2e/download-acceptance.js bundled

# hero + auth-role require the backend DOWN:
node e2e/hero-v3-acceptance.js http://localhost:3003
node e2e/auth-role-design-acceptance.js http://localhost:3003

npx tsc --noEmit
npm run build
```

## R. Next step

**None — the application UI system is CLOSED.** Batch 4 is the final batch:
all surfaces are consistent, all routes reachable and guarded, all gates green,
and the closure gate stands as the permanent regression contract for the
application chrome, workflows, states, forms, tables, responsiveness,
accessibility, and Batch 4 fixes. There is no Batch 5.
