# Generate workflow — the week-centric teacher flow

*Status: Priority 3, local verification complete. Production deploy status in
§7.*

The Generate screen answers one question for a normal teacher: **what lessons
need generating this week, and which of them can I generate right now?** All
allocation machinery (coverage, ordering, capacity) stays in the backend; the
screen only shows its result.

## 1. The five steps

```
SCHEME → WEEKS → INDICATORS → GENERATE → LESSON WORKSPACE
```

1. **SCHEME** — teacher uploads a scheme-of-work DOCX (`/upload`), the
   extraction runs, the teacher confirms subjects/sections
   (`/review/[id]` → *Approve & Configure*), and lands on
   `/generate/[id]`.
2. **WEEKS** — the Generate page is a week surface, not a form. Every
   teaching week of the configured term renders as a week card
   (`data-week-card`, `data-week-number`) listing that week's lesson rows
   (`data-week-row`, `data-occurrence-id`). Each row carries its stable
   occurrence id (`week{w}:{pos}:{code|row}`) — the identity used for
   replace/replay decisions, never list position.
3. **INDICATORS** — each row shows the curriculum indicator it will satisfy
   (`data-lesson-review` rows; indicator codes visible per row). The teacher
   picks *what* to generate; the backend decides *how* (which weeks, which
   slots, what order) from the scheme's own occurrences.
4. **GENERATE** — three entry points, same backend:
   - **row/week buttons** (`data-generate-lesson`, `data-generate-week`):
     regenerate one lesson or one week's lessons;
   - **primary *Generate lesson plans*** (`data-generate-action`): the full
     pending set, capped by the monthly allowance;
   - **Quick Generate / Build with me** (`data-generate-mode`, default
     Quick): Quick = one complete draft; guided = section-by-section review
     afterwards. Mode never changes backend semantics.
5. **LESSON WORKSPACE** — generated lessons land in `/lessons`
   (`/lessons/[id]` detail: *Lesson context* + *Lesson plan*), editable and
   exportable to DOCX/PDF.

## 2. Two gates, one surface

- **Setup gate** (`data-generate-config`): term window, lessons per week,
  class level, template, AI mode — shown when there is no preview/job yet,
  or after *Start New Generation* (back to editing, never a silent reset).
- **Weeks gate** (`data-generate-summary`): loads itself as soon as the
  setup view is ready — no Preview button to discover. Allocation inputs
  (term window, teaching days, class) debounce-refresh the weeks (600 ms),
  so typing a date never spams the server.

## 3. Quota line (the only number that matters)

Server-authoritative, rendered from the preview (`quotaLine` /
`formatWeekCounts` in `frontend/src/lib/generate-coverage.ts`):

- header: `X of 5 Free Tier lesson plans used this month · Y remaining`
- full-set fit: **"`F` of `N` pending can be generated this month — the rest
  stay in your scheme for next month."**

`F` counts **pending** (not-yet-generated) rows only — `fullSelection(rows,
quota)` filters `is_special_period` and fits rows in deterministic order.
Generated rows never inflate the fit line. When the allowance is spent, the
primary action is disabled **with the server's reason on screen** (never a
silent disable), and a single row can still be generated when the
deterministic engine runs in AI-OFF mode (no AI unit involved).

Ledgers (distinct on purpose):

- **lesson plans**: 5 per calendar month (Free Tier), enforced per generated
  indicator/period (`reserve` → `release` + recount around each job);
- **AI generations**: monthly ledger `ai_quota_used` / `ai_quota_remaining`
  (5/month Free). `ai_credits_remaining` in a generate response is the
  monthly remaining, or `null` when the job consumed no AI (deterministic
  fallback). Exhaustion messages: *"You've used all 5 free AI generations
  for this month…"* (403 before job creation) and *"You've used all 5 Free
  Tier lesson plans for this month…"*.

## 4. Allocation rules — backend owns them (never re-added client-side)

The frontend must not (and the current code does not) do: capacity
filtering, carry-forward, slot limiting, cross-week reallocation, or any
re-derivation of coverage. The week view is a **pure function of the
server preview** (`buildWeekPlans` in `generate-coverage.ts`): occurrence
stability (P1), deterministic engine output (P2), replace-mode/replay guards
(`occurrence` / `codes` / `all`, requested codes, ordinal stamping) are all
server-side. The frontend picks WHAT; the backend decides HOW.

## 5. Review edits are never wiped

