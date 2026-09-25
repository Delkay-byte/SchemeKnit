# WAPEF Implementation Report

**Date:** 2026-09-25
**Branch:** `main` · **Scope:** Approved WAPEF Plan template + KG/Nursery scheme ingestion + generation/export integration

---

## A. Executive status

IMPLEMENTED and VERIFIED. The Approved WAPEF Plan is a registered SchemeKnit template rendered from the supplied WAPEF source document itself; the four WAPEF structured fields (Deep Hope, Storyline, Through lines, God's Story) are teacher-selected dropdowns that persist through create → review → save → reload → generation → preview → DOCX/PDF export; WAPEF KG and Nursery schemes ingest through the existing Curriculum IR (Nursery as an indicatorless week-unit variant). All gates green:

| Gate | Result |
| --- | --- |
| Backend pytest (full suite) | **1239 passed**, 11 skipped, 0 failed |
| WAPEF acceptance tests (items A–K) | **31 passed** |
| TypeScript (`tsc --noEmit`) | 0 errors |
| Production build (`next build`) | ✓ Compiled successfully |
| Browser acceptance (KG + Nursery + export) | **32 passed, 0 failed** |
| Responsive overflow (1440×900, 1024×768, 390×844) | no horizontal overflow |
| Uncaught page errors during browser run | 0 |

## B. Source documents inspected

All four real documents were read directly (paragraphs, tables, merged cells, headings, populated examples) and are bundled as acceptance fixtures:

| Document | Role | Status |
| --- | --- | --- |
| `WAPEF Approved Plan.docx` | structural/template authority; bundled verbatim as the render form | SOURCE VERIFIED |
| `WAPEF SAMPLE SCIENCE.docx` | populated acceptance example | SOURCE VERIFIED |
| `WAPEF SCHEME OF LEARNING FOR KG.docx` | KG ingestion fixture (whole-level, 13 weeks, K2.x.x.x.x indicators) | SOURCE VERIFIED |
| `WAPEF SCHEME OF LEARNING FOR NURSERY.docx` | Nursery ingestion fixture (multi-subject, no indicator column) | SOURCE VERIFIED |

Fixtures live at `backend/tests/fixtures/wapef/`.

## C. Approved WAPEF Plan structure

IMPLEMENTED. The template does **not** hand-write the WAPEF layout: the supplied document is tokenized in place (`backend/src/engines/assets/wapef_approved_plan_template.docx`) and filled, so the output is topologically identical to the approved source by construction — school/vision header, LESSON PLAN title, the 16-row metadata table (Week, Ending, Subject, Class, Class Size, Strand, Sub-Strand, Content Standard, Learning Indicator, Performance Indicator, Core Competencies, Key Words, Through line, God's Story, Deep Hope, Storyline), then the PHASE 1 (STARTER) / PHASE 2 (MAIN) / PHASE 3 grid with LEARNER ACTIVITIES and RESOURCES, EVALUATION and REMARKS. Verified by:

- token-topology tests (all 24 tokens present, labels/title preserved, table topology matches the source asset);
- a real export inspection (see J below).

## D. WAPEF special fields

IMPLEMENTED (`backend/src/engines/wapef_fields.py`, TESTED):

- **Deep Hope** — single-select. Approved value: *"Learners will recognize and appreciate the beauty, order, and purpose of design in the physical world around them."*
- **Storyline** — single-select: *"Shaping our world."*
- **Through lines** — multi-select, exact approved labels: God worshiper, Image reflector, Earth keeper, Justice seeker, Community builder, Idolatry descerner, Order discoverer, Servant worker, Creation enjoyer, Beauty creator. Export order follows the approved option list; two values join with "and" per real WAPEF prose.
- **God's Story** — single-select: Creation, Fall, Redemption, Restoration.

Teacher selection wins: AI is contractually blocked from emitting these fields (`validate_wapef_lesson_json` strips any model-emitted WAPEF key; the prompt marks them READ-ONLY; `generation_pipeline` restores teacher values after AI enrichment). Values normalize through the approved lists — unknown values are dropped, never invented. Remark: the four fields are stored on the lesson row (see E), no duplication.

## E. Data model changes

IMPLEMENTED (migration `v025_wapef_lesson_fields`):

- `lesson_plans.wapef_deep_hope` (TEXT, nullable), `wapef_storyline`, `wapef_through_lines` (JSON list), `wapef_gods_story`, plus `remarks` (teacher REMARKS row). Existing GES lessons remain valid with NULLs; nothing is back-filled.
- Draft persistence reuses `schemes.lesson_review_drafts` with the `wapef_*` keys allowed.
- Internal canonical values equal the teacher-facing labels (through-line slugs were rejected in favour of exact labels, satisfying the display-label requirement).

## F. KG ingestion

IMPLEMENTED, TESTED. The KG scheme parses through the existing indicator-oriented Curriculum IR: 13+ weeks, KG 2 class, `K2.1.1.1.1 K2.1.1.1.1-3`-style range codes preserved as ONE indicator (no fabricated second code), normal indicator allocation (one indicator → one period → one lesson), honest objectives ("Learners can …", code-free prose).

**Discovery during acceptance:** the KG document is a *whole-level* scheme with **no subject headings at all**, which dead-ended the upload confirmation card (message with zero buttons). Two fixes:

1. Parser (`docx_parser.py`): when a document has NO subject sections anywhere, `target_subject` now applies the teacher's confirmed subject to the whole document (single table — nothing to mix). The anti-mixing guard still holds for documents WITH sections (Nursery): an unlisted subject yields zero weeks. TESTED by `test_kg_whole_level_scheme_confirm_subject` and `test_confirm_subject_cannot_mix_multi_subject_sections`.
2. Upload UI (`upload/page.tsx`): when weeks extracted but no subject headings exist, the confirmation card now loads the subject catalogue for the detected class level (`GET /api/settings/subjects?level=KG 2`) into a `Select` so the teacher declares the subject. TESTED in browser.

## G. Nursery ingestion

IMPLEMENTED, TESTED. `WAPEF_NURSERY`-style handling: the multi-subject document is sectioned per subject (Numeracy / Language & Literacy / Creative Arts and Design / Our World Our People); confirming one subject re-extracts only that section. Nursery rows legitimately carry no Content Standard / Indicator column; allocation detects the indicatorless condition and creates **one lesson per weekly row** (subject, strand, sub-strand, resources verbatim) without ever fabricating codes or standards. Empty curriculum fields export honestly blank per existing conventions.

## H. Subject isolation

IMPLEMENTED, TESTED. Nursery subject sections are detected generically (paragraph headings + in-table heading rows, order-preserving block iteration), normalized to the `Subject` enum, and weeks/strands/sub-strands/resources are scoped to the confirmed subject. Browser acceptance verified the detection card lists ≥ 3 expected subjects and that only Numeracy rows proceed; cross-subject leakage is covered by the anti-mixing parser test.

## I. Generation integration

IMPLEMENTED, TESTED. Generation context distinguishes SOURCE-AUTHORITATIVE data (week, subject, class, strand, sub-strand, content standard, learning indicator, source TLRs, week-ending — always from the scheme row) from TEACHER-SELECTED WAPEF data (the four fields, read-only guidance for the AI, restored verbatim after enrichment) and GENERATED data (objectives, activities, assessment). AI guard tests: `v2_apply_never_touches_wapef_fields`, `wapef_context_is_read_only_guidance`, `validate_wapef_lesson_json_strips_ai_wapef_keys`.

**Bug found and fixed during acceptance:** `normalize_wapef_payload` read bare keys (`deep_hope`) while the whole pipeline uses `wapef_`-prefixed keys, silently wiping teacher selections at generate time. The normalizer now accepts both spellings (prefixed wins), with junk values still dropped (TESTED).

**Bug found and fixed:** under the Free Tier quota, Nursery-style (indicatorless) allocations were advertised as `selectable_indicators` with EMPTY codes that the UI can never select → Confirm & Generate permanently disabled. The preview now advertises only genuine indicator codes; the generate endpoint already exempted indicatorless schemes. UI now also states quota exhaustion explicitly instead of a silent disable.

## J. DOCX export

IMPLEMENTED, TESTED, VERIFIED ON A REAL EXPORT. Export flows through the same template mechanism (`export_docx_combined` → `is_wapef_template` → `export_wapef`): the bundled WAPEF form is filled in place, one plan per page. A real downloaded `Lesson_Plans_WAPEF_SCHEME_OF_LEARNING_FOR_KG.docx` was inspected from its XML: metadata table populated in approved order, Through line rendered "God worshiper and Image reflector", God's Story / Deep Hope / Storyline verbatim, three-phase grid with activities/resources, zero leftover `{{TOKENS}}`.

**Bug found and fixed:** after reload the generate page reset its template dropdown to the level default, so a WAPEF job exported onto the GES form. The scheme-status endpoint now returns the generating job's `template_id` (from its config snapshot) and the page restores it, keeping exports consistent with how lessons were generated.

## K. PDF export

IMPLEMENTED, VERIFIED. PDF renders from the same canonical call (`export_docx_combined` with the same template id, then LibreOffice conversion) — no duplicated WAPEF logic, so DOCX and PDF cannot drift. A real `Lesson_Plans_WAPEF_SCHEME_OF_LEARNING_FOR_KG.pdf` (17 pages) was produced and text-probed: vision header, FACILITATOR line, metadata table, Deep Hope / Storyline / Through line values all present.

## L. Real-document acceptance

TESTED (`backend/tests/test_wapef_acceptance.py`, 31 tests) against the four real fixtures: template registration, token topology, KG parsing + honest allocation, whole-level confirmation, anti-mixing, Nursery multi-subject + indicatorless week-units, field normalization, draft round-trip, AI guards, DOCX export structure, through-line export order, DB persistence round-trip, options endpoint, and a Basic 9 Science GES end-to-end non-regression.

## M. Browser acceptance

TESTED (`frontend/e2e/wapef-acceptance.js`, 32 checks, Playwright): fresh teacher signup; Nursery leg (multi-subject confirmation → Numeracy isolation → WAPEF template → per-lesson field controls → selections → generate); KG leg (whole-level confirmation via subject catalogue → 13 lessons → no cross-leg leakage → lesson-2 independent God's Story); real DOCX download whose XML carries the teacher's selections verbatim; lessons list; responsive pass; zero page errors.

## N. Regression results

- Full backend suite: **1239 passed** (was failing 5 pre-existing stale tests — fixed: two test paths referenced the pre-`(app)` route-group page location, one Banner role assertion moved into the shared primitive, one date-fragile guard; all root-caused, none masked).
- Existing GES/curriculum/generation/export suites green; WAPEF never becomes the default template (`wapef_template_never_default_for_ges_level`).
- **Lessons-page 390px overflow fixed** (native `<select>` filter grew with long scheme names → `max-w-full`).

## O. Screenshots

`frontend/e2e/wapef-acceptance/*.png` — 01 nursery subject confirm, 02 nursery review, 03/04 nursery fields + post-generate, 05/06 KG confirm + review, 07/08 KG fields + post-generate, 09 export, 10–12 lessons + responsive 1024/390. All visually inspected; no overflow at any viewport.

## P. Known limitations

- PDF page geometry inherits LibreOffice's rendering of the WAPEF form; visual fidelity of fonts/row heights is good but not pixel-audited beyond text presence and pagination.
- The `Content Standard` cell exports blank for the KG fixture (the source table carries no separate content-standard text; nothing is fabricated, per spec).
- Nursery/whole-level confirmation requires the teacher to declare the subject; no auto-detection is attempted (honest-unknown policy).
- AI Mode OFF (deterministic) used for acceptance; AI providers were not exercised end-to-end (quota/keys), though the AI guards are unit-tested.

## Q. Commits

1. `feat(wapef): add Approved WAPEF Plan and structured metadata`
2. `feat(wapef): support KG and Nursery scheme ingestion`
3. `feat(wapef): integrate generation and document exports`
4. `test(wapef): add real document and browser acceptance`
5. `docs(wapef): add implementation and acceptance report`

## R. HEAD / origin parity

Pushed and verified `git rev-parse HEAD` == `git rev-parse origin/main` (see commit section output).
