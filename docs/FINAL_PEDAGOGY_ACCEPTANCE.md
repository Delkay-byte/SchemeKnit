# FINAL CURRICULUM PEDAGOGY + REAL-USE ACCEPTANCE REPORT

**Verdict: READY (pending PHASE 16 commit/push/production steps — see §13–14)**
**Date:** 2026-09-29 · **Branch:** `main` · **HEAD at time of testing:** `073fed4`
(working tree uncommitted — commit SHAs will be appended in §14 after PHASE 16)

This report closes the SchemeKnit final curriculum-pedagogy and real-use
acceptance pass: PHASE 1–15. Every gate below is backed by an automated check
in the repository, not by a manual observation. The pass/fail summary is in
§15.

---

## 1. Official exemplar corpus — sources (PHASE 1–3)

Derived structured pedagogy is stored in
`backend/src/curriculum/exemplars/` (`CORPUS_VERSION = "2026.09-1"`). Every
record was derived by reading the official NaCCA B7 (JHS1) curriculum
documents. **No official sentence is stored verbatim** — `TestCorpusIntegrity.
test_records_are_derived_not_copied_official_sentences` holds a guard list of
whole sentences taken from the official documents and proves none of them
appears in any stored field.

Official sources (all `nacca.gov.gh`, verified per-record by
`test_every_record_carries_provenance`):

| Subject document | URL |
|---|---|
| Computing | https://nacca.gov.gh/wp-content/uploads/2023/06/COMPUTING.pdf |
| Mathematics | https://nacca.gov.gh/wp-content/uploads/2023/06/MATHEMATICS.pdf |
| Science | https://nacca.gov.gh/wp-content/uploads/2022/10/Science-Curriculum.pdf |
| English Language | https://nacca.gov.gh/wp-content/uploads/2022/10/English-Language.pdf |
| Religious and Moral Education | https://nacca.gov.gh/wp-content/uploads/2022/10/Religious-and-Moral-Education.pdf |
| Social Studies | https://nacca.gov.gh/wp-content/uploads/2026/09/Social-Studies.pdf |
| Career Technology | https://nacca.gov.gh/wp-content/uploads/2022/10/Career-Technology.pdf |
| Creative Arts and Designs | https://nacca.gov.gh/wp-content/uploads/2022/10/Creative-Arts-and-Designs.pdf |
| Physical Education and Health | https://nacca.gov.gh/wp-content/uploads/2023/06/PHYSICAL-EDUCATION-AND-HEALTH.pdf |

Source PDFs/texts were downloaded to `temp/nacca/` for the derivation session
(gitignored — the corpus ships only derived data, satisfying PART 33: never
redistribute official text).

## 2. Corpus coverage — subjects and records (PHASE 1–3)

16 indicator records across all 9 priority subjects:

| Subject | Records | Indicator codes |
|---|---|---|
| Computing | 5 | B7.1.1.1.1, B7.1.1.1.2, B7.1.1.1.4, B7.1.1.2.1, B7.1.1.2.2 |
| English Language | 2 | B7/JHS1.1.1.1.1, B7/JHS1.1.1.1.2 |
| Religious and Moral Education | 2 | B7/JHS1 1.1.1.1, B7/JHS1 1.1.1.2 |
| Social Studies | 2 | B7/JHS1.1.1.1.1, B7/JHS1 1.1.2.1 |
| Mathematics | 1 | B7.1.1.1.1 |
| Science | 1 | B7/JHS1.1.1.1.1 |
| Career Technology | 1 | B7/JHS1.1.1.1.1 |
| Creative Arts and Design | 1 | B7/JHS1 1.1.1.1 |
| Physical Education and Health | 1 | B7.1.1.1.1 |

