# Entitlement and Download Remediation

Status: implemented and verified. This is the single source of truth for the
behaviour promised by `backend/src/entitlements.py` and the export download
flow (`backend/src/routers/generation.py`).

## 1. Scope

* A **server-authoritative FREE/PRO plan** for individual teachers with an
  admin activation workflow (activate, revoke, extend) and an audit trail.
* **Working DOCX and PDF downloads** for every plan, and ZIP export for PRO,
  delivered as real files through one-time, worker-agnostic download tokens.
* **Teacher-safe errors**: a denied or failed action returns a sentence the
  teacher can act on (e.g. "ZIP export is available with Teacher Pro."),
  never a stack trace, `Failed to fetch`, or a generic "Action failed".

Explicitly out of scope (unchanged by this work): payment gateways, license-key
redemption, UI redesign, AI provider changes, auth architecture (tab-isolated
Bearer tokens in `sessionStorage` remain), and any change to the quota numbers
themselves.

## 2. How a plan is resolved

`resolve_entitlement(db, user)` is the only authority. Precedence:

1. **Active school license** → plan `PRO` (source `license`): unlimited
   lessons, batch, ZIP, PDF, unlimited AI.
2. **Active individual entitlement row** (`get_user_entitlement` returns the
   row only when `status != revoked` and `expires_at` is in the future) →
   plan `PRO` (paid edition) or Free Tier caps (free edition).
3. **Nothing applicable** → Free Tier defaults.

Lifecycle overlay: when a raw row exists but is revoked or expired, the plan
label stays **FREE** — a revocation never grants a capability — while `status`
reports `revoked` / `expired` so the teacher sees *why* they are on FREE
(`revoked_by`, `revoked_at`, `expires_at` are surfaced too).

Public fields added by v028 and returned by `GET /api/auth/my-plan`:

| Field | Meaning |
|---|---|
| `plan` | `FREE` or `PRO` (never invented client-side) |
| `status` | `active` \| `expired` \| `revoked` |
| `plan_source` | `free` \| `admin` \| `payment` \| `license` \| `activation_code` (distinct from the legacy `source` key: `individual` \| `school` \| `free`) |
| `starts_at`, `activated_at`, `activated_by` | activation audit |
| `revoked_at`, `revoked_by` | revocation audit |

The frontend reads these only from `/my-plan`; there is no client-side storage
of plan state and no request field that can influence it (covered by
`test_entitlement_has_no_client_input_path`).

## 3. Admin workflow (RBAC)

All three endpoints live on the platform-admin router and require
`require_platform_admin` (a teacher calling them gets 403 —
`test_admin_endpoints_require_platform_admin`):

* `POST /api/platform-admin/individual-teachers/activate`
  `{ teacher_id, product_plan_id, duration_days | starts_at/expires_at }` —
  upserts the teacher's row to edition `teacher`, `status=active`,
  `source=admin`, stamps `activated_by/activated_at`, applies
  `PRO_FEATURE_DEFAULTS` when no product plan features apply.
* `POST .../individual-teachers/{teacher_id}/revoke` — sets
  `status=revoked` with `revoked_by/revoked_at/reason` (row is kept, never
  deleted, so the audit trail survives).
* `POST .../individual-teachers/{teacher_id}/extend` — pushes `expires_at`
  out; clearing an expiry on a revoked plan re-activates it.

The platform-admin **teachers tab** renders the roster with plan/status/source
per teacher and the activate/revoke/extend actions.

## 4. Quota policy — deliberately UNCHANGED

Granting PRO flips the edition (which lifts the caps because they are keyed to
`edition == "free"`); it does not invent new allowances.

| Capability | Free Tier | PRO (individual) | School license |
|---|---|---|---|
| Lesson plans | **5 per calendar month** (server ledger, renews on the 1st) | stored `generation_limit`, 0 = unlimited | unlimited |
| AI generations | **5 per calendar month** (`ai_generation_periods` ledger keyed `YYYY-MM`, server clock) | stored `ai_credits`, 0 = unlimited | unlimited |
| DOCX export | yes | yes | yes |
| PDF export | yes | yes | yes |
| ZIP (batch) export | **no — 403** "ZIP export is available with Teacher Pro." | yes | yes |
| Custom templates | 1 | stored limit | ≥10 |

