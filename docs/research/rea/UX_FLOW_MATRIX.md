# REA UX Flow Matrix — Lesson-Planning Products (Black-Box Forensic Study)

Study date: 2026-10-14/15 · Method: REA `capture_browser_scenario` (Playwright/Chromium,
provider-owned profile) + public bundle static analysis · Evidence:
`evidence/scenarios/*_summary.json`, `evidence/scenarios/*_accessibility.txt`,
`evidence/screenshots/*.png`, `evidence/har/*.json`, `../rea/REA_CAPABILITY_DISCOVERY.md`.

**Confidence labels:** `CONFIRMED` (captured response/DOM) · `OBSERVED` (live
interaction) · `STRONGLY INFERRED` (bundle code) · `UNKNOWN` (not established).

**Ethics:** black-box only; public pages and normal flows; no auth/payment bypass;
no guessed endpoints; every request was initiated by our own REA session. Products
that require a paid/blocked login are recorded as limitations and skipped.

---

## 1. Verification of the required journey per product

Legend for **Gen** (generation access): ✅ = we observed real generation or a real
published output; ⚠️ = generation behind login/payment we did not obtain; ➖ = no
generation feature.

| Product | Public browse | Signup reachable | Real lesson output inspected | Gen | Evidence |
|---|---|---|---|---|---|
| GhanaEd | ✅ | ✅ (wizard seen) | ✅ (2 plans previously generated on our own account + training doc) | ✅* | `ghanaed_home/training/register/planner_*`, prior `docs/research/ghanaed/ghanaed_plan_*.json` |
| SHS Planner | ✅ | ✅ (Google/OTP; not completed) | ✅ **8-page real sample (their own "unedited output")** | ✅† | `shs_*`, `evidence/samples/sample-page-1..8.*` |
| Tenaly | ✅ | ✅ (auth page observed) | ⚠️ login required to generate | ⚠️ | `tenaly_home/generate/pricing_*` |
| Scorlar | ✅ | ✅ (`/register` link) | ⚠️ login required | ⚠️ | `scorlar_home_*` |
| Classpiler | ✅ | ✅ (`/register`) | ⚠️ login required | ⚠️ | `classpiler_home/app_*` |
| StudyPlugHub Ghana | ✅ | ✅ (`/signup`) | ⚠️ login required | ⚠️ | `studyplug_home/teachers_*` |
| MagicSchool | ✅ | ✅ (`Free for teachers`) | ⚠️ login required | ⚠️ | `magicschool_lp_*` |
| Eduaide | ✅ | ✅ (`Get Started Free`) | ⚠️ login required | ⚠️ | `eduaide_lp_*` |
| Planbook | ✅ | ✅ (90-day trial) | ➖ (scheduling tool, no AI lesson text) | ➖ | `planbook_home/help_*` |
| Brisk Teaching | ✅ | ✅ | ⚠️ (browser extension / login) | ⚠️ | `brisk_home_*` |

\* GhanaEd's generation was fully exercised in the earlier forensic session on our
own research account (`docs/research/ghanaed/ghanaed_plan_A.json` / `_B.json`);
this session added a fresh register-page capture and the bundle reconstruction.
† SHS Planner: the real generated document is published by the vendor on
`samples.php` as 8 JPEG pages; we downloaded and OCR'd every page (see §4).

**Cross-session note:** the earlier GhanaEd plans are reused as legitimate
first-party evidence; page-count/quality scoring for GhanaEd below cites those
artifacts, and the SHS Planner sample is the second real lesson document in the
study. All other generators sat behind logins we did not create, so their lesson
quality is marked `UNKNOWN` rather than guessed.

---

## 2. Teacher-journey table (PRODUCT | STEP | TEACHER ACTION | SYSTEM ACTION | INPUT REQUIRED | DEFAULTS | OUTPUT | EVIDENCE)