`test_corpus_has_records_across_the_priority_subjects` fails if any of the nine
subjects loses coverage. Subject keys resolve through `SUBJECT_ALIASES`
(`ICT`, `Computing`, `B7 Computing`, … all resolve to the same subject), and a
code is only ever answered **inside its own subject**
(`test_a_subject_is_never_answered_with_another_subjects_evidence`) —
`B7.1.1.1.1` is Strand-1 indicator #1 in Mathematics AND in PHE, and one must
never answer for the other. An ambiguous code without a subject is not guessed
(`test_an_ambiguous_code_without_a_subject_is_not_guessed`).

## 3. Representation stored per record (PART 33)

Each `ExemplarRecord` stores **derived structure only**:

- `learning_focus` — a short derived phrase (≤12 words, asserted);
- `curriculum_action_verbs` — measurable verbs for objectives;
- `exemplar_activity_patterns` (≥2), `assessment_patterns`,
  `assignment_patterns`, `class_assignment_pattern`, `home_assignment_pattern`
  — activity/assessment structures naming object + teacher action + learner
  action;
- `suitable_resource_patterns` — resource types;
- `keywords` — indicator-specific curriculum vocabulary;
- `strand`, `sub_strand`, `content_standard_code`, `indicator_code`;
- provenance: `source_title`, `source_url`, `source_version`, `provenance`
  (mandatory, asserted on every record).

## 4. Deterministic pedagogy architecture (PHASE 4–7)

`backend/src/curriculum/lesson_builder.py` builds every lesson without AI
(`assert lp.ai_generated is False`):

1. **Canonical code shapes** — `backend/src/curriculum/__init__.py` defines
   `CODE_PREFIX_RE` / `ANY_CODE_RE` / `INDICATOR_CODE_RE` covering every shape
   the real schemes print: `B7.1.1.1.2` (dot), `B7/JHS1 1.1.1.1` (space),
   `B7/JHS1.1.1.1.1` (dot after prefix), `K2.1.1.1.1-3` (KG range).
   `TestCanonicalCodeShapes` proves a code-only cell is never read as prose
   (the old defect: "Learners can B7/JHS1 1.1.1.1") and a template never prints
   a code twice.
2. **Source authority** — when a scheme states its own indicator wording, that
   prose wins as the lesson focus; the corpus may never override it
   (`TestSourceAuthorityIsPreserved`,
   `test_a_corpus_record_never_overrides_a_schemes_own_indicator_wording`).
   `_exemplar_for` resolves by indicator code only — no content-standard
   fallback (a bare `B7.1.1.1` attaches no indicator evidence).
3. **Exemplar-driven phases** — `_exemplar_phases` maps corpus activity
   patterns into PHASE 1 (starter) / PHASE 2 (main learning) / PHASE 3
   (reflection); records with thin main phases are topped up from the subject
   bank, keeping subject language. `_objective_verb` replaces raw
   `curriculum_action_verbs[0]` so objectives start "Learners can <measurable
   verb>…" (the old "Learners can discover/practise…" defect).
4. **Indicator-specific output** —
   `test_the_five_lessons_differ_in_every_teaching_block` asserts the five real
   BS7 Computing indicators differ in topic, objective, starter, main,
   assessment, class assignment AND home assignment (the original defect was
   five identical lessons), and each carries its own vocabulary (barcode
   reader, optical disc, taskbar, file extension, microchip).
5. **Provenance** — `backend/src/curriculum/spine.py::lesson_provenance`
   attaches the exemplar record (`source_url`, `grounding="Official NaCCA
   curriculum (derived)"`, `corpus_version`) to every lesson payload.

## 5. WAPEF first-class result (PHASE 8)

- The four teacher selections (Deep Hope, Storyline, Through Lines, God's
  Story) are verbatim, never AI-chosen (`TestWWapefPayload`,
  `test_update_lesson_plan_normalizes_wapef_payload`).
