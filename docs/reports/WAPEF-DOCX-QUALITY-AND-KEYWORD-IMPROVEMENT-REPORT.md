# WAPEF DOCX Quality and Keyword Improvement Report

**Branch:** `feat/cloudflare-free-browser-docx` (fast-forwarded to `main` at
`91828f0` for the release)  
**Reproduction document:** `Lesson_Plans_BASIC_7_TERM_1.docx` (Basic 7 Mathematics, 110 pages)  
**GES visual reference:** `Lesson_Plans_Basic_6_Computing_Deterministic.docx`  
**Date:** 10 November 2026

---

## A. Root-cause findings

The defects did not all come from the DOCX renderer. They came from four layers.

### 1. Blank WAPEF fields

`wapef_template._resolve()` read only the four stored teacher-selection columns
(`wapef_deep_hope`, `wapef_storyline`, `wapef_through_lines`, `wapef_gods_story`).
Those columns were written only from the pre-generation review draft. If the
teacher did not open the WAPEF review card, every field stayed empty. There was
no lesson-specific default and no fallback connection.

### 2. Keyword pollution

`lesson_builder.build_lesson()` built the keyword list in this order:

1. every scheme resource (the primary seed),
2. exemplar terms,
3. a naive `_content_terms()` word scan of the indicator, sub-strand and
   content standard.

Step 1 is why `made currency`, `graph sheets`, `Multi-base materials` and
`paper-` appeared as keywords. Step 3 is why `number`, `quantities`, `graph`
and `numeration` appeared. Neither step preserved multiword terms.

### 3. Fragmented sentences

Two separate character caps cut sentences in the middle:

- `lesson_builder._short_clause()` cut the differentiated support/challenge at
  70 characters. This produced `counting materials so.` and `swap with a.`.
- `assessment_design._short()` cut the assessment focus at 40 characters. This
  produced `… up to 100,000 to and state …`.

The activity templates also embedded the full indicator, including a trailing
apparatus clause (`using graph sheets, isometric paper …`), into every phase.
That is why the apparatus was repeated six times and why the indicator became
a substitute for the teaching move.

### 4. Corrupted resources and numeric splits

- `paper-` entered the plan because the source cell contained a line-wrapped
  hyphenated resource, and the normalizer split the line before the hyphen.
- `1 000 000 000` was stored with ordinary spaces. In a narrow cell LibreOffice
  and Word broke it into `1` / `000` / `000`. A later normalizer converted the
  spaces to commas and then a list splitter split on those commas, which is why
  the Performance Indicator still showed the broken form after the first fix.

### 5. WAPEF table styling and pagination

The bundled WAPEF asset had no cell shading and used Times New Roman 12 pt. The
phase column was too narrow for `PHASE / DURATION` at 14 pt bold, so the heading
split inside the word. Content rows had fixed heights and inherited blank spacer
paragraphs, which created empty continuation space. When a multi-lesson file was
styled by table index, the SECOND lesson's metadata table was painted as a
delivery grid, which pushed it off the page and truncated its left labels.

### 6. One school's vision hard-coded in the footer

The bundled WAPEF footer contained the attached school's vision sentence. That
would print another school's vision on every plan. No school vision field is
currently configured in the product, so the footer now carries only a page
number. Vision text must be supplied by configuration when that field exists.

---

## B. WAPEF faith integration

New module: `backend/src/engines/wapef_connections.py`.

The four fields remain four distinct Teaching for Transformation concepts:

| Field | What it now says | What it must not say |
|---|---|---|
| Throughline | The approved habit label plus how learners practise it in this lesson | A random label with no practice |
| God's Story | A Biblical theme, an accurate reference and a subject connection | A bare label or an unrelated Bible story |
| Deep Hope | An enduring formation desire grounded in the theme and subject | A restatement of the lesson objective |
| Storyline | The learner's place in creation → fall → redemption → restoration, with a call to serve | A copy of the Throughline or Deep Hope |

