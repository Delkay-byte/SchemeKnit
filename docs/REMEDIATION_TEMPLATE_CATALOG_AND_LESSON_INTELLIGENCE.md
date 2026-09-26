# Remediation: Template Catalog, Lesson-Detail Intelligence, Special Periods

Date: 2026-09-26 · Branch: `main`

This phase is a focused production remediation of: template catalog/selection,
template naming, template retirement, AI provider status correctness,
per-lesson metadata generation/defaults, references UX, special-period
handling, review-page usability, and AI regeneration failure handling.
All previously implemented systems (deterministic generation, Gemini/Groq
providers, provider routing, WAPEF/KG/Nursery/Basic 1–3/Basic 4–JHS/GES flows,
Curriculum IR, allocation, subject-aware pedagogy, quality gate, tab-isolated
auth) are preserved.

## TEMPLATES

### Root cause of "only two templates visible" (Parts A/D)
The backend catalog always returned the full active registry. The defect was in
`frontend/src/app/(app)/generate/[id]/page.tsx`: `getTemplatesForScheme()`
filtered templates to `t.educational_level === scheme.educational_level`,
leaving exactly two entries for JHS and Basic 1–3 schemes. Fixed: the generate
page now requests the unfiltered catalog and shows every active template the
teacher is permitted to use (6 verified built-in forms + the teacher's own
custom templates). No fixed count is hard-coded anywhere.

### GES naming (Part B)
Every GES-family display name now explicitly contains "GES":

| Template id | New display name |
|---|---|
| `tpl-official-ges-nacca-jhs` | **Approved GES Plan** |
| `tpl-official-ges-nacca-primary` | **Approved GES Lower Primary Plan** |
| `tpl-official-ges-nacca-kg` | **Approved GES KG / Nursery Plan** |
| `tpl-official-ges-nacca-shs` | **Approved GES SHS Plan** |

Internal template IDs are unchanged.

### WAPEF naming (Part B)
`Approved WAPEF Plan` (Basic 4–JHS subject-teacher model) and
`Approved WAPEF Basic 1–3 Plan` (class-teacher weekly model) already contained
"WAPEF"; verified unchanged. Template routing (Part Z) is untouched.

### Retirement of the legacy "Headteacher Source" template (Part C)
`tpl-approved-org-headteacher` ("Approved Organizational Lesson Plan
(Headteacher Source)") was an alias of the verified JHS form. It is removed
from `DEFAULT_TEMPLATES` (the selectable catalog) via `RETIRED_TEMPLATE_IDS`
(`template_engine.py`); its provenance record is marked RETIRED; and the legacy
wording is gone from `approved_template.TEMPLATE_NAME`. Historical safety: the
id remains fully routable — `get_template_by_id` and `spec_for_template_id`
still resolve it to the same verified JHS renderer, so historical lessons and
exports naming it keep working. Only hard-deleting was avoided.

## AI

### Provider status correctness (Part E)
Trace result: `resolve_provider_mode()` maps `OFF`→OFF, named providers
(`gemini`…)→themselves, and BASIC/ENHANCED→auto-selection in order
gemini→groq→openai→opencode-zen→ollama. The live environment has
`GEMINI_API_KEY` set and no `OPENCODE_ZEN_API_KEY`, so the resolved provider is
**Gemini** for BASIC/ENHANCED. The earlier "opencode-zen" label could only come
from a stale environment or a session resolved before Gemini was configured —
there is no code path that mislabels Gemini. The generate endpoint now also
returns `provider_key` in its `ai` info block, and the UI label renders exactly
what `/ai-status` and the generation response resolve. Verified live:

```
RESOLVED PROVIDER = gemini
DISPLAYED PROVIDER = gemini
```

`opencode-zen` remains displayed if it is genuinely the resolved provider
(configured key, no Gemini key) — asserted by test.

### Regeneration failure handling (Part W)
Root cause of `Regeneration failed: AI response too short or empty`:
`_extract_section_text` looked up the lesson-row column name (`introduction`,
`conclusion`) directly in the provider payload — but the V2 provider contract
returns `starter`/`main_learning`/`plenary`. A valid structured Gemini response
therefore mapped to nothing, and the generic `len(...) < 10` heuristic rejected
it. Fixes in `routers/ai_regeneration.py`:
- `SECTION_TO_PROVIDER_KEYS` maps every regeneratable section onto its
  provider-schema keys before any length logic runs.
- The length floor (`MIN_SECTION_CHARS`) now applies only to the mapped
  SECTION text — never to the raw model output.
- Empty structured payloads surface a real diagnostic through the existing
  error contract (`rate_limit` → 502 "was rate-limited", `malformed_json`,
  `empty_output`, state codes) instead of a generic "too short" message.
- The cross-section fallback (assessment regen silently returning the
  introduction text) was removed.
- The bounded ollama retry runs before the diagnostic so transient empties
  retry instead of failing.

## LESSON METADATA

### Global seeds removed; per-lesson intelligence (Parts F–J, T, U, V)
The review form's four global fields (Keywords/TLRs/Competencies/References
"(seed for all lessons)") are gone from the generate page. The model is now
GLOBAL CONFIGURATION (scheme, calendar, template) + PER-LESSON INTELLIGENT
DEFAULTS + OPTIONAL TEACHER OVERRIDE:

- **Keywords (G):** derived per lesson with priority indicator → sub-strand →
  content standard → activity context (Nursery rows use subject + strand +
  sub-strand + source focus). Lesson 1 and Lesson 2 no longer share one generic
  list. Editable in review; teacher edits win on save/regenerate.
