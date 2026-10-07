# Deterministic Lesson Authoring (Priority 2)

Status: complete — forensic audit (Part 1), architecture (Part 2), the fixes
(Part 3), benchmark before/after (Part 4), known limits (Part 5) and the
verification record (Part 6).

All generation described here is **DETERMINISTIC: AI OFF / Zeli OFF**.
Zeli (Groq) remains an optional enrichment layer that may polish a stored
lesson; it is never required for a lesson to be complete and teachable.

---

## Part 1 — Forensic audit: root-cause map

Complete deterministic path traced:

```
SOURCE OCCURRENCE (allocation_engine, Priority 1 semantics)
→ curriculum evidence (exemplars corpus keyed by (subject, code); indicator_interpreter)
→ objective (_learner_phrase)
→ topic (_derive_topic)
→ pattern selection (batch_context.select_pattern_for_alloc + variation.BatchHistory)
→ Phase 1 (STARTER_MODE_TEMPLATES / _STARTER_BANK / profile.starter_template)
→ Phase 2 (_compose_main_phases: _PHASE_BANK ∥ subject profile main_phases ∥ exemplar patterns)
→ Phase 3 (PLENARY_MODE_TEMPLATES / _PLENARY_BANK / profile.plenary_template)
→ assessment (_ASSESSMENT_BANK / profile.assessment_template)
→ assignment (_CLASS_ASSIGNMENT_BANK / _HOME_ASSIGNMENT_BANK / exemplar patterns)
→ resources (scheme TLRs + interpreter suggestions + _ACTIVITY_RESOURCES + exemplar patterns)
→ references (teacher-entered only — honest empty default ✓)
→ export (docx_export / official_ges_template / pdf via DOCX conversion)
```

### Root causes of weak output (with evidence)

| # | Root cause | Where | Evidence |
|---|---|---|---|
| RC1 | **Timing invariant violated by construction.** `starter_min`/`plenary_min` are computed (`lesson_builder.py:1623-1624`) but never attached to any activity row; only main-phase rows carry minutes, so stored steps sum to `duration − starter − plenary` (32 of 50 min). The `max(duration − starter − plenary, len(phase_specs))` guard can also overshoot for tiny durations. Quality gate only warns above 1.2×. | `lesson_builder.py` | Benchmark: `incomplete_timing` on 11/11 lessons; rubric timing mean 2.0 |
| RC2 | **Topic = strand + sub-strand concatenation.** `_derive_topic` joins `strand - sub_strand` for every source-stated indicator — explicitly rejected taxonomy-label output, not a teachable topic. | `lesson_builder.py:_derive_topic` | Benchmark: topic_specificity = 2.0 on all 11 |
| RC3 | **Empty `{resource}` placeholder never filled.** `fmt["resource"] = ""` with comment "filled per-phase below" — never filled. Learner-bank templates contain `using {resource}` → artifacts `using .` / `using ,` in generated prose. | `lesson_builder.py:1606`, `_LEARNER_PHASE_BANK` | 3/11 lessons hard-fail `filler_text` + `generic_activity` |
| RC4 | **No structured activity-evidence layer.** Phase prose comes from parallel sentence banks selected by activity key; there is no record that binds teacher action, learner action, expected evidence, materials, and timing for a chosen activity. Teacher/learner columns fall back to keyword-guessed generic moves (`_teacher_move`/`_learner_task`: "Watch and listen carefully…", "Take an active part…") that can drift from the main prose. All `TeachingActivity.resources` rows are `[]` — resources are never linked to the activity that needs them. | `lesson_builder.py` banks + `_teacher_move`/`_learner_task` | Rubric: teacher_action_clarity 3.09, learner_action_clarity 3.55, activity_specificity 3.36 |
| RC5 | **Objective voice is indicator-verbatim but fallbacks are generic.** `Learners can <indicator>` preserves verbs when the indicator is verb-initial (fidelity mean 5.0), but indicatorless rows fall back to "explore and talk about {sub_strand}" (Basic) — a banned filler — and non-verb-initial indicators are never restructured into a measurable performance. | `lesson_builder.py:_learner_phrase`, objective construction | Tests + benchmark generic-objective pattern |
| RC6 | **Assessment keyed to activity type, not the indicator verb.** `_ASSESSMENT_BANK[act_key]` is a good activity-level check but does not guarantee the indicator's own action (distinguish/calculate/…) is what is assessed. | `lesson_builder.py` | Rubric: assessment_alignment mean 4.64, verb match not guaranteed |
| RC7 | **Differentiation is two generic lines** (Support/Extension + Grouping); no structured **core** tier and no challenge tied to the evidence of this indicator. | `lesson_builder.py` differentiation | Spec §14 |
| RC8 | **No Ghanaian context strategy.** Context appears only where a bank sentence happens to mention market/community/Ghana; no structured, subject-apt context selection; nothing guarantees context relevance or its deliberate absence. | scattered in banks | Rubric: ghana_context mean 3.64 (neutral) |
| RC9 | **No pedagogical progression for repeated indicators.** Week-2 occurrence of the same indicator differs only through pattern novelty rotation; `BatchHistory` fingerprints carry no indicator identity, so the engine cannot know "this indicator was already taught" and cannot shift emphasis from guided recognition to independent application. | `variation.py:fingerprint_lesson`, `build_lesson` | Priority 2 spec §18 |
| RC10 | **Subject pedagogy exists but is shallow as data.** `SubjectPedagogy` has starter/main/assessment templates and moves, but no structured starter-type list, misconception bank, suitable-activity list or evidence types — so pattern/starter selection cannot reason about subject fit beyond templates. | `pedagogy.py` | Spec §6 |
| RC11 | **Content-standard intent not consumed.** Content standard flows through to the lesson record (available ✓) but never influences objective/activity selection — it is metadata only. | `build_lesson` | Audit |

