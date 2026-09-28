# SchemeKnit — Curriculum Workspace Real-Use Remediation Report

Focused remediation pass on the ten real-use defects observed after the
curriculum-grounded workspace deployment. The architecture was **not**
redesigned: Curriculum Spine, provenance, review states, Quick Generate /
Build with me, structured Main Learning, special periods, entitlements,
monthly quotas, Gemini, DOCX/PDF export, tab-isolated Bearer auth and the
quality gate are all preserved.

---

## 1. Actual root causes

### Defect 1 — false multi-subject detection

**Root cause.** The upload screen treated *any* detected section list as
"multiple subjects detected" (`detectedSections.length > 0`), so a
single-subject document whose heading produced one section was still shown the
multi-subject confirmation card. The parser's structural detection was already
correct — the UI never checked the section *count*.

**Fix.** Multi-subject is now declared only when
`detection.status === 'multiple' && sections.length >= 2`. The success card
states the real count from the parsed structural sections (`1 subject
detected`) via `data-subject-count`.

### Defect 2 — Indicator column exists but weeks say "no indicators"

**Root cause (confirmed against the teacher's own file,
`BS7-1st-Term-Computing-Scheme.docx`).** The source prints its INDICATOR cells
as the **code alone**, with no prose:

```
WEEK  STRAND                     CONTENT STANDARD  INDICATORS
1     Introduction to Computing  B7.1.1.1          B7.1.1.1.1
2     Introduction to Computing  B7.1.1.1          B7.1.1.1.2
6     Introduction to Computing  B7.1.2.1          B7.1.2.1.1 ⏎ B7.1.2.1.2
```

`_merge_week_rows` required **both** a code and a non-empty description
(`if ind_code and ind_desc`), so every code-only cell was silently discarded.
Only week 6 survived — because its cell held two codes, which made
`_clean_description` leave the second code as the “description” (so week 6 was
stored with a wrong description, not two indicators). That is exactly the
reported symptom: *“several weeks say ‘No indicators were found’; only one week
successfully captured the indicators; those weeks are marked Needs review.”*
Weeks 3–8 and 10–13 in the stored production scheme carry 0 indicators for this
reason, and week 9's `MID-TERM` label had been stored as an indicator.

Three further causes were found and separated:

1. **Code-only indicator cells dropped** (the root cause above).
2. **Special-period metadata lost on the confirmation path.** A scheme whose
   class level appears only in its codes pauses for confirmation;
   `POST /documents/{id}/confirm-subject` re-extracted the document but rebuilt
   the `WeekDB` rows **without `special_period_label` / `special_period_type`**,
   so the MID-TERM row's own date range vanished (Defect 5's data loss).
3. **Conflated review semantics.** `classify_week_review` flagged a week with
   no indicator as `needs_review` even when the *whole source* has no Indicator
   column (the WAPEF Nursery/KG shape), i.e. it could not tell "the source has
   none" from "the parser missed this week". Matching period keywords against
   *indicator* text could also drop real curriculum (`"Examine …"` contains
   `"exam"`, ordinary descriptions contain `"sba"`).

**Fix.**
- A **code-only indicator cell is the source data**: it is kept with an empty
  description (mirroring the content-standard column's long-standing rule), and
  a cell listing several codes yields one indicator per code. A range tail
  (`K2.1.1.1.1-3`) still stays a single indicator.
- Special-label guards apply only to a **non-instructional row whose cell
  contains no indicator code**, so a real indicator is never dropped because of
  a keyword substring.
- The strand cell of a special row is the authoritative label; the
  noise-normalising pass keeps the source's date range (`AND VACATION` →
  `VACATION`, `REVISION1` → `REVISION`,
  `MID-TERM (05-11-2026 to 06-11-2026)` unchanged), and the confirmation path
  now persists the label + type.
- `scheme_provides_indicators(weeks)` answers the scheme-wide question. The
  spine and both routers pass the full week list, so:
  * source provides indicators elsewhere + this week empty → **⚠ Needs review**
  * source has no Indicator column at all → **— Not provided in source**
  * special / mixed week → **★ Special period / ◐ Mixed week**
- The label can no longer surface as an indicator, strand or sub-strand.

