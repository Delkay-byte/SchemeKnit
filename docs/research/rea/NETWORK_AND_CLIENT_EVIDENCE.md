# REA Network & Client Evidence — Lesson-Planning Products

Study date: 2026-10-14/15 · Capture: REA `capture_browser_scenario` (Playwright/
Chromium, provider-owned profile) and REA `analyze-javascript-application`
(static bundle reconstruction) · Evidence: `evidence/har/*.json`,
`evidence/har/sanitized_network_evidence.json`, `evidence/scenarios/*_summary.json`.

**Confidence labels:** `CONFIRMED` (captured request/response or bundle code) ·
`OBSERVED` · `STRONGLY INFERRED` · `UNKNOWN`.

**Sanitization:** REA never retains credential header *values*, cookies, or bodies;
it keeps URL **query-parameter names only** (values stripped). The HAR-shaped files
in `evidence/har/` are derived summaries of REA's already-sanitized events, not raw
captures. No tokens/cookies/passwords appear in any committed artifact.

---

## 1. REA capabilities actually used

| Capability | Command | Where used |
|---|---|---|
| Bounded browser scenario (launch) | `rea capture-browser-scenario` | 23 page captures across 15 products |
| Interactive declared actions | same (click/select_option/wait) | SHS Planner cascade (`shs_interact`) |
| Passive DOM + accessibility capture | within scenario `at_end` | all targets |
| Screenshot capture | within scenario `at_end: screenshot` | `evidence/screenshots/*.png` (22) |
| Network event capture | scenario `events: [network]` | `evidence/har/*.json` |
| Static JS/Electron application reconstruction | `rea analyze-javascript-application` | GhanaEd bundle (181 MB graph) |
| Local artifact static reading | filesystem + REA output | GhanaEd routes/endpoints, SHS `app.js` |

Unavailable on this host: Ghidra/IDA/Hopper (no engine), SQLite inspector
(Node 22 < 24.15), Android (no JADX). Recorded in `REA_CAPABILITY_DISCOVERY.md`.

---

## 2. SHS Planner — observed API contract (`CONFIRMED`)

Public, unauthenticated GETs observed during our own session:

| Method | URL | Payload/response |
|---|---|---|
| GET | `/api/curriculum.php?action=subjects&year=1` | `{"success":true,"subjects":[…56 SHS subjects…]}` |
| GET | `/api/curriculum.php?action=subjects&year=2` | same shape (Year 2) |
| GET | `/api/curriculum.php?action=version` | `{"success":true,"cur_ver":"17"}` |
| GET | `/api/curriculum.php?action=full&year=` (bundle) | full curriculum tree (referenced in `app.js`) |
| GET | `/tracker.php?action=visit&sid=…&page=…` | visit analytics |

Generation (**`CONFIRMED` from public bundle `assets/js/app.js?v=10.87`**), a
**streaming** design deliberately hardened for unreliable Ghanaian networks:

```js
// app.js — real production code (concept quotes, not copied into SchemeKnit)
fetch("/api/generate.php", {
  method:"POST",
  headers:{"Content-Type":"application/json","X-Requested-With":"XMLHttpRequest"},
  body: JSON.stringify({
    prompt, system: window._currentGenSystem || null,
    max_tokens: maxTok, stream: true,
    gen_type: window._currentGenType || 'lesson_plan',
    meta: window._currentGenMeta || null,
    batch_id: window._currentGenBatchId || null,
    recovery_id: recoveryId, continue_from: continueFrom || null,
    retry_reason: retryReason || null
  }), signal: ctrl.signal
})
```
- `IDLE_LIMIT_MS = 45000` — an idle timer aborts a stalled stream and feeds the
  **existing `recoverGeneration()`** path (no silent hang).
- Batch id: *"initial + retry billed once"* — retries are not double-charged.
- Related endpoints (`CONFIRMED` strings): `/api/check_generation.php?recovery_id=`,
  `/api/deduct.php`, `/api/refund_batch.php`, `/api/refund_download.php`,
  `/api/refund_ppt.php`, `/api/download.php`, `/api/ppt_generate.php`,
  `/api/quiz.php?action=deploy` (streamed), `/api/auth.php?action=email_send_otp`
  /`email_verify_otp`/`google`, `/api/credits.php?action=initiate`.

