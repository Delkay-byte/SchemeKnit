# Zero-Decision / Autopilot Generation (Priority 3.1)

**Status:** complete, verified locally on 2026-10-08. Production verification is
blocked by the long-standing stale Render build (see §24 below) — nothing here
claims a production rollout.

## 1. What it is

After a scheme has been analysed, the teacher's ONE explicit action —
**"Generate my lesson plans"** — starts the run. The upload screen hands
straight to the Generate page with the intent recorded; the Generate page
plans the run with the server and, when everything is ready, starts it with no
further input. Everything the system can infer is inferred; only genuine
decisions interrupt (subject / class / WAPEF / nothing pending / exhausted
allowance).

Measured teacher-facing effect for an ordinary single-subject scheme:

| | Before (Priority 3 flow) | After (Autopilot) |
|---|---|---|
| Required interactions upload → plans | file pick, **Upload & Process**, **Review Curriculum**, **Approve & Configure**, **Generate lesson plans** (5) | file pick, **Upload & Process**, **Generate my lesson plans** (3) |
| Generation actions | 1 (on the Generate page after 3 screens) | 1 (the same action, recorded at upload) |
| Config/weeks/questions asked first | none either | none either — term dates, duration and lessons/week are seeded from the scheme and saved preferences |

"Review Curriculum" and the whole week-centric advanced flow are unchanged and
stay one click away (§19): nothing was removed, only one new primary path was
added.

## 2. Design decisions (and why)

1. **The browser never counts.** The card renders `counts`, `blockers`,
   `review_message`, `selected_*` verbatim from
   `POST /api/generation/{scheme_id}/autopilot-selection`. Pending/safe
   ordering, quota fitting, WAPEF state and the remaining allowance are pure
   server facts (`frontend/src/app/(app)/generate/[id]/page.tsx` —
   `data-autopilot-counts`).
2. **Explicit click, once.** The upload primary button
   (`data-autopilot-upload`) writes `sessionStorage['schemeknit.autopilot_intent']`
   = `1` then routes to `/generate/{scheme_id}`. The Generate page consumes the
   flag exactly once (cleared on read). A plain visit, a reload, or
   "Start New Generation" never auto-fires — quota can never be spent without
   that click (`autopilotIntent` / `autopilotFired` refs).