**Documented decision — revoked/expired PRO:** the row stops resolving, so the
account falls back to Free Tier lesson quota (5/month) *and* AI is denied with
the standard entitlement message (`_entitlement_ai_decision(None)` → reason
`no_entitlement` → 403 `AI_ENTITLEMENT_REQUIRED`). This matches the
pre-existing expiry semantics: a lapsed plan grants no AI. The entitlement
harness asserts this exact behaviour
(`Revoking PRO returns teacher to FREE`, teacher blocked from AI afterwards).

## 5. Client surfaces

* **Settings → plan card** (`[data-settings-plan]`): plan label, status,
  month-based lesson and AI quota cards — all rendered from `/my-plan`.
* **Platform admin → teachers tab**: roster + activation controls.
* **Upgrade page**: unchanged copy; shows the already-pro surface only when
  `/my-plan` says `is_active`.

## 6. Download architecture (the production blocker this fixes)

```
POST /api/generation/{jobId}/download-url?format=docx|pdf|zip   (Bearer)
  → pre-renders the file, issues a one-time token
GET  /api/generation/downloads/{token}                          (no header;
                                                                 the token IS the credential)
  → 200 + Content-Disposition: attachment + real bytes
```

* **Tokens are persisted** in the `download_tokens` table (migration v029).
  The previous implementation kept them in a process-local dict; on a
  multi-process deployment (Render) the issuing POST and the browser's GET can
  hit different workers, so the token was missing and the download 404'd.
  Persisting makes the handoff worker-agnostic.
* Properties: `secrets.token_urlsafe(32)`, bound to `user_id` + `job_id`,
  **600 s TTL**, **single use** (`used_at` set on first consume; a second use
  404s), expired rows are deleted on read. A cross-user or replayed token is
  rejected (asserted in `TestDownloadTokenPersistence` and the HTTP-level
  single-use / foreign-Bearer tests).
* Entitlement is enforced **at issue time** on the POST: ZIP requires
  `can_export_zip` (PRO), DOCX/PDF are open to Free Tier.
* The browser navigates directly to the token URL (plain navigation, no
  Authorization header) so download managers intercept it cleanly and the page
  never misreads the body as `Failed to fetch`.
* Controlled PDF failure: when the server has no LibreOffice converter the
  POST returns a clear 503-style message that the UI surfaces verbatim
  ("PDF export requires a document converter on the server…"), never a stack
  trace.

## 7. Migrations

| Version | Change | Safety |
|---|---|---|
| `v028_entitlement_status_source` | Adds `status`, `source`, `starts_at`, `activated_by/at`, `revoked_by/at`, `revoked_reason` to `entitlements`; backfills `status` from the existing `expires_at` (elapsed → `expired`, else `active`) and `source='free'` where NULL | additive, nullable/defaulted only; nobody is upgraded to PRO by the backfill |
| `v029_download_tokens` | Creates `download_tokens` (+ user and expiry indexes) | additive; `down` drops the table |

Both are idempotent (guarded by column/table existence checks) and are
applied by the standard migration runner at backend start.

## 8. Verification

* **Backend**: `pytest` — includes `test_entitlement_admin_downloads.py`
  (free defaults, activation/revoke/extend, RBAC, token persistence,
  single-use, user-binding, expiry, real-bytes HTTP download,
  foreign-Bearer rejection) and the updated token tests in
  `test_final_web_ux.py`.
* **Browser (local)**: `frontend/e2e/entitlement-download-acceptance.js` —
  logs in as a FREE teacher, verifies the generated plan renders real content,
  downloads DOCX + PDF with byte-signature checks (`PK`, `%PDF`), checks
  refresh and second-tab downloads, blocks self-upgrade, then admin-activates
  PRO, re-checks the teacher view, and revokes back to FREE.
* **Gates**: the regular acceptance gates (app-ui/chrome/surfaces/closure,
  login-grid, deep-journey, download, tab-isolated-auth, basic13, wapef, kg,
  nursery, hero-v3, auth-role-design) run green alongside it.

## 9. Security summary

* Plan state is server-written only; no client flag, storage key, or request
  field can grant PRO.
* Admin endpoints: `require_platform_admin` dependency on every route.
* Download tokens: unguessable, user-bound, short-lived, single-use; exports
  additionally check job ownership at issue time.
* Errors returned to teachers are stable, user-facing strings; internal
  reasons (e.g. `no_entitlement`, `credits_exhausted`) stay in logs.
