# SchemeKnit — Final Lesson-Quality Remediation Report

Status: **NOT READY — LESSON QUALITY REMEDIATION INCOMPLETE**

Substantial, verified progress was made in this pass, and every change is
covered by a green regression test. Two release gates remain open and are named
at the end: the official NaCCA exemplar corpus (PART 16/32) and the deployed
production acceptance (PART 37). Per the task's own bar, neither the localhost
suite nor a `%PDF` signature is accepted as completion.

All work below is **uncommitted** on `main` (no commit or push was performed).

---

## 1. Save Review — root cause and fix

**Root cause (traced, not guessed).** Two independent faults, both in the
persistence boundary rather than the message:

1. `backend/src/parsers/docx_parser.py` — an in-progress edit had indented
   `res = row.get("resources", "")` inside the `if not label_only:` branch. Any
   week whose indicator cell was a special-period label hit
   `UnboundLocalError: cannot access local variable 'res'` and the whole parse
   (and therefore every dependent save) failed. Fixed by restoring the loop-level
   indentation; `tests/test_curriculum_remediation_defects.py` (52 tests,
   previously 11 errors + 2 failures) is green.
2. The four WAPEF columns were unmapped in the renderer: `WAPEF_TOKEN_FIELDS`
   was renamed to the real lesson attribute names (`wapef_deep_hope`, …) but the
   `_resolve()` branches still tested the old dotted tokens, so every WAPEF value
   resolved to `""`. Fixed by aligning the resolver; `tests/test_wapef_acceptance.py`
   is green.

**Regression coverage.** `backend/tests/test_lesson_persistence_matrix.py`
asserts a complete realistic `PUT /lessons/{id}` payload returns 200 and echoes
verbatim, and that `PUT /{scheme}/lesson-review` accepts every allowed draft key.
`TestCompleteSaveRoundtrip` / `TestSaveReviewCompletePayload` /
`TestWorkspaceSavePayload` pin this.

## 2. Persistence — root cause and fix

The database was already authoritative for the fields the UI *sent*; the loss
was in what the UI sent. The lesson workspace
(`frontend/src/components/lesson-workspace.tsx`) previously saved only
`lesson_topic / introduction / assessment / conclusion / main_activities`.

Now the workspace owns and sends the full teacher-owned set in one payload —
class + home assignment, homework, keywords, lesson resources, structured
references, and the four WAPEF selections — and re-seeds its draft from the
server's echo after save, so the UI cannot drift from the database.
`TestWorkspaceSavePayload` writes that exact payload through a **fresh session**
(the save → navigate → return → reload → reopen path) and asserts every value.

Two supporting fixes made the round-trip honest:

* `service.update_lesson_plan` coerces list/text/numeric columns at the boundary
  and de-duplicates rather than double-encoding;
* `official_ges_template` conclusion de-duplicates `home_assignment` and
  `homework`, so the mirrored pair is never printed twice.

## 3. WAPEF persistence — root cause and fix

See §1.2 (token/attribute mismatch). Additionally the `_phase_resources`
precedence was flipped to `teaching_learning_resources or source_tlrs` so a
teacher-edited lesson resource is not silently replaced by the scheme's raw
value, and WAPEF now places the assignments inside the approved form
(PHASE 2 / PHASE 3) instead of dropping them.
Acceptance (backend, real renderers): `TestWapefFirstClassPersistence`,
`TestStructuredPdfTemplateFidelity`, `TestDocxTemplateFidelity`.

## 4. Class detection — root cause and fix

The scheme document legitimately may not state a class, and "Unknown" was being
rendered as a generation-ready value. Now:

* `frontend/src/app/(app)/generate/[id]/page.tsx` shows **"Class needs confirmation"**
  with a catalogue-validated `<select>` and adds a block reason until chosen;