**Result on the teacher's own file:** from **1/15** weeks carrying an indicator
to **13/15** (the two remaining weeks are the REVISION and EXAMINATION
periods), with every instructional week reading **✓ Parsed** and no
needs-review rows.

### Defect 6 — "Action failed — Validation failed" (main blocker)

**Root cause (confirmed, not assumed).** `POST
/api/generation/{scheme_id}/allocation-preview` with
`term_start_date: ""` / `term_end_date: ""` returns

```
HTTP 422
{"detail": "Validation failed",
 "errors": [{"field": "body -> term_start_date",
             "message": "Input should be a valid date or datetime, input is too short"},
            {"field": "body -> term_end_date", ...}]}
```

A cleared HTML date input writes `''` into the page's single `config` state, so
**Quick Generate and Build with me sent the identical broken payload and failed
identically** — the failure was a request-body invariant, not the allocation
machinery. The response body above was captured live from the deployed backend
during this investigation; the frontend banner renders `detail`, hence the
opaque "Action failed / Validation failed" copy.

**Fix (no suppression — the invariant is now satisfied, never ignored).**
- `TermConfig.term_start_date` / `term_end_date` are `Optional[date] = None`
  with a `mode="before"` validator mapping blank/`None` → unset.
- `resolve_term_window(config, scheme.weeks)` derives the window from the
  scheme's **own extracted week dates** inside both the preview and the generate
  endpoints (source stays authoritative; only a scheme with no dates at all
  falls back to the server date).
- The frontend `sanitizeTermConfig()` restores the scheme-derived span when the
  page has one and otherwise **omits** the key — it never guesses a date.
- `lesson_builder` can no longer emit a null `lesson_date`
  (allocation date → source week ending → term window → server date).
- `service.create_term_config` fills unset dates before writing the NOT NULL
  column.