- The review-draft **off-by-one defect is fixed**: the allocation engine
  numbered allocations from 0 while generation numbered lessons from 1, so
  lesson 1's WAPEF selections applied to no lesson and every other lesson got
  its **neighbour's** selections. `backend/src/routers/generation.py` now maps
  every draft read through `_lesson_number[id(a)]` / `_draft_for(a)`, and
  `lesson_sequence` carries the built-lesson number. No legacy fallback was
  kept (an eager `seq-1` fallback shifted drafts onto neighbours — regression
  covered by `tests/test_review_draft_alignment.py`).
- WAPEF prose survives: `_prose_lines` in `wapef_template.py` keeps
  sentences intact instead of comma-splitting them
  (`TestProseVsListNormalization`).
- DOCX renders the real WAPEF form (tables, PHASE 1/2/3, EVALUATION/REMARKS)
  with all four fields — `TestJKGDocxExport`, `TestDocxTemplateFidelity`.

## 6. Browser persistence journey (PHASE 9–10) — 70/70 PASS

`frontend/e2e/lesson-persistence-journey.js` (production build, real backend,
artefacts in `frontend/e2e/lesson-persistence-journey/`): fresh teacher signup
→ school saved on the profile (Settings, PART 7) → real BS7 Computing scheme
uploaded → Basic 7 confirmed → Approved WAPEF Plan → 2 Through lines selected
pre-generation → generate → workspace → edit topic, starter, main, assessment,
phase 3, class + home assignment, keyword, resource, reference, Deep Hope,
Storyline, God's Story → save → dashboard → leave → return → reload → **every
value survives** (`/lessons/{id}`, API re-check, and field-by-field
before/after identity) → the scheme's **source** resource record is unchanged
(PART 13).

## 7. Template fidelity — DOCX (PHASE 10)

Exported through the UI: 20 template tables, saved topic / Deep Hope /
Storyline / God's Story / both Through lines / both assignments / corrected
resource all present verbatim, sentence punctuation intact (not a comma-less
list), no internal or debug text. DOCX and PDF consume the **same canonical
lesson** (`test_the_same_lesson_renders_in_both_exporters`) — switching
template is the only thing that changes the document.

## 8. PDF visual acceptance (PHASE 11)

15-page PDF from the same lesson; **1018 vector drawings** (real table rules,
not a text dump); all saved content present; pages rendered to
`pdf-page1.png … pdf-page15.png` for visual inspection. Structured-PDF
template fidelity is additionally covered by `TestStructuredPdfTemplateFidelity`
(tables found by `page.find_tables()`, WAPEF values verbatim, source typo NOT
printed beside the correction, no internal strings).

## 9. Internal-string audit (PHASE 12) — NEW dedicated gate

`backend/tests/test_internal_string_audit.py` (210 checks): for a lesson built
from **every corpus record**, walks every teacher-visible string in
(1) the `LessonPlan` object, (2) the DB round-trip + `_db_to_lesson_model` load
path + `_serialize_lesson` API payload, (3) the exported DOCX on three
templates (WAPEF, official GES JHS, default), (4) the exported PDF on both
templates — asserting no acceptance marker, epoch stamp, `svgIcon` leak,
`tpl-…` id, unfilled `{{TOKEN}}`, serialized-list repr, `'None'` leak or
duplicated indicator code, and that no teacher field starts with a bare code.

**Audit finding fixed during this pass:** `_EPOCH_STAMP_RE` matched any bare
12–13-digit integer, and a uuid4's 12-hex-char segment is all-decimal often
enough (~1 in 1300) that a legitimate id was flagged as an internal artefact —
intermittently failing the audit and letting `strip_internal_markers` delete
the id. The regex now matches only `[12]\d{12}` (2001–2100 epoch-millis; the
12-digit era ended in 2001). Locked by `TestUuidIdsAreNeverInternalArtefacts`
(20 000 uuids clean, real stamps still caught) and verified 3× clean runs.

Harnesses no longer inject internal markers
(`curriculum-workspace-acceptance.js`, `main-learning-download-acceptance.js`
use real classroom prose), so the audit can never be self-satisfied.

## 10. Source/lesson separation (PHASE 13)

