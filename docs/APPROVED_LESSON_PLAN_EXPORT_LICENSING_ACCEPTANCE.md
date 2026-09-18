# Approved Lesson Plan + Export + Licensing — Milestone Acceptance

Date: 2026-09-16. Web app is the canonical reference. Desktop EXE was **not** touched.

## Status: PASS (with one environment-dependent item)

Backend 454/454 tests pass. TypeScript passes. Browser acceptance 13/13 in **both real
Chrome and Edge**. The single environment-dependent item is PDF *generation* on a server
with no converter — the app reports that explicitly and correctly (see §PDF).

---

## Approved template

Source: the headteacher-supplied approved weekly lesson notes. Inspected structurally
(tables, grid columns, spans, labels, phase rows), not as text.

| Item | Value |
|---|---|
| Template id / name | `tpl-approved-org-headteacher` / "Approved Organizational Lesson Plan (Headteacher Source)" |
| Table topology | `(7 × 8)` metadata · `(3 × 8)` delivery · `(2 × 3)` continuation |
| Merge map | metadata grid uses 1–5 column spans; `Reference` and `New words` span 8 |
| Phases | PHASE 1: STARTER · PHASE 2: NEW LEARNING · PHASE 3: REFLECTION (exactly three) |
| Field mapping | subject, class_level, class_size, duration, strand, sub_strand, content_standard, indicators, lesson_number, learning_objectives, core_competencies, references, keywords |
| Custom-kept, blank | `Week Ending`, `Day` (no model backing — never fabricated) |
| Not officially GES | source carries no GES/NaCCA designation; app does not claim it |

Generated DOCX from the real browser download: **12 lessons × 3 tables, every lesson
exactly `[(7,8),(3,8),(2,3)]`**, all 15 key labels present inside table cells (not
flattened to paragraphs), structural validator **PASS** with zero failing checks.
Forbidden/sample content absent.

ZIP batch output: 12 members, all 12 matching the approved topology, 0 legacy-layout
members — in both Chrome and Edge downloads.

AI structured output is validated against the approved schema before rendering; unknown
keys are dropped; invalid JSON never reaches the renderer and deterministic content is
preserved. AI OFF generates full lesson plans (verified live: 12 lessons).

---

## Downloads — root causes found

Three independent defects caused "download fails", all now fixed and regression-tested:

1. **Frontend revoked the blob object URL in the click's task.** Chrome aborts the
   download; Edge tolerates it — exactly the reported Chrome-FAIL / Edge-PASS asymmetry
   for Word. Fixed by deferring the revoke.
2. **`Content-Disposition: attachment` on a fetch-consumed response.** Chrome and Edge
   classify an attachment-dispositioned `application/zip` as a *download*, and a download
   cannot be delivered to `fetch()`. The request died the instant the response arrived
   (`TypeError: Failed to fetch`, server had answered `200` with a valid 426 KB archive).
   ZIP export therefore never saved a file in either browser. Filename transport moved to
   a CORS-exposed `X-TeachFlow-Filename` header with `Content-Disposition: inline`.
3. **Export errors were invisible in the UI.** The error banner only rendered when the
   *scheme* failed to load, so any export failure looked like a dead button. Now rendered
   whenever the page has loaded.

Also fixed while verifying: ZIP ignored the selected template (the client never sent
`template_id`), so DOCX and ZIP produced different layouts from the same selection.

| Format | Chrome | Edge |
|---|---|---|
| Word | PASS — saved, real DOCX (PK), `*.docx` | PASS |
| ZIP | PASS — saved, real archive, `*.zip` | PASS |
| PDF | PASS — controlled message shown, no stack trace | PASS |
| XLSX | PASS — 200, opens, 15 rows | PASS |

PDF converter on the test host: none (`docx2pdf` not installed, no LibreOffice) →
layer-1 **503** with the explicit "requires a document converter" message. That is the
documented behaviour. The former silent-corruption bug — falling back to the intermediate
DOCX and serving it as `application/pdf` — is fixed: the PDF path now raises
`PDFConversionError`, verifies the `%PDF-` signature, and never returns a DOCX.

