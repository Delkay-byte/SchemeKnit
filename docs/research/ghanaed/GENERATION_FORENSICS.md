# GhanaEd.com — Generation Forensics (Forensic Study)

Study date: 2026-10-05/06 · Method: two real UI generations on our own research
account (strict budget: 20 free credits → 2 plans at 10 credits each), captured
request/response (`_netlog_experiment1/2.json`, `_exp1_*`, `_exp2_*`), plans
saved as `ghanaed_plan_A.json` / `ghanaed_plan_B.json`, screenshots
`screenshots/exp1-*.png`, `exp2-*.png`.

**Confidence labels:** CONFIRMED (captured) · OBSERVED (UI) · STRONGLY INFERRED
(bundle code) · POSSIBLE-UNCONFIRMED.

---

## 1. Input contract (CONFIRMED)

`POST /api/lesson-planner/generate` (payload annotated in NETWORK_MAP §5).
Key observations from both experiments:

- **Server-side curriculum resolution**: empty `strand/subStrand/
  contentStandard/indicators` fields are accepted; the server resolves them
  from `subject + level + className` (Gen A: B7 → CS `B7.1.1…`, `indicators:[]`).
- **Topic does not drive resolution**: Gen B sent `topic` = the B9.1.3.1.1
  indicator text, but with a mis-picked cascade (`strand:"1 DESIGN"`, empty
  sub-strand/CS) the server resolved **`B9.1.1.1`** content standard instead —
  indicators/CS are driven by the strand/CS pickers + subject/class, NOT by the
  topic text (CONFIRMED by the response).
- Cost gating: `10 credits × day-plans` (bundle constant) — matches balance
  20→10→0 across the two runs (CONFIRMED).

## 2. Output contract (CONFIRMED)

`{lessonPlan}` = full `type:"lplan"` document (schema:
DATA_MODEL_RECONSTRUCTION §2). Both plans:

- pedagogy skeleton: `phase1/2/3` fixed **10/30/10 = 50 minutes** matching
  `duration:"50 minutes"`; every phase has teacher/learner step rows with
  minute-level times + a pre-rendered `activities` string;
- fixed planner fields: `performanceIndicator`, `rpk`, `coreCompetencies`
  (3 NaCCA), `keywords`, `homework`, `teacherNotes`, `differentiation`
  (support/core/challenge), phase3 `qa[]`+`summaryPoints`+`realLife`
  (Ghana-context line), `warmupScript`;
- default `printTemplateId:"jhs-daily"`, `status:"draft"`, `dayLabel:"Monday"`.

Generation latency: single request completes synchronously within the
Playwright action window (OBSERVED; exact ms not instrumented — POSSIBLE-
UNCONFIRMED). Background path (`jobs`) and `generate-series` (SSE) exist but
were **not exercised** (credit-limited).

## 3. Quality: what the prose actually is (CONFIRMED — plan files)

**Gen A (B7, empty curriculum fields, plan `…muxagnbf`)** —
objectives concrete ("Identify the steps in the creative process…"),
activities specific (word game warm-up, "African fabric design" brainstorm,
group roles speaker/writer/checker/reporter), Ghanaian real-life line
("In Ghana, many artisans…"), differentiation, teacher notes operational.
Defects: `indicators:[]` (nothing to align to), `references` generic
("NaCCA / GES curriculum for Creative Arts and Design, JHS 1"),
`weekEndingDate:""`, `classSize:0`, `schemeId:""`.

**Gen B (B9, topic = B9.1.3.1.1, plan `…muxajvco`)** —
rich prose (kingfisher/Shinkansen biomimicry example, palm-tree architecture),
objectives carry code suffixes **of the wrong indicators** (B9.1.1.1.1/.2),
`plan.indicators[]` contain **raw NaCCA PDF OCR/page artefacts** (see §4),
`references` = literal placeholder, `performanceIndicator`/PI mismatch vs topic,
exemplar text corrupted. Still: phase timings valid, differentiation valid,
homework/notes present.

