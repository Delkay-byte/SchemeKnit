# WAPEF KG Implementation Report

**Date:** 2026-09-25
**Phase:** KG curriculum interpretation & lesson generation
**Baseline:** WAPEF phase complete at `d1bd646` (untouched — WAPEF architecture preserved)

---

## A. Source documents inspected

All documents in `C:\Users\SAVIOUR\Documents\DScience\Lesson Plan` were enumerated; every KG-relevant document was inspected in full (paragraphs, tables, merged cells, all rows):

| Document | KG relevance | Status |
| --- | --- | --- |
| `WAPEF SCHEME OF LEARNING FOR KG.docx` | KG2 whole-level scheme: 13 instruction weeks, code-only CS cells (`k2.1.1.1`), code+range indicator cells (`K2.1.1.1.1 K2.1.1.1.1-3`), continuation weeks W6→W7, W12→W13 | SOURCE VERIFIED (fixture) |
| `KG 1 Scheme.pdf` | **KG1 whole-level scheme (newly discovered this phase)**: 15 weeks, vertically merged header (`CONTENT` / `STANDARD` split across rows), `INDICATOR(S)` header, per-week indicator ranges, REVISION (W13-14) + SBA (W15) special weeks, "play-based and authentic assessment … Observation checklist" | SOURCE VERIFIED (fixture) |
| `WAPEF SAMPLE SCIENCE.docx` / `WAPEF SAMPLE MATHS.docx` | Completed Basic-2 plans; behavioral patterns: songs, "Simon Says", demonstration, oral-question evaluation, observation | SOURCE VERIFIED (pedagogy reference; not KG-specific) |
| `Math/My Math Week *.docx`, `Science/My Science Week *.docx` | Basic 9 lesson notes — **not KG** | NOT APPLICABLE to KG |
| `BASIC 6/7/9 SCHEME …`, `BASIC 6 TERM 1` | Basic-level schemes | NOT APPLICABLE to KG |

**NO COMPLETED KG LESSON FIXTURE FOUND** — the directory contains no filled KG lesson plan. KG pedagogy decisions below therefore rest on the KG1/KG2 *schemes* (assessment rows, resource columns, special-week wording) plus the WAPEF sample-plan *style*, and are scoped accordingly.

## B. Existing KG behavior before changes

- KG2 DOCX parsed 13 weeks with indicators (previous phase) but the **content-standard column was dropped entirely** (code-only cell → "no description" → discarded).
- **KG1 PDFs lost both the content-standard AND indicator columns** (merged-header fragments `CONTENT`/`STANDARD` were not aliases; `INDICATOR(S)` was not an alias) → `scheme_has_indicators()` returned False → KG1 was silently misrouted down the **Nursery week-unit path**.
- KG lessons used the **subject pedagogy profile**: KG2 "Numeracy" generated *"worked example on the board"*, *"solves 2-3 problems independently"*, *"written class exercise"* — contradicted by every KG source.
- W12/W13 (identical rows) generated **byte-identical lessons** (the prev/next linkage passed code-only text, which strips to nothing).
- Quality gate warned `boilerplate_detection` on every KG lesson (intro/starter mirror counted twice).

## C. Actual KG curriculum structure discovered

- **One row = one teaching week.** The scheme prints one row per week with WEEK ENDING dates.
- **Indicator cells are code+range families** (`K2.1.1.1.1 K2.1.1.1.1-3`): the code identifies the indicator; the range tail (`-3`) bounds the sub-skills taught across the week.
- **The source splits multi-week topics itself**: KG1 W7 `K1.1.6.1.1-4` and W8 `K1.1.6.1.5-8` share one sub-strand. This is direct evidence that a range does NOT mean "split into N lessons" — the curriculum author already spreads ranges across weeks.
- **Continuation weeks repeat the sub-strand** with a new range slice (KG2 W6→W7, W12→W13).
- **Special weeks are explicitly marked** (REVISION, REVISION AND ASSESSMENT, SBA ACTIVITIES AND VACATION) and carry "-" instead of codes.
- **KG assessment is play-based/authentic**: "Integrated, play-based and authentic assessment", "Observation checklist, portfolio, learner work".
- **KG1 vs KG2 are structurally identical**, differing only in the level digit (K1 vs K2) — one code path handles both.

## D. Indicator interpretation

TESTED. A KG indicator cell = **one teachable indicator family per week**:
- `_split_indicators` keeps `K2.1.1.1.1 K2.1.1.1.1-3` as ONE entry (code+rejoined range) — unchanged from the previous phase, now pinned by tests.
- Distinct merged indicators (Basic schemes) still split — pinned.
- The range tail is retained verbatim in the stored indicator text and on the exported plan; the code never appears in learner-facing prose.

## E. Allocation behavior

TESTED. Indicator-bearing KG schemes use the standard allocation path: one indicator family → one teaching period → one lesson, in curriculum order, with carry-forward into later teaching weeks (verified live: KG1 showed "Carried forward from Week 1"). Special weeks (REVISION/SBA) are excluded from `include_special_weeks=False` runs. Nursery remains on the separate week-unit path (regression-pinned).

## F. KG generation changes