- **Core competencies (H):** selected from the official NaCCA taxonomy by the
  lesson's interpreted activity type (`_COMPETENCIES_BY_ACTIVITY`); never the
  whole taxonomy; AI-suggested + teacher-editable.
- **Other TLRs (I):** default `[]` per lesson. The batch seed is no longer
  copied into `other_tlrs` (nor into the display union). Separate from source
  TLRs; AI suggestions never become teacher-entered data.
- **Source TLRs (J):** unchanged mechanism, verified scoped subject+week+
  allocation+indicator; no cross-subject/week contamination.
- **Period/timing (K):** teacher-entered; when empty the field stays genuinely
  empty — the generated "Period N" placeholder is removed.
- **References (L/M):** teacher-entered only. The builder no longer fabricates
  curriculum/handbook defaults. The review UI shows exactly 3 empty slots;
  "+ Add reference" appends another; empty slots are never persisted (stripped
  in `_apply_lesson_review_draft` and in the lesson-detail save).
- **Prefilling (T):** generation populates 1–5 per lesson automatically; the
  teacher edits only where necessary.

### Empty-field contract (Part N)
Empty fields render empty across review and export: no `-`, `—`, `N/A`,
`unknown`, `none`, `[]` or `[""]`. Exports verified to contain no leftover
bracket tokens and no special-period text.

## SPECIAL PERIODS (Parts O–S)

Root cause of the `MID-TERM (05-11-2026 to 06-11-2026)` bug: the parser's
`SPECIAL_WEEK_KEYWORDS` had no mid-term entries, so the row parsed as
INSTRUCTION; its label leaked into strand/sub-strand/indicators; and
`_extract_indicator_code` returned `text[:30]` as a fake code — producing
"Learners can MID-TERM…" lessons.

Normalized model (Part P): `SpecialPeriodType` (`MID_TERM`, `REVISION`,
`EXAMINATION`, `VACATION`, `OTHER_NON_INSTRUCTIONAL`) with `classify()`;
verbatim source labels kept as `special_period_label` metadata on
Week/AllocatedIndicator/LessonPlan rows (migration `v026`); `_extract_week_info`
never matches date digits inside a special-period cell as a week number.

Generation rule (Part Q): special periods generate NO lesson content — no
topic, objective, indicator, standard, strand, sub-strand, starter, main,
assessment or plenary is invented. AI enrichment explicitly skips special-period
rows, so no placeholders are sent to Gemini.

Review UX (Part R): the allocation review shows
"Special Period: <label> — This period does not contain a normal lesson." and
offers no lesson fields for such rows.

Allocation/quota (Part S): special periods emit a metadata-only allocation row
(no lesson sequence, no lesson count) and never consume a lesson-generation
unit — in both the indicator and the Nursery week-unit paths. A REVISION week
whose source row carries actual teaching content is NOT automatically
non-instructional: with real content it is a real teaching week when the
teacher includes it; only content-less special periods are skipped. The
existing product rule (revision weeks excluded unless
`include_special_weeks`) is preserved and tested.

## REVIEW PAGE UX (Parts X/Y)
The per-lesson review now separates CURRICULUM CONTEXT (read-only source data),
GENERATED LESSON (editable), KEYWORDS (AI-suggested + editable), SOURCE TLRs
(read-only from the scheme), OTHER TLRs (optional teacher additions), CORE
COMPETENCIES (AI-suggested + editable), REFERENCES (teacher-entered, 3 empty
slots + Add reference), PERIOD/TIMING (teacher-entered), and WAPEF fields
(teacher-selected, preserved). Source vs generated vs teacher-entered
categories are labelled and cannot be blurred by AI.

## TESTS (Part AA)
New suites: `tests/test_special_periods_remediation.py` (13 tests, AA-19..29
coverage), `tests/test_template_lesson_remediation.py` (27 tests, AA-1..18,
30..37 coverage). Existing tests updated only where they pinned the removed
behaviours (global TLR seeds, invented references, "Period N" label, legacy
names, old special-label assertions, cross-section regeneration fallback).

## ACCEPTANCE (Parts AB/AC)
- `frontend/e2e/template-remediation-acceptance.js`: real-browser signup →
  login → catalog enumeration → naming assertions → retirement assertion →
  AI-status consistency at 1440×900 / 1024×768 / 390×844 with overflow checks.
  Result: 13 PASS / 0 FAIL (`frontend/e2e/template-remediation-acceptance/results.txt`).
- `backend/export_acceptance_remediation.py`: full API journey — register,
  login, catalog, upload the real WAPEF Nursery scheme, confirm subject,
  allocation preview (no MID-TERM text in review rows), generate 11 lessons,
  per-lesson metadata + empty-field assertions, DOCX export with zip/XML
  verification. Result: 96 PASS / 0 FAIL.

## REGRESSION (Part AD)
- Backend: `pytest tests/` → 1417 passed, 10 skipped (full suite incl. WAPEF,
  KG, Nursery, Basic 1–3, generation, export, auth-lifecycle, providers).
- Frontend: `tsc --noEmit` clean; `next build` succeeds.
- No existing gate weakened.

## DEFINITION OF DONE — status
All TEMPLATE, AI, LESSON METADATA, SPECIAL PERIODS, USABILITY and REGRESSION
criteria from the phase brief are met; live provider verification shows
RESOLVED = DISPLAYED = gemini with the deterministic engine intact for AI OFF.
