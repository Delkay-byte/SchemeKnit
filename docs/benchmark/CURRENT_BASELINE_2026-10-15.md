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
