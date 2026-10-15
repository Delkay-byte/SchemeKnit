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