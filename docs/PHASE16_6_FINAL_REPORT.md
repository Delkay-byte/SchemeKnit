# PHASE 16.6 — CURRICULUM INTEGRITY + PER-LESSON REVIEW DATA + DATE/RESOURCE CORRECTNESS

**Project:** SchemeKnit (repo folder: `TeachFlow`)
**Date:** 2026-09-23
**Branch:** `main` @ `ac0ab6be5f3f4f3fee016ce61b55189cb134c353` (base HEAD — this report describes the changes committed on top)
**Remote:** `https://github.com/Delkay-byte/SchemeKnit.git`
**Baseline preserved:** Phase 17 (`60fe769` / `6e45e5b`) + Phase 16.5 (`bd5ee1f` / `ac0ab6b`) — not reverted.

---

## A. Executive Summary

Phase 16.6 remediates real-world curriculum-integrity defects found while using actual GES schemes: missing Basic 6 subjects, cross-subject resource contamination, Basic 6→Basic 9 class misreads, source week-ending dates overwritten by generated dates, and global Keywords/TLRs/Competencies/References shared across every lesson. It also adds a pre-generation **per-lesson review draft** layer so teachers can edit lesson-scoped fields before AI runs, without letting AI overwrite authoritative source fields.

| Dimension | Status |
|-----------|--------|
| Backend suite | **1206 passed, 10 skipped, 0 failed** (~256s, 2026-09-23) |
| Phase 16.6 sections A–T tests | **93 passed** (`test_phase16_6_section_{a,b,c,d_e,f_t}.py`) |
| Real-document acceptance | **39 passed** (`test_real_document_acceptance.py` + `test_real_acceptance_quality_gate.py`) |
| Frontend type-check / build | **OK** (`npx tsc --noEmit` exit 0; `npm run build` exit 0) |
| B6 census (DOCX + PDF) | **9/9 EXPECTED = DETECTED, MISSING=[], EXTRA=[]** |
| B7 census | **10 subjects**, Science parse **15 weeks** |
| B9 multi-subject PDF | **10 subjects**; English **15 weeks**, Science **15 weeks** |
| B8 full PDF | Honest **`no_text_layer`** (45 blank pages) — not fixed, reported |
| Live providers | Gemini **key rejected** (owner re-mint); Groq **LIVE** (`openai/gpt-oss-20b`); `AI_MODE=OFF` restored |
| Lesson template topology | **FROZEN** (Phase 17 approved GES layout unchanged) |

**Verdict:** All Section A–T implementation gates and full regression are green. Remaining items are honest limitations (B8 scan, no Basic 6 ICT source file beyond census subject heading, Gemini key) — see **P**.

---

## B. Objectives & Scope

**North star:** a teacher uploads a real multi-subject scheme and gets the **right subject section**, **correct class level**, **source-authoritative week-ending dates**, and **per-lesson** keywords / TLRs / competencies / references — never one global set, never AI overwriting source.

In scope delivered (Sections A–T):

