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

Three distinct causes were found and separated:

1. **Stale production extraction.** The deployed rows (scheme
   `2f2e09db-…`, BS7 RME) were written by the *pre-PART-O* parser: weeks 3–8 and
   10–13 carry no indicators, week 2's indicators are mangled
   (`1.1.1.1 B7 B7.1.1.1.2…`), and week 9's `MID-TERM` label is stored **as an
   indicator**. Re-reading the same source with the current parser yields an
   indicator for every week that has one. The production data is stale-deploy
   data, not a current-parser failure.

2. **Real current-parser loss — special-period labels.** The label scan in
   `_merge_week_rows` accepted the first cell in the row that contains a period
   keyword, so the sub-strand cell (bare `MID-TERM`) won over the strand cell
   that carried the **date range**, and the range was lost. Worse, matching
   period keywords against *indicator* text could silently drop real
   curriculum: `"Examine …"` contains `"exam"`, and ordinary descriptions
   contain `"sba"`.

3. **Conflated review semantics.** `classify_week_review` flagged a week with
   no indicator as `needs_review` even when the *whole source* has no Indicator
   column (the WAPEF Nursery/KG shape), i.e. it could not tell "the source has
   none" from "the parser missed this week".

**Fix.**
- The special-label guards now apply only to a **non-instructional row whose
  cell contains no indicator code**, so a real indicator is never dropped
  because of a keyword substring.
- The strand cell of a special row is the authoritative label; the
  noise-normalising pass keeps the source's date range
  (`AND VACATION` → `VACATION`, `REVISION1` → `REVISION`,
  `MID-TERM (05-11-2026 to 06-11-2026)` unchanged).
- `scheme_provides_indicators(weeks)` answers the scheme-wide question. The
  spine and both routers pass the full week list, so:
  * source provides indicators elsewhere + this week empty → **⚠ Needs review**
  * source has no Indicator column at all → **— Not provided in source**
  * special / mixed week → **★ Special period / ◐ Mixed week**
- The label can no longer surface as an indicator, strand or sub-strand.

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
| `backend/src/routers/documents.py` | weeks endpoint passes scheme context, returns segments + `source_provides_indicators` |
| `backend/src/routers/generation.py` | `resolve_term_window()`, scheme-wide review context, review reasons on preview rows |
| `backend/src/service.py` | unset term dates resolved before the NOT NULL write |

Frontend

| File | Change |
|---|---|
| `frontend/src/lib/api.ts` | `sanitizeTermConfig()`, typed `source_provides_indicators` |
| `frontend/src/lib/error-normalizer.ts` | field-specific teacher-facing 422 messages |
| `frontend/src/app/(app)/upload/page.tsx` | multi-subject only for ≥2 sections; explicit "1 subject detected" |
| `frontend/src/app/(app)/review/[id]/page.tsx` | review context banner, mixed-week segments, Parsed/Needs review/Not provided states, review pill in the week list |
| `frontend/src/app/(app)/generate/[id]/page.tsx` | scheme-derived payload fallback, friendly error copy |

Tests & fixtures

| File | Change |
|---|---|
| `backend/tests/test_curriculum_remediation_defects.py` | **new** — 43 tests covering all 15 required backend cases |
| `backend/tests/test_curriculum_spine_and_provenance.py` | week-date helper fixed (timedelta, weeks > 5) |
| `backend/tests/fixtures/remediation/build_fixture.py` + `bs7_mixed_midterm_scheme.docx` | **new** — real-structure regression fixture (Defect 9) |
| `frontend/e2e/curriculum-workspace-acceptance.js` | 21 new browser checks for the remediation defects |

---

## 3. Regression fixture (Defect 9)

`backend/tests/fixtures/remediation/bs7_mixed_midterm_scheme.docx`, built by
`build_fixture.py`, reproduces the real BS7 RME structure that exposed the
defects — **not** a simplified synthetic shape:

* one subject section → `1 subject detected`
* weeks 1,2,4–7,10–12 carry indicators (extraction must succeed)
* week 3's indicator cell is genuinely **empty** (must stay empty)
* week 8's indicator is split across physical lines (continuation cell)
* **week 9 holds a `MID-TERM (05-11-2026 to 06-11-2026)` row *and* a teaching
  row** → mixed week, midterm never a lesson, teaching content kept
* week 13 is a pure `REVISION` period

Asserted end-to-end: single-subject detection, indicator extraction
present/absent/multi-line, needs-review classification, mixed-week
classification, segmented dates, mixed-week allocation, and no indicator
fabrication.

---

## 4. Test and acceptance results

| Gate | Result |
|---|---|
| Backend suite | **1591 passed, 12 skipped, 0 failed** (baseline before this pass: 1549 passed, 11 skipped) |
| Frontend typecheck | `npx tsc --noEmit` clean |
| Frontend build | `NEXT_PUBLIC_BUILD_TARGET=web npx next build` — compiled successfully |
| Browser acceptance (remediation fixture) | **81/81 checks passed** |
| Browser acceptance (real `BASIC 7 ENGLISH SCHEME OF LEARNING.docx`) | **75/75 checks passed** |

New browser checks proven against the running stack (built frontend :3100,
backend :8000):

* single-subject upload never claims multiple subjects; "1 subject detected"
* weeks whose source has an indicator keep it (11/13 on the fixture)
* Needs review click opens the week review context naming what needs attention
* mixed week labelled "Mixed week", never "Other"
* midterm segment keeps the SOURCE date range `2026-11-05 → 2026-11-06`
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