* `backend/src/routers/generation.py` accepts a teacher-confirmed class **only**
  when the scheme states none, validates it against the same `ClassLevel` enum the
  settings endpoint serves, persists it on the scheme (so preview, generation and
  every export agree) and never accepts `"Unknown"`;
* a class the document *does* state is never overwritten by a client value;
* the workspace renders `"Needs confirmation"` rather than `"Unknown"`.

Tests: `test_curriculum_remediation_defects.py::TestConfirmationPersistsSourceMetadata`,
`test_final_web_ux.py` class tests.

## 5. Mixed-week date logic — root cause and fix

`allocation_engine` used the special period's *end* date as the teaching start.
`special_period_date_range()` now parses the label's own `DD-MM-YYYY → DD-MM-YYYY`
range and removes exactly those days from the teaching window, so the observed
`MID-TERM 05-11-2026 → 06-11-2026` yields teaching from `07-11-2026` onward.
Source-defined dates are preserved; no Monday–Friday range is invented. A label
with no dates (bare `REVISION`) excludes nothing.
Test: `test_curriculum_remediation_defects.py::test_mixed_week_allocation_excludes_special_segment`.

## 6. Special-period contamination — root cause and fix

Two leaks, both closed at the source:

* `docx_parser` treated a cell that fused the period label with an indicator code
  as an indicator; it now strips the code first and tests the remainder, so the
  label can never be collected as curriculum content;
* the resource collector now filters any item that `is_special_label_text`, so
  `MID-TERM (05-11-2026 to 06-11-2026)` can never enter a lesson's TLR list.

Content standard, indicator and resources therefore stay clean while the period
is surfaced as separate metadata (`special_period_label` / `special_period_type`).
Tests: `test_curriculum_remediation_defects.py::TestRealSchemeFixtureRegression`,
`test_special_periods_remediation.py`.

## 7. Duplicate indicator / content-standard — root cause and fix

`_code_and_text` prepended the code to text that already began with it, printing
`B7.1.1.1 B7.1.1.1`. The GES renderer was fixed earlier; this pass applied the
same canonical helper to the WAPEF renderer (`wapef_template` now imports
`official_ges_template._code_and_text`), so both forms print a code exactly once
while genuinely distinct values are preserved.
Tests: `TestCurriculumCodeDeduplication` (includes a two-distinct-indicators case
proving dedup never collapses real values).

## 8. PDF renderer — root cause and fix

The old fallback re-extracted DOCX text into paragraphs (a text dump). The
current fallback is the template-aware ReportLab renderer
(`backend/src/engines/structured_pdf.py`), which builds real bordered tables from
the same canonical lesson the DOCX path uses, dispatching on template identity
(WAPEF / official GES / standard) through the same resolvers.
One defect fixed here: `_resource_lines` preferred `source_tlrs`, so a
teacher-corrected lesson resource never reached the PDF; precedence is now the
lesson value with the source as fallback.
Verification (`TestStructuredPdfTemplateFidelity`): `%PDF-` signature **and**
`page.find_tables()` returns real tables **and** the four WAPEF values, both
assignments, the corrected resource and the curriculum code are all found in the
extracted text, while `Acceptance` / `svg` are not.

## 9. AI suggestion — root cause and fix

Traced end to end (`/api/ai/regenerate-section`): entitlement gate
(`require_ai_entitlement`) → provider resolution → availability check → structured
extraction for `main_activities` → teacher-safe `{code, message, diagnostic}`
error contract. The provider-payload key mapping (`SECTION_TO_PROVIDER_KEYS`),
the structured activity normalizer, the one bounded retry and the
"content preserved" guarantee on every failure path were already present and are
pinned by `test_ai_failure_hardening.py` / `test_main_learning_remediation.py`.
The frontend maps the contract through `aiFailure()` and **never blanks** an
existing section: a failure leaves the deterministic content in place and shows
calm copy. No provider internals reach the teacher.

## 10. Phase-generation architecture implemented