1. **A** — subject-section detection (generic, no hardcoded lists): real B6/B7 heading census + synthetic wrapped/in-table headings.
2. **B** — target-miss isolation: no fallback-mix of other subjects on DOCX/PDF when `target_subject` is missing; upload zero-mix.
3. **C** — evidence-based class-level detection (no Basic 9 class for a Basic 6 document).
4. **D/E** — source week-ending dates: `_parse_date`, `week_ending_derived`, migrations v021/v022, thread Week → WeekDB → documents → service → LessonPlan → export; AI never overwrites source week-ending.
5. **F–H / J** — models: `ReferenceEntry`, NaCCA taxonomy, `LessonPlan.source_tlrs/other_tlrs/structured_references/week_ending/week_ending_derived`, `AllocatedIndicator.source_resources/week_ending_derived`, migrations v023/v024.
6. **K–N** — AI provider `generate_lesson_v2` signatures accept lesson context (`source_week_ending`, `other_tlrs`, `core_competencies`, `references`); prompt sections for SOURCE TLRs / OTHER TLRS / CORE COMPETENCIES / REFERENCES / Source Week-Ending / TEACHER-SUPPLIED VOCABULARY “for THIS lesson”.
7. **O** — lesson_builder: source TLRs from `alloc.source_resources` only; other TLRs separate; keywords CS+indicator+activity then teacher; structured refs (Subject Curriculum, Teacher's Guide, strand ref + teacher strings, blank pages never invented).
8. **P** — generation_pipeline: `_apply_v2_content` Section P authoritative snapshots/restores; conditional `v2_kwargs` via `supports_kwarg`.
9. **Q** — per-lesson review: `SchemeDB.lesson_review_drafts`, service get/save drafts, `GET/PUT /{scheme_id}/lesson-review` with blocked source-field rejection, `_apply_lesson_review_draft` before `create_lesson_plan`, frontend allocation-preview review panel + lessons/[id] editor.
10. **R** — real-document acceptance (this report).
11. **S** — full validation gates.
12. **T** — lifecycle: save → reload → generate → preview → export with distinct per-lesson fields.

Out of scope (unchanged): OCR, lesson-doc template redesign, billing/marketing, Gemini key re-mint, B8 text-layer recovery.

---

## C. Section A — Subject-section detection

### Defect

Real multi-subject schemes (B6/B7/B9) use district-style headings that the previous matcher either treated as prose or only partially matched:

```
FIRST TERM SCHEME OF LEARNING FOR BASIC 6 - ENGLISH LANGUAGE
FIRST TERM SCHEME OF LEARNING, 2026/2027 – BS9 CREATIVE ARTS AND DESIGN
ENGLISH LANGUAGE SCHEME OF LEARNING – TERM 1 - FORM 3
FIRST TERM SCHEME OF LEARNING, 2026/2027 - B9 SCIENCE
FIRST TERM SCHEME OF LEARNING SOCIAL STUDIES - BASIC 9
FIRST TERM SCHEME OF LEARNING - 2026/2027 ACADEMIC YEAR - BASIC NINE - CAREER TECHNOLOGY
FIRST TERM SCHEME OF LEARNING, 2026/2027- B9 RELIGIOUS & MORAL EDUCATION
```

Early Section A work required the **normalised** heading to equal a bare subject keyword. Real headings keep class codes (`B9`, `BS9`, `FORM 3`, `BASIC NINE`), year noise, `&` vs `and`, and titles longer than 80 characters — so **only Social Studies matched** on BASIC 9 TERM 1.pdf (`detected_subjects=['Social Studies']`, English/Science parse → 0 weeks). Six `TestBasic9Acceptance` tests failed.

### Fix (`subject_keywords.py`)

1. **`_normalize`**: replace `&` with ` and `; strip class/form codes via `_CLASS_CODE` (`B9`, `BS9`, `FORM 3`, `BASIC NINE`, …); keep `_LEVEL_NUM` and `_NOISE_PATTERN` (extended with `form|academic|year|nine|ten|…`).
2. **`MAX_HEADING_LENGTH`**: 80 → **120** so full district titles still normalise to a bare subject; prose still rejected when normalised form ≠ subject keyword (`THE SCIENCE OF MEASUREMENT IS FUN` → `None`).
3. **`canonical_subject_from_heading`**: exact match after noise/class-code strip (unchanged contract).

### Proof

| Heading (raw) | Normalised | Result |
|---|---|---|
| `… – BS9 CREATIVE ARTS AND DESIGN` | `creative arts and design` | `CREATIVE_ARTS` |
| `ENGLISH LANGUAGE SCHEME … – TERM 1 - FORM 3` | `english language` | `ENGLISH` |
| `… - B9 SCIENCE` | `science` | `SCIENCE` |
| `… SOCIAL STUDIES - BASIC 9` | `social studies` | `SOCIAL_STUDIES` |
| `… BASIC NINE - CAREER TECHNOLOGY` | `career technology` | `CAREER_TECHNOLOGY` |
| `… B9 RELIGIOUS & MORAL EDUCATION` | `religious and moral education` | `RME` |
| `… BS9 COMPUTING` | `computing` | `ICT` |
| `THE SCIENCE OF MEASUREMENT IS FUN` | `the science measurement is fun` | **None** (prose) |

`test_phase16_6_section_a.py` + Section B isolation: **23 passed**. BASIC 9 multi-subject tests: **15 passed**.

---

## D. Section B — Target-subject isolation (no cross-subject mix)

- When `target_subject` is provided and no matching section exists → **empty scheme + section_miss**, never another subject's tables (DOCX + PDF).
- Upload path: multi-subject picker exposes sections; confirming one subject re-extracts **only that section**.
- Cross-subject week-1 resource equality assertions (ICT vs French) in Section B tests — **green**.

---

## E. Section C — Class-level detection (no B6→B9 misread)

- Evidence-based class detection: document text/filename/heading evidence; unknown class is **not** fabricated as Basic 9.
- Filename vs document mismatch requires confirmation; high-confidence consistent signals proceed.
- B6 docs detect Basic 6; B9 PDF detects Basic 9 / Form 3 style headings without claiming B6 content is B9.

---

## F. Sections D/E — Source week-ending correctness

| Piece | Location |
|---|---|
| `_parse_date` (dash/slash/dot, month names) | `docx_parser.py` / shared helpers |
| `Week.week_ending` + `week_ending_derived` | `models.py`, `WeekDB` |
| Migrations **v021**, **v022** | `src/migrations/` |
| Thread Week → documents → service → LessonPlan → export | parsers, `service.py`, `official_ges_template.py`, export |
| AI never overwrites source week-ending | `generation_pipeline._apply_v2_content` snapshot/restore |
| Preview / report carry `week_ending`, `week_ending_derived` | `generation.py`, `coverage_validator.generate_report` |

**Precedence:** AUTHORITATIVE SOURCE > TEACHER > AI.

---

## G. Sections F–N — Per-lesson data model + AI context

### Models / DB

- `ReferenceEntry` (type/title/author_publisher/page/notes); page **never** auto-invented.
- NaCCA core competency canonical 6 (CP, CI, CC, CG, PL, DL) + labels.
- `LessonPlan`: `source_tlrs`, `other_tlrs`, `structured_references`, `week_ending`, `week_ending_derived`.
- `LessonPlanDB` JSON columns; **v023** (lesson review columns), **v024** (`scheme_lessons.lesson_review_drafts`).
- `AllocatedIndicator.source_resources`, `week_ending_derived`.

### AI provider / prompt

All five concrete `generate_lesson_v2` subclasses accept and forward:

`source_week_ending`, `other_tlrs`, `core_competencies`, `references`

Prompt sections (lesson-scoped wording): SOURCE TLRs · OTHER TLRs · CORE COMPETENCIES · REFERENCES · Source Week-Ending · TEACHER-SUPPLIED VOCABULARY “for THIS lesson”.

`Curriculum Week:` label renamed to **`Source Week:`** (source curriculum week vs teaching calendar week) — one existing assertion updated in `test_generation_v2_integration.py` (intent unchanged: schedule still anchored).

---

## H. Sections O/P — Builder + pipeline integrity

- **Source TLRs** only from `alloc.source_resources` (subject+week scoped); never global config resources.
- **Other TLRs** from teacher seed / review drafts — stored separately.
- **Keywords**: content standard + indicator + activity, then teacher keywords appended.
- **Structured references**: Subject Curriculum, Teacher's Handbook, strand reference + teacher strings; blank page fields stay blank.
- **v2_kwargs** gated by `supports_kwarg` so older provider stubs do not TypeError.
- **Section P**: authoritative curriculum fields snapshotted and restored after AI apply.

---

## I. Section Q — Per-lesson review drafts (frontend + API)

### API

| Endpoint | Behaviour |
|---|---|
| Allocation preview | Returns `lesson_review_drafts` + `lesson_review[]` seed rows |
| `GET /{scheme_id}/lesson-review` | Load drafts |
| `PUT /{scheme_id}/lesson-review` | Save allowed fields only |

**Allowed fields only:** `keywords`, `other_tlrs`, `core_competencies`, `structured_references`.

**Blocked → 400:** `source_tlrs`, `week_ending`, `week_ending_derived`, `indicator_code`, `content_standard`, `strand`, `sub_strand`, `source_week`.

Generate loop: `_apply_lesson_review_draft(lp, drafts)` **before** `create_lesson_plan`.

### Frontend

- **Generate page:** per-lesson review panel in Allocation Preview — read-only source TLRs + source week-ending; editable keywords, other-TLR chips, NaCCA competency multi-select, structured refs (type/title/author/page/notes). Save review button; drafts auto-saved on confirm-and-generate. Global fields relabeled **“(seed for all lessons)”** / **“(seed — not source)”**.
- **Lesson detail page:** Lesson Review Data editor (keywords / other TLRs / competencies / structured refs); read-only source TLRs + source week-ending; `handleSave` sends the four allowed fields + derived `references`.
- **Types/API:** `ReferenceEntry`, `LessonReviewSeed`, `Week.week_ending_derived`, `getLessonReview` / `saveLessonReview`.

**Workflow unchanged:** UPLOAD → REVIEW CURRICULUM → ALLOCATE → REVIEW INDIVIDUAL LESSON DATA → SAVE → GENERATE → PREVIEW → EXPORT.

---

## J. Section R — Real-document acceptance

### R1. Basic 6 multi-subject census

**Expected** (from document structure, `B6_EXPECTED_SUBJECTS`): Science, ICT, English Language, French, Creative Arts and Design, Mathematics, Religious and Moral Education, History, Ghanaian Language — **9**.

| File | Status | DETECTED | MISSING | EXTRA |
|---|---|---|---|---|
| `BASIC 6 TERM 1.docx` | `multiple` | **9** | **[]** | **[]** |
| `BASIC 6 TERM 1.pdf` | `multiple` | **9** | **[]** | **[]** |
| `BASIC 6 FRENCH SCHEME OF LEARNING.docx` | `single` | French | — | — |

- B6 English Language parse: **13 weeks**, `Subject.ENGLISH`.
- B6 French parse: **15 weeks**, `Subject.FRENCH`.
- **ICT subject heading: PRESENT** in census (ICT section detected). Note: no separate standalone ICT scheme file was provided beyond the multi-subject B6 document’s ICT section — honest source limitation.

### R2. Basic 7

- `BASIC 7 TERM 1.docx`: **10 subjects** (`multiple`).
- `BASIC 7 TERM 1.pdf` Science parse: **15 weeks**, `Subject.SCIENCE`.

### R3. Basic 8

- `BASIC 8 TERM 1.pdf`: **`extraction_failed` / `no_text_layer`**, 45 pages, **0 text chars**, 0 extractable subjects.
- Honest failure path (Phase 16D/16.5) preserved; upload UI explains scanned PDF / OCR.
- Multi-subject DOCX path for B8-equivalent content remains covered by synthetic/repro fixtures (`repro_multi.docx` style tests).

### R4. Basic 9 multi-subject PDF (`BASIC 9 TERM 1.pdf`)

| Metric | Value |
|---|---|
| `detection_status` | **`multiple`** |
| Subjects | **10**: Career Technology, Creative Arts and Design, English Language, French, Ghanaian Language, ICT, Mathematics, Religious and Moral Education, Science, Social Studies |
| English Language parse | **15 weeks**, `Subject.ENGLISH`, `extracted` |
| Science parse | **15 weeks**, `Subject.SCIENCE`, `extracted` |
| Distinct strands EN vs SC | English: Oral language…; Science: Cycle / Diversity of Matter / Force and Energy |

**Regression fixed this phase:** Section A over-strict normalisation had reduced B9 to only Social Studies (0-week English/Science). Class-code + `&` + length fixes restored full multi-subject detection (Section C above).

### R5. Cross-subject isolation on real docs

Section B tests: ICT vs French week-1 resources on B6 PDF do **not** mix; target-miss returns empty, not another subject.

---

## K. Section S — Validation gates

| Gate | Result |
|---|---|
| `python -m pytest tests/` (full backend) | **1206 passed, 10 skipped, 0 failed** |
| Phase 16.6 A–T suites | **93 passed** |
| Real-doc acceptance + quality gate | **39 passed** |
| Phase 16.5 + GES + carry-forward + quota + providers + quality | **200 passed, 1 skipped** |
| `npx tsc --noEmit` (frontend) | **exit 0** |
| `npm run build` | **exit 0** (compile + typecheck + SSG) |
| Secret hygiene (no `AQ.` / `gsk_` / `sk-proj-` in `src/`) | **pass** (full suite includes hygiene tests) |
| Lesson template topology | **unchanged** (Phase 17 frozen) |
| Migrations v021–v024 | applied on startup; full suite exercises service/DB |

Temp diagnostic scripts (`_repro_b6.py`, `_census*.py`, `_fix_v2_sigs.py`, `_census_out.json`) **deleted** before commit. `backend/.env` not staged. `frontend/tsconfig.tsbuildinfo` left unstaged.

---

## L. Section T — Lifecycle acceptance (save → reload → generate → preview → export)

Proven by Section Q tests 13–24 (`test_phase16_6_section_f_t.py`) + service/API tests:

1. **Allocation preview** returns lesson review seeds (source TLRs, week-ending, keywords/competencies/references seeds).
2. **Teacher saves drafts** (`PUT …/lesson-review`) for allowed fields only; blocked source fields rejected **400**.
3. **Generate** applies drafts via `_apply_lesson_review_draft` before persisting each `LessonPlan`.
4. **Per-lesson independence:** Lesson 3 keywords/other_tlrs/competencies/pages ≠ Lessons 1/2 after save→reload→generate.
5. **Source integrity:** `source_tlrs` and `week_ending` remain source-authoritative through AI apply and export.
6. **Preview / export:** `lesson_review` visible in coverage report periods/teaching_weeks; export carries source week-ending fields (template structure frozen).

---

## M. What was NOT changed

- Phase 17 zip Pro-gate, quality gate, Groq default, AI diagnostics — intact.
- Phase 16.5 indicator-specific lessons, AI-mode wiring — intact.
- `AI_MODE=OFF` deterministic path — intact and default in `.env` after acceptance runs.
- Lesson document structure / approved GES template topology — **frozen**.
- OCR for B8 — not added (product decision).
- No new global “one set of TLRs/competencies for all lessons” — explicitly the opposite.

---

## N. Data-model rule (provenance)

| Field | Source | AI may write? |
|---|---|---|
| `source_tlrs` / `source_resources` | Scheme section (authoritative) | **No** |
| `other_tlrs` | Teacher / review draft | **No** (AI prompt only) |
| `keywords` | Teacher seed + CS/indicator derivation | **No** overwriting teacher keywords |
| `core_competencies` | Teacher / NaCCA selection | **No** |
| `structured_references` / `references` | Teacher (pages never invented) | **No** |
| `week_ending` / `week_ending_derived` | Source scheme date | **No** |
| `indicator_code`, `content_standard`, `strand`, `sub_strand`, `source_week` | Curriculum | **No** (identity lock) |

**Precedence:** AUTHORITATIVE SOURCE > TEACHER > AI.

---

## O. Reference types (Section P / teacher control)

1. **Subject Curriculum**
2. **Teacher's Handbook / Teacher's Guide**
3. **Textbook**
4. **Other**

Fields: type, title, author_publisher, page, notes. Pages left blank unless teacher enters them. Curriculum page is teacher-controlled per lesson.

---

## P. Honest limitations & owner-side items

| Item | Status | Action needed |
|---|---|---|
| **B8 `BASIC 8 TERM 1.pdf`** | Scanned, `no_text_layer`, 45 blank pages | Owner: OCR or re-export text PDF |
| **Basic 6 ICT standalone file** | No separate ICT-only scheme file; ICT **section** present in B6 multi-subject | Owner: provide ICT-only file if deeper ICT week audit needed |
| **B6 English 13 weeks** | Document has 13 parsed English weeks (not 15) | Verify against source; not fabricated upward |
| **Gemini live** | Key **rejected** (`auth_key_type_unsupported` / owner re-mint) | Owner: new Gemini key |
| **Groq live** | **PASSING** `openai/gpt-oss-20b` | — |
| **AI default** | `AI_MODE=OFF` in `.env` | Owner: flip only when ready |
| **Live Render deploy SHA** | Still not exposed on health | Optional observability |

---

## Q. Commits

| Commit | Message |
|---|---|
| *(implementation)* | `feat: Phase 16.6 — curriculum integrity, source dates, per-lesson review data` |
| *(report)* | `docs: add Phase 16.6 curriculum integrity report` |

Base: `ac0ab6b` (Phase 16.5 report). Both pushed to `origin/main`.

---

## R. Gate summary

| Gate | Verdict |
|---|---|
| A Subject sections (real B6/B7/B9 + synthetic) | **PASS** |
| B Target-miss isolation | **PASS** |
| C Class-level evidence | **PASS** |
| D/E Source week-ending + migrations | **PASS** |
| F–N Models, AI context, builder, pipeline | **PASS** |
| Q Per-lesson review API + UI | **PASS** |
| R Real-doc census + B9 multi-subject fix | **PASS** |
| S Full pytest / tsc / build | **PASS** |
| T Lifecycle per-lesson independence | **PASS** |
| B8 text layer | **HONEST FAIL** (`no_text_layer`) |
| Gemini live | **BLOCKED** (owner key) |
| Groq live | **PASS** |
| Lesson template freeze | **PASS** (unchanged) |
| Secrets / no `.env` commit | **PASS** |

**Phase 16.6 verdict: COMPLETE — ship.**