**Both**: no scheme linkage (`schemeId:""`), metadata blanks (§1), teacher/
school/year correctly stamped.

## 4. PDF-ingestion defect (CONFIRMED — the signature finding)

Gen B `plan.indicators[0]` verbatim fragment:

```
"B9.1.1.1.1. and its importance and role as a medium for creative expression …
 Communication and Collaboration (CC), Critical Thinking … Exemplar CC9.1: …
 CP5.1: … CI5.5: … DL6.1: …"
```
`exemplars[2].text` ends with:
```
"… Source: Pinterest.com Beak of kingfisher bird inspired Shinkansen Bullet
 Train – Japan … Colourful bird -- 45 of 136 -- 3© NaCCA, Ministry of
 Education 2021 CONTENT STANDARD INDICATORS AND EXEMPLARS CORE COMPETENCIES"
```
→ The server **extracts indicator/exemplar text from the NaCCA PDF itself**
(`pdfUrl` fields in the curriculum store, ARCHITECTURE §3) and the extractor
**does not trim page furniture**: page numbers ("45 of 136"), copyright lines,
column headers, cross-referenced exemplar tables and even third-party source
credits bleed into teacher-facing fields. Indicator sentences start mid-clause
(`"B9.1.1.1.1. and its importance…"`) — left-truncation at line/row boundaries.
(STRONGLY INFERRED mechanism — the artefact text matches PDF layout text;
the corrupted output itself is CONFIRMED.)

## 5. Consistency defects summary (CONFIRMED)

| Defect | Evidence |
|---|---|
| Topic ↔ resolved curriculum mismatch (B9 topic, B9.1.1.1 content) | `ghanaed_plan_B.json` objectives/CS vs `topic` |
| PDF page furniture in `indicators[]`/`exemplars[]` | `ghanaed_plan_B.json` |
| Placeholder `references` | Gen B |
| Empty `indicators[]`, generic references | Gen A |
| `weekEndingDate:""`, `classSize:0`, `period:""` | both |
| `schemeId:""` (no lineage) | both |
| Sub-strand picker duplicate options; parent-change keeps stale CS | `_exp2_after-*.json`, UX_FLOW §3 |
| Planner taxonomy ≠ raw curriculum taxonomy | DATA_MODEL §3 |

## 6. Credit-limited scope (CONFIRMED — declared per brief)

Budget: 20 free credits, 10/plan → **exactly 2 generations**. Not run (and not
bypassed): 3× same-input repeat, ≥5-subject field study, multi-day
`generate-series`/bulk (would cost ≥50 credits), second benchmark
(B9.1.3.1.2), AI-upsell paths, ad-reward credits
(`ads/status` observed at 0, never exercised), any payment.
Findings are therefore **single-run per configuration**; prose-quality claims
are `n=2` (OBSERVED, not statistically generalised — POSSIBLE-UNCONFIRMED for
run-to-run variance).

## 7. Benchmark indicators (CONFIRMED — probe `ghanaed_benchmark_probe.json`)

```
B9.1.3.1    "Apply the creative process to manage design projects."
B9.1.3.1.1  "Plan and execute design projects using the creative process."
B9.1.3.1.2  "Evaluate and report on design projects."
(subject subject:jhs:creative-arts-and-design; strand "Basic 9 – DESIGN";
 substrand "CREATIVE AND DESIGN PROCESSES")
```
Used as the common benchmark input for SCHEMEKNIT_COMPARISON.md (GhanaEd Gen B
attempted this indicator via topic; SchemeKnit generated it natively —
`../ghanaed/schemeknit_benchmark_lesson.json`).

*Related: UX_FLOW.md · NETWORK_MAP.md · ARCHITECTURE_RECONSTRUCTION.md ·
DATA_MODEL_RECONSTRUCTION.md · SCHEMEKNIT_COMPARISON.md ·
../GHANAED_FORENSIC_ANALYSIS.md*