Deterministic, curriculum-grounded, now genuinely subject-aware:

* `indicator_interpreter` (verb/Bloom analysis → activity type, evidence,
  misconceptions);
* `_PHASE_BANK` (teacher actions) **and** `_LEARNER_PHASE_BANK` (learner actions),
  so every phase answers *what the teacher does / what learners do*;
* `_STARTER_BANK`, `_ASSESSMENT_BANK`, `_PLENARY_BANK`, `_CLASS_ASSIGNMENT_BANK`,
  `_HOME_ASSIGNMENT_BANK` — all keyed by the indicator's activity type;
* `pedagogy.py` subject profiles for 12 curricula;
* **new** `_SUBJECT_PRACTICE_CLAUSE` — one bounded, subject-specific practice
  sentence appended to the consolidating MAIN phase, so the same indicator verb
  is no longer taught with one identical template in every subject.

## 11. Official curriculum / exemplar sources used

The teacher's uploaded scheme remains the planning authority (indicators, codes,
resources, sequence, week allocation). The official NaCCA **exemplar corpus**
(PART 16/32) is **not implemented** — the official subject curriculum documents
are not present in the repository, and PART 33 forbids inventing a false
"official exemplar". The deterministic transform is therefore grounded in the
scheme's own indicator text and the subject pedagogy library, with provenance
kept visible. This is the largest open gap (see *Remaining*).

## 12. New subject-aware pedagogy behaviour

Empirically verified (ICT / RME / Mathematics, same lesson builder):

* *distinguish* → comparison structure;
* *discuss* → discussion structure;
* *solve word problems* → worked example → guided practice → independent practice;

and the consolidating phase now differs per subject, e.g. RME
"…give reasons respectfully, listen to a different view…" vs Mathematics
"…insist on the full working, not only the answer…".
Tests: `TestSubjectAwarePedagogy`.

## 13. Class Assignment behaviour

Generated deterministically from the indicator's activity type (a classification
lesson sets a sorting task; an investigation sets an evidence-recording task),
editable in the workspace, persisted, and placed in the approved template's own
location: WAPEF PHASE 2 (MAIN) and the GES assessment cell, labelled
`Class Assignment:`.

## 14. Home Assignment behaviour

Same mechanism, placed in WAPEF PHASE 3 (PLENARY / REFLECTION) and the GES
conclusion row. AI enrichment writes *both* `home_assignment` and the legacy
`homework` column together so the two can never disagree, and the renderers
de-duplicate them.

## 15. Keyword behaviour

