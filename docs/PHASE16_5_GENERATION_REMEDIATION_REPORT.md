# PHASE 16.5 — GENERATION REMEDIATION REPORT
## Real-World Content Correctness + AI Mode Wiring

**Date:** 2026-09-23
**Scope:** document ingestion diagnostics · AI mode/provider wiring · indicator-specific generation · user-input propagation · lesson-to-lesson content variation · quality/anti-cloning
**Phase 17:** deliberately NOT started (per instruction); readiness assessed in section O.

---

## A. Basic 8 full-document failure

### What was reproduced

`real_documents/BASIC 8 TERM 1.pdf` was scanned with `PDFParser.analyze()`:

```
status: extraction_failed
title: (empty)
detected_subjects: []
scan: {'pages': 45, 'text_chars': 0, 'blank_pages': 45}
```

**Every one of the 45 pages contains 0 extractable characters.** The document
is an image-only (scanned) PDF with no text layer. There is nothing for the
parser to read — `fitz.find_tables()` returns nothing and `get_text("blocks")`
returns nothing.

### Why a one-subject upload "worked" but the full Basic 8 did not

The subject-only documents that succeeded in teacher-style testing were
**DOCX files** (`BASIC 9 MATH SCHEME OF LEARNING.docx`,
`BASIC 9 SCIENCE SCHEME OF LEARNING.docx`) — a different file with a real text
layer. The multi-subject DOCX path (`repro_multi.docx`,
`repro_0weeks.docx` — a captured full Basic 8 scheme) was re-verified during
this phase and detects **6 subject sections × 15 weeks each** with
`detection_status = "multiple"` and each section parsing to a full curriculum.
The multi-subject ingestion path itself is working for documents with a text
layer; the Basic 8 PDF failure is a *text-layer* failure, not a
subject-boundary failure. This was already diagnosed in Phase 16D
(`tests/test_scanned_pdf_diagnostics.py`), which this phase preserves and
extends rather than contradicts.

### Where information was lost (pipeline stage audit)

| Stage | Result |
|---|---|
| PDF text extraction | **0 chars — this is the failing stage** (no text layer) |
| Table extraction | never reached (no text) |
| Subject boundary detection | working (DOCX multi-subject verified) |
| Section grouping / normalization | working (verified) |
| Class / subject / week / indicator detection | working (verified) |
| Selected-subject confirmation | working (verified) |
| Curriculum IR → allocation → generation | working (verified) |

### Fix

1. **Upload response now carries an extraction reason**
   (`backend/src/routers/documents.py`): the upload response's
   `extraction` block includes the machine-readable `reason`
   (`no_text_layer` / `no_curriculum_table`) plus the per-subject sections.
2. **The upload UI no longer dead-ends** (`frontend/src/app/upload/page.tsx`):
   an `extraction_failed` result now shows an honest, actionable panel —
   for `no_text_layer` it explains the file is a scanned/image-only PDF and
   tells the teacher to export/print a text PDF or run OCR before re-uploading.
   The multi-subject picker still appears for genuinely multi-subject
   documents, with an explanatory message if no subject heading was
   recognized.
3. A **generic multi-subject regression test** with a synthetic 3-subject
   document (plus a revision-week variant) was added so the fix is proven
   generically, not against one fixture.

### Not done (and why)

OCR was **not** added. Tesseract/EasyOCR are not installed, not in
`requirements.txt`, and bundling an OCR engine is a product decision that
belongs in Phase 17+ planning. The failure is now *honest, explained, and
actionable* instead of a silent 0-lesson dead end.

### Genuine special weeks

`test_special_week_does_not_become_extraction_failure` proves that
REVISION/SBA weeks with no instructional indicators are classified as special
weeks, never as parser failure, and only instructional indicators are
allocated.

---

## B–C. AI mode root cause and fix (Defects 2, 9, 10)

### Root cause

Tracing UI → state → API → backend → provider → response → UI found:

1. **No persistence**: the AI-mode `<select>` wrote only to component state;
   a page reload silently reset it to `OFF` — hence "always OFF-deterministic".
2. **No visibility**: the backend resolved `BASIC`/`ENHANCED` onto a real
   provider via `resolve_provider_mode()`, but neither the generate screen nor
   the result ever reported which provider was resolved, whether AI was
   actually active, or how many lessons were AI-generated.
3. **Bad suggestion wiring**: the lesson page hard-coded `'ollama'` as the AI
   mode for "Suggest" buttons. On a machine without Ollama this could only
   ever produce *"AI provider not available. Please try again later or use AI
   OFF mode."* — a dead-end message with no diagnosis.
4. **Inaccurate diagnostics**: unavailable-provider errors returned a generic
   string with no provider name or state.

### Fix

* **Persistence** (`frontend/src/app/generate/[id]/page.tsx`): the chosen mode
  is saved to `localStorage` and restored on load.
* **Live truth on the configure screen**: new backend endpoint
  `GET /api/settings/ai-status?ai_mode=…` (`backend/src/routers/settings.py`)
  resolves the requested mode through the *same* `resolve_provider_mode()` the
  pipeline uses and returns `{mode, active, provider, state, reason}` with
  secrets never exposed. The screen shows e.g.
  `AI active · provider: groq` or
  `No AI provider available — lessons will be deterministic.`
* **Truthful generation result** (`backend/src/routers/generation.py`): the
  generate response now includes an `ai` block —
  `{mode, active, provider, state, lessons_ai, lessons_deterministic, reason}` —
  computed from what the job *actually did*. The result panel states exactly
  how many lessons were AI-enriched vs deterministic.
* **Suggest buttons use the teacher's chosen mode**
  (`frontend/src/app/lessons/[id]/page.tsx`): no longer hard-coded to
  `ollama`; the persisted mode (defaulting to `BASIC`, which auto-selects any
  configured provider) is used, and the page shows whether AI is active
  *before* the click.
* **Accurate unavailability diagnostics**
  (`backend/src/routers/ai_regeneration.py`): 503 responses now name the
  resolved provider and its state (via `provider_status()`), e.g.
  *"AI provider 'ollama' is not available (state: MISSING_KEY). … Deterministic
  lesson data is unchanged — configure a provider (Gemini, Groq, OpenAI) or
  start local Ollama."* The provider field in responses is now the provider
  key (e.g. `groq`) instead of a class name.

The existing mode enum (`OFF`/`BASIC`/`ENHANCED` + named providers) is
unchanged — no second architecture was introduced; UI labels now match
backend behaviour.

---

## D–E. 12-lesson cloning root cause and fix (Defects 3, 5)

### Root cause

`build_lesson()` composed every phase from **one fixed subject template**
(`profile.starter_template`, `profile.main_phases`,
`profile.assessment_template`, `profile.plenary_template`) whose only
indicator-derived input was the `{skill}` placeholder. For 12 indicators in
the same subject, the sentence skeleton was byte-identical across lessons;
only the quoted indicator text changed. Keywords, TLRs, core competencies and
references were copied from the same static profile/config lists every time.
No template objects were shared or mutated — it was purely static-template
cloning.

### Fix — content derived from the indicator

`backend/src/curriculum/lesson_builder.py` was rewritten around the
indicator's **activity type** (from `indicator_interpreter.py`: the verb the
curriculum uses — solve / investigate / classify / read / write / discuss /
compare / create / analyse / reflect / observe / demonstrate / practical) and
its **evidence of achievement**:

* **Starter bank by activity type** — a problem-solving lesson starts with a
  mental drill on the prerequisite skill; an investigation starts by
  collecting predictions; a reading lesson starts with vocabulary preview; a
  discussion starts from a local scenario.
* **Main-phase bank by activity type** — worked example → guided practice →
  independent practice for problem-solving; predict → investigate → explain
  for investigation; present examples → classify → accuracy check for
  classification; etc. The subject pedagogy profile still supplies the
  structure when the indicator does not genuinely express a recognised
  activity (`_activity_key` returns `None` rather than forcing "discussion").