The module selects a theme from the lesson's subject, strand, sub-strand,
content standard and indicator. It contains a hand-checked bank of themes:
order and place value, faithful number work, data and truth, design and parts,
digital wisdom, living systems, earth stewardship, language and truth, justice
and community, creativity and craft, worship and faith, body and discipline,
wisdom and work, and a faithful-learning fallback. No Scripture text is quoted,
so no verse can be misquoted; the reference is named and its theme is summarised.

Teacher values always win:

- an approved label is preserved exactly and followed by a lesson-specific
  practice/connection sentence;
- teacher-written free text is returned verbatim and is not rewritten;
- a blank field is rendered from the suggestion at export time, while the
  database stays genuinely empty (the established save-boundary contract);
- teacher text is accepted by `normalize_wapef_payload(..., allow_custom=True)`
  only on the generation route; the strict option-list validators are unchanged.

The review UI now offers editable text areas for Deep Hope, Storyline and God's
Story, the approved chips as one-click values, "Use suggested …" actions, and a
free-text add control for Throughline. WAPEF fields never appear in GES plans.

---

## C. WAPEF DOCX styling

New module: `backend/src/engines/wapef_style.py`; applied to the bundled asset by
`backend/scripts/style_wapef_template.py` and again at render time.

Visual tokens taken from the GES reference:

| Token | Value | Use |
|---|---|---|
| Header fill | `1A365D` | Delivery-grid header row |
| Header text | `FFFFFF`, bold, centred | Header row |
| Label fill | `F2F4F8` | WAPEF metadata cells |
| Label text | `2D3748` | Metadata labels |
| Phase fill | `F8FAFC` | Phase label column |
| Border | black, 4 eighth-points | `Table Grid` |
| Cell padding | 100/140 twip vertical, 150 twip horizontal | All cells |
| Body font | Calibri 10–10.5 pt | Fits WAPEF's larger field set while preserving readability |
| Paragraph spacing | 10–40 twip | Compact metadata, readable activity cells |

Pagination corrections:

- fixed, balanced column widths: phase 1.3", activities 4.1", resources 1.8";
- the phase column is wide enough for `PHASE / DURATION`; the heading wraps
  between words, never inside `DURATION`;
- the delivery header repeats on continuation pages (`w:tblHeader`);
- short rows are kept whole (`w:cantSplit`); only a row over 2000 characters is
  allowed to continue, so a single orphan line no longer appears under a
  repeated header with an empty phase label;
- fixed content-row heights and blank spacer paragraphs are removed, so rows
  expand with their content;
- merged cells now receive the sum of their grid-span widths. Previously the
  second lesson's merged metadata table received phase-column widths and ran
  off the page;
- page margins 0.5"/0.55"/0.65", footer page number, no hard-coded school vision.

The browser OOXML filler (`frontend/src/lib/docx/ooxml.ts`) applies the same
repeat-header and row-split rules after filling, so browser-exported WAPEF files
paginate like server-rendered files.

### Basic 1-3 weekly template (same pipeline, separate topology)

The weekly class-teacher plan (`tpl-wapef-basic13-weekly-plan`) uses the same
content builders and export path as the Approved Plan, but one table per subject
instead of a metadata table plus two delivery tables. `build_lesson`, the
vocabulary engine, the faith connection engine and the resource filter are
shared; only the weekly metadata/day assembly and the five-column DOCX form are
different. It was therefore styled by
`style_basic13_document()` rather than the three-table `style_wapef_document()`
loop:

- five-column grid widths `(1400, 750, 750, 4400, 3000)` twips: a readable DAYS
  column, a wide MAIN column and balanced starter/reflection columns;
- metadata labels `F2F4F8`; DAYS header `1A365D` with white bold text;
- blank spacer row between Key words and DAYS removed;
- day rows are kept whole (`w:cantSplit`), so a row taller than the remaining
  page moves to the next page instead of leaving empty phase labels behind;
- footer page number and margins identical to the Approved Plan;
- the asset's `TableGrid` style spelling is handled, because the weekly asset
  does not carry the `Table Grid` alias.

