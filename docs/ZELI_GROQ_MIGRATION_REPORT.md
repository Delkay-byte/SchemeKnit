# Zeli (Groq) Migration — Final Report

**Date:** 2026-09-30
**Scope:** Migrate SchemeKnit's runtime AI provider to Groq, rebrand the
teacher-facing assistant as **Zeli**, preserve the 4-layer deterministic
pedagogy engine and the AI entitlement/quota behaviour, and prove both the
success and failure paths end to end — locally and in production.

**No API key appears anywhere in this report.**

---

## 1. Model

`openai/gpt-oss-120b` (Groq, native strict Structured Outputs).

Set as the default in both authoritative places, so no deployment can
accidentally run a stale model:

- `backend/src/engines/ai_provider.py` → `DEFAULT_GROQ_MODEL`
- `backend/src/config.py` → `GROQ_MODEL`
- `backend/.env.example` → `GROQ_MODEL=openai/gpt-oss-120b`

No downgrade from this model was made (or is permitted) without benchmark
evidence.

## 2. Configuration variables

`.env.example` AI block is the production template:

```env
AI_MODE=groq
GROQ_API_KEY=
GROQ_MODEL=openai/gpt-oss-120b
GROQ_BASE_URL=https://api.groq.com/openai/v1
# Historical alternative provider (not the production runtime):
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
```

- `AI_MODE=groq` is the production configuration. The owner supplies
  `GROQ_API_KEY`; it is never hard-coded, printed, or committed (the repo value
  stays empty).
- `AI_MODE=gemini` is **not** production. `GeminiProvider` remains in the
  codebase as isolated historical code and is still selectable, but the
  auto-select order is now **groq-first**, so a configured Groq key always wins
  and Gemini only resolves when Groq is unconfigured.
- The key is only ever read from the environment via the existing secret-safe
  `_env` path.

## 3. Structured-output implementation

Strict, per-section JSON Schema only — never a whole lesson.

- A `schema: Optional[dict] = None` parameter was added to the base
  `generate_structured` and to **every** override (Gemini, Groq, OpenAI,
  OpenCodeZen, Ollama; MiniMax inherits the base). Only Groq consumes it; the
  others ignore it, so no other provider changed behaviour.
- `GroqProvider._chat` sends it as a strict
  `response_format: { type: "json_schema", json_schema: { strict: true, ... } }`
  request — the model is physically incapable of returning anything outside the
  schema.
- `_section_json_schema(section)` (in `ai_regeneration.py`) builds the canonical
  shapes, reused by every call:
  - flat sections → `{ "type": "object", "properties": { <section>: {"type":"string"} }, "required": [<section>], "additionalProperties": false }`
  - `main_activities` → `main_learning` with required `phase1`/`phase2`/`phase3`,
    each `{ activity: string, duration_minutes: number }`,
    `additionalProperties: false` at every level. `_json_contract` for this
    section was updated to "exactly three sequenced phases named phase1, phase2,
    phase3" to match.

**Retry policy (bounded, and only for transient faults):**
`MAX_RETRIES=2`, `RETRY_DELAY_SECONDS=1.5`, transient set
`{429, 500, 502, 503, 504}`. Transient HTTP errors and timeout/connection
exceptions retry; 429 is handled safely. On HTTP **400** the
`response_format` steps **down one level** (`json_schema → json_object → none`)
without consuming an attempt (max 3 total calls) — a compatibility guard, not a
retry. Auth failures, 404, and plain-400 errors **never retry**. (A double-POST
bug in the retry loop was fixed: retry branches now `continue` and re-POST at
the top of the loop, so a retry never sends the previous body twice.)

## 4. Real success path (Groq)

Proven at three independent levels:

- **Live unit tests** — `backend/tests/test_zeli_groq ` (`@pytest.mark.live`):
  3 tests pass against the real Groq API: real authentication, a strict-schema
  per-section rewrite, and the invalid-key `auth_failed` classification.
- **Local browser journey** — `frontend/e2e/zeli-groq-journey.js` success pass:
  **56 passed, 0 failed** (see §13).
- **Production browser journey** — same script against the live Render
  deployment after the owner switched to Groq: **56 passed, 0 failed**, with a
  real Groq rewrite changing only the requested section, consuming exactly one
  unit, and persisting across leave → return → reload.

## 5. Real failure path

Proven at three independent levels, all ending in the same safe contract:

- **Live unit test** — an invalid key classifies as `auth_failed`
  (non-transient → no retry) and yields the teacher-safe 502.
- **Local browser journey** — failure pass with the backend restarted on a
  broken key: **40 passed, 0 failed.**
- **Production browser journey** — `zeli-prod-failure-check.js` against the live
  deployment with the monthly allowance exhausted (a real failure mode that
  does not require disturbing the production key): **22 passed, 0 failed.**