| PRODUCT | STEP | TEACHER ACTION | SYSTEM ACTION | INPUT REQUIRED | DEFAULTS | OUTPUT | EVIDENCE |
|---|---|---|---|---|---|---|---|
| **GhanaEd** | Visit | open `/` | SPA loads, promo fetch | — | — | dashboard/login | `ghanaed_home_accessibility.txt` |
| | Signup | pick School/Personal → 3-step wizard | `POST /api/auth/signup` → 20 credits | school, region, district, level, role, name, user, pass | level select | `/dashboard` + tour | `ghanaed_register_accessibility.txt`, prior `_netlog_register.json` |
| | Plan | open Lesson Planner | load `/api/lesson-planner/curriculum` | scheme(optional), level, class, subject, term, strand→CS→indicator cascade, week, topic | duration, days | plan draft | prior `_netlog_experiment*.json` |
| | Generate | click "Generate lesson plan · N credits" | synchronous AI `{lessonPlan}` | — | 10 credits/day-plan | full `lplan` doc | prior `ghanaed_plan_A/B.json` |
| | Batch | "Run in background" / series | `POST /jobs`, SSE `generate-series` | — | — | job + streamed days | prior `NETWORK_MAP.md` §5 |
| | Export | download | `download-credit` (0 cost) | — | — | print/DOCX | prior study |
| **SHS Planner** | Visit | open `/` | loads `curriculum.php?action=subjects&version` | — | Year 1, 1 hr, 30 students, Mixed, MA proficiency | form | `shs_home_accessibility.txt`, `shs_interact_summary.json` |
| | Inputs | Year, Region, School name, School type, Subject, Week/Topic, Lessons/week, Duration, Class size, Proficiency, Special notes, Resources | cascade fetch per change | Year, Region, Subject, Week (4 mandatory) | above defaults pre-set | ready to generate | `shs_home_accessibility.txt` |
| | Generate | click "Generate Lesson Plan" | `POST /api/generate.php` (stream, gen_type=`lesson_plan`) | — | prompt+system built client-side | DOCX (Word) | `shs_samples_accessibility.txt`, `app.js` |
| | Batch/term | Assessments / Scheme of Work tabs | `ppt_generate.php`, assessment builder | — | — | exam+marking scheme, semester scheme | `shs_samples_accessibility.txt` |
| | Export | tap page / download | standard Word/PowerPoint file | — | — | editable file | `shs_faq_accessibility.txt` |
| **Tenaly** | Visit | open `/` | marketing; "Browse freely" | — | — | — | `tenaly_home_accessibility.txt` |
| | Generate | click "Generate a lesson plan" | redirect to `/auth?redirect=/generate` | login (email/Google) | — | Daily SOL | `tenaly_generate_summary.json`, `tenaly_generate_accessibility.txt` |
| | Cascade | level→subject→strand→sub→indicator (stated) | preloaded NaCCA | (post-login) | — | — | `tenaly_home_accessibility.txt` |
| **Scorlar** | Visit/register | open `/` → "Start for Free" | `/register` | account | free=100 credits/mo | — | `scorlar_home_accessibility.txt` |
| | Generate | (post-login) "AI Lesson Planning" | GES-aligned plan | topic/cascade | — | plan PDF/DOCX | `scorlar_home_accessibility.txt` |
| **Classpiler** | Visit/register | open app → Sign Up Free | `/register` | account | free tier | — | `classpiler_app_accessibility.txt` |
| | Generate | "Create a lesson plan" | Claude Haiku 4.5 plan | cascade | GES/NaCCA | plan; schemes PDF/Excel | `classpiler_home_accessibility.txt` |
| **StudyPlugHub** | Visit | open teachers portal | login/signup | account | free | — | `studyplug_teachers_accessibility.txt` |
| | Generate | Lesson Planner (from uploaded PDF) | "one PDF → teaching pack" | upload resource | — | lesson plan/handout/exam | `studyplug_home_accessibility.txt` |
| **MagicSchool** | Visit | open tool page | marketing form | login for free tool | — | — | `magicschool_lp_accessibility.txt` |
| **Eduaide** | Visit | open solution page | marketing; 8 free plans/mo | login | — | 11 instructional models | `eduaide_lp_accessibility.txt` |
| **Planbook** | Visit | open `/` | 90-day trial | account | layouts | scheduling (no AI text) | `planbook_home/help_accessibility.txt` |
| **Brisk** | Visit | open `/` | extension/browser | login | — | Lesson Plan Generator | `brisk_home_accessibility.txt` |