Scheme resources are now the primary seed, then indicator → sub-strand (2) →
content standard (2) → activity context, with a new noise filter that removes
stopwords (`between`), Bloom action verbs (`distinguish`, `compare`, `discuss`)
and generic activity synonyms. Verified: Computing yields
`["Touchscreen", "Mouse", "Keyboard", "manual", "automatic", "devices"]`
(the spec's own example), and RME → `["Holy Bible", "nature", "god", "worship"]`.
Tests: `TestKeywordQuality`.

## 16. School field behaviour

Server-authoritative. `/api/auth/profile` now lets an **independent** teacher
(no school membership) declare their institution once; a school-attached
teacher's membership always wins and cannot be overwritten. The value is resolved
per generation from the authenticated user, shown on the generation summary and
in the workspace header, and carried into DOCX/PDF. No internal account IDs are
exposed. Tests: `test_final_web_ux.py::TestServerDerivedIdentity`.

## 17. Internal / debug-string audit

Audited the whole repository for `Acceptance`, `test marker`, `debug`, `fixture`,
long digit runs and `svgSuggest`:

* **no production source** ever generated such a string — the exported Word
  contained a value typed by the *acceptance harness* into Main Learning;
* the two tracked harnesses now type realistic teacher content
  (`curriculum-workspace-acceptance.js`, `main-learning-download-acceptance.js`);
* defence in depth: `strip_internal_markers()` in `ai_resource_text` removes
  acceptance/debug/fixture markers, bare 12–13-digit epoch stamps and the
  `svg…` icon-serialization leak, and is applied to text, list and
  activity/objective fields on the save boundary and to AI-generated homework;
* the workspace's Suggest icon is now `aria-hidden`.

`svgSuggest` itself was a text-scraping artefact of the icon beside "Suggest";
with `aria-hidden` and the sanitizer it cannot enter a lesson or an export.
Tests: `TestInternalMarkerGuard`.

## 18. DOCX verification

`TestDocxTemplateFidelity` renders the canonical WAPEF lesson to DOCX and asserts
a `PK` (valid OOXML) body containing the form's real tables, all four WAPEF
values, both assignments, and the corrected lesson resource.
`test_wapef_acceptance.py` / `test_export_download.py` remain green (370 tests).

## 19. PDF visual verification

Beyond the `%PDF` signature (PART 30): page images/tables are inspected in tests —
`find_tables()` must return real tables, WAPEF fields must be visible, phases must
land in the delivery grid, resources in the Resources column, assessment in
EVALUATION, and no internal string may appear.

## 20. Backend tests

`1659 collected`. Full suite run in three batches:
`602 passed, 2 skipped` / `636 passed, 1 skipped` / `407 passed, 9 skipped`
— **1645 passed, 12 skipped, 0 failed**.
New this pass: `backend/tests/test_lesson_quality_remediation.py` (29 tests,
all green).
Note: `reportlab==4.2.5` is declared in `requirements.txt` but was missing from
the local venv; it was installed to run the PDF acceptance (the three
previously-failing PDF tests are environmental, not code, failures).

## 21. Browser tests

Not run in this pass (no local stack was started). The tracked acceptance
harnesses were updated for PART 21 but were not executed here — PART 29's
comprehensive WAPEF save/reload/export browser journey has **not** been run or
evidenced from this pass.

## 22. Production tests / 23. Real Render results

**Not performed.** No deploy, no Render run. Per PART 37 this task cannot be
declared complete on localhost alone.

## 24. Commit hashes

None — the work is uncommitted. `HEAD` is `073fed4`
("fix(parser): restore cell-evidence week classification and green baseline").

## 25. HEAD == origin/main

Not inspected/pushed. The tree contains uncommitted work, so this is **false**.

## 26. Tracked tree

**Dirty** (21 modified tracked files + 1 new test file). Not clean.

---

## Verification performed this pass

| Gate | Result |
|---|---|
| Backend suite (all batches) | 1645 passed, 12 skipped, 0 failed |
| Frontend typecheck | `npx tsc --noEmit` clean |
| Frontend build | `NEXT_PUBLIC_BUILD_TARGET=web npx next build` succeeded |
| WAPEF DOCX (4 fields + assignments + tables) | verified in-test |
| WAPEF structured PDF (tables + 4 fields + assignments) | verified in-test |

## Remaining work (why this is NOT READY)

1. **PART 16/32 — official NaCCA exemplar corpus.** The exemplar-driven
   deterministic layer is not built; the official curriculum documents are not
   in the repo and PART 33 forbids fabricating them. The deterministic engine is
   grounded in the scheme + subject pedagogy instead.
2. **PART 29 — comprehensive browser journey** (open WAPEF lesson → edit all
   fields → save → dashboard → return → reload → verify → export DOCX/PDF →
   verify in both) has not been executed from this pass.
3. **PART 37 — deployed production acceptance** has not been run; nothing was
   deployed.
4. **PART 10** — revision-week classification is implemented and unit-tested, but
   the "Case B mixed revision week" is not yet exercised against a real document
   end to end.
5. The working tree is uncommitted and ahead of `origin/main` is unverified.

**Verdict: NOT READY — LESSON QUALITY REMEDIATION INCOMPLETE.**