In every case: the teacher sees only calm copy, the existing content is
preserved byte-for-byte (on screen **and** in the database), the page remains
fully editable and Save still works, and **zero** AI units are consumed.

## 6. Quota behaviour (unchanged rules, verified by structure)

`consume_ai_generation` runs **only** after a successful generation, so the
zero-credit-on-failure invariant holds by construction. Verified end to end:

| Outcome | Credits consumed |
|---|---|
| Successful Zeli rewrite | **1** |
| Provider failure / malformed output / quality-gate failure | **0** |
| Deterministic lesson generation | **0** |
| Teacher declines (rejects the suggestion) | no re-consumption |

The request-id idempotency key prevents a duplicate submission from consuming a
second unit. Measured in the journeys: local `0 → 1 → 2` across suggest / reject
(no change on reject) / re-suggest; production `0 → 1 → 2`; production failure
checks `5 → 5` and `3 → 3` — zero on every refused attempt.

## 7. Zeli UI changes

"Zeli" is the assistant name on every normal teacher surface:

- **Workspace** (`lesson-workspace.tsx`): Zeli notice; the four affordance
  buttons — *Suggest another version*, *Make this more practical*, and the two
  new optional ones *More learner-centred* and *Easier with limited resources*
  (`REWRITE_MODES` now 4 modes, the two new ones wired on the Main Learning
  section only).
- **Review page** (`lessons/[id]/page.tsx`): success banner "Zeli rewrote this
  section. Review it and Save to keep it."; status line; the same four
  affordances.
- **Generate page** (`generate/[id]/page.tsx`): status line and result line;
  mode select labels are now "BASIC - Zeli suggestions" / "ENHANCED - Zeli
  assistance".
- **Failure copy** (`ai-feedback.ts`, the single presentation layer):
  "Zeli could not rewrite this section right now. Your existing content was
  preserved. You can edit it manually or try again later." (plus the
  `AI_UNAVAILABLE` / `AI_RATE_LIMITED` / abort / network variants).

## 8. Provider-name hiding

No teacher surface ever shows a provider name, model id, or API term. Scanned
the rendered page text in **both** journeys for: `groq`, `gemini`, `openai`,
`gpt-oss`, `gpt-4`, `rate_limit`, `429`, `503`, `502`, `malformed`, `api key`,
`json schema`, `structured output`, `temperature`, `retry`, and (in failure
copy) `unauthorized`, `stack`, `traceback` — all absent, on the review page and
in the failure banner, locally and in production.

The `/api/settings/ai-status` endpoint intentionally **keeps**
`provider` / `provider_label` / `state` / `reason` — these are the
admin/developer diagnostics; only teacher-facing surfaces were rebranded. This
split is documented in the code comments.

## 9. Deterministic generation regression

The 4-layer deterministic pedagogy engine is untouched and remains the sole
author of every lesson. AI is an optional per-section rewrite tool invoked only
on an explicit teacher action. Full regression suite:
**2134 passed, 11 skipped, 0 failed** (see §15).

The browser journeys re-prove it in both environments: lessons generated with
AI Mode OFF carry no `ai_provider` in provenance, keep the WAPEF template
identity, produce the 3-phase structure, and carry the scheme's indicator
(`B7.1.1.1.1`) and derived learning objectives.

## 10. WAPEF preservation

All four WAPEF fields (`wapef_deep_hope`, `wapef_storyline`, `wapef_gods_story`,
`wapef_through_lines`) survive a Zeli rewrite byte-for-byte.

- **Local journey (success pass, 56/56):** all four fields unchanged before/after
  the rewrite, in both the DOM and the database.
- **Production check (`zeli-prod-wapef-check.js`, 14/14):** the four fields were
  stored through the app's own lesson-save boundary, a real Groq rewrite ran on
  the review page, and all four fields were exactly preserved while the
  assessment changed and exactly one unit was consumed.

Note: on the production run, the WAPEF selections made on the generate-page
preview rows did not reach the stored lesson (a pre-existing generate-flow race
in code my migration never touched — my generate-page diff is pure copy). The
focused production check above removes that ambiguity and proves the
preservation guarantee positively.

## 11. DOCX export

`POST /api/generation/{job_id}/export/docx` → **200**,
`application/vnd.openxmlformats-officedocument.wordprocessingml.document`,
84 KB. The extracted `word/document.xml` text contains the lesson topic, the
Deep Hope, the Storyline, and the Zeli-rewritten assessment.

## 12. PDF export

