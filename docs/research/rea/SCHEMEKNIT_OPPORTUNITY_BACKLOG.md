# SchemeKnit Opportunity Backlog (REA-Powered Benchmark)

Derived from the REA study (`UX_FLOW_MATRIX.md`, `NETWORK_AND_CLIENT_EVIDENCE.md`,
`LESSON_QUALITY_COMPARISON.md`). **No SchemeKnit source was changed in this session.**
This is an evidence-based plan for a separate implementation session.

**Classification:** A = adopt directly as a principle · B = adapt to SchemeKnit's
architecture · C = investigate further · D = do not adopt.

**Guardrails held constant:** teacher's scheme is authority; source occurrence →
own-week lesson; timetable periods are metadata; deterministic generation must work
AI-OFF; P4 quality gate + bounded deterministic rebuild; Zeli optional; Autopilot
minimises input safely; accepted lessons survive persistence/reload/DOCX-PDF; quotas,
auth, WAPEF, provenance are correctness constraints. No new vector DB / paid model /
orchestration framework is proposed (no evidence any is needed).

---

## Backlog item 1 — Deterministic prose: slot-fill hardening + real topic + timing invariant
**Classification: B (adapt). Priority: 1 (highest).**

- **Teacher problem:** deterministic lessons currently read as slot-fill
  ("…using ;", "…process.."), use a strand-concat topic, and account for only part
  of the lesson duration → **substantive editing**, the largest measured effort.
- **Reference:** SchemeKnit's own artifact (`schemeknit_benchmark_lesson.json`) +
  SHS Planner's clean, time-budgeted prose (`evidence/samples/sample-page-4..6.txt`).
- **Evidence:** `LESSON_QUALITY_COMPARISON.md` §2, §4 — SK scores 1–2 on topic,
  starter, teacher/learner actions, activity detail, timing.
- **Expected effort reduction:** removes the core substantive edit pass; converts
  `SUBSTANTIVE EDIT` toward `MINOR EDIT`.
- **Curriculum-correctness risk:** LOW — no change to binding or provenance.
- **Deterministic-compat:** YES (change is entirely inside the deterministic builder).
- **P4-compat:** YES — strengthens candidates that P4 already prefers.
- **Engineering cost:** M (branch text on empty slots; derive topic from
  indicator+sub-strand or require teacher topic input; assert `Σ phase durations ==
  duration_minutes`).
- **Test strategy:** golden-file fixtures for empty-slot / no-TLR / repeated-indicator
  schemes; a property test asserting the timing invariant and no
  "empty interpolation" artefacts (regex for `;\s*the`, double punctuation).
- **Dependencies:** none.

## Backlog item 2 — Ghanaian localization bank for deterministic mode
**Classification: A (adopt). Priority: 2.**

- **Teacher problem:** deterministic lessons carry no local context, so they feel
  generic and need contextual edits.
- **Reference:** GhanaEd (African-fabric/artisan examples) and SHS Planner
  (GES/GESI) — `LESSON_QUALITY_COMPARISON.md` §3.
- **Evidence:** both real documents weave Ghana-specific framing; SK scores 1 on
  Ghanaian context.
- **Expected effort reduction:** removes most "make it relevant to my class" edits.
- **Correctness risk:** LOW — additive example banks, no curriculum change.
- **Deterministic-compat / P4-compat:** YES.
- **Engineering cost:** S–M (curated, subject/strand-keyed example pools the
  builder may reference; deterministic selection, not AI).
- **Test strategy:** bank coverage test per subject; snapshot test that a chosen
  example is stable for a given (subject, strand, indicator).
- **Dependencies:** item 1 (prose rendering).

## Backlog item 3 — Reach the teachable output format: DoK-leveled assessment, rubric, woven differentiation
**Classification: A (adapt). Priority: 3.**

- **Teacher problem:** SchemeKnit's deterministic assessment is a single generic
  sentence and differentiation is templated; teachers rewrite these for supervision.
- **Reference:** SHS Planner page 7 (DoK 1–3 tasks + 4-band rubric) and pages 2–3
  (MA/HP/NS woven into activity text) — `evidence/samples/`.