### What is already good (preserve — "improve rather than replace")

- Pattern framework (15 patterns, starter/plenary modes, novelty rotation) — concrete, curriculum-grounded.
- Exemplar corpus records (16 real NaCCA indicators) with provenance — rich when attached.
- Honest-empty references; scheme TLRs first; no fabricated citations.
- Teacher/learner/main parallel columns with equal counts; per-subject profiles exist for 11 profiles incl. Computing (`ict`).
- Priority 1 source-occurrence semantics (untouched).

### Benchmark BEFORE (recorded)

`backend/tests/benchmark_deterministic_lessons.py` → `docs/benchmark/before.json`

- 11 lessons, 10 real indicators + 1 repeated occurrence, 6 subjects
  (Mathematics, Science, English, Computing, Creative Arts, Social Studies),
  AI OFF / Zeli OFF, real `GenerationPipeline`.
- **Teacher-ready: 0/11 (0%); mean rubric 56.1/75.** (Measured by running the
  *final* rubric on the baseline worktree at `fee98d9`, so the two JSON files
  are directly comparable — same rubric, same corpus, different generator.)
- Hard failures: `incomplete_timing` 11/11, `filler_text` 3/11,
  `generic_activity` 3/11.
- Lowest criteria: timing 2.0, topic 2.0, teachability 2.82, teacher_action
  3.09, activity_specificity 3.36.

---

## Part 2 — Architecture: how a deterministic lesson is composed

Composition principle (unchanged by this work, now actually enforced):

```
SELECT TEACHING INTENT → ACTIVITY → LEARNER ACTION → EVIDENCE → RESOURCE
→ TIME → RENDER PROSE
```

Structured data decides everything; prose is written last from the structure.
No giant prompt, no new external dependency, no vector store.

| Layer | What it decides | Where |
|---|---|---|
| Intent | primary verb, Bloom level, activity type, evidence of achievement, assessment mode, misconceptions | `curriculum/indicator_interpreter.py`, `curriculum/lesson_evidence.py`, exemplar corpus |
| Activity | which activity object (materials, support/challenge, evidence sentence) the lesson performs | `curriculum/activity_library.py::select_activity` (subject-fit `SUBJECT_ACTIVITY_PREFERENCE`, `activity_type_matches`) |
| Pattern | starter mode, phase shape, plenary mode, novelty rotation, repeat-occurrence emphasis | `curriculum/patterns.py`, `variation.py` (`BatchHistory` fingerprints carry the indicator code) |
| Banks | phase sentences keyed by activity key + subject profile (`_PHASE_BANK`, `_LEARNER_PHASE_BANK`, `_STARTER_BANK`, `_PLENARY_BANK`, assessment/assignment banks) | `lesson_builder.py` |
| Evidence | the observable check for EVERY step (first row, each middle step, final step) and for Phase 3 | `lesson_builder.py` step evidence + `_EVIDENCE_CUE` guards |
| Resources | scheme TLR → interpreter suggestions → activity materials → profile base; every `TeachingActivity.resources` row carries what that step needs | `lesson_builder.py` |
| Time | `starter_min` + every row's minutes + `plenary_min` == `duration_minutes`, exactly | `lesson_builder.py` |
| Render | prose cells print a row only in its OWN phase; grids with a Duration column keep all rows | `official_ges_template.py`, `wapef_template.py`, `docx_export.py`, `structured_pdf.py` |