3. **Server-authoritative selection.** `backend/src/engines/autopilot.py`
   (pure, unit-tested):
   - `select_autopilot_rows`: source order greedy over pending, safe
     (non-special, non-needs-review, non-generated) rows; quota counted per
     distinct indicator code (the backend's reservation rule — unchanged);
     indicatorless schemes fit everything.
   - `selection_blockers`: only
     `subject_confirmation` (multi/unknown subject, extraction failure),
     `class_confirmation`, `wapef_required`, and — only when none of those
     exist — `nothing_pending` / `needs_review` / `quota_exhausted`, in the
     order the teacher fixes them.
   - `wapef_autopilot_state`: WAPEF only required for
     `tpl-wapef-approved-plan`; "saved" = any non-empty
     `wapef_deep_hope | wapef_storyline | wapef_through_lines | wapef_gods_story`
     in `scheme_db.lesson_review_drafts`. The system never invents these values.
4. **No AI in the core path.** The plan is deterministic; AI/Zeli stays an
   explicit Generate-page choice exactly as in Priority 3 (`ai_mode` OFF
   default).
5. **One synchronous POST, honest progress.** The generate endpoint commits
   the whole run at the end (unchanged from P3), so there is no live
   per-lesson progress to poll (§25). The UI shows the ordered work list
   (`data-autopilot-progress`, `N of M · Week w — topic`) during the run and
   never a fake percentage or `setInterval` poller.
6. **Results view (§18).** Multi-lesson runs lead with
   `data-autopilot-results` — "N lesson plans ready" plus week · topic ·
   Generated · Open lesson per row; a single lesson opens in the workspace
   directly. "Start New Generation" clears it.
7. **Seeding (§8).** Term window comes from the scheme's own week dates
   (first start / last end) instead of hardcoded dates; duration and
   lessons/week come from `GET /api/settings/preferences` with the established
   defaults as fallback. Class/subject come from the scheme; an unknown class
   is a blocker, never a guess.
8. **Re-plan on config change.** The plan effect depends on
   class / subject / template, so changing settings (e.g. selecting the WAPEF
   template) re-plans the card immediately — a stale plan cannot exist.
9. **Smallest WAPEF interrupt.** A `wapef_required` blocker offers "Add
   missing WAPEF fields", which loads the preview and scrolls to the WAPEF
   inputs only (`focusWapef`). Filling them re-plans to ready.

## 3. The endpoint

`POST /api/generation/{scheme_id}/autopilot-selection` (TermConfig body,
teacher auth) in `backend/src/routers/generation.py`:

```json
{
  "ready": true,
  "blockers": [{"code": "quota_exhausted", "message": "..."}],
  "review_message": null,
  "needs_review_items": [],
  "counts": {
    "pending_count": 22, "safe_pending_count": 22, "needs_review_count": 0,
    "selected_count": 5, "generated_count": 0, "quota_skipped_count": 17
  },
  "selected_occurrence_ids": ["week1:0:B9.1.1.1.1", "..."],
  "selected_indicator_codes": ["B9.1.1.1.1", "..."],
  "selected_rows": [{"source_occurrence_id": "...", "indicator_code": "...",
    "week_number": 1, "topic": "Materials", "indicator": "..."}],
  "quota": {"limit": 5, "used": 0, "remaining": 5, "unlimited": false, "...": "..."},
  "wapef": {"required": false, "saved": true, "template_id": ""},
  "template_id": null,
  "scheme_id": "..."
}
```

The plan is read-only: generation still goes through the existing
`POST /{scheme_id}/generate` with the exact `selected_*` from the plan. The
generate endpoint's own gates (quota reservation, occurrence validation,
needs-review protection) remain the enforcement boundary — the plan cannot
bypass them.

## 4. Screen contract (data attributes)

- Upload: `data-autopilot-upload` (primary), secondary "Review Curriculum" /
  "Back to Dashboard" (Priority-3 e2e labels untouched).
- Generate: `data-autopilot`, `data-autopilot-counts`,
  `data-autopilot-review`, `data-autopilot-blocker` +
  `data-blocker-code`, `data-autopilot-action` (label
  `Generate N lesson plans` when the plan is capped, else
  `Generate my lesson plans`; disabled unless `ready`),
  `data-autopilot-manual` ("Choose manually" → the week surface),
  `data-autopilot-settings` ("Change settings" → the config card),
  `data-autopilot-progress` (+ `data-progress-row`),
  `data-autopilot-results` (rows: week · topic · Generated · Open lesson).
- Unchanged: `data-generate-config`, `data-allocation-preview`,
  `data-allocation-weeks`, `data-lesson-review`, all `#cfg-*` ids, the exact
  strings "Generating your lesson plans", "Review Curriculum",
  "Approve & Configure", "Lesson plans by week".

## 5. Verification

### 5.1 Automated

- `backend/tests/test_autopilot_generation.py` — **27/27**: pure matrix
  A/B/C/D/E/H/I/K + indicatorless + blockers + WAPEF F/G + `ai_mode OFF` (L);
  API: ready one-click, cap-at-5, unlimited (`generation_limit=0`), small
  scheme, partial resume, exhausted (direct generate 403, no job created),
  WAPEF saved/missing + resume, unknown subject/class blockers.
- `backend/tests/test_autopilot_ui_source.py` — **15/15** UI source contracts
  (one-action upload, single-consumed intent, honest progress, results view,
  server-authoritative counts, manual flow untouched, scheme-seeded dates).
