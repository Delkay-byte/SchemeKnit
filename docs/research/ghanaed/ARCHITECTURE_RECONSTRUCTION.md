# GhanaEd.com — Architecture Reconstruction (Forensic Study)

Study date: 2026-10-05/06 · Method: static analysis of downloaded client bundles
(`index.js`, `vendor-react.js`, `vendor-icons.js`, `LessonPlannerPage.js`,
`SchoolCreditsPage-CQbTDeJh.js`) + observed network behaviour (NETWORK_MAP.md) +
DOM route registry (`_dom_nav_probe.json`).

**Confidence labels:** CONFIRMED (directly observed) · OBSERVED (runtime
behaviour) · STRONGLY INFERRED (bundle code/constants, cross-checked) ·
POSSIBLE-UNCONFIRMED.

---

## 1. Client (CONFIRMED / STRONGLY INFERRED)

- **SPA**: React + hash-hinted vendor chunks; route-based code splitting per page
  (`_chunk_map.json`). Vite/rollup-style hashed filenames (STRONGLY INFERRED
  from `PageName-<hash>.js` convention).
- **Router**: history-path routes matching the anchor registry
  (`/school/lesson-planner`, `/subscribe`, `/curriculum/*`, `/mt/*` …). Two
  shells: desktop web + mobile web (`/m /mt /ma`), plus Android APK distribution
  ("teaChat" sideload marketing — bundle strings, STRONGLY INFERRED as separate
  product surface).
- **State**: server state via fetch wrappers (token header injection), local
  onboarding flags (`onboardingCompleted` server-persisted via PATCH — CONFIRMED).
- **Dependent-form engine**: planner selects are a client-driven cascade that
  re-queries `/api/lesson-planner/curriculum` per level change (CONFIRMED in
  `LessonPlannerPage.js` + observed in experiment logs).
- **Transport**: SSE for `generate-series?stream=1` (bundle constant; stream
  protocol names `start|day_done|complete|error`).

## 2. Server (STRONGLY INFERRED, evidence-cited)

- **API style**: REST JSON under `/api/*`, bearer-token auth (JWT carried in
  `Authorization`, format `eyJ…` observed in our own signup response — CONFIRMED
  for auth; CONFIRMED role of token in our subsequent calls).
- **Persistence model**: **document store with CouchDB-style documents** —
  `_id`/`_rev` fields on curriculum records
  (`subject:jhs:arabic`, `strand:…`, `substrand:…`, `cs:…`, `indicator:…`)
  and on saved plans (`_id: "lplan:user:<school>:<username>:<rand>"`,
  `type: "lplan"`) — CONFIRMED from API responses. Backend engine
  (CouchDB, or Mongo/other mimicking that envelope) is
  POSSIBLE-UNCONFIRMED; the envelope itself is CONFIRMED.
- **ID conventions (CONFIRMED)**:
  - users: `user:<school-slug>:<username>`
  - schools: slug `forensic-research-basic-school`
  - curriculum: `<type>:<level>:<slug>` / `<type>:<subject>:<code>`
  - plans: `lplan:<userId>:<rand>`; internal `schoolId` slug
- **Service groups (STRONGLY INFERRED from URL namespaces)**:
  `auth`, `curriculum`, `lesson-planner` (generation core),
  `subscription` + `ads` (credit economy), `assignments`, `lessons`,
  `school`, `admin`, `scheme-analyzer`, `akua` (AI chat), `bece/wassce` tools,
  payments (pesewas amounts), `quiz/assessment`, `reports`.
- **Background execution**: job documents (`bulkJobId`, `/jobs` create/list/
  cancel, run-in-background option in UI) — CONFIRMED for job id plumbing in
  generate payload; worker internals POSSIBLE-UNCONFIRMED.
- **Generation pipeline (STRONGLY INFERRED from behaviour)**: client sends form
  context → server resolves curriculum fields when missing (subject/class
  defaults), builds lesson document server-side (AI-composed prose; PDF-sourced
  exemplars/indicators), returns complete `lplan` document. Evidence of server
  resolution & PDF ingestion: GENERATION_FORENSICS.md.

## 3. Curriculum data layer (CONFIRMED)

- Raw NaCCA curriculum exposed as a **read-only document collection** with
  subject→strand→substrand→content-standard→indicator hierarchies, each level a
  separate queryable type (`/api/curriculum/levels` + per-type fetches), plus
  `pdfUrl` fields pointing at `nacca.gov.gh` PDFs (STRONGLY INFERRED: server
  ingests/indexes those PDFs — corruption artefacts in generated output show
  PDF page text bleeding in, GENERATION_FORENSICS.md §4).
- **Two taxonomies coexist**: raw API names (`DESIGN`) vs planner-numbered
  names (`1 DESIGN`) — OBSERVED divergence between `/api/curriculum` and
  `/api/lesson-planner/curriculum` (CONFIRMED both, mismatch noted).

## 4. Credit economy subsystem (CONFIRMED)

- `subscription/status` gate → per-route enforcement (402) at data layer.
- Ads-rewarded credits activate only when `accountActive=false`/0 credits
  (CONFIRMED state transition, reward flow not exercised).
- Admin/school grant endpoints exist for staff/heads (bundle strings).
- Promo layer (2× credit promos, timed) independent of base pack table.

## 5. Product surface map (CONFIRMED bundle strings + routes)

Teacher: dashboard, lesson planner (+schemes/analyser/termly exams/BSTEM),
assignments, lessons portal, assessments, progress, discussions, classroom,
messages, self-tutor, curriculum browser, Akua chat, school workspace, credit
store, term reports, CPD/logbook tooling (form strings "Head Teacher
confirmation", "teacher logbooks" observed in copy dump — POSSIBLE-UNCONFIRMED
as fully shipped feature set).
Student: BECE/CSSPS prep, WASSCE prep, practice, grade pathways.
Growth: referral codes, webinar landing pages, APK sideload, promo banners.

## 6. Comparison anchors for SchemeKnit (see SCHEMEKNIT_COMPARISON.md)

| Concern | GhanaEd (this study) | SchemeKnit (local repo, own system) |
|---|---|---|
| Client | Single SPA, chunked, mobile shells | Next.js app router (own repo) |
| API | REST `/api/*`, JWT | FastAPI `/api/*`, JWT (own source) |
| Store | Doc store w/ `_id/_rev` envelopes | SQLite relational (SQLAlchemy) |
| Curriculum | National doc collection + PDF ingest | Scheme-derived spine (`curriculum/spine.py`) |
| Generation | Server-side AI compose, forgiving inputs | Deterministic builder + optional AI mode |
| Gating | Credits/`accountActive` → 402 | Free-tier quota (5 plans + 5 AI/calendar month) |

*Related: UX_FLOW.md · NETWORK_MAP.md · DATA_MODEL_RECONSTRUCTION.md ·
GENERATION_FORENSICS.md · SCHEMEKNIT_COMPARISON.md ·
../GHANAED_FORENSIC_ANALYSIS.md*