---

## D. Content quality

### Corrected examples

| Before | After |
|---|---|
| `counting materials so.` | The complete support sentence is rendered, or the inline cue is omitted. |
| `swap with a.` | `… swap with a partner, and solve it.` |
| `paper-` | The malformed source entry is dropped; `paper-based` is rejoined when the source supplies the rest of the word. |
| `1` / `000` / `000` in a cell | `1,000,000,000` |
| Indicator repeated in every phase | Focus named at most twice in the MAIN block; later phases refer to `the same content`. |
| `using graph sheets, isometric paper` in every activity | Apparatus clause removed from the teaching focus; resources stay in the resources column. |
| `Distinguish` as a keyword | Action verbs are rejected; subject terminology (`automatic devices`, `manual`) is selected. |

The teaching focus now drops a trailing apparatus clause before composing prose.
Math `model` is interpreted as representation rather than demonstration. The
activity selection still follows the official indicator and subject pedagogy;
multiple indicators still produce separate lessons.

---

## E. Resources

- Parser-level malformed entries are rejected (`is_malformed_fragment`).
- Hyphen line wraps are rejoined before splitting (`paper-\nbased` →
  `paper-based`).
- `teaching_learning_resources` is filtered to resources the lesson actually
  names or uses. `source_tlrs` keeps the scheme's verbatim record for provenance.
- Computing/ICT keeps the scheme's devices because the apparatus is the subject
  matter; universal classroom basics remain available.
- Unrelated week-level resources (`made currency` beside a place-value lesson)
  no longer appear in the lesson's resource cell or in `{resource}` sentences.
- Every displayed resource is still named in an activity, so a resource is never
  only a summary-row decoration.

---

## F. Keywords / New Vocabulary

New shared module: `backend/src/curriculum/vocabulary.py`, used by the lesson
builder for both WAPEF and GES.

Selection rules:

1. Curriculum text first: indicator, content standard, sub-strand, strand and
   official exemplar focus terms.
2. Subject glossary first, longest phrase first, so `place value`,
   `base ten numerals`, `equivalent fractions` and `significant figures` stay
   whole.
3. Resource names and material words are rejected unless the lesson explicitly
   teaches the term.
4. Generic function words and action verbs are rejected by default.
5. Explicit language targets are rescued: `the conjunction 'or'`, the verb
   `"is"`, and a quoted word are valid when the lesson teaches them.
6. `difference` is kept when the indicator teaches subtraction or comparison of
   quantities, and is not added to an unrelated science lesson.
7. Malformed fragments, duplicates, singular/plural repeats and contained phrases
   are removed.
8. Teacher terms always survive; provider/AI terms pass
   `filter_supported_terms()` and cannot add random vocabulary.
9. An empty result is valid. The generator does not fabricate a list.

This is consistent with NaCCA's vocabulary guidance: contextually relevant,
subject-specific vocabulary, introduced and used in context, with content and
sight vocabulary distinguished. It is not presented as an official NaCCA
algorithm.

---

## G. Teacher input

Two entry points, both optional:

1. **Generation review card** — per-lesson editable chips for
   `Key Words / New Vocabulary`, with suggested chips, add/remove, and
   "Use suggestions". The row is marked touched on the first edit, so an
   explicitly emptied list is honoured.
2. **Configure teaching setup dialog** — per-indicator
   `Key words / New vocabulary` multiline field, keyed by canonical source
   occurrence id. Saved on the scheme and applied only to that lesson.

Teacher vocabulary is persisted in `TermConfig.indicator_keywords` and the
scheme's lesson configuration. Regeneration merges teacher terms instead of
overwriting them. WAPEF fields preserve teacher text through
`allow_custom=True` and the four approved-value normalizers remain strict for
all other callers.

---

## H. GES preservation

- The GES template assets were not modified.
- GES layout, fields, phase structure and styling are unchanged.
- No Throughline, God's Story, Deep Hope or Storyline field is added to GES.
- The only shared change outside WAPEF is the keyword engine and the numeric
  normalization in `_text`, which prevents broken numbers in any template.