* **Assessment bank by activity type**, each ending with the indicator's own
  success evidence ("Success = Learner can …").
* **Plenary bank by activity type** — consolidation matches what was taught.
* **Resources derived from context**: interpretation-suggested resources +
  activity-specific resources (a practical lesson gets tools/safety items, a
  reading lesson gets texts/word cards) + subject base + teacher TLRs. A
  measurement lesson no longer inherits a classification lesson's materials.
* **Core competencies derived from the activity** — practical/creation
  lessons yield Creativity & Innovation; analysis/reflect yield Critical
  Thinking & Personal Development; discussion yields Communication &
  Cultural Identity — with teacher-supplied competencies always first.
* **References derived from the curriculum context** (subject curriculum +
  level teacher's guide + strand-specific reference) plus teacher references.
* **Vocabulary derived from the indicator** — significant content terms
  extracted from the indicator text (`_content_terms`) + activity keywords +
  subject profile keywords, with teacher keywords first.
* **Fragment-tolerant focus extraction** (`_first_clause`): real schemes carry
  fragmented codes (`"B9.2.1.1 .2 Reflect on …"`,
  `"5.1.1.1 B9. Investigate …"`); the builder strips orphan code fragments so
  lessons say "about Reflect on how reading impacts self…" instead of
  "about B9" / "about .2". This fixed two Basic 9 quality-gate failures
  (`indicator_exactness`) that were caused by code fragments replacing the
  actual focus text.
* **Essential questions per activity type.**

No random wording and no synonym swapping is used anywhere; the same input
always yields the same lesson, and the difference between lessons is exactly
the difference between their indicators.

---

## F–G. Teacher keyword propagation root cause and fix (Defect 4)

### Root cause

Two loss points:

1. **AI enrichment overwrote** teacher values: `_apply_v2_content` assigned
   `lp.keywords = content["key_vocabulary"]` — the AI's vocabulary replaced
   the teacher's keywords outright (same for other metadata on the
   deterministic path it silently dropped them from context).
2. **Prompts never received the keywords**: neither the deterministic builder
   nor the AI prompt contained the teacher's vocabulary, so AI output could
   never use it.

### Fix

* `build_lesson()` places teacher keywords **first** in every lesson's
  vocabulary (verified: present in every deterministic lesson).
* The AI prompt builder (`generation_prompt.py`) gained a
  `teacher_keywords` parameter and a **TEACHER-SUPPLIED VOCABULARY (REQUIRED)**
  section instructing the model to include every term verbatim in
  `key_vocabulary` and use them naturally. It flows through
  `_build_v2_prompt_from_context` → every provider's `generate_lesson_v2`
  (`teacher_keywords` is passed via `supports_kwarg()` so third-party/test
  providers that predate the field keep working).
* `_apply_v2_content` now **merges, never replaces**: teacher keywords,
  TLRs, core competencies and references always survive AI enrichment, with
  AI suggestions appended (case-insensitive dedupe). AI-suggested phase
  resources are folded into the lesson's TLRs.

---

## H–I. Test coverage added

New file `backend/tests/test_phase16_5_generation_remediation.py` (17 tests):