Minimum-input meta the client builds (`CONFIRMED`, `buildLsnMeta`):
```
{ type:'Lesson Plan', year, subject, week, topic, strand, subStrand,
  lessons, duration, classSize, planType, region, school,
  proficiency:'MA'|'HP'|'NS', notes, numClasses? }
```
`topic/strand/subStrand` are read from `CUR[year][subject][week]` — i.e. **the week
index is the join key to the whole curriculum header** (`CONFIRMED`).

System-prompt design (`CONFIRMED`, `buildLsnSystemPrompt`): frames the model as a
"senior Ghanaian SHS curriculum specialist"; instructs it to treat Content Standard
as a multi-week umbrella and drive this week's content from **Learning Indicators +
Focal Areas + Teacher Manual excerpts**; omits already-DB-covered fields from the
prompt for cache hits. Truncation recovery (`CONFIRMED`): `isLsnPlanComplete()`
detects missing Key Assessment/closure and continues from `continue_from` rather
than restarting blindly.

---

## 3. GhanaEd — reconstructed surface (`CONFIRMED` from bundle)

- Bundle route registry: **230+ client routes** across desktop + `/m` `/mt` `/ma`
  mobile shells (lesson-planner, school, classroom, fees, conduct, SBA, BECE…).
- API groups (specimen): `/api/lesson-planner/{generate,generate-series,jobs,
  exemplar-preview,schemes,schemes/parse-upload,schemes/build-ai,bstem/*}`,
  `/api/curriculum`, `/api/bece/{generate-questions,predict-topics}`,
  `/api/ai…`, `/api/auth/{onboarding,profile,google-config,pin}`,
  `/api/ads/status`, `/api/admin/*`, `/api/school/*`.
- Credit constants present as identifiers: `LESSON_PLAN_GENERATE`, `LESSON_GENERATE`,
  `QUIZ_GENERATE`, `AI_TUTOR`, `SCHEME_ANALYZER_FILE`, `SCHEME_ANALYZER_GENERATE`,
  `TERMLY_EXAM_GENERATE`, `BECE_PREDICT` (values documented in the earlier study).
- Generation contract (earlier session, `CONFIRMED`): single-day `POST
  /api/lesson-planner/generate`; multi-day `generate-series?stream=1` (SSE);
  background `POST /jobs`. Server resolves empty curriculum fields from
  subject/class, **not** from the topic text.

---

## 4. Cross-product client/architecture observations

| Product | Client model | Generation transport | Notes |
|---|---|---|---|
| GhanaEd | React SPA, 230+ routes, PWA + mobile shells | REST + SSE + background jobs | forgiving inputs, server-side resolution |
| SHS Planner | vanilla JS SPA, PWA, OneSignal push | `POST /generate.php` stream, 45s idle abort, recovery + batch refunds | **network-resilience is a first-class design** |
| Tenaly | SPA + Google auth | (post-login) | per-indicator **plan cache** |
| Scorlar | SPA, pre-loaded curriculum | (post-login) | "no uploads; pre-ingested" |
| Classpiler | React 18 + Node/Express + Mongo + Firebase, **offline PWA** | Claude Haiku 4.5 | diagnostics + remedial generation |
| StudyPlugHub | SPA, two portals (student/teacher) | (post-login) | "one PDF → teaching pack" |
| MagicSchool / Eduaide / Brisk | marketing SPAs; tools behind login | (post-login) | multi-model pedagogies (Eduaide) |
| Planbook | scheduling app, layouts | n/a (no AI text) | organisational patterns only |

## 5. Evidence index

| File | Content |
|---|---|
| `evidence/har/sanitized_network_evidence.json` | all 23 targets: sanitized request lists |
| `evidence/har/har_<id>.json` | per-target HAR-shaped sanitized summary |
| `evidence/scenarios/<id>_summary.json` | REA normalized capture (steps, completeness) |
| `evidence/scenarios/<id>_accessibility.txt` | full accessibility tree text |
| `evidence/scenarios/<id>_dom.txt` | DOM text (selectors/ids for forms) |
| `evidence/screenshots/*.png` | 22 final-state screenshots |
| `evidence/samples/sample-page-1..8.jpg` + `.txt` | SHS Planner real lesson (image + OCR) |
| `evidence/samples/shs_curriculum_subjects_year1.json` | captured curriculum subjects |

*Related: ../REA_LESSON_PLANNER_BENCHMARK.md · UX_FLOW_MATRIX.md ·
LESSON_QUALITY_COMPARISON.md · SCHEMEKNIT_OPPORTUNITY_BACKLOG.md*