- GES regression suites passed: `test_official_ges_template.py`,
  `test_export_model.py`, `test_lesson_quality_parts.py`,
  `test_guided_lesson_configuration.py`.

---

## I. Testing

### Automated

Targeted suite:

```text
python -m pytest \
  tests/test_vocabulary_and_wapef_integration.py \
  tests/test_wapef_acceptance.py \
  tests/test_wapef_save_boundary.py \
  tests/test_official_ges_template.py \
  tests/test_export_model.py \
  tests/test_corpus_prose_quality.py \
  tests/test_lesson_quality_parts.py \
  tests/test_guided_lesson_configuration.py -q

221 passed
```

Additional suites:

```text
tests/test_curriculum_remediation_defects.py
tests/test_lesson_quality_remediation.py
tests/test_generation_quality_v3.py
tests/test_no_synthetic_content.py
tests/test_corpus_prose_quality.py
tests/test_prose_composition.py
tests/test_structured_references_integrity.py   139 passed
```

Full backend suite (one uninterrupted run, CI marker selection):

```text
python -m pytest -q -m "not live_provider"
3357 passed, 27 skipped, 5 deselected in 1123.23 s
```

Total discovered: 3389. The five deselected tests are the explicitly marked
`live_provider` cases; the 27 skipped are the suite's documented skips. No test
was deleted, suppressed or marked xfail to obtain this result.

Frontend:

```text
npx tsc --noEmit      clean
npm run lint -- --quiet   clean
npm run test:docx     14 passed
npm run test:ux       87 passed
npm run build         succeeded (49 routes)
```

Frontend total: 101 tests passed.

New regression file:
`backend/tests/test_vocabulary_and_wapef_integration.py` (25 tests) covers
resource exclusion, multiword phrases, generic words, malformed fragments,
`difference` positive/negative, `or`/`is` context, per-indicator lists, teacher
overrides, WAPEF distinctness, custom text, blank-field rendering, GES absence
and DOCX style tokens.

Basic 1-3 regression coverage was extended in
`backend/tests/test_wapef_basic13_acceptance.py` with six acceptance tests:
curriculum-derived keywords, teacher keyword persistence/removal, activity-
relevant resources, blank faith-field rendering plus teacher-value preservation,
and DOCX style tokens/header integrity.

### Visual

The reproduction document and a fresh sample were rendered with LibreOffice and
inspected as page images (including a contact sheet, then every suspicious page).

`backend/scripts/audit_wapef_docx.py` on the supplied Basic 7 document:

```text
empty_wapef_fields: ['Through line', "God's Story", 'Deep Hope', 'Storyline']
malformed_fragments: 43   (examples: paper-, hundred-)
numeric_splits: 18
indicator_mentions: 76
style: {'header_fill': '', 'label_fill': ''}
```

On the fresh sample (Basic 7 Mathematics, Basic 4 English, Basic 6 Computing):

```text
empty_wapef_fields: []
malformed_fragments: 0
numeric_splits: 0
phase_heading_splits: 0
style: {'header_fill': '1A365D', 'label_fill': 'F2F4F8'}
```

The sample used the same three subject/class combinations required by the brief
and showed correct table widths, coloured headers, repeated delivery headers,
page numbers and no orphan continuation row.

### Basic 1-3 weekly sample (local render)

`temp/wapef-basic13-sample.docx` was generated from the four-subject fixture
(English, Mathematics, Science, RME; 18 teaching-day rows) and converted to PDF
with LibreOffice. All 18 pages were inspected.

Result:

- metadata labels use `F2F4F8`; the DAYS header uses `1A365D` with white bold
  text;
- the blank spacer row between Key words and DAYS is removed;
- day rows are whole: a day never splits into empty phase columns on the next
  page (the source plan itself split rows, so this is stricter than the supplied
  document);
