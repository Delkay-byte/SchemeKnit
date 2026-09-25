# WAPEF Nursery Curriculum & Lesson-Generation Hardening — Implementation Report

**Date:** 2026-09-25
**Phase:** Nursery curriculum interpretation & lesson generation production-readiness
**Base:** `9a02bb8` (HEAD == origin/main, clean tree)

## A. Source inventory

`C:\Users\SAVIOUR\Documents\DScience\Lesson Plan` was searched for every
Nursery-related document: schemes, PDFs, DOCX files, lesson plans, teacher
examples, curriculum documents, and the alternative terms N1, N2, Nursery 1,
Nursery 2, Pre-school, Early Years (every DOCX/PDF in the directory was
content-scanned, not just filename-matched).

| File | Relevance | Classification |
|---|---|---|
| `WAPEF SCHEME OF LEARNING FOR NURSERY.docx` | **The only Nursery source document.** Declares "SCHEME OF LEARNING FOR NURSERY 1 – TERM 1 (2024/2025)". Four subject sections, each its own 15-row table. | **SOURCE VERIFIED** |
| `WAPEF SCHEME OF LEARNING FOR KG.docx` | KG2 scheme — regression fixture only | SOURCE VERIFIED (not Nursery) |
| `KG 1 Scheme.pdf` | KG1 scheme — regression fixture only | SOURCE VERIFIED (not Nursery) |
| All other DOCX/PDF | Content-scanned; no Nursery content anywhere else | NOT APPLICABLE |