---

## Licensing

Live end-to-end on the real API: Platform Admin creates school → plan → license
(`pending`, `activated_at=NULL`) → school redeems the code → license `active`,
`activated_at` set, `claimed_by_school=true`.

| Item | Result |
|---|---|
| Activation | PASS — redeem flips license to active and records `activated_at` + code |
| Platform Admin state | PASS — `status`, `effective_status`, `is_active`, `activated_at`, activation code + status, plan, expiry all server-derived per request |
| School usage | PASS — `seats_used` 0 → 1 on activation, → 2 after adding a teacher (was counting teachers only, hiding the admin account activation creates) |
| School association | PASS — school always derived from the code's license; client `school_id` never trusted |
| Replay protection | PASS — used/revoked/expired → 403, unknown → 404; first claim wins, a replacement code cannot rewrite `activated_at` |
| Suspend / reactivate | PASS — `effective_status` reflects both immediately |
| Migration | v011 adds `activated_at` / `activation_code_id` additively; verified on a copy of the production database (applies v007–v011, existing rows preserved) |

---

## Scheme lifecycle

| Case | Result |
|---|---|
| Own scheme, no generated lessons | 200, deleted, source file cleaned |
| Own scheme with generated lessons | 409, explicit message, nothing deleted — **source file preserved** |
| Not the owner | 403 |
| Missing | 404 |
| Shared storage file | kept until the last referencing scheme goes |
| Missing/unreadable file | deletion still succeeds |

---

## AI entitlement (owner decision: option (a), licence required, free tier excluded)

Verified live against the running app:

| State | AI regenerate-section | Generate with AI |
|---|---|---|
| Active licence | 200 | 200 |
| Suspended | 403 (entitlement message) | 403 (workflow licence gate) |
| Reactivated | 200 | 200 |
| AI OFF | n/a | 200, 12 lessons |

Unit-tested reasons: `school_license`, `paid_entitlement`, `no_entitlement`,
`no_active_license`, `license_expired`. The gate runs **before any provider is
constructed**, so an installed local provider (Ollama) can never grant access by itself —
asserted by a test that fails if the provider factory is even called.

---

## Verification commands

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests -q     # 454 passed
cd frontend && npx tsc --noEmit                                # clean
cd frontend && TF_SCHEME_ID=<job> npm run e2e:downloads:chrome  # 13/13
cd frontend && TF_SCHEME_ID=<job> npm run e2e:downloads:edge    # 13/13
```

## Files changed

Backend
: `src/database.py`, `src/main.py`, `src/entitlements.py`, `src/routers/auth.py`,
  `src/routers/generation.py`, `src/routers/platform_admin.py`, `src/routers/ai_regeneration.py`,
  `src/engines/pdf_export.py`, `src/migrations/v011_license_activation_state.py`

Frontend
: `src/lib/api.ts`, `src/lib/utils-display.ts`, `src/app/generate/[id]/page.tsx`,
  `src/app/platform-admin/page.tsx`, `package.json`; new `e2e/`

Tests
: new `tests/test_export_download.py`; extended `test_licensing.py`, `test_ai_production.py`,
  `test_approval_template.py`, `test_release_boundaries.py`, `conftest.py`

Docs
: new `WEB_BEHAVIOR_BASELINE_FOR_DESKTOP.md`, this file; updated
  `ROLE_AND_ENTITLEMENT_DECISION_MATRIX.md`

Not touched: `desktop/` (no rebuild, no code change), the legacy Flask/Jinja project.

## Known limitations

* PDF *generation* needs LibreOffice (or MS Word via docx2pdf) on the server. Absent that,
  users get the explicit controlled message; this is by design, not a download failure.
* The full 18-step click-through journey was exercised at the API level (upload → approve →
  configure → generate → export → structure validation). The browser harness covers the
  download/export layer, where the reported defects actually lived.
* Acceptance data lives in a disposable, gitignored environment
  (`backend/temp/ba/`), including the downloaded artefacts used for validation.
