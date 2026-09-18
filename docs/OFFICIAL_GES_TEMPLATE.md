# Official GES / NaCCA Lesson Plan Templates

Four official forms, one per level, all `is_official = True`:

| Level | Template id | Bundled file | Family / level | Default for |
|---|---|---|---|---|
| KG | `tpl-official-ges-nacca-kg` | `ges_kg_lesson_plan_template.docx` | Early Childhood | Nursery, KG 1, KG 2 |
| Lower Primary | `tpl-official-ges-nacca-primary` | `ges_primary_lesson_plan_template.docx` | Primary | **Basic 1-3 only** |
| JHS | `tpl-official-ges-nacca-jhs` | `ges_jhs_lesson_plan_template.docx` | JHS | Basic 7-9 |
| SHS | `tpl-official-ges-nacca-shs` | `ges_shs_lesson_plan_template.docx` | SHS | SHS 1-3 |

Files live in `backend/src/engines/assets/`; contracts in
`engines/official_ges_levels.py`; the renderer in `engines/official_ges_template.py`.

`tpl-official-ges-nacca-jhs` (the JHS form) heads `DEFAULT_TEMPLATES`, which is what
`get_template_by_type` returns, so it stays the generic fallback. Level-aware callers
resolve their own form through `default_template_for_lessons` (see *Default selection*).

## Provenance

| | |
|---|---|
| Source | teacher-supplied files, each labelled "Official GES/NaCCA … LESSON PLAN TEMPLATE" |
| Bundled | verbatim and unmodified |
| Claim | `OFFICIAL_GES_CLAIM = True` |

This differs from `tpl-approved-org-headteacher`
(`docs/APPROVED_LESSON_PLAN_EXPORT_LICENSING_ACCEPTANCE.md`), which stays
structural-reference-only (`official_ges_claim = False`) because its headteacher JPEG
source carries no GES/NaCCA designation. It remains selectable.

## Shape of the source files

Every form is a *placeholder* document — bracketed tokens inside two tables — so
rendering fills the form in place rather than rebuilding its layout with python-docx.
Two kinds of authoring text are baked in and must never reach a teacher's page:

1. **Guidance blocks (JHS form only).** Four numbered block headings
   (`1. ADMINISTRATIVE METADATA BLOCK`, …), each with an "Instructions for AI Engine:"
   paragraph, plus example bullets sharing a run with a phase token
   (`[PHASE_1_STARTER_ACTIVITIES]- Review prior knowledge.- Brain preparation hook.`).
   `strip_guidance()` removes the blocks (8 paragraphs); the bullets vanish because
   filling a token rewrites the whole paragraph.
2. **Example prose in untokened delivery-grid columns (KG, Primary, SHS).** Declared as
   `grid_fills` and overwritten from stored lesson data — blank when there is nothing to
   resolve, so example prose never ships.

## Token contracts

Administrative and curriculum tokens are **deterministic-only** (they resolve from the
stored lesson, never from AI). `AI` marks activity-family tokens a provider may assist
with. Every level's `WEEK_ENDING` is the Friday of the lesson's own week, derived
arithmetically from `lesson_date`.

### KG (14 tokens)

`WEEK_ENDING` · `LEVEL_OR_THEME` (class + theme, e.g. `KG 2 / Our World Our People`) ·
`CLASS_SIZE` · `DURATION` · `INSERT_STRAND` · `INSERT_SUB_STRAND` · `CONTENT_STANDARD` ·
`INDICATOR_CODE` · `CORE_COMPETENCIES` · `KEYWORDS` (AI) · `TLRS` (AI) ·
`TUNING_IN_PHASE` (AI) · `ACTIVE_LEARNING_PHASE` (AI) · `REFLECTION_PHASE` (AI)

### Lower Primary (18 tokens)

`WEEK_ENDING` · `SUBJECT` · `CLASS` · `CLASS_SIZE` · `PERIOD` · `DURATION` ·
`REFERENCE_MATERIAL` · `INSERT_STRAND` · `INSERT_SUB_STRAND` · `CONTENT_STANDARD` ·
`INDICATOR_CODE` · `CORE_COMPETENCIES` · `PERFORMANCE_INDICATOR` · `KEYWORDS` (AI) ·
`TLRS` (AI) · `PHASE_1_STARTER` (AI) · `PHASE_2_MAIN` (AI) · `PHASE_3_PLENARY` (AI)

### JHS (22 tokens)

`INSERT_WEEK_ENDING` · `INSERT_CLASS_LEVEL` · `INSERT_SUBJECT` · `INSERT_CLASS_SIZE` ·
`INSERT_DATE_DAY` · `INSERT_PERIOD` · `INSERT_DURATION` · `INSERT_REFERENCE_SYLLABUS` ·
`INSERT_STRAND_NAME_AND_CODE` · `INSERT_SUB_STRAND_NAME_AND_CODE` ·
`INSERT_CONTENT_STANDARD_CODE_AND_TEXT` · `INSERT_INDICATOR_CODE_AND_TEXT` ·
`INSERT_CORE_COMPETENCIES_E_G_CRITICAL_THINKING_COLLABORATION` ·
`INSERT_EXPECTED_LEARNER_PERFORMANCE_OUTCOME` · `INSERT_KEY_TERMINOLOGIES_TO_BE_TAUGHT` (AI) ·
`INSERT_RESOURCES_BOOKS_TOOLS_OR_VISUAL_AIDS` (AI) · `PHASE_1_STARTER_ACTIVITIES` (AI) ·
`PHASE_1_RESOURCES_OR_DIAGNOSTIC_ASSESSMENT` (AI) · `PHASE_2_MAIN_LEARNING_STEPS` (AI) ·
`PHASE_2_FORMATIVE_ASSESSMENT_STRATEGIES_AND_TOOLS` (AI) ·
`PHASE_3_PLENARY_AND_REFLECTION` (AI) · `PHASE_3_SUMMATIVE_EVALUATION_METRICS` (blank by design)

