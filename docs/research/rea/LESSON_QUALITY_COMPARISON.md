# REA Lesson Quality Comparison — Observed Outputs vs SchemeKnit

Study date: 2026-10-14/15 · Basis: only **real, first-party-observable** lesson
documents — SHS Planner's published 8-page sample, GhanaEd's two generated plans
from the earlier session, and SchemeKnit's own deterministic benchmark lesson
(`docs/research/ghanaed/schemeknit_benchmark_lesson.json`).

**Confidence labels:** `CONFIRMED` (document inspected) · `OBSERVED` ·
`STRONGLY INFERRED` · `UNKNOWN`.

**Edit-burden scale:** `NO EDIT` usable as produced · `MINOR EDIT` wording/punctuation
· `SUBSTANTIVE EDIT` objective/activity/resource/assessment/timing/alignment/phase.

---

## 1. Common benchmark

Requested common indicator for the study:
`B9.1.3.1.1` "Distinguish between creativity and innovation and their application
for developing design solutions to problems in society."

**Availability of that exact indicator:**

| Product | Could accept B9.1.3.1.1? | Comparable input used |
|---|---|---|
| SchemeKnit | ✅ native (own scheme upload) | exact `B9.1.3.1.1` (its NaCCA tree) |
| GhanaEd | ✅ (JHS Creative Arts & Design) | exact topic `B9.1.3.1.1` (trade note: earlier session; vendor CS tree used `B9.1.3.1` = "Apply the creative process to manage design projects.") |
| SHS Planner | ❌ SHS only (Year 1–2, 56 subjects) | **non-identical**: General Science, Year 1, Week 11 |
| Tenaly | ⚠️ KG–JHS incl. Creative Arts per marketing | login required → `UNKNOWN` |
| Scorlar / Classpiler | ⚠️ claim JHS coverage | login required → `UNKNOWN` |
| StudyPlugHub | ⚠️ PDF-driven | login required → `UNKNOWN` |

