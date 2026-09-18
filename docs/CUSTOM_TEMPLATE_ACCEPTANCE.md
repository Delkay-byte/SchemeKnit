# Custom Sample-Template Acceptance

Date: 2026-09-16
Milestone: custom sample lesson-plan template import, mapping, preview, production rendering.
Environment: same clean web stack as the core gate — frontend http://localhost:3000,
backend http://127.0.0.1:8000, dedicated DB
`C:\Users\SAVIOUR\teachflow_web_acceptance\teachflow_web_acceptance.db`.
Teacher: Test Teacher (owner of all acceptance records).

## 1. Sample document (real teacher file)

- File: `BASIC 9 SCIENCE SAMPLE WEEK 2.docx`
  (staged copy of the genuine teacher file `MY-SCIENCE-WEEK 2-LESSON PLAN.docx`; original untouched)
- Content: "WEEK 2" title + 3 tables. Table 1 is an 11-row × 8-grid-column metadata grid with
  horizontal merges (`gridSpan`), `Label: value` cells (Date, Period, Subject, Duration, Strand,
  Class, Class Size, Sub Strand, Content Standard, Indicator, Lesson, Performance Indicator,
  Core Competencies, References, New words), phase rows, and a 2×3 phases table; table 3 repeats
  the grid for the week's second lesson. JHS (Basic 7) content.

## 2. Structure detected (deterministic analyzer, no LLM)

- 3 tables, 15 distinct field labels, merged-cell maps (colspans up to 3), per-cell bold flags,
  page layout (portrait), detected family `jhs` / level `Junior High School`.
- High-confidence mappings: Date→lesson_date, Subject→subject, Strand→strand,
  Class→class_level, Class Size→class_size, Sub Strand→sub_strand,
  Content Standard→content_standard, Indicator→indicators, Lesson→lesson_number,
  Duration→duration_minutes, References→references.
- Medium: Performance Indicator→learning_objectives.
- Custom-kept (unknown, never dropped): Period, Teaching Method, New words.
- Phase-marker cells (`PHASE 1: STARTER`…) classified structural, not fields.

## 3. Manual correction during review

In the mapping-review step the teacher explicitly confirmed
**Performance Indicator → Learning Objectives** (confidence became `confirmed`).
Period stayed kept-as-custom with a blank value slot.

## 4. Saved template

- Name: **My JHS Science Format**, v1.0 → bumped to **v1.1** via UI → **archived** via UI
  (full lifecycle proven; archived template hidden from lists, history preserved).
- Owner: Test Teacher only (second teacher gets 403; random id 404).
- Structure IR + confirmed mappings + original filename persisted (`template_definitions`,
  migration v007: `status`, `original_filename`, `structure`).

## 5. Generation with the custom template

- Template dropdown on the generate page is now level-filtered (server-side):
  JHS scheme → GES-Style (JHS), Professional (JHS), My JHS Science Format only.
- Added a "Start New Generation" button (a completed job previously blocked regenerating
  with different settings — dead-end fixed).
- Selected My JHS Science Format → generated 12 lessons → exported DOCX via browser click.

## 6. DOCX verification (opened with python-docx)

Output `Science Basic 9 - Lesson Plans.docx`:
- 36 tables = 12 lessons × 3 sample tables; grids 11×8 / 2×3 / 12×8 reproduced; merges present.
- Labels present: Date, Subject, Strand, Content Standard, Indicator, References,
  Period (blank value), Class Size, PHASE markers.
- New lesson data filled: Diversity of Matter, B9.1.1.1, dates as DD/MM/YYYY (sample convention).
- Sample's foreign data absent: no `01/05/2026`, `Forces & Energy`, `B7.4.3.1`, `60mins`.
- Custom Period label kept with blank value; unmapped prose cells blank (never copies sample content).
- School/Teacher labels absent because the sample grid has no such cells — faithful to the sample.

## 7. Known fidelity limitations (explicit)

- Pixel-perfect reproduction is not claimed: fonts/spacing approximate; repeated-lesson
  sub-tables render per lesson rather than grouped per week; vertical merges supported in
  analysis + renderer but absent from this sample (covered by unit tests, not live data).
- Sample body prose is intentionally NOT copied (presentation/content separation).
- ZIP browser-click transfer issue from the core gate is unchanged and untouched per scope;
  ZIP bytes remain valid via API. PDF remains optional (export_pdf 500s on missing OS engine).

## 8. Validation, ownership, errors (all verified live)

- Owner GET 200; other teacher GET 403 "You do not have access to this template"; random id 404.
- `.txt` upload → 400; malformed `.docx` → 400 with cleanup; oversize → 413; empty → 400.
- Bad version string → 400 (X.Y required).
- Wizard shows loading / empty ("No custom templates yet") / error / retry states;
  unmappable samples show the "could not confidently map" notice instead of a corrupt save.

## 9. Automated tests

- 12 analyzer tests (`test_template_analyzer.py`: merges, aliases, confidence, custom-keep,
  phase markers, malformed/empty rejection, real-sample integration).
- 6 template tests (`test_custom_templates.py`: persistence, owner isolation, version/archive,
  field formatting, structural render incl. merges/labels/values/no-leak, empty fallback).
- Full suite: **271 passed** (was 253). `tsc --noEmit` clean.

## 10. Core regression

Dashboard (2 schemes), Science review, lessons workspace (36 across 2 schemes), Math generate —
all intact after this milestone. No parser/allocation/generation/auth/licensing changes.

## Verdict

**CUSTOM TEMPLATE MILESTONE: PASS.** A real teacher can upload a sample lesson plan, review and
correct its field mappings, preview, save it as a versioned private template, select it during
generation, and download a DOCX whose table/section/label/merge structure reflects the sample
while carrying the new lesson's curriculum data.
