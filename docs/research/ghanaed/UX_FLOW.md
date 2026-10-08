# GhanaEd.com — UX Flow Reconstruction (Forensic Study)

Study date: 2026-10-05/06 · Method: Playwright automation with a single own research
account (`skforensic42188`, Forensic Research Basic School — fictional data) ·
Evidence files prefixed `_step_*`, `_ui_*`, `_route_*`, `screenshots/`.

**Confidence labels:** CONFIRMED (API response / DOM content observed directly) ·
OBSERVED (UI behaviour seen in automation) · STRONGLY INFERRED (client bundle code) ·
POSSIBLE-UNCONFIRMED (plausible, not verified).

---

## 1. Registration & onboarding (CONFIRMED / OBSERVED)

Landing → `/register` wizard (screenshots `01`–`14`, `_step_*.json`):

| Step | Screen | Fields / controls |
|---|---|---|
| 1 | SCHOOL | Organisation/school name (new-org form), **Region** select, **District** autocomplete ("Search district…" — free-text search over district list; type picker, screenshots `debug-step1-*`), Type/level select: `basic_kg_jhs \| kg \| primary \| jhs \| shs \| private \| office \| grade-based \| other` |
| 2 | ROLE | Role cards **Teacher / Student**, optional **coupon / referral code** inputs (`_step_11-step2-role.json`) |
| 3 | ACCOUNT | Full name, Username, Password, Confirm password; CTA **"Get started free"** (`_step_13-account-filled.json`) |

- Submit → `POST /api/auth/signup` → **201** `{token, user{…, credits: 20, …}}`
  (`_netlog_register.json`, `_step_14-after-submit.json`) — **CONFIRMED**.
- Marketing copy: "20 free AI credits on signup · No card" (**STRONGLY INFERRED**
  as growth copy; credit grant itself CONFIRMED in signup response).
- New account lands on `/dashboard` with an **onboarding tour modal** that blocks
  interaction until dismissed; tour completion is `PATCH /api/auth/onboarding
  {completed:true}` (**CONFIRMED**, response 200, behaviour persists across reload).
  `_ui_dashboard.json` / `ui-dashboard*.png`.
- A first-time **"Back to School" credit promo** banner/notice appears
  (`GET /api/subscription/promo`, promo `back-to-school`, `endsAt` 2026-11-11).

## 2. Global navigation (CONFIRMED from anchor hrefs; OBSERVED)

Route map extracted from DOM anchors (`_dom_nav_probe.json`) and per-route
snapshots (`_route_*.json`, `screenshots/route-*.png`):

- Core: `/dashboard`, `/profile`, `/messages`, `/progress`
- Teaching: `/school` (school workspace), **`/school/lesson-planner`** (planner),
  `/assignments`, `/lessons` (Study Notes portal), `/practicals`, `/assessment`,
  `/discussions`, `/classroom`, `/tutorials`
- Curriculum/reference: `/curriculum/{jhs,kg,lower-primary,shs,upper-primary}`,
  `/bece-prep`, `/wassce-prep`, `/self-tutor?view=practice`
- Commerce: **`/subscribe`** (credit store), `/school/credits` (school packs)
- AI assistant: `/akua`
- Mobile web shells: `/m/`, `/mt/` (lesson-plan), `/ma/credits` — desktop redirects
  to web routes; mobile-specific new/edit/detail paths exist
  (`_ui_route-mt-lesson-plan*.json`).

Sidebar **text clicks failed in automation** (drawer copy was off-viewport in the
mobile-rendered DOM) — navigation was done by URL/anchor href (**OBSERVED**
quirk, relevant to any future scraping: navigate by href, not label text).

## 3. Lesson Planner flow (CONFIRMED — `/school/lesson-planner`)

**Tools tabs:** Generate Plan · Schemes of Work · Scheme Analyzer · Termly Exams ·
BSTEM Library · My Lesson Plans (`route-school-lesson-planner.png`,
`_route_lesson-planner-plan.json`, `_route_lesson-planner-termly.json`).