- A 422 that survives now names the field in teacher language
  ("The term dates are incomplete. Set the Term Start and Term End dates, then
  try again.") instead of "Validation failed".

### Defects 4 & 5 — mixed weeks and source date segments

**Root cause.** A week cell holding both a `MID-TERM` period row and a teaching
row was merged from `rows[0]` only, so the type became `OTHER` ("Other" in the
UI), and the label was either normalised into nothing or leaked into curriculum
fields. No source-defined span was modelled at all, so the UI could only show
the single week-ending date.

**Fix.**
- New `WeekType.MIXED`. A week with a non-instructional period row **and** a
  separate row carrying real teaching content becomes `mixed`; the teaching
  row supplies strand, sub-strand and the week's dates, and the special row
  supplies only the label (metadata).
- `week_special_segments()` parses the label's own date range, day-first and
  clamped, yielding `{"type": "mid_term", "label": "MID-TERM (05-11-2026 to
  06-11-2026)", "start": "2026-11-05", "end": "2026-11-06"}` — nothing is
  invented and a label without dates yields `start/end = None`.
- `week_teaching_segments()` reports the teaching span from the source teaching
  row. The Week-9 fixture resolves to special `2026-11-05 → 2026-11-06` and
  teaching `2026-11-07` — exactly the source.
- Allocation keeps a mixed week allocatable (special segment excluded, teaching
  segment allocated); `week_is_non_instructional` and `scheme_has_indicators`
  both account for MIXED.
- Teacher-facing "Other" is gone: the extraction table and spine use
  Teaching / ★ Special period / ◐ Mixed week / ⚠ Needs review.

### Class level the document never states (the same file's second blocker)

The teacher's scheme names the subject (`SUBJECT: COMPUTING`) but never the
class — the level lives only in the curriculum codes (`B7.1.1.1.1`), which the
level detector deliberately ignores to avoid false positives. The confirmation
card therefore offered only the subject, so the scheme stayed `Unknown` class
and generation dead-ended at the 409 guard.

**Fix (curriculum authority, no guessing).** The confirmation card now asks the
teacher for the class level when the document does not state one
(`#confirm-class-level`, populated from the canonical
`/api/settings/class-levels` catalogue), and
`POST /documents/{id}/confirm-subject` accepts and validates an optional
`class_level`. An unrecognised value is rejected with a 400 — the field is
never free text and is never inferred.

### Defect 3 — Needs review opens the actual problem

Needs-review rows are amber-highlighted and carry `data-needs-review`. Clicking
one opens the week pane with a review-context banner
(`data-week-review-context`) listing the teacher-facing reasons, naming the
problematic field ("Indicator — ⚠ Needs review: SchemeKnit could not
confidently read an indicator for this week. The week stays exactly as read —
nothing is guessed"), and stating the safe continue path. The sidebar now shows
the week's *review* state instead of a misleading "Instruction" pill. Mixed
weeks render their special and teaching segments (`data-mixed-week-segments`,
`data-special-segment`, `data-teaching-segment`).

### Defect 7 — review status must not block valid teaching data

| Case | Behaviour |
|---|---|
| A · indicator confidently extracted | normal generation |
| B · indicator genuinely absent | week flagged for review; the allocation payload is **valid** and every other week generates |
| C · special period | no lesson allocated |
| D · mixed week | special segment excluded, teaching segment allocated |
| blank term dates | derived from the scheme — no rejection |

Allocation rejects only a genuinely missing invariant (subject/class
undetermined, or an unconfirmed multi-subject document) with its own
teacher-facing message.

### Defect 8 — curriculum authority preserved

No AI is involved in extraction. The empty-source week produces no lesson and no
invented indicator (asserted by tests at parser, spine and allocation level).

---

## 2. Exact files changed

Backend

| File | Change |
|---|---|
| `backend/src/models.py` | `WeekType.MIXED`; `TermConfig` term dates optional + blank→unset validator |
| `backend/src/parsers/docx_parser.py` | mixed-week merge, teaching-row framing/dates, authoritative special label with source dates, indicator guard limited to non-instructional rows |
| `backend/src/curriculum/spine.py` | mixed review state, `scheme_provides_indicators`, `special_segments` / `teaching_segments`, `classify_week_review(week, scheme_weeks)` |
| `backend/src/curriculum/lesson_builder.py` | never emit a null lesson date |
| `backend/src/engines/allocation_engine.py` | MIXED handling in `week_is_non_instructional`, `reclassify_special_weeks`, `scheme_has_indicators`, week selection |
| `backend/src/routers/documents.py` | weeks endpoint passes scheme context, returns segments + `source_provides_indicators`; confirm-subject persists special-period metadata and accepts a teacher-confirmed `class_level` |
| `backend/src/routers/generation.py` | `resolve_term_window()`, scheme-wide review context, review reasons on preview rows |
| `backend/src/service.py` | unset term dates resolved before the NOT NULL write |

Frontend

| File | Change |
|---|---|
| `frontend/src/lib/api.ts` | `sanitizeTermConfig()`, typed `source_provides_indicators` |
| `frontend/src/lib/error-normalizer.ts` | field-specific teacher-facing 422 messages |
| `frontend/src/app/(app)/upload/page.tsx` | multi-subject only for ≥2 sections; explicit "1 subject detected"; teacher confirms the class level a document omits |
| `frontend/src/app/(app)/review/[id]/page.tsx` | review context banner, mixed-week segments, Parsed/Needs review/Not provided states, review pill in the week list |
| `frontend/src/app/(app)/generate/[id]/page.tsx` | scheme-derived payload fallback, friendly error copy |

Tests & fixtures

| File | Change |
|---|---|
| `backend/tests/test_curriculum_remediation_defects.py` | **new** — 52 tests covering all 15 required backend cases |
| `backend/tests/test_curriculum_spine_and_provenance.py` | week-date helper fixed (timedelta, weeks > 5) |
| `backend/tests/fixtures/remediation/build_fixture.py` + `bs7_mixed_midterm_scheme.docx` + `bs7_code_only_indicators_scheme.docx` | **new** — real-structure regression fixtures (Defect 9) |
| `frontend/e2e/curriculum-workspace-acceptance.js` | 26 new browser checks for the remediation defects, plus a template selector (`TF_TEMPLATE`) |

---

## 3. Regression fixture (Defect 9)

Two fixtures are built by `fixtures/remediation/build_fixture.py` — both
reproduce real source structures, **not** simplified synthetic shapes:

`bs7_mixed_midterm_scheme.docx` (the prose+code shape of `BS7-1st-Term-RME`):

* one subject section → `1 subject detected`
* weeks 1,2,4–7,10–12 carry indicators (extraction must succeed)
* week 3's indicator cell is genuinely **empty** (must stay empty)
* week 8's indicator is split across physical lines (continuation cell)
* **week 9 holds a `MID-TERM (05-11-2026 to 06-11-2026)` row *and* a teaching
  row** → mixed week, midterm never a lesson, teaching content kept
* week 13 is a pure `REVISION` period

`bs7_code_only_indicators_scheme.docx` (the exact shape of the teacher's
`BS7-1st-Term-Computing-Scheme.docx` that produced "only one week captured the
indicators"):

* the INDICATOR column prints **codes only** — no prose anywhere
* week 6 lists two codes in one cell → two indicators
* week 9 shares its week cell with a `MID-TERM (05-11-2026 to 06-11-2026)` row
* weeks 14/15 are `REVISION` / `EXAMINATION`
* a guard test asserts the cells really are code-only, so the regression cannot
  pass by accident

Asserted end-to-end: single-subject detection, indicator extraction
present/absent/multi-line/code-only, needs-review classification, mixed-week
classification, segmented dates, mixed-week allocation, confirmation-path
metadata persistence, teacher-confirmed class level, and no indicator
fabrication.

---

## 4. Test and acceptance results

| Gate | Result |
|---|---|
| Backend suite | **1600 passed, 12 skipped, 0 failed** (baseline before this pass: 1549 passed, 11 skipped) |
| Frontend typecheck | `npx tsc --noEmit` clean |
| Frontend build | `NEXT_PUBLIC_BUILD_TARGET=web npx next build` — compiled successfully |
| Browser acceptance (the teacher's real `BS7-1st-Term-Computing-Scheme.docx`, Approved WAPEF Plan) | **79/79 checks passed** |
| Browser acceptance (remediation fixtures) | **81/81 checks passed** |
| Browser acceptance (real `BASIC 7 ENGLISH SCHEME OF LEARNING.docx`) | **75/75 checks passed** |

New browser checks proven against the running stack (built frontend :3100,
backend :8000):

* single-subject upload never claims multiple subjects; "1 subject detected"
* the class level a document omits can be confirmed by the teacher
* weeks whose source has an indicator keep it — **13/15** on the teacher's real
  Computing scheme (previously 1/15) and 11/13 on the fixture
* Needs review click opens the week review context naming what needs attention
* mixed week labelled "Mixed week", never "Other"
* midterm segment keeps the SOURCE date range — the report records
  `Special period: MID-TERM (05-11-2026 to 06-11-2026) · 2026-11-05 → 2026-11-06`
* teaching segment shown beside the special period; spine exposes
  `special_segments`
* **Quick Generate → Preview Allocation succeeds (HTTP 200)**
* **emptied term dates do NOT produce a validation failure (HTTP 200)**
* **Build with me → Preview Allocation succeeds (HTTP 200)**
* no "Validation failed" / "Action failed" anywhere on valid paths
* workspace, provenance, Main Learning edit+persist, DOCX (43,995 B `PK`) and
  PDF (222,986 B `%PDF-`) downloads, mobile viewport — all still pass

---

## 5. Production acceptance

**Status: blocked — not claimed.** The Render deployment does not auto-deploy
on push, and the deployed build still serves the pre-remediation code (its week
payload has no `review_status`, the spine route 404s and the live BS7 RME rows
still show the stale extraction). The same blocker applied to the previous
task.

Once the owner triggers a redeploy, the verification run is:

```
cd frontend
TF_WEB_URL=https://schemeknit-frontend.onrender.com \
TF_API_URL=https://schemeknit-api.onrender.com \
TF_UPLOAD_FILE="<the teacher's single-subject scheme>.docx" \
node e2e/curriculum-workspace-acceptance.js
```

which drives UPLOAD → subject count → week/indicator extraction → review states
→ mixed week → review interaction → Preview Allocation (both modes) → the real
lesson workspace. Per the spec, this task is **not** declared complete until
Preview Allocation succeeds in the deployed environment.

Locally the same command with `TF_TEMPLATE="WAPEF"` and the teacher's real file
(`C:\Users\SAVIOUR\Downloads\BS7-1st-Term-Computing-Scheme.docx`) passes all 79
checks against the built frontend and local backend.
