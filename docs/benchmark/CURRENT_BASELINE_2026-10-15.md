# Current-Code Baseline — SchemeKnit Lesson Quality (2026-10-15)

**Code state:** HEAD `3ef1a41` → Phase 0 (doc-only) → Phase 1 verb correction
`c9412b0` → this report. AI **OFF**, Zeli **OFF** throughout. Deterministic
GenerationPipeline + canonical 15-criterion rubric + P4 gate, one shared
implementation (`src/curriculum/lesson_rubric.py`).

**Why this report exists:** the REA research
(`docs/research/rea/LESSON_QUALITY_COMPARISON.md`) scored a historical
SchemeKnit artifact at **40/75** with strand-concat topic, slot-fill prose and
32/50-minute phase timing. That artifact
(`docs/research/ghanaed/schemeknit_benchmark_lesson.json`) **predates P2/P2.1**
and is preserved unmodified as historical research. This report establishes the
**current** baseline; the historical numbers must not be quoted as current.

## 1. Frozen corpora — current results (thresholds unchanged)

Corpora are the frozen fixtures from the P2/P2.1 calibrations (rerun; fixture
sets untouched; the Phase 1 verb correction is the only scoring-relevant code
delta, recorded in `phase1_verb_correction.md`).

| Corpus | Lessons | Teacher-ready | Rate | Mean canonical rubric | Hard failures | Rebuilds |
|---|---|---|---|---|---|---|
| 11-lesson core | 11 | 11 | 100% | 74.0/75 | 0 | 0 |
| 40-lesson expanded (12 subjects) | 40 | 40 | 100% | 72.7/75 | 0 | 0 |
| 19-lesson messy (verbatim real docx rows) | 19 | 19 | 100% | 71.1/75 | 0 | 0 |

- **P4 rejection categories:** zero across all 70 current runs (the 14 prior
  `generic_objective` hard failures were exactly the Phase 1 false positives —
  see `phase1_verb_correction.md`; no weak-objective rejection was removed:
  the negative tests in `test_phase1_measurable_verbs.py` still reject them).
- **Activity specificity:** expanded 4.21, messy 4.21 (weakest criteria; see §3).
- **Resource realism:** expanded 4.47, messy 4.47.
- **Assessment alignment** 5.0 · **subject-pedagogy fit** 4.47/4.21 ·
  **Ghanaian context** 4.63/4.63 · **timing integrity** 5.0 (all corpora).
- Raw evidence: `current_core11_2026-10-15.json`,
  `current_hardening_2026-10-15.json` (frozen `after.json` /
  `hardening_after.json` are the pre-correction P4 calibration baselines and
  stay unchanged).

## 2. Current-code REA criterion comparison (B9.1.3.1.1 Creative Arts)

Same analyst criteria and 1–5 scale as REA §2, same indicator and inputs
(code, strand, content standard, 50 min, scheme TLRs) — inputs COMPARABLE —
regenerated on current code (`phase2_reproduction_b9_creative_arts.json`,
produced by `backend/tests/phase2_repro_b9_creative_arts.py`):

| # | Criterion | SHS Planner sample | Historical SchemeKnit | **Current SchemeKnit** | Basis (current) |
|---|---|---|---|---|---|
| 1 | Curriculum fidelity | 5 | 5 | **5** | exact binding B9.1.3.1.1/standard/strand; provenance kept |
| 2 | Objective quality | 5 | 3 | **4** | verb-led objective w/ indicator wording; single objective, no sub-goals |
| 3 | Topic specificity | 5 | 1 | **4** | topic derived from the indicator (no strand concat) |
| 4 | Starter/engagement | 5 | 2 | **4** | predict-the-next-step hook + "what to look for" |
| 5 | Teacher actions | 5 | 2 | **4** | model/think-aloud, circulate + on-spot correction, lead critique |
| 6 | Learner actions | 5 | 2 | **4** | recall keyword, examine sample, create, display/critique, exit answer |
| 7 | Activity detail | 5 | 2 | **3** | phases concrete but SHARE AND CRITIQUE reuses creation phrasing |
| 8 | Learning progression (DoK) | 5 | 2 | **3** | recognise→apply→justify arc, single assessment mode; DoK levelling is Phase 3 work |
| 9 | Assessment alignment | 5 | 3 | **4** | indicator-tied success criteria + exit check; rubric axes still generic |
| 10 | Resource realism | 5 | 5 | **5** | locally available materials only |
| 11 | Differentiation | 5 | 3 | **4** | Support/Core/Challenge concrete + grouping |
| 12 | Classroom feasibility | 5 | 3 | **4** | grouping given; timings realistic |
| 13 | Ghanaian context | 4 | 1 | **4** | home/market/community situation, local materials |
| 14 | Duration & timing | 5 | 2 | **5** | Σ phase minutes = 50 exactly |
| 15 | Formatting/completeness | 5 | 4 | **4** | minor punctuation residue ("process.."), keywords contaminated with TLR names |
| | **Total /75** | 72 | 40 | **61** | |
| | **Edit burden** | NO/MINOR | SUBSTANTIVE | **MINOR** | |