**Form (dependent cascade, left→right):**

1. Scheme (select) — optional/uploaded schemes-of-work context
2. Level: `KG | LP | UP | JHS | SHS` … (planner-level codes)
3. Class: `B7 | B8 | B9` … (planner-class codes)
4. Subject: 13 options incl. **"Creative Arts and Design"**
5. Term
6. Strand — planner taxonomy is **numbered** (`1 DESIGN`, `2 CREATIVE ARTS`),
   *different* from the raw NaCCA curriculum API names (`DESIGN`)
7. Sub-strand — **duplicate options observed** (picker defect)
8. Content standard → 9. Indicator (each re-fetched after parent change)

Plus: **Week** text input, **Lesson topic** (free text), **Learner needs**,
diagram checkbox, school name, teacher full name, duration, class size;
teaching days Mon–Fri; pedagogy chips (teaching methods); AI extras.
Endpoint `GET /api/lesson-planner/curriculum?subject=&level=&className=` feeds
steps 6–9 with its own numbered taxonomy (**CONFIRMED**).

**Actions & modal:** primary button **"Generate lesson plan · N credits"**
(cost = 10 credits × day-plans, from bundle constants) and **"Run in
background"**; confirmation modal offers **Generate** + **Run in background**
(`screenshots/exp1-before-generate.png`).

**UI input defects OBSERVED in the experiment runs:**
- Sub-strand/CS selects silently kept a *mismatched* selection when the parent
  strand changed (Gen B: B9 topic but picker ended on strand `1 DESIGN`, empty
  sub-strand/CS) — server then resolved a *different* indicator than the topic.
- Empty curriculum fields are allowed; server auto-resolves from subject/class
  (Gen A) instead of erroring.

## 4. Onboarding tour & other modals (CONFIRMED)

- Tour modal blocks first-use until `PATCH /api/auth/onboarding` fires; it
  auto-marks completion server-side when walked through.
- Generation confirm modal (above).
- At 0 credits, planner hard-redirects to `/subscribe` (**OBSERVED**,
  `route-zero-planner*.png`).

## 5. Paywall UX boundary (CONFIRMED / OBSERVED)

With `credits = 0` (after the two budgeted experiments):
- Data endpoints return **402 `{"error":"credits_required"}`** — see
  `NETWORK_MAP.md` §4; UI state: `subscription/status.accountActive = false`.
- `/school/lesson-planner` → **redirect `/subscribe`** (`_route_zero-planner.json`,
  `route-zero-planner.png`); lesson lists/assignment views fail similarly
  (`route-zero-planner-plans.png`).
- `GET /api/ads/status` switches to `adsEnabled: true, rewardsRemainingToday: 5,
  pointsPerAd: 5` — a watch-an-ad reward path activates at zero
  (observed only; **never exercised**).
- Credit store remains reachable with full pack table
  (`route-zero-store.png`, `NETWORK_MAP.md` §6).

## 6. Flow-level takeaways

- **Time-to-first-lesson ≈ 3 clicks after login** (planner → pick cascade →
  topic → Generate) — the entire curriculum lookup is hidden behind dependent
  selects; the teacher never sees raw curriculum codes unless they open the
  indicator dropdown (**OBSERVED**).
- Failures are *forgiving*: empty pickers are accepted and resolved server-side;
  a mis-picked cascade still produces a complete-looking plan (Gen A/Gen B) —
  see `GENERATION_FORENSICS.md` for the quality cost of that forgiveness.
- Zero-credit state is a hard functional stop with an upsell redirect plus an
  ad-reward safety valve (**CONFIRMED**).

*Related: NETWORK_MAP.md · ARCHITECTURE_RECONSTRUCTION.md ·
DATA_MODEL_RECONSTRUCTION.md · GENERATION_FORENSICS.md ·
SCHEMEKNIT_COMPARISON.md · ../GHANAED_FORENSIC_ANALYSIS.md*
