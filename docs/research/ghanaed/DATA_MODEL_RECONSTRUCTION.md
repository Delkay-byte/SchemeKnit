# GhanaEd.com — Data Model Reconstruction (Forensic Study)

Study date: 2026-10-05/06 · Evidence: signup/auth responses
(`_netlog_register.json`), saved plans (`ghanaed_plan_A.json`,
`ghanaed_plan_B.json`), curriculum tree dump (temp `ghanaed_curriculum_tree.json`
+ summary `_curriculum_summary.json`), zero-credit probe (`_zero_credit_probe.json`).

**Confidence labels:** CONFIRMED (field present in captured payload/response) ·
OBSERVED (UI-level) · STRONGLY INFERRED (bundle) · POSSIBLE-UNCONFIRMED.

---

## 1. Account / user (CONFIRMED — signup 201 body + `/api/auth/me`)

```
user { id:"user:<school-slug>:<username>", name, username, role:"teacher",
       schoolId:<slug>, isHeadTeacher, accountActive, credits:20,
       onboardingCompleted, gamePoints, referralCode, region?, district?, level? }
token: JWT (bearer; redacted — never reproduced in evidence)
```
- School profile recorded at signup: `schoolName, region, district, level`
  (level enum `basic_kg_jhs|kg|primary|jhs|shs|private|office|grade-based|other`).
- Promo state separate: `GET /api/subscription/promo`
  `{promoId:"back-to-school", endsAt:"2026-11-11", …}` (CONFIRMED).
- Credit state: `GET /api/subscription/status {credits, accountActive,…}`;
  ads state `{adsEnabled, rewardsRemainingToday, pointsPerAd}` (CONFIRMED at 0).

## 2. Lesson plan document `type:"lplan"` (CONFIRMED — full captures)

Envelope:

```
_id: "lplan:user:<school>:<username>:<rand>"   type:"lplan"
userId, schoolId, schemeId, sourceHub
subject, level ("JHS"), className ("B7"/"B9"), term (1), week (1)
duration ("50 minutes"), status ("draft")
plan { … }                       ← pedagogical body (below)
teachingMethods[], dayLabel ("Monday"), weekEndingDate, classSize,
teacherName, schoolName, academicYear ("2026/2027"),
bulkJobId, exemplarContinuation, printTemplateId ("jhs-daily"|"primary-ges"),
period, createdAt, updatedAt (ISO)
```

`plan` body (both experiments):

| Field | Shape | Notes |
|---|---|---|
| `topic` | string | free-text lesson topic |
| `objectives` | string[] | AI-authored; may embed curriculum codes |
| `strand`, `subStrand`, `contentStandard` | string | **server-resolved** when picker empty |
| `indicators` | string[] | raw indicator text; **corrupted in Gen B** (§5) |
| `performanceIndicator` | string | derived PI statement |
| `rpk` | string | previous knowledge |
| `coreCompetencies` | string[] | NaCCA core competencies |
| `keywords`, `references`, `teachingMethods` | string[]/string | `references` placeholder in Gen B |
| `phase1/2/3` | object | fixed 10/30/10 = 50 min; each has `steps[]`
|  |  | `{time, teacher, learner, resourceUse, formative, n, exemplarN?}`, `resources`, `assessment`, pre-rendered `activities` string; phase1 adds `piShare`, `warmupType`, `warmupScript`; phase2 adds `coreConcept`, `differentiation{support,core,challenge}`, `tables`, `imageNeeds`, `misconceptions`; phase3 adds `qa[]`, `summaryPoints`, `realLife`, `feedbackPrompt` |
| `homework`, `teacherNotes`, `safetyNotes` | string | |
| `exemplars` | `[{n, text, visual}]` | exemplar text = curriculum PDF excerpt (Gen B corrupted) |
| `exemplarContinuation` | bool | |

`printTemplateId` implies server-side printable templates (`jhs-daily`,
`primary-ges`) — template assets seen as `/lesson-plan-templates/*.jpg` in bundle
(STRONGLY INFERRED).

## 3. Curriculum document store (CONFIRMED — tree dump)

CouchDB-style records, one per node:

```
{ _id:"subject:jhs:creative-arts-and-design", type:"subject", name, level:"jhs",
  strands:[strand-id,…], _rev, pdfUrl:"https://www.nacca.gov.gh/…" }
{ _id:"strand:…", name, substrands:[…] } { _id:"substrand:…", standards:[…] }
{ _id:"cs:…", code, description, indicators:[…] }
{ _id:"indicator:…", code:"B9.1.3.1.1", description }
```

Observed tree sizes (`_curriculum_summary.json`):

| Level/subject | strands | substrands | standards | indicators |
|---|---|---|---|---|
| jhs:Arabic | 12 | 25 | 25 | 38 |
| jhs:Ghanaian Language | 15 | 57 | 57 | 75 |
| upper-primary:Computing | 15 | 44 | 44 | 206 |
| lower-primary:Creative Arts | 6 | 24 | 42 | 124 |
| kg:Kindergarten | 12 | 36 | 36 | 144 |

Benchmark codes (CONFIRMED): `B9.1.3.1` (CS), `B9.1.3.1.1`, `B9.1.3.1.2`
(indicators), subject `subject:jhs:creative-arts-and-design`, strand
"Basic 9 – DESIGN", substrand "CREATIVE AND DESIGN PROCESSES"
(temp `ghanaed_benchmark_probe.json`).

**Second, planner-only taxonomy**: `/api/lesson-planner/curriculum` returns
numbered strands (`1 DESIGN`) with duplicate substrand options (OBSERVED) —
schema not byte-identical to the raw store (STRONGLY INFERRED: planner
aggregates/flattens differently, and numbered labels come from the planner layer).

## 4. Scheme-of-work context (STRONGLY INFERRED)

`generate` accepts `schemeId` (empty string in both experiments — no scheme
uploaded), planner has "Schemes of Work" tab + upload; scheme docs feed weeks/
strands into the planner. Schema of stored schemes NOT captured
(POSSIBLE-UNCONFIRMED).

## 5. Known data-quality defects in stored documents (CONFIRMED — evidence files)

- `weekEndingDate: ""`, `classSize: 0`, `period: ""`, `indicators: []`
  (Gen A) — server does not backfill these metadata fields.
- Gen B `plan.indicators[]` contain **raw PDF page artefacts**
  ("… -- 45 of 136 -- 3© NaCCA, Ministry of Education 2021 CONTENT STANDARD
  INDICATORS AND EXEMPLARS …", exemplar bleeding CC/CP/CI/DL exemplar lines and
  page footers) — parser bug in server-side extraction (GENERATION_FORENSICS §4).
- Gen B `references` = literal placeholder
  "NaCCA / GES curriculum title for this subject and class".
- Both plans: `schemeId: ""`, `sourceHub: ""` — no lineage link to a source
  scheme document when generated ad-hoc.

## 6. Credit/store entities (STRONGLY INFERRED — bundle)

`credits packs {credits, amountPesewas, label}`; school plans
`{maxStudents, creditsPerTerm, termlyPesewas, yearlyPesewas}`;
admin `grant credits`, `credit-promo`; usage logs
`/api/school/credits/usage`. Enum `lesson_plans`, `termly_exams`,
`schemes`, `lesson_notes` appear as report/portal section keys.

*Related: UX_FLOW.md · NETWORK_MAP.md · ARCHITECTURE_RECONSTRUCTION.md ·
GENERATION_FORENSICS.md · SCHEMEKNIT_COMPARISON.md ·
../GHANAED_FORENSIC_ANALYSIS.md*
