# SchemeKnit UX Reliability — Acceptance Report

Date: 2026-11-02
Branch: `ux/teacher-workflow-reliability`
Starting `origin/main`: `b13aeec4a466c01573299c2b57f259a01ed83abd`
Commits under acceptance:

- `15b2539` — skeletons, prefill, optimistic deletes, drafts, error normalisation
- `d91d0a6` — blank-value prefills, optimistic saves, more drafts, full error coverage
- Final commit: see §2

## 1. Executive summary

The five UX reliability improvements are implemented across the teacher workspace
and the administrative areas. Ordinary page loading uses skeletons that mirror
the destination content; profile values prefill only eligible blank fields and
deliberate blanks persist; safe mutations update immediately with rollback;
supported forms recover interrupted work; and API failures use one normaliser
with teacher-facing language and functional retries.

Lesson and weekly-plan editing now use server revision tokens. A stale editor is
blocked with a 409, and the teacher chooses between the latest server version and
their local draft; the server never silently overwrites a newer record.

Recommendation: **release**, subject to the normal CI and deployment gates. The
known exclusions in §10 are acceptable for this release and are listed for
transparency.

## 2. Commits and release identifiers

| Item | Value |
|---|---|
| Starting `origin/main` | `b13aeec4a466c01573299c2b57f259a01ed83abd` |
| Feature branch | `ux/teacher-workflow-reliability` |
| Pre-release commits | `15b2539`, `d91d0a6` |
| Final feature commit | `e5733ab` |
| Production merge commit | `be7d5c8d54327a58da856e941d05fa41b8d5a6d1` (PR #6) |
| Render backend deploy | `dep-dbkh6o95efls73d5l730`, live |
| Render frontend deploy | `dep-dbkh7p8ae00c7384q9t0`, live |

## 3. Requirement status

Status labels: **Implemented**, **Tested locally**, **CI verified**, **Merged**,
**Deployed**, **Production verified**.

| Requirement | Status |
|---|---|
| Shared skeleton system | Implemented, Tested locally |
| Skeleton coverage, teacher pages | Implemented, browser-tested on dashboard; source-reviewed elsewhere |
| Skeleton coverage, admin pages | Implemented, source-reviewed |
| Profile prefill | Implemented, Tested locally, browser-tested |
| Deliberate blank preservation | Implemented, Tested locally, browser-tested |
| Restore profile default | Implemented, Tested locally, browser-tested |
| Optimistic deletion + rollback | Implemented, Tested locally, browser-tested |
| Optimistic saves (lesson/weekly/settings) | Implemented, Tested locally, browser-tested for lesson/weekly |
| Teacher account activate/deactivate | Implemented, Tested locally (policy + helper); no browser admin test |
| Licence/payment/MFA non-optimistic | Implemented by policy; unit-tested classification |
| Drafts: lesson config/editor/weekly new+edit/school settings/upload completion | Implemented, partially browser-tested |
| Draft isolation, expiry, quota, sensitive stripping | Implemented, Tested locally |
| Server-version conflict: lesson | Implemented, backend + browser tested |
| Server-version conflict: weekly plan | Implemented, backend + browser tested |
| Friendly error normalisation | Implemented, all raw `.message` catch sites removed |
| Retry actions | Implemented; browser-tested for lesson retry and dashboard/list retry |
| 404/error boundaries | Implemented, browser-tested at four widths |
| Electron isolated runtime | Implemented, Tested locally (15 checks) |

## 4. Coverage matrix

| Workflow | Implementation | Test type | Result / evidence |
|---|---|---|---|
| Dashboard load | Dashboard skeleton | Browser E2E | Skeleton visible, replaced by real content |
| Dashboard delete | Optimistic remove + rollback | Browser E2E | Immediate removal; failed delete restores + retry |
| Dashboard/list errors | Normalised 5xx + retry | Browser E2E | Friendly text, no traceback |
| Lesson config prefill | Profile name/school | Browser E2E | Both prefilled |
| Lesson config saved value | Server value wins | Browser E2E | Reopen shows saved value |
| Lesson config blank | Per-user/scheme override | Browser E2E + unit | Blank survives reopen; restore action works |
| Lesson save | Version check + `If-Match` | Browser E2E + backend | Success reconciles; stale save 409 |
| Lesson save failure | Preserve editor, retry | Browser E2E | Text preserved; retry succeeds |
| Weekly plan load/save | Saved values + version | Browser E2E | Values load; save persists |
| Weekly plan draft | Autosave + recovery | Browser E2E | Banner after refresh; value restored |
| Weekly plan conflict | 409 + choice | Browser E2E + backend | Stale save blocked; latest loads |
| Teacher account status | Optimistic toggle | Unit policy test | Allowed; rollback helper tested |
| Licence/payment/credit/MFA | Server-confirmed only | Unit policy test | Never optimistic |
| Upload completion | Server resource resume | Source-reviewed | Draft stores scheme ID only, never file bytes |
| Not found | Recovery page | Browser E2E | Four viewports, no overflow |
| Electron startup/backend | Isolated ports/userData | Electron E2E | Correct UI, backend 200, no exceptions |
| Electron draft persistence | localStorage across relaunch | Electron E2E | Draft survives close/reopen and restores |
| Explicit overwrite | Confirmed action against latest revision | Browser E2E | Server replaced only after explicit choice; second update still 409 |
| Lesson/weekly backend conflict | DB/JSON revision checks | Backend tests | Stale writes rejected without mutation |

## 5. Tests and commands

### Frontend unit

```text
cd frontend && npm run test:ux
45 tests, 45 passed, 0 failed
```

Covers drafts, baseline conflicts, prefill, overrides, optimistic policy,
optimistic sequencing/rollback, error mappings.

### Browser E2E

```text
cd frontend && npm run e2e:ux          # 16 passed
cd frontend && npm run e2e:ux:editing  # 20 passed
```

Disposable local SQLite backend (`:8100`) and local production build (`:3100`).
No production data. Coverage listed in §4.

### Electron runtime

```text
cd frontend && npm run build:desktop
SCHEMEKNIT_PYTHON=<local python> UX_WEB_URL=http://127.0.0.1:18335 npm run e2e:electron
15 passed, 0 failed
```

Ports: backend `18334`, static frontend `18335`. Isolated user-data directory:
`%TEMP%/opencode/schemeknit-electron-ux`. The run verified:

- the SchemeKnit UI, not another local application;
- non-blank renderer;
- isolated backend health 200;
- renderer uses the configured backend port;
- first-run setup + login;
- dashboard skeleton and real content;
- reload;
- settings route;
- no renderer exceptions;
- draft written to Electron localStorage;
- draft survives full app close/reopen;
- both sessions exit cleanly.

### TypeScript and builds

```text
cd frontend && npx tsc --noEmit        # pass
cd frontend && npm run build           # pass
cd frontend && npm run build:desktop   # pass (after making robots/sitemap static)
```

### Backend

```text
cd backend && python -m compileall -q src tests   # pass
cd backend && python -m pytest -q                 # full suite result below
```

Focused conflict tests: `tests/test_optimistic_concurrency.py` (5 passed).
Existing lesson-edit, authorization and architecture tests: 52 passed.

Full suite: 3,150 passed, 23 skipped, 2 failed in the first run. The two
failures were live Gemini/Groq provider tests; both passed when rerun alone
(4 min 18 s). They are external, flaky and unrelated to the files changed here.
No migrations were added.

## 6. Lesson and weekly-plan conflict scenarios

Tested in the browser against a disposable backend:

1. Draft baseline equals current server revision → normal recovery banner.
2. Server updated after recovery → conflict banner before overwrite.
3. Server updated after recovery and before save → fresh GET detects it; save
   is not attempted.
4. Stale `If-Match` sent directly → backend returns 409; stored row/file is
   unchanged.
5. Load latest version → editor shows the server value.
6. Keep my draft → local work remains editable; the server is untouched until
   the teacher explicitly chooses overwrite.
7. Explicit overwrite → confirmed action writes against the freshly read
   revision; a second update still returns 409.
8. Successful save → new revision returned and stored as the new baseline.
9. Missing baseline (legacy draft) → treated as unverified/conflict.
10. Two writers: the older save is rejected; the newer value survives.
11. Network failure during the pre-save version check → safe error, no write.

## 7. Responsive coverage

| Width | Checked |
|---|---|
| 390 px | Not-found layout, no horizontal overflow; dashboard/reduced-motion |
| 768 px | Not-found layout, no overflow |
| 1024 px | Not-found layout, no overflow |
| 1440 px | Dashboard skeleton/content, not-found layout |

Not re-tested at every width: lesson editor, weekly editor, modals, admin
tables. These use the existing responsive grids and were source-reviewed only.

## 8. Accessibility checks

Performed:

- Skeleton regions expose `role="status"`, `aria-busy`, and screen-reader labels.
- `prefers-reduced-motion: reduce` computed `animation-name: none` on skeletons.
- Toasts expose `aria-live`; error toasts use `role="alert"`; dismiss buttons
  have accessible names; actions are keyboard-focusable.
- Draft recovery/conflict/status use `aria-live` or `role="alert"`.
- Not-found page keyboard Tab reaches the recovery action.
- Form labels exist for tested fields.

Not performed: automated axe/Lighthouse audit, formal certification, full
screen-reader walkthrough, dialog focus-restoration test.

## 9. Production regression checks

Source preservation verified:

- invite-only registration policy unchanged;
- Turnstile widget, keys, hostname, action, timeout, length, replay protection
  unchanged;
- MFA enforcement path unchanged;
- authentication token storage remains tab-scoped `sessionStorage`;
- payment, credit, entitlement, referral and licence business logic unchanged;
- no new migration and no production data writes from tests;
- curriculum extraction, allocation, generation and export logic untouched.

Production verification (2026-11-02):

- Render backend `dep-dbkh6o95efls73d5l730` live on `be7d5c8d`.
- Render frontend `dep-dbkh7p8ae00c7384q9t0` live on `be7d5c8d`.
- `GET /api/health` → 200 `{"status":"healthy"}`.
- `GET /api/auth/registration-policy` → `invite_only`, invite code required.
- Registration with no Turnstile token → 428 `turnstile_required`; no account
  created.
- Public routes `/`, `/signup`, `/login` → 200; unknown route → the new 404
  page; no unexpected page-level console errors.
- No production records were created or modified.

Status: **Deployed** and smoke-tested. Teacher-authenticated production
conflict/prefill checks were not run because they would require a production
account and data changes; those were verified against the disposable environment.

## 10. Intentional exclusions and limitations

| Feature | Status | Why / impact | Alternative | Release blocker? |
|---|---|---|---|---|
| Template wizard drafts | Not implemented | The wizard contains file analysis plus generated mappings; restoring a stale mapping over a newer server template is unsafe without a template revision contract. Teacher must re-enter wizard fields after an interruption. | Server-saved templates remain available | No |
| Generation configuration drafts | Not implemented | The generate page restores authoritative job state and configuration from the server; a local draft could submit a duplicate or stale generation. | Server job resume/view/restart covers recovery | No |
| Teacher/licence/admin dialog drafts | Lesson config + school settings only | One-click or short admin dialogs have low re-entry cost; licence fields are security-sensitive. | Server values remain | No |
| Upload pre-file metadata drafts | Partial | Upload UI has no class/subject/term inputs; raw files cannot be stored. Completed uploads resume from the server scheme ID. An unfinished file must be selected again, and the UI says so. | Re-select file; completed upload resumes | No |
| Template/admin optimistic CRUD | Not implemented | Multi-step or irreversible; no reliable rollback contract. | Explicit save + server refresh | No |
| Non-idempotent retry | Not automated | Payments/registration/generation/credits are never blindly retried. | Server state check | No |
| Full responsive/a11y matrix | Partial | Time/environment; source-reviewed only for some screens. | Manual QA | No |
| Packaged installer Electron test | Not run | Acceptance used the real Electron runtime but unpackaged main process and current static export, not the NSIS installer. | Same main/preload/renderer code | No |
| Browser tested with axe | Not run | No axe dependency installed; avoided adding one. | Manual checks | No |
| Lint | Not available | Repository has no ESLint 9 flat config; `next lint` is absent in Next 16. | TypeScript + build | No |

## 11. Known risks

- Weekly-plan persistence is a JSON store protected by an in-process lock plus
  `If-Match`. Multi-process deployments could still interleave at the OS file
  level; the revision check still rejects the stale write but a torn file write
  is theoretically possible. Single-instance Render deployment is assumed.
- Draft overrides are local to one browser/profile; another device can reapply a
  profile default that was deliberately cleared on the first device.
- `remoteip`/security behaviour is untouched.

## 12. Deferred work

- Template and generation configuration drafts.
- Automated axe/Lighthouse and a full four-width matrix.
- Packaged installer acceptance and offline upgrade test.
- Durable database-backed weekly plans (out of scope).