### SHS (18 tokens)

`WEEK_ENDING` · `SUBJECT` · `PROGRAMME` · `CLASS` · `PERIOD` · `DURATION` ·
`REFERENCE_MATERIAL` · `INSERT_STRAND` · `INSERT_SUB_STRAND` · `CONTENT_STANDARD` ·
`INDICATOR_CODE` · `PRIOR_KNOWLEDGE` · `CORE_COMPETENCIES` · `KEYWORDS` (AI) · `TLRS` (AI) ·
`PHASE_1_INTRODUCTION` (AI) · `PHASE_2_MAIN_DELIVERY` (AI) · `PHASE_3_EVALUATION` (AI)

Rules that hold for every token:

- A value that cannot be derived renders **blank**; nothing is invented.
  `PERIOD` and `PROGRAMME` are timetable/programme facts TeachFlow does not store, so
  they come from the caller's render context (`{"period": "1 & 2"}`,
  `{"programme": "General Science"}`) or stay empty.
- JSON columns are accepted as lists or as JSON strings (SQLite returns strings on some
  paths); both render identically.
- Enum fields render their value (`Subject.ICT` → `ICT`, not `Subject.ICT`).

## Delivery-grid fills

Columns with no placeholder, filled from stored lesson data:

| Form | Cell | Source |
|---|---|---|
| KG, Primary | `RESOURCES / ASSESSMENT` and `TLRs / ASSESSMENT`, rows 1-3 | resource list, then assessment |
| SHS | `LEARNER ACTIVITIES`, rows 1-3 | learner activities |
| SHS | `TLMs / ASSESSMENT`, rows 1-3 | resource list, then assessment |
| JHS | — | every content column carries a token |

Stored resources and assessment are **lesson-level** in TeachFlow, not per-phase, so the
same values appear against each phase row. Instruct the change if a per-phase split is
wanted.

## Rendering

`DOCXExportEngine.export_official_ges()` dispatches automatically for any official form
(the PDF path converts the DOCX produced here; ZIP carries the chosen template):

1. Open the bundled form (`load_document(spec)`).
2. `strip_guidance()` — drop the JHS numbered blocks and instruction lines.
3. Fill every token from the lesson (`render_into`).
4. Overwrite the declared untokened grid cells.
5. For multiple lessons, clone the stripped form once per lesson after a page break
   (`render_document`): a token can only be filled once, so later lessons need their own
   copy. Grid fills are addressed with a per-page table offset so page two cannot
   overwrite page one.

`validate_rendered_document()` returns any token left unfilled; a clean form returns `[]`.
Generated documents contain no bracket characters at all.

## Default selection

- **Frontend:** `GET /api/templates?educational_level=…&class_level=…` reports
  `is_default` for the class level being planned, so Basic 2 preselects the official
  primary form while Basic 5 preselects the standard primary template.
- **Backend:** any export that does not name a template resolves the default from the
  lessons' own class level (`docx_export.default_template_for_lessons`), so a KG job can
  never render the JHS form.
- `get_default_template_for_class_level()` is the single rule; Basic 4-6 deliberately
  keeps `tpl-primary-standard` until an upper-primary GES form is supplied.
- Nursery uses the KG form, because the app groups Nursery with KG in one
  Early Childhood profile.

## AI assistance

`enrich-lesson` writes activity-family columns only. `EnrichLessonRequest.template_id`
selects the level's prompt and phase names, which are the form's own printed row labels:

| Level | Required phase names |
|---|---|
| KG | Phase 1: Tuning-In, Phase 2: Active Learning, Phase 3: Reflection |
| Primary | Phase 1: Starter, Phase 2: Main Learning, Phase 3: Plenary |
| JHS | PHASE 1: STARTER / INTRO, PHASE 2: MAIN LEARNING, PHASE 3: PLENARY / REFLECTION |
| SHS | Phase 1: Introduction, Phase 2: Main Delivery, Phase 3: Evaluation |

Each prompt adds level framing (`prompt_tailoring`): play-based for KG, teacher modelling
and foundational skills for Lower Primary, tridelivery for JHS, academic depth and
21st-century competencies for SHS. An empty or unknown `template_id` keeps the approved
organizational prompt. All paths use the same strict server-side validator, so a model
response can never write strand, standard, indicator or other curriculum facts.

## Verification

`backend/tests/test_official_ges_template.py` (106 tests) covers all four levels: bundled
assets, token contracts, guidance and example-prose removal, deterministic values, grid
fills, per-level rendering (single and multi-lesson, including that cloned pages do not
share data), registration and default rules, and the AI contract.