---

## 3. Minimum-input model (A=explicit required, B=auto-detected, C=saved, D=default, E=optional, F=must-confirm)

| Field | GhanaEd | SHS Planner | Tenaly | Scorlar | Classpiler | StudyPlugHub |
|---|---|---|---|---|---|---|
| Level/class | A (level+class) | A (Year) | A (level) | A | A | B (from PDF) |
| Subject | A | A | A | A | A | B (from PDF) |
| Term | A (select) | D (week-based) | A | A | A | B |
| Strand/sub-strand | A (cascade) | B (from Week/Topic) | B (cascade auto-populates) | A | A | B |
| Content standard | A (cascade) | B | B | A | A | B |
| Indicator | A (cascade) | B | B | A | A | B |
| Duration | D (50 min) | D (1 hr) | E | D | D | B |
| School/teacher | C (profile) | E (name optional) | A (post-login) | A | A | C |
| Template | D (`jhs-daily`/`primary-ges`) | D (official GES/NaCCA template) | D (Daily SOL) | D | D | D |
| Resources | E (checkbox) | E (toggle list) | E | D | D | B |
| Approach | E (method chips) | D (AI-chosen) | D | D | D (RPK) | D |
| Lesson count | D (1/day) | A (lessons/week 1–4) | D (1) | D | D | D |
| Weekly planning ctx | E (week no.) | **A (Week/Topic is the driver)** | D | D | D | E |

**Key contrast (`CONFIRMED`):**
- **SHS Planner's minimum input is Year + Region + Subject + Week/Topic.** The
  entire NaCCA strand/sub-strand/content-standard/indicator set is **auto-resolved
  from the chosen Week** (`buildLsnMeta` reads `CUR[year][subject][week]` —
  `app.js`). One decision (which week) yields the whole curriculum header.
- **GhanaEd's minimum input is the cascade** (level→class→subject→term→strand→
  sub-strand→CS→indicator) — more clicks, but the teacher can also leave pickers
  empty and let the server resolve (Gen A in the prior study).
- **Tenaly** documents the same "cascade auto-populates" model and, uniquely,
  **caches generated plans per indicator** so the next teacher gets them "instantly
  — no extra tokens" (`tenaly_home_accessibility.txt`) — a reuse/saved-state pattern.

---

## 4. Lesson-output quality (real documents only)

### 4a. SHS Planner — 8-page General Science lesson (`evidence/samples/`)
Source: vendor-published "real, unedited output" JPEGs; OCR text also saved.
Pages: (1) header+strand+indicators+essential questions+pedagogy, (2) resources +
differentiation, (3) differentiation detail + GESI, (4) introduction/engagement,
(5–6) main activities + group tasks, (7) assessment (DoK 1–3 + summative + rubric),
(8) closure/reflection.

| Criterion | Finding | Label |
|---|---|---|
| Curriculum fidelity | Strand "Processes for Living", Sub-Strand "Essentials for Survival", Content Standard + Learning Indicators copied from NaCCA | `CONFIRMED` |
| Objective quality | Specific, observable, outcome-framed | `CONFIRMED` |
| Topic specificity | Names the structures/functions precisely | `CONFIRMED` |
| Starter specificity | Written engagement with a talk-partner prompt and prior-knowledge surfacing | `CONFIRMED` |
| Teacher/learner actions | Separated, timed (10/15/10/20/5/5 min) | `CONFIRMED` |
| Learning progression | Recall → application → DOK-3 reasoning | `CONFIRMED` |
| Assessment alignment | DOK levels 1–3 + summative task + 4-band rubric | `CONFIRMED` |
| Resource realism | Whiteboard, charts, "tablets if available" | `CONFIRMED` |
| Differentiation | **MA/HP/NS built into the activity text** (per the guide) | `CONFIRMED` (guide + plan) |
| Classroom feasibility | Time-budgeted; GESI/safeguarding agreement | `CONFIRMED` |
| Ghanaian context | GES/NaCCA framing; GESI explicit | `CONFIRMED` |
| Duration/timing | Budgeted in minutes per activity | `CONFIRMED` |
| Formatting | Page-per-section GES template | `CONFIRMED` |
| Completeness | All sections present incl. reflection-to-complete | `CONFIRMED` |