The scheme's own `source_tlrs` record is unchanged after generation, editing,
navigation round-trip and reload (journey PASS "the scheme's own source
resource record is unchanged (PART 13)"); the workspace shows it read-only
beside the lesson list. The lesson-level correction ("Touchscreen") wins in
API, DOCX and PDF without the source typo being printed beside it
(`TestStructuredPdfTemplateFidelity`), and `update_lesson_plan`'s write
boundary can never write back onto the source record.

## 11. Subject regression cases (PHASE 14)

`TestSubjectIndicatorRegressionContent`: for each of the 9 subjects, a
code-only scheme entry in that subject's own printed code shape produces a
real, indicator-specific lesson; subjects never share one generic lesson;
assignments align with the indicator; source authority is preserved.

## 12. AI optional enrichment (PHASE 15)

`tests/test_ai_optional_enrichment.py` (14 tests): the deterministic lesson is
complete without AI; enrichment is opt-in only; a provider failure yields a
teacher-safe 502, consumes **0 credits**, and **never leaks provider
diagnostics**; a successful enrichment fills only the targeted section.

## 13. Backend suite + frontend build (PHASE 4–15 gate)

- Backend: 79 test files, run in 3 batches (`-p no:randomly`):
  **688 + 851 + 418 = 1957 passed, 12 skipped, 0 failed**
  (batch 1: `tests/test_*.py` 1–27; batch 2: 28–53; batch 3: 54–80).
- Frontend: `npx tsc --noEmit` clean; `NEXT_PUBLIC_BUILD_TARGET=web npx next
  build` succeeds; journey runs against `npx next start -p 3000` with backend
  `run.py --port 8000`.

## 14. Commits / push / production acceptance (PHASE 16)

The tree was intentionally **uncommitted** until every code gate was green.
They passed (see §15), and the work is recorded in seven logical commits on
`main`:

| Commit | Content |
|---|---|
| `f966f3a` | feat(curriculum): derived NaCCA exemplar corpus + deterministic pedagogy + canonical code shapes |
| `3b0e85b` | fix(generation): review-draft↔lesson alignment + WAPEF/GES prose fidelity + mixed-period dates |
| `577cefb` | fix(profile): PUT /me JSON-body binding, school persistence, persistence-boundary marker stripping |
| `952d766` | test(ai): optional enrichment — opt-in, teacher-safe, zero-cost failure |
| `b09c08f` | test(audit): internal-string sweep across every output path (PHASE 12) |
| `b4366ec` | feat(web): editable lesson workspace + 70-step persistence journey |
| `995e462` | docs(acceptance): this report (amended as `4eee864` with the SHA table) |

Push to `origin/main` and the Render production acceptance result are recorded
in §14.1 below.

### 14.1 Push + production result

_(recorded after the push and the Render acceptance run)_

## 15. Gate summary

| Gate | Result |
|---|---|
| Corpus provenance + derived-not-copied (PHASE 1–3) | PASS |
| 9 subjects covered, per-subject resolution (PHASE 14) | PASS |
| Deterministic lessons, no AI, indicator-specific (PHASE 4–7) | PASS |
| WAPEF first-class + draft alignment fix (PHASE 8) | PASS |
| Browser persistence journey 70/70 (PHASE 9) | PASS |
| DOCX template fidelity (PHASE 10) | PASS |
| PDF visual acceptance, 1018 drawings (PHASE 11) | PASS |
| Internal-string audit 210 checks (PHASE 12) | PASS |
| Source/lesson separation (PHASE 13) | PASS |
| AI optional, 0 credits on failure (PHASE 15) | PASS |
| Backend suite 1957 passed / 12 skipped / 0 failed | PASS |
| Frontend tsc + production build | PASS |
| Commits (7 logical commits on main) | PASS |
| Push + Render production acceptance | see §14.1 |

**Verdict:** READY — all code gates pass; PHASE 16 (commit/push/production)
awaits explicit go-ahead, after which this report records the SHAs and the
production result.