| Requirement | Test(s) |
|---|---|
| TEST 1 — full multi-subject scheme → selectable indicators → lessons | `test_full_multi_subject_docx_yields_usable_lessons` (synthetic 3-subject DOCX; analyze → confirm Science → allocation > 0) |
| TEST 1 — special/revision weeks are not parser failure | `test_special_week_does_not_become_extraction_failure` |
| TEST 2 — AI mode change reaches backend | `test_ai_status_*`, `test_ai_off_generates_deterministically`, `test_ai_mode_without_provider_falls_back_and_is_honest` |
| TEST 3 — actual provider/mode reported | `test_ai_status_reports_available_provider`, `test_ai_mode_with_provider_marks_ai_generated` |
| TEST 4 — 12 distinct indicators → different content | `test_twelve_indicators_produce_different_phase_content` (signature-set ≥ 5 + every lesson contains its indicator's own terminology), `test_activities_differ_for_different_activity_types` |
| TEST 5 — teacher keywords survive full path | `test_keywords_in_every_deterministic_lesson`, `test_keywords_survive_ai_enrichment_merge` (AI that *ignores* teacher terms cannot delete them) |
| TEST 6 — indicator-specific TLRs | `test_resources_track_activity_type`, `test_teacher_resources_are_preserved` |
| TEST 7 — indicator-specific assessments | `test_assessment_is_indicator_specific` (≥ 5 distinct assessments across 12) |
| TEST 8 — competencies/references from context | `test_competencies_vary_by_activity`, `test_references_are_curriculum_derived` |
| TEST 9/10 — AI suggestion available / accurate diagnostic | `test_ai_status_reports_unavailable_provider` (+ provider-named 503s verified at router level) |
| TEST 11 — deterministic indicator-specific content | `test_twelve_indicators_produce_different_phase_content` (AI OFF) |
| TEST 12 — AI indicator-specific content | `test_ai_mode_with_provider_marks_ai_generated` (per-lesson AI starters all distinct) |

Also extended indirectly: `_first_clause` fragment handling is covered by the
repaired Basic 9 real-document quality-gate tests.

---

## J. Full regression results

| Suite | Result |
|---|---|
| Full backend `pytest` (incl. all 5 defect tests, ingestion, allocation, quota, AI provider, quality gate, real-document acceptance) | **1113 passed, 10 skipped, 0 failed** |
| `frontend tsc --noEmit` | clean |
| `frontend npm run build` | succeeds (all routes prerendered) |
| Backend app import / startup (`from src.main import app`) | ok |

Real-document acceptance run (Basic 9 PDF, Mathematics, AI OFF, 21 lessons):
**21/21 distinct starters, 21/21 distinct assessments, 21/21 distinct
plenaries**, teacher keywords present in every lesson, and every lesson's
content containing its own indicator's terminology.

---

## K. Remaining generation weaknesses

1. **Scanned PDFs still need external OCR** — the app explains the problem
   and what to do, but cannot read image-only files itself.
2. **Vocabulary extraction is lexical** — `_content_terms` picks significant
   indicator words; it cannot know that "surds" is a richer key term than
   "simple". AI mode mitigates this when a provider is configured.
3. **Suggested resources are heuristic** — activity-appropriate but not
   class-size- or region-aware beyond the Ghanaian baseline profiles.
4. **BASIC vs ENHANCED currently resolve identically** — both auto-select the
   best available provider. Differentiating them (e.g. ENHANCED = per-lesson
   regeneration passes) is a product decision left for Phase 17.
5. **AI-enriched lessons still depend on provider output quality** — the
   quality gate reverts to deterministic content on failure, so weak
   providers degrade to good deterministic lessons rather than bad AI ones.

---

## L. Is Phase 17 ready?

**Yes, with the item below resolved first.** Phase 17 (provider validation)
can proceed: mode/provider resolution, entitlement gating, quality-gating of
AI output and diagnostics are now consistent end-to-end and covered by
regression tests. Recommended prerequisite: decide the OCR strategy for
scanned schemes (bundle an OCR engine vs. guided re-export), since that is the
one remaining ingestion gap observed in real teacher use.

---

## M. Acceptance statement

When a teacher uploads a real scheme containing multiple indicators, the
pipeline now delivers: correct subject section → correct indicator per
period → indicator-specific starter/main/assessment/plenary → teacher input
included → contextually appropriate resources, vocabulary, competencies and
references — while academic term/period metadata stays consistent across the
term. Verified against the real Basic 9 PDF and synthetic multi-subject
documents; the original Basic 8 scanned PDF is now reported honestly with an
actionable reason instead of silently producing 0 lessons.
