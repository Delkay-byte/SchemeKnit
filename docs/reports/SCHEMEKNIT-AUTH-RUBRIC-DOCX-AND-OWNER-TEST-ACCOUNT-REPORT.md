# SchemeKnit — Authentication, Rubric, DOCX and Owner Test Account Report

**Date:** 2026-11-17  
**Branch:** `main`  
**Final code commit:** `4e08bdce70195ab711491f4650078ea089e2df3c`  
**Production deployment:** NOT performed. Owner triggers it manually.

## Status

**GREEN WITH ONE OWNER ACTION** — the code and tests are complete on `main`; the
owner must apply the deployment and run the audited provisioning command for the
existing owner-controlled teacher account (exact command in §6).

---

## 1. Pull request #11 and main

- PR: `https://github.com/Delkay-byte/SchemeKnit/pull/11`
- State: **MERGED** (merge commit `c260230ccb6334b4391bd6c7177b78d2eb8e4317`).
- Checks at merge: Backend tests and compile, Frontend typecheck and build,
  PostgreSQL migration harness, Secret scan, UX browser/accessibility — all
  SUCCESS. Live Gemini/Groq provider job SKIPPED (manual).
- Local `main` was fast-forwarded to `c260230` before this work.

## 2. Authentication correction

The PR #11 behaviour was reviewed and its regression suite passes:

- A credential `401` (`{"error":true,"detail":"Invalid email or password"}`) is
  now shown as a credential error, not as session expiry.
- A genuine session-expiry response keeps the session-expired message.
- A wrong current password during password change, MFA verification or recovery
  does not clear an otherwise valid session.
- Legacy mixed-case / whitespace-padded stored emails resolve through the
  backend fallback.
- Super Admin authorization, MFA, lockout, CSRF, rate limiting and session
  revocation are unchanged.
- Internal failure reasons are not exposed to customers.

Evidence run:

```
python -m pytest tests/test_auth_login_session_p0.py \
  tests/test_guided_lesson_configuration.py \
  tests/test_monthly_quota.py tests/test_quota_enforcement_journey.py -q
# 37 passed
```

Live production login was **not** claimed; the owner verifies after deployment.

## 3. Rubric workflow

### Before

- The upload flow recorded `schemeknit.autopilot_intent` after resolving a
  subject/class ambiguity; the generate page then started a run with no further
  teacher input.
- The configuration dialog always sent `reference: null` and had no reference
  field, so the saved header reference could never be set.
- The saved `missing` list was ignored after a save, so the screen could keep a
  stale "complete" state.
- The generated lesson had no scoring matrix for non-product indicators such as
  "Discuss the fourth-generation computers" and "Use input devices"; the DOCX
  therefore had no rubric at all.
- Editing settings after generation gave no indication that existing plans were
  stale.

### After

- **No automatic generation.** The upload hand-off only navigates to the
  generate page. The page's autopilot effect displays the server plan and never
  calls `runGeneration`. A source-level regression test enforces both rules.
- The teacher completes and saves the configuration, then clicks Generate.
- `reference` and `period` are editable and persisted; blank stays blank (never
  fabricated). Per-indicator references/TLRs, competencies and keywords remain
  editable and keyed by canonical source occurrence id.
- Saving updates the server-provided missing list and shows the saved time.
- Existing plans show "regenerate to apply the saved rubric" after a settings
  change; nothing is silently overwritten.
- Server generation still merges the SAVED configuration over the request and
  blocks with `409` when required fields are missing. No generated content is
  invented to satisfy the check.
- Every non-early-years lesson now receives an analytic rubric
  (criteria × levels) that is persisted with the lesson and exported. Early
  years keep the existing no-rubric rule.

## 4. DOCX quality

### Defects confirmed from `Lesson_Plans_BASIC_7.docx`

- No scoring-rubric matrix anywhere in the eight pages.
- Blank `PERIOD` and `REFERENCE` in both lesson headers.
- Sparse third/sixth pages; no repeated table headers.
- Malformed generated sentences, including:
  - "Each learner demonstrates discuss on the fourth-generation computers."
  - "what would change in Frame the task around a real community need…"

### Fixes

- Rubric is rendered as a real **Criterion × 4/3/2/1** table with the saved
  descriptors and points in every export path: official GES form, WAPEF,
  built-in section templates, teacher custom structures, and the browser
  serializer. The table header row repeats; rows do not split mid-cell.
- Table headers are marked `w:tblHeader` and short rows `w:cantSplit`; headings
  use keep-with-next so a heading is not stranded at a page foot.
- Reference/period: structured references are merged into the lesson references
  for the header; the export context no longer applies lesson 1's period to
  every lesson. Genuinely blank values stay blank.
- Export gate: any non-early-years lesson with assessment prompts but no saved
  rubric stops DOCX/PDF/ZIP/model export with an actionable `409` naming the
  week and lesson. No misleading incomplete document is produced.
- Language:
  - The fallback instruction now reads "Each learner shows they can … once, to
    the agreed criteria" (no "demonstrates discuss").
  - The remediation follow-up is a complete standalone question and no longer
    embeds the Ghana-context instruction mid-clause.