- "MONDAY" no longer breaks inside the word after the column-width correction;
- the repeated starter sentence at the top of MAIN is removed once, so each
  phase prints its own move;
- Throughlines, God's Story, Deep Hope and Storyline are all populated from the
  connection engine when the teacher left them blank; a teacher value is
  rendered verbatim;
- Key words show `counting sequences`, `number names` and `oracy` for the
  fixture lessons; resource names are absent;
- `made currency` does not appear in Mathematics resources; `Counters` and
  `bundle and loose straws` do;
- page 1 carries the metadata block; delivery pages carry the navy DAYS header
  and complete activity sentences.

The audit script reports:

```text
empty_wapef_fields: []
malformed_fragments: 0
numeric_splits: 0
phase_heading_splits: 0
label_fill: F2F4F8
```

`header_fill` is empty only because the audit script looks at the first row of
each table; the Basic 1-3 DAYS header is a mid-table row by the supplied form's
topology. The regression test asserts `1A365D` on that row directly.

---

## J. Production environment and deployment

Official frontend: `https://schemeknit.bloomcoretech.com` (HTTP 200).  
Production backend: `https://schemeknit-api.onrender.com` (health HTTP 200).  
Deployed application version: `1.0.5`.  
Final deployed commit: `efb7df8` (documentation commit; the production code
commit is `820ebaf`, `fix: display Computing instead of internal ICT label`).

The branded domain was used for all UI testing. The old
`schemeknit-frontend.onrender.com` hostname is not treated as a production
failure; its Render subdomain remains blocked and was not re-enabled.

Render deployments completed for both services at `820ebaf`:

```text
schemeknit-api      dep-dbpqgc0u01pc738t9jt0  LIVE  commit efb7df8
schemeknit-frontend dep-dbpqgcd6e07s73b67ca0  LIVE  commit efb7df8
```

Smoke checks after deployment:

```text
GET https://schemeknit.bloomcoretech.com                 200
GET https://schemeknit-api.onrender.com/api/health       200
{"status":"healthy","service":"SchemeKnit","version":"1.0.5"}
```

The frontend network log confirms all runtime API calls target
`https://schemeknit-api.onrender.com`; no localhost or staging origin is used.

## K. Production authentication

Authentication through the branded UI succeeded. The normal production
registration flow was used with the authorised pilot invitation and the live
Turnstile widget; the challenge completed and the account was created normally.
No security control was disabled, bypassed or weakened. Credentials, tokens,
cookies and invitation values are deliberately not recorded here.

The account is a normal Free Tier teacher account with **2 lesson-plan credits
for the calendar month**.

## L. Production generation results

| Test | Production generated | DOCX downloaded | Content passed | Formatting passed | Result |
|---|---|---|---|---|---|
| P1 WAPEF Basic 7 Mathematics | Yes | Yes | Yes | Yes | **PASS** |
| P2 WAPEF Basic 1–3 weekly | Yes | Yes | Yes | Yes | **PASS** |
| P3 GES Basic 6 Computing | Yes | Yes | Yes | Yes | **PASS** |
| P4 GES Mathematics | No | No | — | — | **BLOCKED: 0 of 2 credits remaining** |

Artifacts (local secure acceptance folder, no personal data):
`temp/production-acceptance/P1_WAPEF_Basic7_Mathematics.docx`,
`P2_WAPEF_Basic1_Weekly.docx`, `P3_GES_Basic6_Computing.docx`, with PDF page
renders used for visual inspection.

### P1 — WAPEF Basic 7 Mathematics

- Throughline populated (fallback connection; relevant to place value).
- God's Story, Deep Hope and Storyline populated from teacher-selected values.
- Teacher-selected Deep Hope/Storyline/God's Story survived save and export.
- No hard-coded school vision.
- `1,000,000,000` is printed intact after the numeric-grouping fix.
- Content standard code printed once.
- Dark-blue `#1A365D` phase headers, light-grey `#F2F4F8` labels and phase
  shading render correctly; 5 pages inspected.