WAPEF fields (`select[id^="wapef-"]`, 1-based sequence ids), Deep Hope /
storyline / through-lines / God's story, keyword chips and structured
references are edited in `lessonReview` state and saved
(`saveLessonReviewDrafts`) immediately before every generate.

A debounced allocation preview replaces rows from the server. Teacher edits
made since the last preview are preserved: `updateLessonReviewRow` /
`updateStructuredRef` mark the row's `source_occurrence_id` as *touched*
(`touchedOccurrences` ref), and `handlePreviewAllocation` re-merges those
rows on top of the fresh server rows by occurrence id. New allocation rows
(new occurrence ids) correctly start from server truth.

## 6. Vocabulary & guarantees

- Forbidden in page source: provider names (`gemini`, `groq`, `openai`,
  `anthropic`, `llama`, `mistral`). The AI-mode control speaks of
  *enhanced / deterministic* output only; *"Zeli available"* is the user-facing
  capability hint.
- Forbidden raw errors: `Validation failed` / `Action failed` — every error
  is normalized to teacher-facing copy (`normalizeError`).
- No `confirm()`, no inline `<select>`/`<textarea>` in the flow's controls;
  one `<h1>` per page; quota/servers state always beats the client.
- Provenance: source strand/indicator codes, resources and lesson-topic
  derivation are shown and export-verified (e.g. `K2.1.1.1.1`,
  `Poster/ cut out`, three-phase `PHASE 1/2/3` rows in DOCX exports).

Test hooks (`data-*`): `generate-summary`, `generate-config`, `generate-action`,
`allocation-preview`, `allocation-weeks`, `week-card`, `week-number`,
`week-row`, `occurrence-id`, `generate-week`, `generate-lesson`,
`week-coverage`, `generate-total`, `lesson-review`, `quota-banner`,
`coverage`, `lesson-workspace`, `generate-mode`, `class-level-select`,
`selected-template`. First template select: `#cfg-template`; term inputs
`#cfg-term-start` / `#cfg-term-end`; `#cfg-lessons-per-week`;
`#cfg-ai-mode`; `input[id^="period-"]`.

## 7. Verification & production status (2026-10-08)

Local (fresh backend `:8000`, `next start` `:3000`, committed fixtures
`accept.sa` / `accept.pa` / `accept-school-001`, local DB only):

| Suite | Result |
|---|---|
| backend suite (`pytest -m "not live"`) | 2267 passed, 11 skipped |
| UI source + priority-3 API tests | 28/28 |
| `deep-journey` | 21/21 |
| `phase17` run A (quota/allowance/idempotency/exhaustion) | 30/30 |
| `phase17` run B (AI burn-down) | 17/21 · 14/21 · 17/21 across three attempts in one day — the failures are only the AI burn/block chain: the provider's daily token window (shared by run A and the suites earlier the same day) served ~2 of the 5 required burns per run, 429s fell back to deterministic content by design; everything else (quota gating, OFF-after-exhaustion, exports, no-unexpected-requests) stayed green. Re-run on a fresh provider day. |
| `curriculum-workspace` | 75/75 |
| `app-ui` / `app-surfaces` / `app-closure` | 57/57 · 114/114 · 95/95 |
| `entitlement-download` | 28/28 |
| `kg-acceptance` | 31/31 |
| `nursery-acceptance` | 130/130 |
| `lesson-persistence-journey` | 70/70 |
| `wapef-acceptance` | 32/32 |
| `wapef-generate-boundary` | 29/29 |
| `zeli-groq-journey` (success + failure pass) | 56/56 |
| `tsc --noEmit` / `next build` | clean / passes |

**Production (`schemeknit-api/-frontend.onrender.com`): the deployed build
predates Priority 2** — the deploy marker (same scheme, same codes,
`already_counted` re-billing) still returns the pre-P2 objective
(*"Learners can Discuss…"*), health `200` (`version 1.0.5`). There is no
deploy hook, no CI workflow and no Render dashboard access from this
environment (`docs/RENDER_DEPLOYMENT_FIX_REPORT.md`), so a production run of
current code requires an **owner-side redeploy**; until then production
verification is limited to the deployed build. This document's results are
**local-verification only**, stated honestly (Priority 3 §30).

## 8. Non-goals (frozen)

Deterministic generation semantics, activity libraries/pedagogy, weekly
coverage semantics, quota rules, provenance and the lesson model are not
changed by this screen. Zeli/Groq provider work is Priority 4. The frontend
adds no second source of allocation truth.