Canonical (P4) scoring of the same current lesson: **74/75, teacher-ready,
0 hard failures**.

**Honest remaining gaps (do NOT round up):** double-period punctuation
(`process..`) in the introduction; SHARE AND CRITIQUE activity text reuses
creation phrasing; a single assessment mode (no DoK spread); generic rubric
axes; keyword list bleeds TLR names. These are the Phase 3–4 targets — scored
as-is, not aspirationally.

## 3. Correlation of REA methodology to canonical rubric

The REA analyst scale and the canonical rubric measure different things
(REA: visible prose teachability; canonical: curriculum integrity + floors).
Current state: strong canonical fidelity (74/75) with REA prose quality
(61/75) dominated by activity detail, DoK levelling and formatting residue —
exactly the backlog items in Phase 3 (DoK + analytic rubric) and Phase 4
(differentiation depth, resource realism).

## 4. Benchmark integrity reconciliation (2026-10-15 execution pass)

Question raised: the P2.1-era calibration recorded **31/40 expanded** and
**12/19 messy**, while this report records **40/40** and **19/19**. Both are
correct — they measure the same corpora under the same harness at two code
states. Evidence:

- **Same fixtures:** the indicator-code sequence in
  `hardening_after.json` (pre-correction) and
  `current_hardening_2026-10-15.json` (post-correction) is identical for
  both corpora (verified pairwise, 40/40 and 19/19).
- **Same harness:** `git diff ae84f19..HEAD -- benchmark_hardening.py
  benchmark_deterministic_lessons.py gate_metrics.py` is **empty** — the
  scoring harness is byte-identical across both runs.
- **Same readiness definition:** `lesson_rubric.teacher_ready` is unchanged
  (no hard failures + floors: timing 5, objective_specificity ≥ 4, topic ≥ 3,
  phase usefulness ≥ 3, assessment ≥ 3, resources ≥ 3).
- **Only rubric delta = the Phase 1 correction:** the sole scoring-relevant
  diff between `ae84f19` and `c9412b0` is `lesson_rubric.py` (±30/29 lines,
  verb-inventory rewiring). No threshold, floor or fixture was touched.
- **Per-lesson attribution (expanded):** the 9 pre-correction not-ready
  lessons were 7 × `generic_objective` hard failure + **2 with zero hard
  failures** (`B6.1.1.1.1`, `B6.1.3.3.1`) that failed the
  `objective_specificity ≥ 4` floor (scored 2). All 9 had verb-led official
  indicators misread by the stale substring inventory. Post-correction every
  one scores `objective_specificity = 5` and clears both the hard failure
  and the floor. Messy corpus: all 7 not-ready lessons were
  `generic_objective` with `objective_specificity = 2`, same mechanism.
- **Honest per-criterion movement:** not every criterion moved up — e.g.
  `B6.1.1.1.1` subject-pedagogy 5→2 and Ghana-context 5→3 post-correction
  while clearing readiness. The deltas reflect regenerated lesson text under
  the corrected objective builder, not threshold tuning.

**Conclusion:** the jump 31/40 → 40/40 and 12/19 → 19/19 is fully
attributable to the documented Phase 1 false-positive correction, executed
under identical fixtures, harness and thresholds. The pre-correction
numbers remain the valid baseline for the pre-correction code state; the
current numbers are the valid baseline for current code. Both are reported
without adjustment.