- Keywords are `significant figures, base ten numerals, decimal places, place
  value, rounding`; no resource name appears.
- Resources are graph sheets and multi-base materials; `made currency` is gone.

### P2 — WAPEF Basic 1–3 weekly

- Basic 1 weekly class-teacher structure intact; day rows not split into empty
  phase columns; DAYS headings complete.
- Spacer row absent; `#1A365D` DAYS header and `#F2F4F8` labels render.
- Throughlines, God's Story, Deep Hope and Storyline populated.
- Teacher-selected Deep Hope/Storyline/God's Story survived export.
- Content standard code printed once after the production fix.
- Key words `counting sequences, number names`; resources are counters, straws
  and number cards.
- 6 pages inspected; page numbers and table structure correct.

### P3 — GES Basic 6 Computing

- Subject displays as **Computing**; internal canonical storage remains ICT.
- Approved GES structure preserved; indicator, content standard, keywords and
  resources are Computing-specific.
- Keywords: `computer system, peopleware, hardware, software, technology`.
- Resources: Computer, keyboard, system unit, monitor, USB mouse, printer.
- Sentences complete; no resource names in the vocabulary list.
- 4 pages inspected; repeated table headers, headings and page breaks render.

### P4 — GES Mathematics (not generated)

The Free Tier account had exactly two lesson-plan credits. P1 consumed one and
P3 consumed one; P2 (weekly plan) consumed none. The dashboard then reported
`0 of 2` remaining. P4 therefore could not be generated. No purchase, credit
top-up or account-privilege change was made, and no second account was created
to evade the allowance. This is an account-allowance limitation, not an
application defect. The local GES Mathematics sample remains local evidence
only and is not counted as production acceptance.

## M. Defects found and fixed during production acceptance

1. **Content standard code printed twice** in the Basic 1–3 weekly DOCX
   (`B1.1.1.1 B1.1.1.1 Describe ...`). Fixed by using the shared
   `_code_and_text` helper; regression test added.
2. **Thousands separators split into list items** (`1,000,000,000` became
   `1 / 000 / 000`) in WAPEF output. Fixed in `ai_resource_text._split_items`
   by protecting numeric comma groups; regression test added.
3. **Approved WAPEF Plan was not selectable for Basic 4–JHS** in the production
   template list. Fixed `get_templates_for_class_level` to add the shared WAPEF
   form beside the level's GES default; regression tests added for Basic 7 and
   Basic 1–3.
4. **Computing printed as ICT** in GES output. Added canonical subject display
   mapping (`Subject.ICT` → `Computing`) across renderers; existing contract
   tests updated to the new user-facing label; regression test added.

## N. Quality gates after the production fixes

```text
Backend full suite: 3362 passed, 27 skipped, 5 deselected, 0 failed
Discovered: 3394 tests
Frontend: TypeScript clean, lint clean, 14 DOCX tests passed,
          87 UX tests passed, production build succeeded
```

The full backend suite was rerun after each backend change; no tests were
deleted, skipped or weakened to obtain a pass. Targeted WAPEF/GES suites also
passed after every fix.

Remaining known limitations:

- P4 production generation requires a teacher account with at least one
  available lesson-plan credit (or a paid package). The current authorised Free
  Tier account is exhausted for this calendar month.
- Custom free-text WAPEF prose was verified by automated tests and local
  rendering, but the production P1 run used approved teacher-selected values;
  custom prose should be rechecked in the P4 or follow-up production run.
- School vision remains configuration-driven and is intentionally not printed
  until a school vision field exists.
- WAPEF suggestions remain deterministic, not provider-generated.

## O. Final status

**AMBER — Production acceptance incomplete by account allowance.**

P1, P2 and P3 were generated by the official production application, downloaded
and inspected successfully. The deployed commit contains the tested fixes, and
production smoke checks pass. P4 could not be generated because the authorised
Free Tier account has 0 of 2 lesson-plan credits remaining. No application,
security or document-formatting defect remains open from the three completed
cases.