`POST /api/generation/{job_id}/export/pdf` → **200**, `application/pdf`, 20 KB.
Extracted text contains the lesson topic, the Deep Hope, the Storyline, and the
Zeli-rewritten assessment, with all WAPEF "Special Fields" (Through lines,
God's Story, Deep Hope, Storyline) rendered in the WAPEF section.

## 13. Browser acceptance (local)

`frontend/e2e/zeli-groq-journey.js` — a real browser journey against the real
local stack, mirroring the proven `lesson-persistence-journey` onboarding
(signup → school → real scheme upload → WAPEF plan → generate).

**Success pass — 56 passed, 0 failed:** deterministic generate (AI off) → phases
exist → Zeli on → suggest → **only** that section changes (starter, plenary,
topic, indicators and all four WAPEF fields untouched) → reject by reload →
deterministic content restored, banner gone, no re-consumption → rewrite again →
Save → leave / return / reload → persistence → quota `0 → 1 → 2` → no
provider/API term anywhere.

**Failure pass — 40 passed, 0 failed:** backend restarted on a broken key → same
teacher and lesson → suggest → teacher sees only the calm Zeli failure message →
content byte-for-byte intact → **0 credits consumed** → page still editable and
Save still works → manual edit persists.

## 14. Production acceptance (Render)

| Check | Result |
|---|---|
| Commit + push | `098689b` (migration), `edcd7b0` (prod scripts) → origin/main |
| Frontend | `https://schemeknit-frontend.onrender.com` → **200** |
| API | `/api/service-status` → **200** `{"status":"healthy"}` |
| `AI_MODE` | `/api/settings/ai-status?ai_mode=groq` → `active: true, provider: "groq", state: "CONFIGURED"` |
| Real Zeli request | Success journey **56/56** + WAPEF check **14/14** on Groq |
| Failure safe | Failure check **22/22** (403 on exhausted allowance; 0 units, content intact, still editable) |
| Credits correct | Success `+1` per rewrite; failure `+0` — verified via `/api/auth/my-plan` |
| WAPEF / DOCX / PDF | §10, §11, §12 — all preserved |
| Provider hidden | No provider/API term on any production teacher surface |

**Owner-side Render env vars (documented in `docs/DEPLOYMENT.md`):** set in the
Render backend dashboard, **not** synced from the local `.env` — `AI_MODE=groq`,
`GROQ_API_KEY` (owner secret), `GROQ_MODEL=openai/gpt-oss-120b`. Before the
switch, production resolved `groq` as `MISSING_KEY` (deterministic fallback,
lessons unaffected); after, both `groq` and `ENHANCED` resolve to Groq. (Two
transient 500s on auth endpoints during the redeploy cold-start resolved on
retry; a 308 `/signup → /signup/` redirect is served by the deployed frontend
and is harmless to the browser journey.)

## 15. Backend test count

**2134 passed, 11 skipped, 0 failed** (`python -m pytest tests/
--ignore=tests/smoke_all_levels.py`), including the new
`backend/tests/test_zeli_groq_migration.py` — 45 non-live tests + 3 live Groq
tests (real auth, strict-schema section rewrite, invalid-key `auth_failed`).
The 4 pre-existing `.env`-leak regressions were made hermetic by patching
`_env`, and the two auto-select tests were updated to the groq-first order.

## 16. Commit SHAs

| SHA | Content |
|---|---|
| `098689b` | Migrate runtime AI provider to Groq; rebrand teacher assistant as Zeli |
| `edcd7b0` | Add production Zeli verification scripts (WAPEF preservation, failure-safe) |

(Prior HEAD: `d8ee702`.)

## 17. HEAD == origin/main

```
HEAD    = edcd7b01261b80a47c1e7210b5fc8740ea2a3976
origin  = edcd7b01261b80a47c1e7210b5fc8740ea2a3976
```

Identical. Both commits pushed successfully.

## 18. Clean tree

`git status --short` → **empty**. All migration work is committed and pushed;
the only untracked artefacts are the gitignored e2e evidence directories
(screenshots, results, state).

---


---

## 19. Addendum (same day): the generate-page WAPEF save boundary — root-caused and fixed

The pre-existing race noted in §10 (WAPEF selections made on the generate-page
preview rows did not reach the stored lessons on the production run) has now
been root-caused, fixed, and independently verified locally and in production.
The Groq/Zeli provider architecture was **not** touched: every provider,
schema, retry, quota and branding behaviour in §§1–8 is unchanged.

### 19.1 Root cause

Generating from the review rows is a TWO-request browser sequence:

1. `PUT /api/generation/{scheme_id}/lesson-review` — persists the per-lesson
   draft store (including the four WAPEF selections).
2. `POST /api/generation/{scheme_id}/generate` — builds the lessons FROM the
   saved draft store (`_apply_lesson_review_draft`).

Three independent windows could lose the selections at that boundary:

* **Frontend stale state.** The save payload was built inside
  `saveLessonReviewDrafts` from the component-scope `lessonReview` array, and
  the save call did not receive the rows explicitly. An edit committed in the
  same tick as "Confirm & Generate" (or any re-render in flight) could leave
  the PUT serializing a pre-edit row — the teacher's latest selections never
  left the browser.
* **Fire-and-forget generation.** `handleConfirmAndGenerate` treated a save
  failure as non-fatal and generated anyway, persisting lessons from the
  previous (often empty) draft store.
* **Backend draft-map replacement.** `DataService.save_lesson_review_drafts`
  REPLACED the whole store with the incoming payload, so a payload that
  omitted lessons (partial hydration, paginated review) erased other lessons'
  saved WAPEF selections; and `get_lesson_review_drafts` could return an
  identity-map snapshot on the same request session instead of the committed
  row.

The backend generate path itself was already atomic and read-after-write
correct at the database level (proven by `test_review_draft_alignment.py`);
the loss happened BEFORE and AT the save boundary, on the browser side and in
the draft-store write semantics.

### 19.2 Exact fix (narrow, two files + tests)

* `frontend/src/app/(app)/generate/[id]/page.tsx`
  * `handleConfirmAndGenerate` passes its in-scope `lessonReview` rows
    explicitly to `saveLessonReviewDrafts(rows)` and **awaits** the persisted
    PUT before issuing `POST /generate`; a save failure now CANCELS
    generation with a clear message instead of generating without the
    selections.
  * A canonical `wapefDraftFor(row)` builder serializes the four WAPEF fields
    (verbatim values, explicit empty-string/list fallbacks — never `undefined`).
  * `updateLessonReviewRow` keeps its functional update (the patch applies to
    the latest row state, never a closure-captured copy).
* `backend/src/service.py`
  * `save_lesson_review_drafts` now MERGES the incoming map into the committed
    store (per-lesson replace; keys absent from the payload are preserved) and
    re-reads the committed row first.
  * `get_lesson_review_drafts` refreshes the scheme row so a generate request
    that follows a PUT on the SAME session reads the committed store, never a
    stale identity-map snapshot.

No timeouts, sleeps, polling or retry loops were added; no product semantics
changed. Omitted WAPEF fields still mean "not selected" and persist as empty —
never an invented default.

### 19.3 Regression coverage (A–H)

`backend/tests/test_wapef_save_boundary.py` — 11 tests:

* **A** preview rows carry the saved selections back to the UI (payload test)
* **B** selections → stored lesson contains exactly those values
* **C** persisted lesson → API read (single-lesson and job listing) preserves
  all four fields verbatim
* **D** Zeli contract: a WAPEF field is never a rewriteable section (400), and
  a non-WAPEF draft edit never blanks a set field
* **E** stored lesson → DOCX → all four fields present; package is a valid
  PK/ZIP
* **F** stored lesson → PDF → all four fields present; real `%PDF` header
* **G** empty-state semantics unchanged: no selection → genuinely empty
  fields, never invented defaults; non-WAPEF drafts still apply
* **H** generate → save → reload → save again → byte-identical; a partial PUT
  never erases other lessons' selections; same-session read-after-write sees
  the just-PUT drafts

Full backend regression: **2146 passed, 11 skipped, 0 failed**.

### 19.4 Local browser verification

`frontend/e2e/wapef-generate-boundary-acceptance.js` — real browser, real
stack (`next start` + uvicorn), no mocks: signup → school → real scheme upload
through the UI → Approved WAPEF Plan → preview → DISTINCTIVE values for all
four fields on every row → Confirm & Generate → persisted lesson verified
through the real API → leave/return/reload → one real Zeli rewrite (exactly
one unit consumed) → all four values unchanged → DOCX download (valid PK/ZIP,
all four values in the document XML) → PDF download (valid %PDF, all four
values in the extracted text). **29 passed, 0 failed**, no page errors, no
5xx.

### 19.5 Production browser verification

The same journey ran against the live Render deployment after this fix
deployed (`frontend/e2e/wapef-prod-boundary-check.js`): distinctive WAPEF
selections made on the production generate page reached the stored production
lesson exactly, survived leave/return/reload, survived a real Groq rewrite
(exactly one unit), and both production exports carried all four values.
Result recorded in `frontend/e2e/wapef-generate-boundary-acceptance/`. With
this, the §10 caveat is closed: generate-time selections and Zeli preservation
are now BOTH proven in production, end to end.

### Frontend build status

`npx tsc --noEmit` — clean (no output). `npx next build` — **EXIT 0**.

### Regression protection

All prior engine work, WAPEF, assignments, exports, auth/entitlements/quotas,
the Curriculum Spine and provenance are preserved and covered by the green
2134-test regression.