**Verdict:** `NO EDIT → MINOR EDIT` for a Ghanaian SHS teacher — this is a
genuinely teachable, supervision-ready document. (Vendor labels it a "draft for a
professional to review"; the content itself is complete.)

### 4b. GhanaEd — plans A & B (`docs/research/ghanaed/ghanaed_plan_*.json`)
Detailed in the earlier study; summary for this benchmark:
- Rich pedagogy, Ghanaian localization, fixed 10/30/10 skeleton, warm-up scripts,
  QA pairs — `NO EDIT` to `MINOR EDIT` for the **prose**.
- Defects: Gen B carries **raw NaCCA PDF artefacts** in `indicators[]`/`exemplars[]`,
  a placeholder `references`, and topic↔resolved-standard mismatch; Gen A has
  `indicators:[]`, `weekEndingDate:""`, `classSize:0` → `SUBSTANTIVE EDIT` required
  to fix the curriculum block before submission.

### 4c. Other Tier 1 products
No legitimate access to generation was obtained (login/payment), so lesson quality
is `UNKNOWN`. We recorded each product's **own** quality claims
(`10–20 min`, `NaCCA-aligned`, `MA/HP/NS`, `Kofi/Ama/GH₵ contexts`,
`offline PWA`) as **marketing claims, not verified output**.

---

## 5. Instructional/workflow ideas (Tier 2 observations, `CONFIRMED` where shown)

| Product | Idea worth studying | Evidence |
|---|---|---|
| Eduaide | 11 named instructional models (5E, UbD, Hunter, Gagné, UDL, PBL, Montessori, SPARK, Lesson Seed) as first-class choices | `eduaide_lp_accessibility.txt` |
| SHS Planner | DoK-leveled assessment + full rubric + MA/HP/NS differentiation **built into activity text**, not labelled | `evidence/samples` |
| SHS Planner | Online self-marking MCQ with **shuffled per-student question order** + automatic gradebook/item analysis | `shs_faq_accessibility.txt` |
| GhanaEd | Scheme of Work bulk generation ("Bulk to generate for the whole term … confirm the cost, watch live progress") + BSTEM library (49 activities) | `ghanaed_training_accessibility.txt` |
| Tenaly | Per-indicator **plan caching** ("no extra tokens" for the next teacher) | `tenaly_home_accessibility.txt` |
| Classpiler | DL+/GALOP **ability grouping** → one targeted lesson per group; offline PWA | `classpiler_home_accessibility.txt` |
| Planbook | Lesson **Layouts** (reusable structure templates applied per class/year) | `planbook_help_accessibility.txt` |
| StudyPlugHub | **One uploaded PDF → whole teaching pack** (plan + handout + exam + report card) | `studyplug_home_accessibility.txt` |

---

## 6. Limitations recorded

- Tier 1 generators **Tenaly, Scorlar, Classpiler, StudyPlugHub**, and Tier 2
  **MagicSchool, Eduaide, Brisk** require logins we did not create → lesson quality
  `UNKNOWN`; only their public flow/defaults/pricing were observed.
- **Planbook** has no AI lesson-text generation (scheduling/lesson-organisation tool).
- SHS Planner sample is a **single** published document (General Science, Year 1,
  Week 11) — quality is real but `n=1`; variation across subjects is `UNKNOWN`.
- GhanaEd generation was exercised in the earlier session; this session did not
  re-spend credits.

*Related: ../REA_LESSON_PLANNER_BENCHMARK.md · NETWORK_AND_CLIENT_EVIDENCE.md ·
LESSON_QUALITY_COMPARISON.md · SCHEMEKNIT_OPPORTUNITY_BACKLOG.md*