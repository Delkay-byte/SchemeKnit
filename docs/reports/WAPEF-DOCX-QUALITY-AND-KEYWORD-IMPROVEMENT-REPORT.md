# WAPEF DOCX Quality and Keyword Improvement Report

**Branch:** `feat/cloudflare-free-browser-docx`
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

218 passed
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

New regression file:
`backend/tests/test_vocabulary_and_wapef_integration.py` (22 tests) covers
resource exclusion, multiword phrases, generic words, malformed fragments,
`difference` positive/negative, `or`/`is` context, per-indicator lists, teacher
overrides, WAPEF distinctness, custom text, blank-field rendering, GES absence
and DOCX style tokens.

Frontend:

```text
npx tsc --noEmit      clean
npm run lint -- --quiet   clean
npm run test:docx     14 passed
npm run build         succeeded
```

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

---

## J. Git and deployment

Repository: `https://github.com/Delkay-byte/SchemeKnit.git`
Branch: `feat/cloudflare-free-browser-docx`

Local changes are on that branch. Push/deployment requires repository
credentials and the project's production workflow; the local environment has no
verified deployment target. Production generation and post-deploy inspection were
therefore not performed in this run. The committed code and local visual samples
are the deployable artefacts.

---

## K. Outstanding issues

1. **Production verification not performed.** No credentials/deployment target
   were available. After deployment, generate one WAPEF Mathematics plan and one
   GES plan, then run `backend/scripts/audit_wapef_docx.py` on both.
2. **The Basic 1–3 weekly WAPEF template was not restyled.** The supplied 110-page
   reproduction is the Approved WAPEF Plan (`tpl-wapef-approved-plan`); the
   weekly template has a different topology and was left structurally untouched.
   Apply the same `wapef_style` tokens to it only after a separate visual review.
3. **School vision is not configurable yet.** The hard-coded footer was removed;
   the footer now shows only a page number. When a school vision field is added
   to configuration, pass it into the WAPEF render context.
4. **WAPEF suggestions are deterministic, not provider-generated.** This was a
   deliberate choice so blank fields are always populated without spending AI
   credit and without risking fabricated Scripture. Teacher text still overrides.