- Full backend suite: **2309 passed, 11 skipped** (was 2267 before P3.1).
- `npx tsc --noEmit` clean; `npx next build` clean.

### 5.2 Real-browser acceptance — `frontend/e2e/autopilot-acceptance.js`

**39/39 passed** (screenshots + `results.txt` in `e2e/autopilot-acceptance/`),
covering the §23 scenario table:

1. Fresh signup + single-subject scheme → ONE action → 5 lesson plans
   generated, results card, workspace, quota `used=5 remaining=0` server-side.
2. The capped plan is the server's: "22 lesson plans found · 5 can be
   generated this month · 17 wait for next month".
3. Capped button names the exact server count ("Generate 5 lesson plans").
4. Unlimited account: "22 can be generated this month", no "wait" segment,
   plain label, enabled.
5. Genuine interrupts: upload-time class prompt (a scheme that states no
   class), WAPEF prompt with focused "Add missing WAPEF fields" → Deep Hope
   inputs, exhausted-quota blocker after Start New Generation.
6. "Choose manually" lands on the week surface; "Change settings" brings the
   config into view; week-centric heading untouched.
7. Plain visit and reload never auto-generate (0 selection/generate POSTs);
   reload restores the completed job; mobile 375 px card and action fit.

Regression sweep after the feature (all green, 0 failures):
phase17-A 30/30, deep-journey 21/21, curriculum-workspace 75/75,
app-ui, app-surfaces, app-closure, kg 31/31, nursery 130/130,
lesson-persistence 70/70, wapef 32/32, wapef-boundary 29/29,
zeli-groq 56/56.

### 5.3 Defects found and fixed while verifying

- Counts line read `selected` for "found" — now reads `pending_count`.
- Capped label could say "Generate 0 lesson plans" when blocked and empty —
  now falls back to "Generate my lesson plans" (disabled).
- Mobile 375 px overflow (pre-existing on the Generate page): the week-row
  description used `truncate` (white-space: nowrap), whose intrinsic width
  blew the document out to ~2460 px. Switched to `line-clamp-1` (same
  single-line ellipsis look, wraps for sizing) for the row description and
  the provenance `<dd>` — document width now exactly 375 px.

## 6. Known limitations / out of scope

- **Needs-review in the browser:** no real uploaded document currently
  produces codeless (`lesson_date is None`) rows, so the `needs_review`
  blocker was verified at API level (pytest matrix) and shares its renderer
  (`data-autopilot-blocker`) with the browser-proven WAPEF/class/quota
  blockers.
- **Generate-page class blocker via UI:** the upload confirm screen requires
  the class before the subject chip unlocks, so a scheme reaches the Generate
  page with a confirmed class. The generate-side `class_confirmation`
  blocker + "Confirm class level" action are covered by pytest (API) and the
  UI-source test; the browser covers the class interruption where teachers
  actually meet it (upload).
- Live per-lesson progress remains impossible without changing the generate
  endpoint's transaction shape (deliberately untouched — §25).
- Quota rules, capacity filtering, activity libraries and P1/P2/P3 semantics
  are unchanged.

## 7. Production (§24)

Deploy marker re-run 2026-10-08 against `https://schemeknit-api.onrender.com`
(`marker_driver.py`, real doc, codes `B9.1.1.1.2` / `B9.1.2.1.1`):

- Production objectives: **"Learners can Discuss…"** — byte-identical to the
  saved pre-P2 (`marker_old`) output.
- Current local code objectives: **"Learners can Explain…"** (`marker_new`).

Production is therefore still running the pre-P2 build; the owner-side
redeploy blocker in `docs/RENDER_DEPLOYMENT_FIX_REPORT.md` is unchanged.
Autopilot is claimed **locally only** — no production verification of this
feature is possible until Render serves the current build (note: Autopilot
itself only needs the API routes + frontend bundle to ship together; the
detectable P2 marker is the standing staleness witness).