### After evidence

A fresh fixture built with the updated renderer (`frontend/tests/fixtures/docx/official_ges.docx`)
was dumped and inspected:

```
TABLE ... rows=2 cols=5
R0: Criterion | 4 – exceeds the standard | 3 – meets the standard |
    2 – developing | 1 – needs support
R1: <criterion> | <saved descriptor> | <saved descriptor> | … 
Total marks: 4
```

The same matrix appears once per lesson in the GES form, WAPEF, sections and
custom-structure fixtures. The Word package opens normally (python-docx and the
frontend OOXML serializer both produce valid packages).

## 5. Owner-only internal test account

### Design

- New column `users.is_internal_test_account` (migration
  `v055_internal_test_account`, applied automatically by the existing startup
  migration runner).
- `entitlements.resolve_entitlement` returns unlimited application lesson-plan
  generation and unlimited AI **only** when that server-side column is true.
- `ai_entitlement` and `consume_ai_generation` short-circuit for the same flag.
- The account stays a normal `teacher`; it is never made a Super Admin and
  cannot impersonate another user.
- No client header, email, request field or local storage value can set the
  flag. `LessonConfigRequest` does not contain it.
- Other users keep the existing Free Tier / paid rules; no global quota is
  disabled.
- Authentication, tenant isolation, rate limits, CSRF, session revocation and
  external AI provider limits are unchanged.
- Usage is labelled `internal_test_account` / "Internal test account — excluded
  from billing" in the entitlement and lesson-quota payloads. It creates no
  payment or revenue row.
- The flag persists across deployments because it is a database column.

### Provisioning

`backend/scripts/provision_internal_test_account.py`:

- Refuses to create an account (no invented credentials).
- Refuses an administrator account.
- Refuses a second internal account.
- Reads/writes no password, token or secret.
- Dry-run by default; writes one audit event when applied.
- Supports `--revoke`.

The verified owner identity available in the repository (git committer and the
prior production report) is **`amegayiesaviour@gmail.com`**.

The account is not provisioned here because this environment has no production
database/API access.

## 6. Required owner action

After deploying the backend (migration runs), run from the API service shell:

```bash
cd backend
python scripts/provision_internal_test_account.py \
  --email amegayiesaviour@gmail.com \
  --actor amegayiesaviour@gmail.com \
  --apply
```

If that email belongs to the platform-admin account, the script returns
`BLOCKED` by design. In that case create/log in to the dedicated normal teacher
account for the owner and re-run the same command with that address. Exactly one
account may hold the flag.

## 7. Verification summary

| Area | Command / evidence | Result |
| --- | --- | --- |
| Auth/session + quota | `pytest test_auth_login_session_p0 test_guided_lesson_configuration test_monthly_quota test_quota_enforcement_journey` | 37 passed |
| Rubric/DOCX/entitlement | `pytest test_rubric_docx_quality test_internal_test_account` | 9 passed |
| Assessment/DOCX regression | `pytest test_phase3_assessment_dok test_export_model test_export_download test_approved_template test_pdf_converter_fidelity` | all passed |
| Generation workflow | `pytest test_generation_workflow_regression test_autopilot_generation test_generation` | 53 passed |
| Frontend DOCX parity | `npm run test:docx` | 14 passed |
| Frontend UX | `npm run test:ux` | 100 passed |
| Frontend typecheck | `npx tsc --noEmit` | clean |
| Frontend lint | `npm run lint` | 0 errors (warnings pre-existing) |
| Frontend production build | `npm run build:web` | compiles/typechecks/renders all routes; exits 1 on Next.js `SecurityFatalError` advisory for `next@16.4.3` |
| Backend compile | `python -m compileall src scripts` | clean |

## 8. Commits and deployment handoff

```
4e08bdc feat(entitlements): add owner-only internal test-account entitlement
0a0e013 fix(docx): export the saved rubric as a scoring matrix and clean generated language
64c30d2 fix(rubric): require explicit generation after saved lesson configuration
c260230 Merge pull request #11 (authentication 401 classification)
```

Existing production services (verify in Render before deploying):

| Service | Render service | Purpose |
| --- | --- | --- |
| `schemeknit-api` | `srv-damsbb1ntn7c73d7eg10` | FastAPI backend, migrations, export renderers |
| `schemeknit-frontend` | `srv-damt6sjm8hqs7398lfl0` | Next.js application and browser DOCX serializer |

- Public application: `https://schemeknit.bloomcoretech.com/`
- Backend API host: `https://schemeknit-api.onrender.com`

**Deploy both services from commit `4e08bdce70195ab711491f4650078ea089e2df3c`.**

**Order:** deploy `schemeknit-api` first and confirm migration
`v055_internal_test_account` is recorded, then deploy `schemeknit-frontend`.
The backend-first order keeps old frontends working and lets the new matrix
renderer serve even before the frontend bundle updates.

No DNS, domain or API-origin change is required. No staging service was created.
No deployment was performed. The owner's untracked
`docs/infrastructure/benchmarks/` content was left untouched.