**The timing invariant (RC1).** The stored timeline contains two *boundary*
rows — `PHASE 1 · STARTER` and `PHASE 3 · PLENARY` — that carry the starter's
and the plenary's own minutes. `sum(row.duration_minutes) == duration_minutes`
by construction, which the parallel-length tests
(`test_batch_variation_benchmark.py`, `test_lesson_quality_remediation.py`)
and `test_generation_quality_v3.py:154` enforce. The boundary rows stay in
storage (they are the timeline); each renderer decides where they belong.

**The one-sentence-one-place rule.** A boundary row's prose *is* the
introduction/starter and the conclusion, which the Phase 1 and Phase 3 prose
cells already carry. Therefore:

- prose cells (GES Phase 1/Phase 3 cells, WAPEF `_phase_block`, the DOCX
  `_activity_block` prose form) print rows only in their own phase;
- grids that carry a Duration column (the standard DOCX/PDF activity grid,
  WAPEF timing) print every row, because the minutes only make sense there;
- `quality_gate._lesson_text` and `benchmark.lesson_body` skip rows that
  verbatim-mirror `introduction` / `starter_activity` / `conclusion`, so the
  boilerplate/context checks measure what a teacher reads;
- `official_ges_template.dedupe_lines` removes any line that repeats inside
  one rendered cell.

Storage is never rewritten to achieve this — exports filter, the workspace
shows Phase 2 only (`isBoundaryPhase`), and the save payload keeps every row.