IMPLEMENTED (`lesson_builder.py`, `allocation_engine.py`, `quality_gate.py`):
1. **Class-level pedagogy override**: KG1/KG2 lessons use the existing `early_childhood` profile regardless of confirmed subject — song/rhyme/movement starters, play-based practice, individual try, "Observe children during play … no written test" assessment. Evidence: KG1 scheme assessment row + resource columns; WAPEF sample activity style.
2. **KG objective phrasing**: "Learners can identify, talk about and act out {sub-strand}" — observable verbs (the gate's measurable-verb bank) matching the sources' demonstration/identification pattern.
3. **Continuation-week linkage**: code-only prev/next indicator text is substituted with the row's sub-strand, so W13 opens "Build on the previous lesson ('My School Family') …" instead of cloning W12.
4. **Boilerplate false positive fixed**: `introduction == starter_activity` mirror no longer counts twice (the renderers dedupe it into one phase-1 bullet).
5. **Content-standard preservation**: code-only CS cells are kept canonically (`K2.1.1.1`, lowercase source normalized, never duplicated).

## G. WAPEF integration

UNCHANGED and regression-pinned: one `Approved WAPEF Plan` template (`len([t for t in DEFAULT_TEMPLATES if t.id.startswith("tpl-wapef")]) == 1`); the four WAPEF fields remain teacher-selected; AI guards untouched; KG lessons accept and export the teacher selections (tested through the real export XML).

## H. Resource preservation

TESTED. KG source TLRs ("Poster/ cut out, Cut out shapes, big books, counters, crayons"; KG1: "Posters, cut-outs, big books, mirrors, counters, crayons") survive parsing, allocation, generation (`source_tlrs` verbatim, head of the display list) and export. KG1 multi-line PDF cells are preserved.

## I. Assessment behavior

IMPLEMENTED per source evidence: observation-checklist style ("Observe children during play and the individual try … there is no written test") tied to the lesson's own focus text — never a generic block. Quality gate verifies `assessment_alignment` passes on KG lessons.

## J. Real-document tests

`backend/tests/test_kg_acceptance.py` — **33 tests, all green**, covering A–N: KG class detection (KG1 ≠ KG2 pinned), scheme parsing both files, merged-header indicator recovery, special-week classification, multi-row/continuation handling, indicator-range non-splitting (and Basic-scheme splitting still works), code-only CS preservation, resource preservation, allocation order, continuation-week difference, play-based generation assertions (song/play present; "on the board"/"written class exercise" absent), observation-based assessment, code-free objectives, quality gate zero warnings, WAPEF metadata on KG lessons, real DOCX export content verification, Nursery/Basic/WAPEF regressions, KG1 whole-level PDF confirmation.

## K. Browser acceptance

`frontend/e2e/kg-acceptance.js` — **31 passed, 0 failed**: KG2 DOCX journey (whole-level confirmation → KG 2 + Numeracy on review → strand/indicator visible → WAPEF selections → generate → DOCX verified in XML: class/strand/indicator/CS-code/source-resources/Deep Hope/play-based activities/three phases → PDF with real `%PDF-` signature) and KG1 PDF journey (fresh teacher, own quota → confirmation → review shows **KG 1**, `K1.1.1.1.1` codes, content standard, resources → generate → post-generate). Zero overflow at 1440×900 / 1024×768 / 390×844; zero page errors; screenshots inspected. The existing WAPEF acceptance suite (32 checks) also re-ran green.

## L. DOCX verification

Real `Lesson_Plans_WAPEF_SCHEME_OF_LEARNING_FOR_KG.docx` inspected from `word/document.xml`: `KG 2`, `All About Me`, `K2.1.1.1.1`, content-standard code, `Poster/ cut out`, Deep Hope verbatim, play-based activity text, PHASE 1→2→3, EVALUATION, REMARKS; zero leftover tokens.

## M. PDF verification

Real `exported-kg2.pdf` (253 KB) and a 17-page KG PDF earlier in the phase: `%PDF-` signature verified; text extraction confirms Deep Hope / Storyline / Through line content (PDF derives from the same canonical DOCX call — single-source rendering retained).

## N. Full regression

- Backend: **1272 passed, 11 skipped, 0 failed** (includes 33 new KG tests and all prior suites).
- WAPEF acceptance: 31 + browser 32/32 green. Nursery and Basic 7–9 behavior regression-pinned.
- `tsc --noEmit` clean; production build ✓.
- One intermediate regression caught and fixed: bare `content`/`standard` header aliases initially matched **data-row cells** (`test_no_headers` failed) — fragment aliases were scoped to the multi-row merged-header path only, restoring the test while keeping KG1 PDF columns.

## O. Known limitations

- No completed KG lesson-plan fixture exists in the source directory; pedagogy claims rest on scheme evidence (assessment rows, resource columns, special-week wording), not on filled KG plans. Claims are scoped accordingly.
- KG indicator ranges are not expanded into sub-skill lessons — direct consequence of the source's own cross-week splitting; if WAPEF later supplies per-sub-skill guidance, that is a new evidence cycle.
- Free Tier monthly quota (5 lessons) applies to browser journeys; the KG script uses a fresh teacher per leg.
- AI-mode enrichment was not exercised end-to-end (no provider keys in acceptance); AI guards for KG fields are unchanged and unit-tested from the prior phase.

## P. Commits

1. `feat(kg): normalize WAPEF KG curriculum semantics`
2. `feat(kg): improve KG lesson generation`
3. `test(kg): add real KG curriculum and generation acceptance`
4. `docs(kg): add KG implementation report`

## Q. HEAD/origin parity

Pushed; `git rev-parse HEAD` == `git rev-parse origin/main` (verified after push). Working tree clean.
