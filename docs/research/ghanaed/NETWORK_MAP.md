# GhanaEd.com — Network Map (Forensic Study)

Study date: 2026-10-05/06 · Capture: Playwright request/response logging from a
single own research account · Evidence: `_netlog_*.json`, `_zero_credit_probe.json`,
`_chunk_map.json`, `_route_*.json`, `_exp*_post.json`.

**Confidence labels:** CONFIRMED (captured response/body) · OBSERVED (request seen,
response not fully inspected) · STRONGLY INFERRED (client-bundle constant) ·
POSSIBLE-UNCONFIRMED.

**Note:** all captures contain bearer tokens/JWTs of the research account. Files
are evidence artefacts kept in-repo under `docs/research/ghanaed/`; **tokens are
redacted in this document** and must never be copied out of the study context.

---

## 1. Origin & static layer (CONFIRMED)

- Same-origin SPA: HTML shell + hashed JS/CSS under `/assets/`.
- Route-level code splitting observed: `_chunk_map.json` lists per-route chunks;
  planner chunk `assets/LessonPlannerPage-BlGcjwpV.js` (259 KB captured to temp),
  `assets/SchoolCreditsPage-CQbTDeJh.js`, plus vendor chunks (`vendor-react`,
  icon lib). Main bundle `index.js` ≈ 380 KB.
- Mobile shells `/m/ /mt/ /ma/` are separate route trees.

## 2. Auth endpoints (CONFIRMED — `_netlog_register.json`, session logs)

| Method | Path | Notes |
|---|---|---|
| POST | `/api/auth/signup` | body `{name, username, schoolId, role, password, schoolName, region, district, level}` → **201** `{token, user{…, credits:20, accountActive, onboardingCompleted, gamePoints, referralCode, …}}` |
| POST | `/api/auth/login` | (research-account session refresh, `ghanaed_session.json`) |
| GET | `/api/auth/me` | session probe; stays 200 at 0 credits |
| PATCH | `/api/auth/onboarding` | `{completed:true}` → 200 (tour dismissal, persists) |
| POST | `/api/auth/logout` | observed in bundle |

## 3. Curriculum & planner endpoints (CONFIRMED)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/curriculum/levels` | level tree; **402 at 0 credits** |
| GET | `/api/lesson-planner/curriculum?subject=&level=&className=` | planner's own numbered taxonomy (strands `1 DESIGN` …); feeds dependent selects |
| POST | `/api/lesson-planner/generate` | single-day lesson (payload contract §5) |
| POST | `/api/lesson-planner/generate-series?stream=1` | SSE `start`/`day_done`/`complete`/`error` multi-day run |
| POST | `/api/lesson-planner/jobs` | background batch `{items[…], meta}`; `GET /jobs`, `POST /jobs/{id}/cancel` |
| POST | `/api/lesson-planner/exemplar-preview` | exemplar preview (bundle) |
| GET | `/api/lesson-planner/plans` (list) | saved plans; **402 at 0 credits** |
| POST | `/api/lesson-planner/download-credit` | zero-cost download guard (bundle) |

## 4. Session/account state (CONFIRMED)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/subscription/status` | `{credits, accountActive, …}`; **`accountActive` flips false at 0 credits** |
| GET | `/api/subscription/promo` | promo `back-to-school`, `endsAt` 2026-11-11 (site copy says "until 31 December 2026" — **copy/config mismatch, OBSERVED**) |
| GET | `/api/subscription/history` | purchase history (200 with empty history) |
| GET | `/api/ads/status` | at 0 credits: `{adsEnabled:true, rewardsRemainingToday:5, pointsPerAd:5}` |
| GET | `/api/assignments`, `/api/lessons` | student/teacher data lists; **402 at 0 credits** |

### 402 matrix at `credits = 0` (`_zero_credit_probe.json`, CONFIRMED)