**Limitation (documented, §1):** no completed Nursery lesson plans exist in
the source directory. Developmental-appropriateness (§11) and assessment
shape (§14) are therefore derived from the **scheme's own evidence** — its
oral-skills strands, concrete resource columns ("Cut out shapes", "Counters,
sticks, flash cards", "Colours"), pre-writing/pre-reading sub-strands
("Scribbling", "Tracing", "Colouring, Tracing and Alphabets") — and from the
KG lesson-plan exemplars for shared early-years infrastructure. Nothing is
claimed to be lesson-plan-exemplar-derived that is not.

## B. Source-derived Nursery structure

Verified against the document, cell by cell:

| Property | Value | Classification |
|---|---|---|
| Level | `NURSERY 1`, declared in the body | SOURCE VERIFIED |
| Term | `TERM 1 (2024/2025)` | SOURCE VERIFIED |
| Columns per table | `WEEKS / STRAND / SUB STRAND / RESOURCES` | SOURCE VERIFIED |
| Tables | 4 (one per subject section) | SOURCE VERIFIED |
| Weeks per table | 15 (header + 15 rows) | SOURCE VERIFIED |
| Subjects | NUMERACY, LANGUAGE & LITERACY, CREATIVE ARTS, OUR WORLD OUR PEOPLE | SOURCE VERIFIED |
| Content Standard column | **absent** | SOURCE VERIFIED |
| Indicator column | **absent** | SOURCE VERIFIED |
| Week 1 | REVISION (every cell "REVISION") | SOURCE VERIFIED |
| Weeks 13/14 | REVISION / EXAMINATION | SOURCE VERIFIED |
| Week 15 | VACATION | SOURCE VERIFIED |
| Repeated rows | Numeracy W5/W6 "Pairing"; Creative Arts W2/W3; OWOP W2/W3, W4/W5, W6/W7, W9/W10 | SOURCE VERIFIED |
| Empty resource cell | Numeracy W12, Creative Arts W12 | SOURCE VERIFIED |

Ambiguity resolution (§2), each resolved by document evidence, not assumption:

* **Repeated rows are continuation weeks, not separate lessons in one week** —
  the source gives one row per week and repeats the *content* across two
  week numbers; one row = one teaching week. **SOURCE VERIFIED.**
* **Resources belong to the row**, not the section: rows in the same section
  carry different resources (Numeracy W2 "Cut out shapes" vs W5 "Counters,
  sticks, flash cards"). **SOURCE VERIFIED.**
* **A subject heading applies to the table that follows it** and no further —
  each section has its own complete table with its own week 1…15. **SOURCE
  VERIFIED.**
* **Blank cells carry forward** only inside a column where the source itself
  repeats (strand repeats down a section); a blank RESOURCES cell (W12)
  keeps the row a real curriculum row. **SOURCE VERIFIED.**
* **Nursery 2 does not appear in this document** — this is a Nursery 1
  scheme. `ClassLevel.NURSERY_2` exists as an enum member so a scheme that
  declares it is detected the same way; no behaviour is special-cased.
  **INFERRED from the same detection path.**

## C. Nursery level handling

* The body declares `NURSERY 1`; detection resolves `ClassLevel.NURSERY_1`.
  **IMPLEMENTED + TESTED.**
* A same-family conflict (a table cell saying `NURSERY` while the body says
  `NURSERY 1`) resolves to the **more specific** declaration — never
  collapsed to the generic family name, never renumbered. **IMPLEMENTED +
  TESTED.**
* Genuinely contradictory declarations stay **unknown** for teacher
  confirmation; KG 1/KG 2 is never silently assigned. **IMPLEMENTED +
  TESTED.**

## D. Subject-section handling

* A confirmed subject resolves through the **same canonical heading matcher**
  that detected the sections ("CREATIVE ARTS" ↔ "Creative Arts"), in both the
  DOCX and PDF paths — no subject-specific hard-coded branch. **IMPLEMENTED +
  TESTED.**
* `analyze()` accepts `target_subject` (it previously referenced an
  undefined name and raised `NameError` on the KG analysis path — a real bug
  this phase fixed). **IMPLEMENTED + TESTED.**
* Anti-mixing guard intact: confirming a subject not present in the document
  yields no weeks rather than a mix. **TESTED (existing suite).**

## E. Curriculum normalization

* No fabricated indicator codes, content standards or performance indicators
  anywhere in the Nursery pipeline — `indicators`, `indicator_codes`,
  `content_standard` and `content_standard_code` stay empty end to end.
  **SOURCE VERIFIED + IMPLEMENTED + TESTED.**
* The curriculum unit is what the source actually has: week + subject +
  strand + sub-strand + resources. **IMPLEMENTED.**
* Special-period row noise is normalised ("AND VACATION" → "VACATION",
  "REVISION1" → "REVISION") by a rule that only rewrites a cell that *is*
  exactly a special-period name after the noise — no filename logic, no
  subject logic, no row-index logic. **IMPLEMENTED + TESTED.**

## F. Lesson-unit semantics

* One lesson per instruction week, in source week order; 11 lessons per
  subject (weeks 2–12). **IMPLEMENTED + TESTED.**
* `scheme_has_indicators()` is `False` for Nursery, so the indicator
  allocation path never applies. **TESTED.**

## G. Allocation behavior

* Source week numbers are preserved verbatim on every plan (2…12) and never
  shifted. **TESTED.**
* Special weeks (1, 13, 14, 15) generate no lessons and no fabricated subject
  content; they are classified (REVISION/ASSESSMENT/SBA-non-instruction) and
  excluded. **IMPLEMENTED + TESTED.**
* Source week-ending semantics and the week_ending_derived flag are
  untouched (§18). **NOT APPLICABLE — this Nursery source has no dates.**

## H. Resource preservation

* Source resources reach the lesson verbatim as `source_tlrs`
  ("Cut out shapes", "Counters, sticks, flash cards", "Colours", "Charts &
  Pictures"). **IMPLEMENTED + TESTED.**
* The generated profile resources may supplement (`teaching_learning_resources`
  is the union) but never overwrite the source list. **TESTED.**
* Resources are per-subject and per-row: Numeracy's "Cut out shapes" does not
  appear in any Creative Arts lesson. **TESTED (unit + browser).**
* **Export fix:** the WAPEF renderer previously emitted the full source
  resource list in *every* phase row, triple-counting one resource set inside
  a single lesson. It now renders once, in the MAIN teaching-resources row.
  **IMPLEMENTED + TESTED.**

## I. Special-week handling

REVISION / EXAMINATION / VACATION are classified by the existing
`_classify_special_week` architecture (VACATION shares the non-instruction
bucket with SBA weeks) and are excluded from generation. No vacation row
receives fabricated indicators or objectives. **IMPLEMENTED + TESTED.**

## J. Generation behavior

* Deterministic generation works with `AI_MODE=OFF` (all acceptance runs were
  deterministic). **TESTED.**
* Nursery keeps its **own** pedagogy profile: song/rhyme starter with real
  objects; MAIN = teacher modelling → guided participation → playful
  practice; observation/oral assessment that explicitly states there is no
  written test; circle-time plenary. **IMPLEMENTED + TESTED.**
* Objectives are "Learners can show and talk about …" — the source's
  sub-strand topics are do-and-say activities, so this is a demonstrable
  outcome. Basic-style measurable-analysis phrasing and the KG role-play
  phrasing are both avoided. **IMPLEMENTED + TESTED.**
* Indicatorless rows are interpreted from the row's own curriculum text for
  activity typing only; no code is invented. **IMPLEMENTED + TESTED.**
* SOURCE DATA stays distinguishable from GENERATED TEACHING CONTENT: source
  strand/sub-strand/resources are preserved as themselves, generated text is
  composed around them. **IMPLEMENTED.**

## K. Assessment behavior

Observation + simple oral questions (point to / name / show), with the
evidence target made lesson-specific ("each child shows or names one example
of …"). No generic identical evaluation text across weeks. **IMPLEMENTED +
TESTED.**

## L. Anti-cloning verification

* Different weeks → different starter, main activities and assessment.
  **TESTED.**
* **Continuation weeks** (Numeracy W5/W6, identical source rows) still
  produce different lessons: the second links to the previous lesson. This
  was a real defect — the link previously keyed on indicator prose, which
  Nursery rows never have. **IMPLEMENTED + TESTED.**
* No intra-lesson duplicate teacher/learner/phase activity text (a real
  duplication bug the Nursery profile exposed: "Guided participation" and
  "Playful practice" matched the same branch in the move tables). **IMPLEMENTED
  + TESTED.**
* Cross-subject DOCX exports differ, with no neighbour leakage. **TESTED
  (browser).**

## M. WAPEF integration

* One output structure: the **Approved WAPEF Plan** (`tpl-wapef-approved-plan`).
  No Nursery/KG variant template exists. **TESTED.**
* Deep Hope / Storyline / Through lines / God's Story remain
  teacher-selected and are never AI-chosen or overwritten. **TESTED.**

## N. DOCX verification

Exported Nursery DOCX inspected programmatically (XML-level):

* `Nursery 1`, `Numeracy`, strand `Number`, sub-strand verbatim,
  source resources, Deep Hope/Storyline/Through lines/God's Story verbatim.
* `PHASE 1 / PHASE 2 / PHASE 3`, `EVALUATION`, `REMARKS` present.
* No fabricated curriculum codes (`\b[BN]\d\.\d` absent).
* No leftover template tokens (`{{…}}`), no sample-content leakage.
* No duplicated activity lines within a lesson.
**TESTED (unit + browser).**

## O. PDF verification

PDF export derives from the same canonical lesson object via the shared
DOCX→PDF converter (LibreOffice/docx2pdf). Real `%PDF-` signature, 4 files
exported (one per subject), 229–342 KB. **TESTED (unit + browser).**

## P. Browser acceptance

`frontend/e2e/nursery-acceptance.js` — **130 assertions, 0 failed**, on the
real frontend + backend at 1440×900:

* Fresh teacher per subject (own Free-Tier quota) → signup → upload →
  multi-subject confirmation → review → approve & configure → Approved WAPEF
  Plan template → allocation preview → WAPEF teacher selections → generate →
  reload → DOCX download → PDF download.
* Review assertions: level `Nursery 1`, confirmed subject, **own** week-2
  strand/sub-strand/resources, **no neighbour-subject leakage**, no
  fabricated codes.
* Export assertions per subject (content-inspected DOCX + real PDF
  signature), cross-subject isolation on the exported documents.
* Responsive: no horizontal overflow at 1024 and 390; zero uncaught page
  errors. **TESTED.**
* Screenshots captured to `frontend/e2e/nursery-acceptance/`. **ENVIRONMENT
  LIMITATION:** screenshots were verified structurally (capture, per-subject
  byte differences showing distinct rendered content) — this environment
  cannot render images for visual inspection.

## Q. Regression results

| Gate | Result |
|---|---|
| Full backend pytest | **1332 passed, 11 skipped, 0 failed** (baseline at phase start: 1209 passed, 11 skipped) |
| Nursery acceptance (new) | **60 passed** |
| KG acceptance | green — KG level, indicators, play-based profile and code-only content-standard handling unchanged |
| WAPEF acceptance | green — Approved WAPEF Plan structure, option lists and metadata persistence unchanged |
| Basic/JHS regression | green — `profile_for_subject("Science")` and a Basic 9 build both keep the subject profile; the Nursery override keys on class level |
| Frontend `tsc --noEmit` | **PASS** |
| Frontend `npm run build` | **PASS** |
| Backend startup (SQLite) | health 200 |

Two stale expectations were updated **because the source evidence changed
them**, each with the evidence recorded in the test:
the Nursery objective phrasing ("Learners can show and talk about") and the
detected level ("Nursery 1"). No threshold was lowered to make anything pass.

## R. Known limitations

1. **No completed Nursery lesson plans exist in the source directory**, so
   developmental-appropriateness is derived from the scheme's own evidence
   (§A, §11) rather than a lesson-plan exemplar.
2. **Render SHA is not exposed on the live API** — deployment verification
   requires the owner's dashboard (same as prior phases).
3. Screenshots verified structurally, not visually (§P).
4. This is a Nursery 1 document; Nursery 2 is handled by the same detection
   path but has no source fixture.

## S. Commit hashes

| Commit | Message |
|---|---|
| `4a4163c` | `feat(nursery): normalize WAPEF nursery curriculum semantics` |
| `e641604` | `feat(nursery): improve nursery lesson generation` |
| `fa9237d` | `test(nursery): add real nursery curriculum and generation acceptance` |
| (this commit) | `docs(nursery): add nursery implementation report` |

## T. HEAD / origin parity

To be confirmed at push time — see the final verification output below.
