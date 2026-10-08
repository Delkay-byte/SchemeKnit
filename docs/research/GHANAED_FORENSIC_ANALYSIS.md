# GhanaEd.com — Forensic Analysis (Master Report)

**Study:** Forensic reverse-engineering of https://ghanaed.com for the
SchemeKnit project · **Dates:** 2026-10-05/06 · **Status:** analysis-only; no
SchemeKnit source changes; no commits · **Sub-reports:** `ghanaed/UX_FLOW.md`,
`ghanaed/NETWORK_MAP.md`, `ghanaed/ARCHITECTURE_RECONSTRUCTION.md`,
`ghanaed/DATA_MODEL_RECONSTRUCTION.md`, `ghanaed/GENERATION_FORENSICS.md`,
`ghanaed/SCHEMEKNIT_COMPARISON.md`.

**Confidence labels used throughout:**
`CONFIRMED` — directly observed in captured API responses/DOM/artifacts ·
`OBSERVED` — behaviour seen live in automation ·
`STRONGLY INFERRED` — derived from client-bundle code/constants, cross-checked ·
`POSSIBLE-UNCONFIRMED` — plausible, explicitly not verified.

**Scope & boundaries honored (CONFIRMED by construction):** one own research
account created via the normal registration flow (fictional school/persona);
no auth bypass, no other users' data, no payment/credit bypass, no brute force,
no crawling of robots-disallowed paths outside normal logged-in use, no
exploitation of the ad-reward path, bearer tokens never published (redacted in
all reports; raw session files live only in the analysis session's temp dir).

---

## The 15 executive questions

### Q1. What is GhanaEd.com?
A Ghanaian K–12 **teacher/classroom workspace**: daily lesson planning,
schemes of work, assessments/quizzes, assignments, progress tracking, study
notes portal, self-tutor/BECE/WASSCE prep, Akua AI chat, school admin tools,
and a credits-based AI economy — sold to individual teachers and schools.
`CONFIRMED` (routes + bundle copy + live pages).

### Q2. Who is the onboarding for and what does a new user get?
Teacher/Student roles; 3-step wizard (school: org+region+district+level →
role ± coupon → account). Signup returns a JWT and **20 free credits**,
`onboardingCompleted:false` → guided tour. `CONFIRMED` (`_netlog_register.json`).

### Q3. What is the core value loop?
Pick cascade (level→class→subject→term→strand→sub-strand→CS→indicator) +
week + topic → **Generate (10 credits/day-plan)** → complete `lplan` document →
review/edit → print template (`jhs-daily`/`primary-ges`) → submit. Background
jobs and multi-day SSE series exist for bulk. `CONFIRMED`.

### Q4. How does registration/onboarding actually behave?
See `ghanaed/UX_FLOW.md` §1: wizard screens captured step-by-step; district is
a searchable autocomplete; tour blocks UI until `PATCH /api/auth/onboarding`;
promo banner driven by `GET /api/subscription/promo`. `CONFIRMED/OBSERVED`.

### Q5. What is the client architecture?
Single React SPA with route-level code splitting (hashed chunks; planner chunk
`LessonPlannerPage-BlGcjwpV.js`), history routing, desktop + `/m /mt /ma`
mobile shells, SSE for series runs. `CONFIRMED` (`_chunk_map.json`, captured
bundles).

### Q6. What is the API surface?
REST under `/api/*`, bearer JWT; groups: `auth`, `curriculum`,
`lesson-planner` (generate/generate-series/jobs/plans), `subscription`/`ads`,
`assignments`, `lessons`, `school`, `admin`, payments (pesewas), plus
scheme-analyzer/BECE tools. Full table: `ghanaed/NETWORK_MAP.md` §2–6.
`CONFIRMED` for captured endpoints, `STRONGLY INFERRED` for bundle-only ones.

### Q7. How is curriculum data modelled?
A document store of NaCCA curriculum nodes with CouchDB-style envelopes —
`_id` like `subject:jhs:…`, `strand:…`, `substrand:…`, `cs:…`, `indicator:…`,
each carrying `pdfUrl` to nacca.gov.gh PDFs; five-level hierarchy dumped
(5 subjects, 400+ indicators). A *second*, planner-numbered taxonomy
(`1 DESIGN`) is served by `/api/lesson-planner/curriculum`.
`CONFIRMED` (dump + summary `_curriculum_summary.json`).

### Q8. How is a lesson plan modelled?
Envelope `type:"lplan"`, `_id:lplan:<user>:<rand>`, metadata (subject/level/
class/term/week/duration/status/day/weekEnding/classSize/teacher/school/year/
printTemplateId/…) + `plan{topic, objectives, strand, subStrand,
contentStandard, indicators, performanceIndicator, rpk, coreCompetencies,
keywords, references, phase1/2/3 with step rows, homework, teacherNotes,
differentiation, exemplars…}`. Full schema + quirks:
`ghanaed/DATA_MODEL_RECONSTRUCTION.md` §2. `CONFIRMED`.

### Q9. What is the generation contract?
Input: form context + curriculum selections + week/topic/metadata (payload
annotated in NETWORK_MAP §5). Server behaviour: **accepts empty curriculum
fields and resolves them itself**; resolution is driven by picker state +
subject/class, **not by topic text**; cost debited synchronously
(10 × day-plans). Output: one complete `lplan` document, `status:"draft"`.
`CONFIRMED` (two full request/response captures).

### Q10. What output quality does generation achieve?
Strong pedagogy: fixed 10/30/10 GES daily skeleton with minute-level steps,
pre-rendered `activities`, warm-up scripts, QA pairs, differentiation,
homework, teacher notes, Ghanaian localization examples — largely non-empty
from minimal input. Benchmark scores: G-A 55/75, G-B 45/75
(`ghanaed/SCHEMEKNIT_COMPARISON.md`). `CONFIRMED/OBSERVED` (n=2).

### Q11. What defects did GhanaEd's generation show?
`CONFIRMED` (evidence in both plan files + GENERATION_FORENSICS §4–5):
topic/curriculum misalignment (G-B); **raw NaCCA PDF page furniture inside
`indicators[]`/`exemplars[]`** ("45 of 136", © NaCCA footer, cross-column
bleed); literal placeholder `references`; `weekEndingDate:""`, `classSize:0`;
`schemeId:""` lineage; duplicate substrand options; stale selection after
parent-picker change; dual taxonomy mismatch. `POSSIBLE-UNCONFIRMED`:
run-to-run prose variance (no repeats within the credit budget).

### Q12. What is the credit/economics model?
20 free credits; per-operation costs (generate 10, quiz 3, tutor 1, …);
packs GHS5→0.04/credit volume tiers (50–3,000 credit consumer packs;
school term packs GHS130–2,400 = 4k–120k credits); 2× promo
(`back-to-school`, API `endsAt` 2026-11-11 vs marketing copy "until 31 December
2026" — mismatch `OBSERVED`); admin/school grant endpoints; ad-reward valve
(5/day × 5 points) at zero. `CONFIRMED`/`STRONGLY INFERRED` per
NETWORK_MAP §6.

### Q13. What happens at 0 credits?
`accountActive` flips false → **402 `credits_required` on all data endpoints**
(planner, curriculum, assignments, lessons) while auth/subscription/ads stay
200; planner UI hard-redirects to `/subscribe`; ads reward path activates
(not exercised). `CONFIRMED` (`_zero_credit_probe.json`, zero-credit routes).

### Q14. Why do GhanaEd teachers need little editing while SchemeKnit has struggled?
`CONFIRMED` (this study's central answer, detailed in
`ghanaed/SCHEMEKNIT_COMPARISON.md` §2–3):
1. GhanaEd's server **completes every prose field** from a topic +
   forgiving cascade — output is print-ready GES-format prose with Ghanaian
   examples and pre-rendered activities; visible quality is high.
2. Its remaining defects are **metadata/alignment fields teachers rarely
   check** (codes, references, blanks) — quality is skin-deep but sufficient
   for submission (`POSSIBLE-UNCONFIRMED` on teacher checking behaviour).
3. SchemeKnit's deterministic builder produces **perfect curriculum wiring
   + provenance but robotic prose, timing gaps (32/50 min), strand-concat
   topics and no localization** — the teacher edits what GhanaEd auto-fills,
   while GhanaEd's corruption is what SchemeKnit would never emit.
4. Entry friction differs: GhanaEd generates ad-hoc in 3 clicks; SchemeKnit
   requires scheme upload → detection → quota-aware selection first
   (`OBSERVED` both flows).

### Q15. What should SchemeKnit do?
Ranked recommendations with confidence labels:
`ghanaed/SCHEMEKNIT_COMPARISON.md` §4 — top items: keep strict curriculum
binding (CONFIRMED differentiator); graceful slot-fill + punctuation
normalization (CONFIRMED defect); enforce phase-duration invariant (CONFIRMED);
real lesson-topic derivation (CONFIRMED); Ghanaian localization pack for
deterministic mode (STRONGLY INFERRED as GhanaEd's edge); GES print template
with pre-rendered activities (STRONGLY INFERRED); reference resolution
(CONFIRMED defect both sides); AI as prose enricher over the deterministic
spine with provenance kept (STRONGLY INFERRED architecture to emulate);
keep quota/preview transparency (CONFIRMED strength).

---

## Method summary
Playwright automation (own account) → route/DOM/network captures; manual
bundle acquisition + constant extraction; live API probes (auth, curriculum
cascade, generation ×2 within the 20-credit budget, zero-credit boundary);
SchemeKnit-side benchmark on the same indicator (local FastAPI + synthetic
B9 Creative Arts scheme docx → upload → detection → preview → generate →
lesson + provenance).

## Evidence inventory
- **In-repo (`docs/research/ghanaed/`)** — plans: `ghanaed_plan_A.json`,
  `ghanaed_plan_B.json`, `schemeknit_benchmark_lesson.json`,
  `schemeknit_benchmark_provenance.json`; logs: `_netlog_*.json` (6),
  `_zero_credit_probe.json`, `_chunk_map.json`, `_curriculum_summary.json`,
  `_dom_nav_probe.json`; route/UI/step snapshots `_route_*.json` (15),
  `_ui_*.json` (11), `_step_*.json` (10), `_debug_*.json` (2),
  `_register_state.json`; screenshots: 39 PNGs (registration, experiments,
  routes, zero-credit states).
- **Session temp (not committed, cited in reports)** — captured bundles
  (`index.js`, `vendor-react.js`, `vendor-icons.js`, `LessonPlannerPage.js`,
  `SchoolCreditsPage-*.js`), `ghanaed_curriculum_tree.json` (638 KB full dump),
  `ghanaed_benchmark_probe.json`, experiment step snapshots `_exp1_*`/`_exp2_*`
  (36), automation scripts (`register*.js`, `explore*.js`, `experiment*.js`,
  `probe*.js`, `sk_*.py`), research session/token files (sensitive — never
  copied into the repo), `sk_b9_creative_arts_scheme.docx`.

## Limitations
- Credit budget (20) → exactly **2 GhanaEd generations**; no repeats, no
  multi-subject study, no bulk/series run — all bypasses deliberately refused
  (GENERATION_FORENSICS §6).
- SchemeKnit benchmark ran **AI OFF**; AI-mode parity untested
  (POSSIBLE-UNCONFIRMED).
- Server internals (worker model, DB engine, payment provider) remain
  inference-level where noted.
- One geography/classroom persona; no real-teacher interviews
  (behaviour claims labelled accordingly).

## Relationship to the paused remediation work
This session made **no code changes**; the 37-part LESSON-QUALITY REMEDIATION
remains paused exactly where it was (Wave 1 persistence uncommitted, two
cancelled delegation streams outstanding). The recommendations in Q15 are
analysis output for a future implementation session, not implemented here.

*Sub-reports: `ghanaed/UX_FLOW.md` · `ghanaed/NETWORK_MAP.md` ·
`ghanaed/ARCHITECTURE_RECONSTRUCTION.md` · `ghanaed/DATA_MODEL_RECONSTRUCTION.md`
· `ghanaed/GENERATION_FORENSICS.md` · `ghanaed/SCHEMEKNIT_COMPARISON.md`*