```
402 {"error":"credits_required"}  lesson-planner/*, /api/curriculum/levels,
                                   /api/assignments, /api/lessons, planner lists
200                              /api/auth/me, /api/subscription/*, /api/ads/status
redirect 302/HTML               /school/lesson-planner → /subscribe  (UI)
```

→ **Gating layer = `accountActive`/credits check inside API routes**, not a
WAF/edge feature; non-credit surfaces keep working for retention
(STRONGLY INFERRED from which routes 402 vs 200).

## 5. Generation payload & response (CONFIRMED — `_netlog_experiment1/2.json`)

`POST /api/lesson-planner/generate` request body (captured verbatim; field
annotations from the request, not guessed):

```
{ schoolId, schemeId, week, subject, level, className, term, topic,
  strand, subStrand, contentStandard, indicators[], dayLabel, weekEndingDate,
  classSize, teacherName, schoolName, academicYear, durationOverride,
  bulkJobId, printTemplateId:"jhs-daily"|"primary-ges", period,
  teachingMethods[], firstTime, learnerNeeds, ghanaianLanguage, includeImages }
```

→ 200 `{lessonPlan}` (full document shape: `DATA_MODEL_RECONSTRUCTION.md` §2;
saved evidence `ghanaed_plan_A.json`, `ghanaed_plan_B.json`).

Multi-day: `POST /api/lesson-planner/generate-series?stream=1` (SSE stream);
background: `POST /api/lesson-planner/jobs` + `GET /jobs`
(STRONGLY INFERRED for job polling shape; start/job-create CONFIRMED in bundle).

## 6. Commerce (STRONGLY INFERRED from bundles; store page CONFIRMED)

- Pack table (pesewas = GHS×100): 50cr→GHS5 (GHS0.10/cr), 150→GHS12 (0.08),
  500→GHS35 (0.07), 1,200→GHS60 (0.05), 3,000→GHS120 (0.04);
  school term packs GHS130/280/600/1,200/2,400 for
  4k/10k/25k/55k/120k credits (maxStudents 100/300/800/1500/unlimited),
  yearly tiers also present. Admin endpoints `/api/admin/users/{id}/credits`,
  `/api/admin/credit-promo`, `/api/school/credits{,/usage,/initialize}`.
- Per-operation credit constants (bundle): lesson-plan generate **10**,
  explainer 5, quiz 3, tutor/chat 1, image-fast 2, scheme-analyzer 1/2/8,
  termly exam 10, pre/post 8, BECE/WASSCE 3/5/3/1, TTS 2, term report 10,
  BSTEM 2/1, download 0. Cost = 10 × number of day-plans.
- Payments: amounts in **pesewas** (GHS minor unit) → mobile-money/Paystack-style
  flow (PROBABLE; checkout itself not exercised).

## 7. Misc client network behaviour (OBSERVED)

- Onboarding completion PATCH fires during tour walkthrough.
- Region/district data fetched for the register wizard (searchable district list).
- No third-party analytics observed in-session in our captures
  (POSSIBLE-UNCONFIRMED — bundle strings may include some; not verified).

## 8. Evidence index

| File | Content |
|---|---|
| `_netlog_register.json` | signup wizard requests (signup 201, promo, onboarding) |
| `_netlog_session1/1b/2.json` | authenticated route/session traffic |
| `_netlog_experiment1/2.json` | full planner cascade + generate requests/responses |
| `_zero_credit_probe.json` | 402/200 matrix + ads/status at 0 credits |
| `_route_*.json` | per-route DOM snapshots incl. zero-credit redirects |
| `_chunk_map.json`, temp `index.js`, `LessonPlannerPage.js` | static bundle map + captured chunks |

*Related: UX_FLOW.md · ARCHITECTURE_RECONSTRUCTION.md ·
DATA_MODEL_RECONSTRUCTION.md · GENERATION_FORENSICS.md ·
SCHEMEKNIT_COMPARISON.md · ../GHANAED_FORENSIC_ANALYSIS.md*