**Shared quality vocabulary.** The builder and the benchmark agree on three
cue regexes by construction (`_EVIDENCE_CUE`, `_CLOSURE_CUE`,
`_LOCAL_CONTEXT_CUE` in `lesson_builder.py`, documented as "the benchmark
scores the same words"). The generator composes, then *repairs* with explicit
guards — each one appended only when the composed text lacks it:

| Guard | Fires when | Appends |
|---|---|---|
| Exit check | Phase 3 has no evidence cue | `Exit check: … the teacher marks each answer…` |
| Recap | Phase 3 has no closure cue | `Recap: each learner states in one sentence…` |
| Lived experience | the lesson names no place word other than the bare adjective `local` | `Set it in a situation from the learners' home, the nearby market or their local community.` (on the class assignment) |
| Assessment success | the assessment carries no evidence cue | `Success = <interpreter's success sentence>` |
| Verb check | the assessment lacks the indicator's own verb | `activity_library.assessment_for_verb(...)` |

**Role model for teacher/learner columns (RC4).** `_phase_role(phase_name)`
classifies a step as `play / open / input / guided / independent / share /
reflect / other`, and `_TEACHER_MOVES` / `_LEARNER_TASKS` hold an *ordered*
sentence bank per role. The phase loop keeps a per-role occurrence counter, so
the second guided step gets the second guided sentence — never the same
sentence twice in one lesson, and never a generic "Facilitate the activity" /
"Take an active part" fallback.

**Frontend.** Phase 1 now shows two fields — the framing sentence
(`introduction`, `aria-label="Phase 1 starter"`, unchanged selector so the
persistence journey keeps passing) and the starter activity itself
(`starter_activity`, `aria-label="Phase 1 starter activity"`); Phase 2 lists
only non-boundary rows while the draft (and the save payload) keeps them, and
Add/Move operate on stored indices.

---

## Part 3 — The fixes, against the root-cause map

| RC | Fix | Where |
|---|---|---|
| RC1 timing | Boundary rows carry starter/plenary minutes; `sum == duration_minutes` hard assertion | `lesson_builder.py`, `test_generation_quality_v3.py` |
| RC2 topic | Topic derived from the indicator's own content (`_derive_topic` → indicator/strand text), not `strand - sub_strand` concatenation | `lesson_builder.py` |
| RC3 placeholder | `_resource_pool` (scheme → activity → profile) fills `{resource}` before any template is formatted; `_safe_format` never leaves `using .` | `lesson_builder.py` fmt construction |
| RC4 activity layer | `activity_library.select_activity` binds materials/evidence/support/challenge to the chosen activity; per-row resources; role banks replace generic teacher/learner moves | `activity_library.py`, `lesson_builder.py` |
| RC5 objective | Leading-verb Bloom detection (first verb in text order) + focus-aware performance clause; objective keeps the capitalized `Learners can <Verb>` shape pinned by `test_final_web_ux.py` | `indicator_interpreter.py`, `lesson_builder.py` |
| RC6 assessment | Verb-matched check appended when missing, plus the success-cue guard; `quality_gate` no longer counts mirrored prose as boilerplate | `lesson_builder.py`, `quality_gate.py` |
| RC7 differentiation | Support/Core/Challenge/Grouping where Core states this activity's evidence sentence | `lesson_builder.py` |
| RC8 Ghana context | `_LOCAL_CONTEXT_CUE` guard + context-aware bank sentences (`_GHANA_CONTEXT_RE` counted by the benchmark) | `lesson_builder.py` |
| RC9 repeats | `BatchHistory` fingerprints carry `indicator_code`; repeat occurrences keep content but shift to application (`stage="repeat"`) | `variation.py`, `lesson_builder.py` |
| RC10 subject pedagogy | `SUBJECT_ACTIVITY_PREFERENCE` + `_SUBJECT_DEFAULT_ACTIVITY` + `bank_key` so subject fit is data, not a template coincidence | `indicator_interpreter.py`, `lesson_builder.py` |
| RC11 content standard | Content standard feeds `_derive_topic`, evidence and templates as text (never as a code-only placeholder) | `lesson_builder.py` |

Rendering/export fixes that follow from RC1's boundary rows: shared row helpers
(`activity_rows`, `phase_items`, `row_in_phase`, `dedupe_lines`) in
`official_ges_template.py`; GES Phase 1 = introduction + starter (deduped), GES
MAIN = Phase-2 rows only; WAPEF `_phase_block(1|2|3)` renders only its own
phase and reads whole descriptions (no comma-splitting); DOCX `_activity_block`
mirrors the same rule.

---

## Part 4 — Benchmark AFTER

`backend/tests/benchmark_deterministic_lessons.py` → `docs/benchmark/after.json`
(same rubric, same corpus; `before.json` regenerated with this exact script on
the baseline worktree at `fee98d9`).

| | BEFORE (`fee98d9`) | AFTER |
|---|---|---|
| Teacher-ready | **0/11 (0%)** | **11/11 (100%)** |
| Mean rubric | **56.1/75** | **73.7/75** |
| Hard failures | `incomplete_timing` 11, `generic_activity` 3, `filler_text` 3 | none |

| Criterion | Before | After | Change |
|---|---|---|---|
| indicator_fidelity | 5.0 | 5.0 | +0.00 |
| objective_specificity | 5.0 | 5.0 | +0.00 |
| topic_specificity | 2.0 | 5.0 | +3.00 |
| phase1_usefulness | 3.82 | 5.0 | +1.18 |
| phase2_usefulness | 4.82 | 5.0 | +0.18 |
| phase3_usefulness | 3.73 | 5.0 | +1.27 |
| activity_specificity | 3.36 | 4.64 | +1.28 |
| teacher_action_clarity | 3.09 | 5.0 | +1.91 |
| learner_action_clarity | 3.55 | 5.0 | +1.45 |
| assessment_alignment | 4.82 | 5.0 | +0.18 |
| resource_realism | 4.09 | 4.55 | +0.46 |
| timing_integrity | 2.0 | 5.0 | +3.00 |
| subject_pedagogy_fit | 4.36 | 4.82 | +0.46 |
| ghana_context | 3.64 | 4.73 | +1.09 |
| teachability | 2.82 | 5.0 | +2.18 |

Reproduce:

```bash
cd backend
./venv/Scripts/python tests/benchmark_deterministic_lessons.py --out ../docs/benchmark/after.json
```

---

## Part 5 — Known limits (honest)

- `activity_specificity` (4.64) and `resource_realism` (4.55) are the two
  weakest criteria: a few phase rows still read as instructions without an
  explicit grouping/quantity marker, and a resource list only scores top marks
  when a resource word also appears in the step text. Both are content
  improvements in the banks, not architecture gaps.
- `subject_pedagogy_fit` (4.82) and `ghana_context` (4.73) are capped by two
  lessons; the context guard adds exactly one place-based sentence, never more.
- The rubric is heuristic (regex + keyword overlap) and is deliberately NOT
  tuned to the generator's vocabulary: `_TEACHER_VERBS`, `_MONITOR_RE`,
  `_EVIDENCE_RE`, `_CLOSURE_RE`, `_GHANA_CONTEXT_RE`, `_FILLER_PATTERNS` and
  `_COMMON_RESOURCES` were left as written; where the rubric under-measured,
  the generator was changed instead. One genuine rubric parsing bug was fixed:
  `first_indicator_verb` stripped everything up to the first capital, so
  "Demonstrate how to use the Start screen..." lost its own verb — it now
  strips only a leading GES code (`B7.1.1.1.1 `).
- Reference lists stay empty unless the teacher enters them (honest default).
- GES and WAPEF are two documents of the same lesson: a line repeated across
  the two is expected, a line repeated inside one document is not — measured
  per document by `export_inspect.py`.

---

## Part 6 — Verification record

| Gate | Result |
|---|---|
| Full backend suite | `pytest tests -q -p no:randomly -m "not live"` -> **2161 passed, 11 skipped, 0 failed** |
| Deterministic benchmark (AI OFF, Zeli OFF) | **11/11 teacher-ready, 73.7/75**, no hard failures (`docs/benchmark/after.json`) |
| Baseline comparison | same script on `fee98d9` -> **0/11, 56.1/75** (`docs/benchmark/before.json`) |
| Export inspection (GES + WAPEF, Mathematics and Science) | Phase 1/2/3 cells carry their own rows only; **no duplicate line inside either document**; WAPEF bullets keep full sentences (no comma fragmentation) |
| Browser journey (real app, AI OFF) | `frontend/e2e/lesson-persistence-journey.js` -> **70/70** — sign-up, upload, generate, edit Phase 1/2/3 + assignments, save, reload, `/lessons/{id}`, DOCX + PDF |
| Curriculum workspace acceptance | `npm run e2e:workspace` -> **75/75** (desktop + mobile, GES template, DOCX/PDF) |
| Frontend typecheck | `npx tsc --noEmit` -> clean |
| Frontend build | `npm run build` -> clean |

Commands:

```bash
cd backend
./venv/Scripts/python -m pytest tests -q -p no:randomly -m "not live"
./venv/Scripts/python tests/benchmark_deterministic_lessons.py --out ../docs/benchmark/after.json

cd ../frontend
npx tsc --noEmit && npm run build
node e2e/lesson-persistence-journey.js     # backend :8000 + `npm start` :3000
npm run e2e:workspace
```

---

## Part 7 — Priority 2.1 hardening pass (after this document)

Priority 2.1 was one focused hardening pass over the engine this document
describes — no architecture change, no AI, no Zeli. It executed the A–L
re-audit, expanded the activity/resource/subject banks, made verb/intent,
progression and variation handling deterministic but subject-sensitive, froze
and re-ran two NEW corpora (a 40-lesson expanded corpus and a 19-lesson messy
corpus built from real district/GES documents) before/after every edit, and
verified locally AND against the deployed production app.

Headline (full tables, change list, honest gaps and both verification records
in `docs/DETERMINISTIC_LESSON_HARDENING_REPORT.md`):

| Corpus (AI OFF, Zeli OFF) | Teacher-ready before | after | Hard failures before | after |
|---|---|---|---|---|
| Expanded — 40 lessons, 12 subjects | 23/40 (57.5%) | **31/40 (77.5%)** | generic_objective 14, generic_activity 1, filler_text 1 | generic_objective 7 only |
| Messy — 19 lessons, 9 subjects (verbatim district rows) | 9/19 (47.4%) | **12/19 (63.2%)** | generic_objective 7, duplicate_phases 1 | generic_objective 7 only |
| Priority 2 rubric corpus (frozen) | 11/11 @ 73.7 | **11/11 @ 73.7 (unchanged)** | none | none |

The remaining `generic_objective` failures are a MEASUREMENT gap in the
frozen rubric's `_MEASURABLE_VERBS` inventory (its verbatim text keeps verbs
like *add, multiply, install, indicate, assess, relate, recognise, skip count*
and French leads out), not generic generator prose — classified lesson by
lesson in the hardening report, with the recommended Priority 3 fix.

New coverage: `backend/tests/test_priority21_hardening.py` (73 tests) pins the
library scale/selection, verb-matched assessment, PHE/history/early-childhood
strategies, objective cleanup (including the real-scheme verb-lead regression
cases fixed in `a38e35c` — "Listen to…"/"Simplify…"/"REVISION…" cells from
`backend/real_documents/`), resource realism, the 30–80 minute timing
invariant and the repeat-stage progression. Full suite: **2234 passed**.

Production caveat: the deployed Render build predates Priority 2 and is not
auto-deployed from `main` (owner-side redeploy required, no deploy hook in
this environment) — the hardening report's §5b records the deployed-build
verification (workspace 75/75, persistence 68/70 with the two stale-build
WAPEF checks) and the deploy marker that re-checks our code for free once a
redeploy lands.