- **Evidence:** `LESSON_QUALITY_COMPARISON.md` §2 (SK assessment 3, differentiation 3).
- **Expected effort reduction:** removes the assessment/differentiation rewrite.
- **Correctness risk:** LOW — additive structured fields (already partly present).
- **Deterministic-compat / P4-compat:** YES.
- **Engineering cost:** M (structured assessment object + rubric bands; weave
  differentiation into activity descriptions rather than a labelled block).
- **Test strategy:** schema tests; golden lessons per proficiency mix; P4 checks that
  assessment references the same indicator as the lesson.
- **Dependencies:** item 1.

## Backlog item 4 — Reuse & resilience: per-source caching, resume, honest batch semantics
**Classification: B (adapt). Priority: 4.**

- **Teacher problem:** re-generating or regenerating a previously-produced lesson
  wastes time/quota; a stalled generation should not be a dead end.
- **Reference:** Tenaly per-indicator plan cache ("next teacher gets it instantly —
  no extra tokens"); SHS Planner stream idle-abort (45 s) + `recovery_id` /
  `continue_from` + `refund_batch` / initial+retry-billed-once
  (`NETWORK_AND_CLIENT_EVIDENCE.md` §2).
- **Evidence:** SK already has accepted-only persistence and quota; the gap is
  visible resume/refund/“already generated” signalling outside Autopilot.
- **Expected effort reduction:** MODERATE — removes re-runs and anxious retries.
- **Correctness risk:** MEDIUM — caching must key on the **source occurrence +
  config**, never on text similarity, or it could serve a stale/misaligned lesson.
  Refunds must not break quota accounting.
- **Deterministic-compat / P4-compat:** YES if cache key includes the occurrence id
  and config digest; P4 still runs on new builds.
- **Engineering cost:** M–L.
- **Test strategy:** quota invariants under retry; cache-key collision tests; a
  stalled-job resume test.
- **Dependencies:** none.

## Backlog item 5 — Explicitly assess removing more teacher decisions (safely)
**Classification: B, with C for the parts that need evidence. Priority: 5 (gate item).**

**Question (required by the brief): can SchemeKnit remove more teacher decisions
without sacrificing Autopilot/P4 safety?** Evidence-based answer:

- **Already-safe to remove (do it):**
  - *Re-asking for facts already in the scheme/profile.* SHS Planner's whole design
    is "pick the week, the system knows the rest" (`buildLsnMeta`). SchemeKnit
    already resolves class/subject from the scheme and preserves it
    (`_persist_confirmed_class`), and Autopilot selects occurrences without teacher
    input (`select_autopilot_rows`). **Action:** where a scheme states class/subject
    unambiguously, default the confirmation and only interrupt on genuine ambiguity —
    the code already expresses this as `selection_blockers`; the opportunity is to
    make the non-ambiguous path strictly zero-click from the upload page (the
    `schemeknit.autopilot_intent` handoff already exists in
    `generate/[id]/page.tsx`).
  - *Template defaults.* GhanaEd/SHS Planner default the print template; SK already
    defaults `template_id` to None→deterministic. Low-risk to keep defaulting.
- **Must NOT be auto-decided (keep the interrupt):**
  - WAPEF values (Deep Hope/Storyline/Through lines/God's Story) — `wapef_autopilot_state`
    correctly interrupts when unsaved; **never invent** (matches the "don't fabricate"
    evidence rule). Keeping this is a feature.
  - `needs_review` occurrences — must stay visible, never silently generated.
  - Curriculum-code disambiguation when the scheme is genuinely ambiguous.
- **Uncertain, needs evidence (C):**
  - Auto-selecting a *subset* under free-tier quota. Autopilot already shares quota
    units for repeated indicators; whether to auto-drop vs auto-include borderline
    quota items should be measured against teacher preference.
- **Expected effort reduction:** SMALL-to-MODERATE (removes residual clicks/redirects).
- **Correctness risk:** LOW if limited to the "already-known facts" list above;
  otherwise HIGH.
- **Deterministic-compat / P4-compat:** YES — this is UI/decision-plumbing only.
- **Engineering cost:** S–M.
- **Test strategy:** extend the acceptance matrix so the zero-click path is asserted
  for unambiguous schemes and the WAPEF/needs-review interrupts are asserted to
  still fire.
- **Dependencies:** item 1–3 for the "zero-edit" outcome to be worth the reduced
  friction (a one-click path that still needs substantive editing moves the problem).

---

## Also considered and why NOT top-5 (D / C)

| Idea | Reference | Decision | Why |
|---|---|---|---|
| Pre-loaded national curriculum (no upload) | Scorlar, Tenaly | **D** | Contradicts SchemeKnit's core principle that the teacher's scheme is the authority; would weaken provenance. |
| 11 instructional models as first-class choices | Eduaide | **D** | Adds configuration/decision burden the brief says to avoid; not evidenced as a teacher need here. |
| Diagnostic/ability-grouping subsystems | Classpiler (GALOP) | **C** | Different product surface; out of scope for lesson-authoring quality. |
| "One PDF → whole teaching pack" | StudyPlugHub | **C** | Broad feature; SchemeKnit already has DOCX/PDF export of the lesson; assess later. |
| New vector DB / paid model / orchestration framework | — | **D** | No evidence any capability is missing; deterministic path is sufficient. |

---

## Sequencing

1 → 2 → 3 form the **quality spine** (prose, localisation, assessment) and together
convert the dominant `SUBSTANTIVE EDIT` into `MINOR EDIT`. 4 then removes rework.
5 is the cheap decision-reduction layer that only pays off **after** 1–3.

*Related: ../REA_LESSON_PLANNER_BENCHMARK.md · UX_FLOW_MATRIX.md ·
NETWORK_AND_CLIENT_EVIDENCE.md · LESSON_QUALITY_COMPARISON.md*

---

## Continuing product-quality workstreams — 2026-10-28

The REA audit's release-blocking defects are closed in the working tree (see
`FINAL_ACCEPTANCE_REPORT.md` §10), and the cinematic landing hero is
implemented and locally accepted (§11). **These five priorities remain active.**
Passing the existing suites is necessary but not sufficient: each item below
still needs output-level or field evidence before it can be closed.

| Priority | Current evidence | Next local-first deliverable | Acceptance evidence required |
|---|---|---|---|
| **1 — Lesson quality** | 70/70 frozen-corpus lessons teacher-ready (11/40/19; means 74.0/73.3/72.3); corpus-wide prose regression passes; deterministic builder and quality gate covered | Add real GES Basic/SHS source rows and a teacher-edit sample; inspect topic specificity, phase coherence, timing and sequencing on generated lessons | No hard failures; prose assertions pass; a reviewed sample shows fewer substantive edits and no timing gaps |
| **2 — Ghanaian context** | Early-years localization reaches the real KG/Nursery builder path; 12-profile context bank wired; localization tests pass | Audit localization coverage by subject and level (Nursery/KG through Basic/SHS); check for repetition and age appropriateness in real outputs | A per-level lesson sample uses correct local examples/terminology without displacing the teacher's source |
| **3 — Assessment and differentiation** | DoK/assessment/rubric tests and 4-band export checks pass; assessment fields exist in generated lessons | Audit actual assessment items, rubric bands and MA/HP/NS support across subjects and levels, not just field presence | Reviewed outputs show aligned DoK, usable marking guidance and differentiated support that a teacher can act on |
| **4 - Reliability** | True same-job resume; PostgreSQL advisory lock; quota atomicity; cache-key/idempotency; **5 true two-process PostgreSQL tests** (same-scheme 409, different schemes, killed-worker lock release, cross-process resume, retry idempotency); heartbeat-backed stale policy with deterministic boundaries; post-commit recovery tests; LibreOffice DOCX->PDF fidelity with no empty/truncated pages | Stage a live multi-worker uvicorn run and a post-commit drill in that deployment; add cache-hit/observability assertions | No duplicate lessons or charges across independent OS processes; crashed-worker lock release and resume; post-commit response truthful; converter output complete and ordered |
| **5 — Less teacher effort** | Autopilot browser journey 39/39; one-action path, blockers and quota messaging verified; ambiguous schemes interrupt only when required | Measure residual decisions on clean vs ambiguous schemes; keep improving quota-limited/blocked/resumable reporting | Browser journey shows zero unnecessary prompts, accurate generated/already/pending/blocked counts, and no false success |

The current local release slice includes the landing hero and the reliability/export hardening recorded in `FINAL_ACCEPTANCE_REPORT.md` section 13. Priorities 1-5 remain active and are not relabelled complete.

---

## Completion status (mission pass, 2026-10-16)

All five backlog items are now closed with pinned tests. Evidence:

| Item | Change | Evidence |
|---|---|---|
| 1 — prose/timing | Already shipped in prior passes (slot-fill, real topic, duration invariant). | Frozen corpora 11/40/19 still 100% first-pass, timing_integrity 5.0. |
| 2 — Ghana bank | `GHANA_CONTEXT_BY_SUBJECT` expanded to all 12 pedagogy profiles × 3 examples; `ghana_context_for(subject, variant)` normalises spaces/aliases and rotates deterministically; wired as the fallback `context_hint` for activities that carry no task-specific framing (`lesson_builder.py`). | `tests/test_ghana_context_bank.py` (10 tests: coverage, resolution, stability, builder wiring). |
| 3 — rubric/differentiation | Rubric is now 4-band ("4 — exceeds" / "3 — meets" / "2 — developing" / "1 — needs support"), 4 points per criterion. Differentiation uses GES labels Needs Support (NS) / High Performing (HP) / More Able (MA), and a compact `(NS: …; MA: …)` cue is woven into the last practice learner activity. AI enrichment path labels updated to match. | `test_phase3_assessment_dok.py` (28 pass; total_points 16 for the create-category rubric); `test_differentiation_uses_ma_hp_ns_and_is_woven` in `test_generation_quality_v3.py`. |
| 4 — cache/double-submit | `ai_enrichment_cache.indicator_hash` now populated (sha256 of lesson+section+input+provider). Read path: regenerate-section / enrich-lesson return the cached generation for an identical input or a replayed `request_id` (`already_generated: true`) without a second provider call or quota consumption. `/generate` 409s while a scheme job is in flight; generate response and scheme/status report `already_generated_occurrence_ids`. | `tests/test_ai_cache_double_submit.py` (6 tests). |
| 5 — zero-click | Confirm-subject hands to autopilot (`/generate/{id}` with intent flag); server-side needs_review gate on `/generate` rejects uncertain occurrences with 409. | `test_autopilot_generation.py::test_generate_rejects_needs_review_occurrence_server_side`; `test_autopilot_ui_source.py::test_confirm_path_also_hands_to_autopilot`. |

Regression gate at closure: frozen corpora 11/40/19 = 100% first-pass / 100%
teacher-ready (mean rubric 74.2 / 73.3 / 72.3 of 75); P4 + quality-gate suites
131 passed; quota/entitlement suites 123 passed (4 PG-only skipped).

---

## Zeli generation method — 2026-10-29 (local-only evidence)

The product now offers a **second, user-selectable generation method** alongside
the existing Standard path. Nothing below closes priorities 1–5; it adds a
provider-authored path whose output still has to pass the same quality gate.

| What changed | Evidence |
|---|---|
| Zeli is a first-class `GenerationMethod` (`standard` \| `zeli`) persisted on the job/lesson, independent of the enrichment `AI Mode` (OFF/BASIC/ENHANCED). | `test_zeli_generation_method.py` (48 tests); browser journey asserts both buttons, `aria-pressed` persistence, and that Standard still offers OFF/BASIC/ENHANCED. |
| Zeli's verified runtime provider is the existing Groq integration: provider `groq`, model `openai/gpt-oss-120b`, base `https://api.groq.com/openai/v1`. No new SDK/endpoint/model was invented. | Real provider probe in the isolated environment: `available: True`, `last_error: None`, `validate_zeli_content → OK`; persisted lessons carry `ai_provider=groq`, `ai_model=openai/gpt-oss-120b`. |
| Credentials stay server-side. `ZELI_*` settings fall back to `GROQ_*`; the status endpoint returns booleans/reason text only. | Settings/availability tests; teacher-surface audit in the journey (`groq`, `gpt-oss`, `openai/gpt`, `api key`, `rate_limit` absent from the page). |
| Zeli does whole-lesson V2 generation, strict validation, structural timeline normalisation, then the **unchanged** quality gate. Output failing the gate is dropped and not replaced by deterministic content. | `test_zeli_generation_method.py`; `_run_quality_gate(..., allow_rebuild=False)`; real-Groq gate detail: **5/5 accepted**, mean 69.4, hard/soft rejections `{}` (post-fix). Pre-fix 1/5 evidence is preserved separately. |
| Quota, credits, cache, retries and resume stay intact. Zeli consumes one existing AI credit per successful job (job-id idempotent); lesson quota remains per accepted indicator code. The cache key includes method, provider, model, prompt version and every material input. | Zeli cache/credit/quota tests; isolated DB job `completed`, 5/5 lessons, 0 failed, `generation_method=zeli` on every row; `zeli_generation_cache` populated. |
| Teacher-facing failures map to truthful codes (429/503/504/502) and never silent-fallback. | Failure-classification tests; result copy distinguishes Zeli, Standard and no-content runs. |

**Local verifications:** typecheck clean; production build succeeded; whole-lesson
browser journey **24/24**; real-Groq diagnostic **5/5 accepted**; isolated DB
shows all five lessons persisted with Zeli provenance. Full-suite and targeted
backend results are recorded in `FINAL_ACCEPTANCE_REPORT.md` section 14.

**Limitations:** Groq is the only verified Zeli provider; no live staging or
production deployment was exercised; real-model quality varies by lesson and
the gate remains the authority; Zeli is one whole-scheme job, not per-lesson
retry UI beyond the existing resume/retry contract.
## Guided configuration and professional lesson output — 2026-10-29 (local-only evidence)

One coordinated round against the Basic 9 Science GES-format regression fixture.
None of the five product-quality priorities is closed by this; it advances
**lesson quality (1)**, **reduced teacher effort (5)** and **reliability (4)**.

| What changed | Priority | Evidence |
|---|---|---|
| Guided configuration: the seven plan-wide lesson fields (school, teacher, class size, reference, duration, periods, teaching days) are set in ONE "Configure lesson rubrics" modal after extraction and before generation; saved per plan; server-validated with readiness reporting; the UI blocks generation while required fields are unsaved. | 5 (teacher effort) | `test_guided_lesson_configuration.py` (7 passed); browser journey `e2e/lesson-config-acceptance.js` 9/9. |
| No invented data: fabricated class-size defaults (24/11) removed everywhere; blank stays blank; generation 409s on missing required configuration. | 4 | `test_guided_lesson_configuration.py::test_generate_without_required_configuration_is_refused`. |
| Week sequence: the parser no longer merges two weekly sections whose label repeats — the fixture's "Week 1, 2, 2, 3, 4" class of defect is split and renumbered to a gapless sequence; real multi-strand weeks preserved. | 1 / 4 | `test_week_and_header_regression.py` (18 passed) + Basic 7/Basic 9 real-document non-regression. |
| Professional output: drafting artefacts removed at source ("What to look for:", "Quick check (unprompted):", mid-dot step labels, raw woven NS:/MA: markers, "…" truncations); deterministic text-hygiene layer + quality-gate hard failures shared by deterministic AND Zeli output; header = School / Teacher / Week 1 first page, week-only after; DATE/DAY row shows teaching days, never dates. | 1 | Real-pipeline export inspection: every fixture artefact string absent, week sequence 1..12 monotonic; `test_week_and_header_regression.py`. |
| Reliability preserved: quota, cache identity (Zeli cache key carries class size/duration/period), idempotency, resume (original snapshot kept), WAPEF contracts untouched. | 4 | Full backend suite + WAPEF acceptance tests green after the changes. |

**Local verifications:** backend suite (final counts in
`FINAL_ACCEPTANCE_REPORT.md` §15.4), frontend typecheck + production build,
browser journey 9/9, real-pipeline DOCX content inspection.

**Limitations:** local-only (no deploy); the recovered fixture copy was
shallow so the week-defect test reconstructs the documented failure rather
than parsing the original 23-page file; indicator wording itself is preserved
verbatim where it reads awkwardly (source authority).