**Important definitional note (`CONFIRMED`, discrepancy):** the benchmark string
given for this study (`B9.1.3.1.1` = "Distinguish between creativity and
innovation…") does not match the NaCCA text captured in the earlier GhanaEd
curriculum dump (`B9.1.3.1.1` = "Plan and execute design projects using the
creative process"). They are the same code under **different curriculum revisions**
(or a differently-transcribed indicator). We preserve this as a finding: **indicator
meaning is revision-sensitive**, which is exactly the fidelity risk a lesson tool
must manage. SchemeKnit's benchmark lesson used the code from its own tree and the
teacher's scheme; GhanaEd's Gen B mis-bound the code (see §4).

---

## 2. Scoring table (1–5, 5 = no edit; only inspected documents)

| # | Criterion | SHS Planner (sample) | GhanaEd Gen A | GhanaEd Gen B | SchemeKnit (det.) |
|---|---|---|---|---|---|
| 1 | Curriculum fidelity | 5 | 2 | 1 | 5 |
| 2 | Objective quality | 5 | 4 | 3 | 3 |
| 3 | Topic specificity | 5 | 3 | 3 | 1 |
| 4 | Starter/engagement specificity | 5 | 4 | 4 | 2 |
| 5 | Teacher actions | 5 | 4 | 4 | 2 |
| 6 | Learner actions | 5 | 4 | 4 | 2 |
| 7 | Activity detail | 5 | 4 | 4 | 2 |
| 8 | Learning progression (DoK) | 5 | 3 | 3 | 2 |
| 9 | Assessment alignment | 5 | 4 | 4 | 3 |
| 10 | Resource realism | 5 | 3 | 3 | 5 |
| 11 | Differentiation | 5 | 4 | 4 | 3 |
| 12 | Classroom feasibility | 5 | 4 | 4 | 3 |
| 13 | Ghanaian context | 4 | 4 | 4 | 1 |
| 14 | Duration & timing | 5 | 5 | 5 | 2 |
| 15 | Formatting/completeness | 5 | 5 | 5 | 4 |
| | **Total /75** | **72** | **55** | **45** | **40** |
| | **Edit burden** | **NO/MINOR** | MINOR–SUBSTANTIVE | SUBSTANTIVE | **SUBSTANTIVE** |

SHS Planner is scored against **non-identical** input (SHS Science, not the JHS
benchmark) → its row is indicative of *technique*, not a code-for-code match.
SchemeKnit scored **deterministic AI-OFF** (its default). GhanaEd scored from the
earlier human-read plan files.

---

## 3. What makes SHS Planner's output teachable (`CONFIRMED`)

1. **Week-indexed curriculum header** — teacher picks the week; the tool already
   knows strand/sub-strand/content-standard/indicators (`buildLsnMeta`). Zero
   curriculum typing.
2. **DoK-leveled assessment** with a full 4-band rubric and an explicit summative
   task (`evidence/samples/sample-page-7.txt`).
3. **Differentiation woven into the activity text** (MA/HP/NS) instead of labelled
   blocks — the vendor's own guide states this as the design rule
   (`sample-page-2/3.txt`).
4. **Time-budgeted activities** (10/15/10/20/5/5 min) summing to the lesson length.
5. **GESI + safeguarding** (mixed-gender roles, respectful-classroom agreement)
   built into the engagement step.
6. **Resilient delivery** — streamed generation with idle-abort + auto-recovery +
   batch refunds (`NETWORK_AND_CLIENT_EVIDENCE.md` §2): the teacher is not left
   with a hung spinner on a poor connection.

These are **technique** observations (not code); they are the strongest "borrow"
candidates for SchemeKnit (see backlog).

---

## 4. Confirmed defects worth not copying (`CONFIRMED`)

| Product | Defect | Evidence |
|---|---|---|
| GhanaEd Gen B | Raw NaCCA **PDF page furniture** ("45 of 136 -- 3© NaCCA… CONTENT STANDARD INDICATORS AND EXEMPLARS") inside `indicators[]`/`exemplars[]` | `docs/research/ghanaed/ghanaed_plan_B.json` |
| GhanaEd Gen B | Topic `B9.1.3.1.1` but resolved Content Standard `B9.1.1.1` (topic ignored) | same |
| GhanaEd Gen B | Literal placeholder reference "NaCCA / GES curriculum title for this subject and class" | same |
| GhanaEd Gen A | `indicators:[]`, `weekEndingDate:""`, `classSize:0` | `ghanaed_plan_A.json` |
| SchemeKnit det. | Slot-fill prose artefacts ("…using ;", "…process.."), strand-concat topic, 32/50 min accounted | `schemeknit_benchmark_lesson.json` |

The contrast is the study's core finding: **SHS Planner and GhanaEd optimise the
visible, teachable prose (and GhanaEd pays with hidden curriculum corruption);
SchemeKnit optimises curriculum integrity (and pays with visible, robotic prose).**

---

## 5. Variation study

The brief asks for ≥3 comparable generations to test variation. **Credit/access
limits prevented this**: GhanaEd's account was at 0 credits (prior session), and
Tenaly/Scorlar/Classpiler/StudyPlugHub/MagicSchool/Eduaide/Brisk generation sits
behind logins we did not create. SHS Planner publishes a single sample. Therefore:

- **Meaningful-variation claim: `UNKNOWN`** for every product except where two
  GhanaEd plans exist (A and B differ by class/pickers, not by identical input).
- No claim is made about private prompts, seeds, retrieval indexes or caching
  except where the vendor states it publicly (Tenaly's per-indicator cache —
  `CONFIRMED` marketing claim, `UNKNOWN` behaviour).

This limitation is recorded honestly rather than papered over.

---

## 6. SchemeKnit reproducible baseline used

From `docs/research/ghanaed/schemeknit_benchmark_lesson.json` (deterministic, AI OFF):
exact `B9.1.3.1.1`, complete provenance (`curriculum_source:"Teacher scheme"`,
`generation:"Curriculum-first (deterministic)"`), `week_ending` derived from the
scheme row, TLRs carried from the scheme — but strand-concat topic, slot-fill prose,
and incomplete phase timing. This is the honest current state the backlog targets.

---

## 7. CURRENT-CODE COMPARISON (2026-10-15) — do not confuse with the historical scores above

The SchemeKnit artifact scored in §2 is a **historical, P1/P2-era**
deterministic output (preserved unmodified as
`docs/research/ghanaed/schemeknit_benchmark_lesson.json`). It predates the
P2/P2.1 deterministic hardening and P4 quality gate, so its 40/75 must NOT be
quoted as the current state. On 2026-10-15 the SAME inputs (Basic 9 Creative
Arts & Design · `B9.1.3.1.1`
"Plan and execute design projects using the creative process" · strand
DESIGN · 50 minutes · the scheme's own TLRs · AI OFF, Zeli OFF) were
regenerated on the CURRENT engine and re-scored with the same 15 criteria:

| Score row | Historical (§2) | **Current code** |
|---|---|---|
| Total /75 (REA analyst criteria) | 40 | **61** |
| Edit burden | SUBSTANTIVE | **MINOR** |
| Canonical P4 rubric (same lesson) | not in use then | 74/75, teacher-ready, 0 hard failures |

Defect reproduction checks on current code (`docs/benchmark/`
`phase2_reproduction_b9_creative_arts.json`, produced by
`backend/tests/phase2_repro_b9_creative_arts.py`):

- strand-concat topic — **no longer reproduces** (topic = the indicator);
- slot-fill artefacts ("…using ;", "…process.." residues are limited to a
  double-period in the introduction — honest residue recorded);
- incomplete phase timing (32/50) — **no longer reproduces** (50/50 exact).

Full current analysis, the fresh frozen-corpus baseline and the honest
remaining gaps (activity detail, DoK levelling, formatting residue):
`docs/benchmark/CURRENT_BASELINE_2026-10-15.md`.

*Related: ../REA_LESSON_PLANNER_BENCHMARK.md · UX_FLOW_MATRIX.md ·
NETWORK_AND_CLIENT_EVIDENCE.md · SCHEMEKNIT_OPPORTUNITY_BACKLOG.md*