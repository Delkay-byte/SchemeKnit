# Deterministic Lesson-Authoring Hardening Report (Priority 2.1)

**Scope:** one focused hardening pass over the deterministic lesson engine
built in Priority 2 — make it more robust, less repetitive, more
curriculum-sensitive and credible against messy real-world Ghanaian schemes,
so an ordinary lesson is usable **without Zeli**.

**Mode:** AI OFF, Zeli OFF everywhere. No architecture change, no new model,
no second lesson schema, no Priority 3 (GENERATE→SCORE→REJECT→REBUILD), no
Priority 4 work. Priority 1 weekly-coverage semantics/quotas/WAPEF persistence
untouched. The Priority 2 rubric (`tests/benchmark_deterministic_lessons.py`)
was **frozen and not modified**.

**Date:** 2026-10-07 · **Base:** `6189b6a` (Priority 2) · **Benchmarks frozen
before the first `src/` edit.**

---

## 1. A–L audit → what was actually wrong

The pre-pass audit (A–L) confirmed the Priority 2 architecture was sound and
found the residual defects in *content derivation and variation*, not in
structure:

| # | Finding | Root cause (file) |
|---|---|---|
| A | Orphan code fragments in prose ("…about .2", "B9. Investigate…") | `allocation_engine._indicator_description` stripped only old dotted codes |
| B | Dangling clause cuts ("…numbers using.") | `lesson_builder._first_clause` never trimmed connector tails |
| C | Verbless objectives ("Attributes of God…", "Food nutrients…") and generic leads ("Explore…", "Discuss…") failed the rubric | `_learner_phrase` had no lead-verb repair |
| D | Duplicate phase steps in one lesson | `_render_pattern_step` had no per-lesson distinct-fallback tracking |
| E | Same starter/addendum stamped on every revisit of a code | `stage` was **always "first"** — `LessonFingerprint` lacked `indicator_code`, so `getattr(fp, "indicator_code", "")` never matched (Priority 2 §18 was dead code) |
| F | Lessons REQUIRING "projector"/"internet"/"laboratory equipment" in non-digital subjects | no display-resource realism filter |
| G | PHE / history / OWOP / early-childhood subjects fell through to default strategy & preference | `SUBJECT_TO_STRATEGY` gaps; `"phe"` preference unreachable; leading-space resource bug (" locally available materials") |
| H | Activity library too small (9 structures); interpreter `activity_type` hint never matched the library | `select_activity` scored only `hint in activity.id` (substring of the id, not the type) |
| I | Verb-matched assessment bank had a dead `"compare_"` key and no entries for common verbs (add, assess, relate, …) | `ASSESSMENT_FOR_VERB` gaps |
| J | Messy GES rows ("B6.1.1.1.1 : …", ". Explain …") left separator artifacts | code regex had no tail → separators survived into phrasing |
| K | French/non-English objectives risked English rephrasing | needed explicit verbatim guard (added/kept) |
| L | Timing already exact (30–80) but untested outside the rubric corpus | no stress test |

---

## 2. Changes (generator-side only; rubric untouched)

### C — Activity library (`src/curriculum/activity_library.py`)
- **9 → 28 `ActivityPattern` entries.** 19 new structures, each with full
  metadata (teacher/learner action, materials, evidence, assessment, support,
  challenge, stages, Ghana context, adaptation): guided reading/retell,
  guided writing, listen & respond, sing & perform, trace/colour/make,
  count & practise, label & annotate, map & locate, debate & argue, assess &
  review, research & report, sequence the steps, troubleshoot & fix, game &
  drill, reflect & discuss, present & share, critique & improve, observe &
  describe, summarise & restate.
- New `activity_types: Tuple[str, ...]` field on every entry + scoring in
  `select_activity`: the interpreter's `activity_type` hint now weighs
  `hint in activity.id or hint in activity.activity_types` (**+1.5**) — the
  hint was previously dead weight.
- **Churn control:** new entries claim only currently-unclaimed verbs (ties
  still favour the earlier entries; two over-claims found in smoke testing
  were moved back — `summarise` stayed solely on `summarise_and_restate`,
  `label_annotate_diagram` dropped the `observation` type so `identify + ict`
  keeps its original winner).
- `ASSESSMENT_FOR_VERB`: dead `"compare_"` key removed; **22 new entries**
  covering the previously unclaimed verbs (add, subtract, multiply, divide,
  count, install, assess, review, relate, recognise, sing, summarise(ise),
  retell, label, locate, sequence, troubleshoot, observe, reflect, present,
  critique).

### D — Interpreter (`src/curriculum/indicator_interpreter.py`)
- New `SUBJECT_STRATEGIES` entries: **`phe`** (movement/drill/game phases) and
  **`early_childhood`** (play/song/hands-on phases).
- `SUBJECT_TO_STRATEGY` extended to mirror `SUBJECT_TO_PROFILE`: PHE,
  physical development, history, geography, economics, government,
  OWOP/owop, biology/chemistry/physics, general agriculture, numeracy,
  elective mathematics, literature in english, general knowledge in art,
  business management/financial/cost accounting, language and literacy,
  early childhood, nursery.
- `SUBJECT_ACTIVITY_PREFERENCE`: added `early_childhood` (the existing `phe`
  key is now reachable through the mapping).
- Fixed the `" locally available materials"` leading-space artifact.

### E — Objectives, prose and progression (`src/curriculum/lesson_builder.py`, `variation.py`)
- `_learner_phrase(indicator, subject)` (objective shaping only — the
  test-pinned `_phrase_performance_indicator`/`_generate_objectives` path was
  **not** touched): strip code + source separator artifacts → French/non-ASCII
  lead kept verbatim → generic lead ("explore/understand/discuss/…") becomes
  **"explain"** with the indicator's wording kept → gerund lead reduced to its
  base verb ("Demonstrating…" → "Demonstrate…") → verbless noun phrase
  receives the subject's verb (`_NOUN_LEAD_VERBS`: PHE→identify, RME→explain,
  maths→use, science→investigate, …) → genuine lead verbs kept verbatim.
- **Follow-up fix (`a38e35c`, found while building the production deploy
  marker):** running every indicator cell of `backend/real_documents/` through
  the repair showed 21 real NaCCA lead verbs absent from the shared
  inventories were falling into the noun path and being mangled
  ("Learners can Listen to …" → "Describe listen to …", "Simplify given
  surds." → "Use simplify …"). Those leads were added to
  `_EXTRA_LEAD_VERBS (listen, give, follow, elaborate, tell, answer,
  experiment, pay, discover, propose, translate, extend, mention, simplify,
  approximate, derive, generate, blend, dramatize, edit, proofread), plus
  four never-noun source shapes are now kept verbatim: slashed verb pairs
  ("Edit/proofread draft …"), adverb leads ("Orally produce …"), dotted list
  markers ("ii. Relative pronouns …") and whole-cell specials
  ("REVISION"/"END OF TERM ASSESSMENT" — first-letter lower-casing mangled
  them into "rEVISION"); dashed list bullets are separators so the non-ASCII
  guard sees the text, and a y-stem rule reduces "Multiplying …" →
  "Multiply …". After the fix a full scan of real_documents/ shows no verb
  sentence taking the noun path (12 regression tests cover these exact cells).
- `_first_clause`/`_trim_dangling_tail`: connector tails ("using", "with",
  "from"…) trimmed so no clause ends on a preposition (filler_text 1 → 0).
- `_render_pattern_step(step, fmt, profile, act_key, used=None)`: ordered
  candidates (indicator bank → subject move → bank → generic fallback →
  step-scoped distinct fallback) with first-unused selection; the pattern loop
  passes a per-lesson `used_phase_descs` set. Empty `used` is byte-identical
  to the old behaviour (no change outside pattern lessons).
- **Repeat stage repaired (§18):** `LessonFingerprint` now records
  `indicator_code`; `build_lesson` derives `stage`/`prior` from matching
  fingerprints in `batch_history`. Revisits get `_repeat_addendum`
  (learner/conclusion/challenge/assignment — variant 1 byte-identical to the
  established text, later revisits rotate through 3 variants) and
  `_STARTER_VARIANTS` (index 0 = "" so a first-occurrence starter is
  byte-identical to before).

### F — Resource realism
- `_IMPOSSIBLE_RESOURCE_RE` (projector, smart/interactive board, laptop,
  tablet, computer lab, laboratory equipment, internet) + `_resource_is_available`
  (**ICT/Computing/digital exempt** — those ARE the subject matter).
- The lesson's display `teaching_learning_resources` is filtered to available
  items (fallback: profile resources, then original), **`source_tlrs` stays
  verbatim** (source authority), and the `{resource}` substitution pool is
  filtered so a banned item never lands in prose.

### G/H — Selection and timing
- `select_activity` unchanged in mechanics (deterministic, ties → library
  order) but now benefits from the metadata above; scoring verified for both
  the new winners and the original winners (churn-guard tests).
- Timing invariant (starter + every step + plenary == `duration_minutes`)
  re-verified for **30–80 min in 5-min steps** by unit test.

---

## 3. Benchmarks (frozen corpora, frozen rubric)

Two corpora were built and snapshotted (`docs/benchmark/hardening_before.json`)
**before any `src/` edit**, then re-run unchanged after
(`docs/benchmark/hardening_after.json`):

- **Expanded:** 40 lessons across 12 subjects (incl. PHE, History, French,
  Career Technology), mixed indicator shapes.
- **Messy:** 19 lessons from real district/GES documents
  (`real_documents/BASIC 6 TERM 1.docx` rows, verbatim — code-prefixed
  separators, French leads, sparse rows).

### Results (AI OFF, Zeli OFF)

| Corpus | Teacher-ready | Mean /75 | Hard failures |
|---|---|---|---|
| Expanded — before | 23/40 (57.5%) | 71.1 | generic_objective 14, generic_activity 1, filler_text 1 |
| Expanded — **after** | **31/40 (77.5%)** | **71.7** | generic_objective 7 |
| Messy — before | 9/19 (47.4%) | 68.9 | generic_objective 7, duplicate_phases 1 |
| Messy — **after** | **12/19 (63.2%)** | **69.6** | generic_objective 7 |
| Priority 2 rubric corpus (frozen) | **11/11 @ 73.7 — unchanged** | — | none |

Criterion movements worth naming:

| Criterion | Expanded | Messy |
|---|---|---|
| objective_specificity | 3.77 → **4.33** (+0.56) | 3.89 → 3.89 |
| teachability | 4.80 → **4.95** | 4.37 → **4.58** |
| resource_realism | 4.55 → 4.55 | 4.21 → **4.47** |
| ghana_context | 4.62 → 4.62 | 4.32 → **4.63** |
| activity_specificity | 4.53 → 4.58 | 4.26 → 4.21 |
| subject_pedagogy_fit | 4.47 → 4.40 | 4.47 → 4.47 |

(The two −0.0x movements are re-shuffles inside a frozen heuristic, not
regressions of content; both corpora's ready counts and hard failures move
strongly in the right direction.)

Reproduce:

```bash
cd backend
./venv/Scripts/python tests/benchmark_hardening.py --out ../docs/benchmark/hardening_after.json
./venv/Scripts/python tests/benchmark_deterministic_lessons.py --out /tmp/after_check.json   # must stay 11/11 @73.7
```

---

## 4. Remaining failures — classified honestly

**Every remaining `generic_objective` hard failure is a measurement gap in the
frozen rubric's `_MEASURABLE_VERBS` inventory, not generic generator prose.**
Verified lesson by lesson: `_GENERIC_OBJECTIVE_RE` does **not** match, the
objective is exactly the indicator's own measurable lead, but the verb is
absent from the rubric's list:

| Failing lesson (both corpora) | Objective lead | In `_MEASURABLE_VERBS`? |
|---|---|---|
| B7.1.1.1.1 | **Add** whole numbers up to 10,000 | no ("add") |
| B7.1.1.2.1 | **Multiply** two-digit numbers… | no |
| B7.1.1.2 | **Install** an operating system | no |
| B6.1.4.1.1 | **Indicate** the similarities… | no |
| B6.1.3.1.1 | **Relate** the central messages of poems… | no |
| B6.3.4.1.1 | **Assess** the changes… | no |
| B6.6.1.1.1 | **Recognise** topics for magazine | no |
| B6.1.1.1.6 | **Skip count** forwards and backwards… | no ("skip") |
| B6.1.1.1.1 / B6.1.1.2.1 (messy) | **Écouter**/Regarder… (French lead) | no |
| B6.1.4.3.1 (expanded) | **Lire** et comprendre… (French lead) | no |
| B6.1.1.1.1 (expanded, below 70-point threshold, not a hard fail) | **Sing** some traditional songs… | has "use" only |

Two further expanded lessons (B6.1.1.1.1, B6.1.3.3.1) sit just under the
70-point readiness threshold with **no** hard failure — score-bound, not
defect-bound.

**Recommended Priority 3 fix (rubric-side, deliberately NOT done here):**
extend `_MEASURABLE_VERBS` with the NaCCA-published leads above and give
French leads their own measurable-verb branch (the generator already keeps
them verbatim). This alone converts up to 14 of the 16 not-ready lessons
across the two corpora. Per the frozen-rubric decision, no generator change
was made to chase those checks.

### Bounded-variant note (accepted limit)
- Repeat-stage addenda rotate through **3 variants per slot**, cycling on the
  4th revisit of the same code.
- Starter variants cover **the first 3 occurrences** of identical starter text
  in one batch; a 4th occurrence in the same batch re-uses the last variant.
  Both bounds are documented here by design — the alternative (unbounded
  text generation) would leave the deterministic path.

---

## 5. Verification

### 5a. LOCAL (this workspace, code at final state)

| Gate | Result |
|---|---|
| Full backend suite | `pytest tests -q -p no:randomly -m "not live"` → **2234 passed, 11 skipped, 5 deselected, 0 failed** (2161 pre-existing + 73 hardening tests) |
| New hardening tests | `tests/test_priority21_hardening.py` → **73/73** (library scale & churn guards, assessment bank, PHE/history/early-childhood strategies, objective cleanup incl. French + the real-scheme verb-lead regression cases, resource realism, 30–80 timing, fingerprint/repeat/starter progression) |
| Frozen rubric benchmark | **11/11 teacher-ready, 73.7/75, no hard failures** — byte-identical summary to the Priority 2 `after.json`, re-verified after the `a38e35c` fix |
| Hardening benchmark | expanded **23→31/40**, messy **9→12/19** (tables above; unchanged by `a38e35c` — those corpora contain none of the fixed leads) |
| Export inspection (GES + WAPEF, Mathematics + Science) | exit 0; Phase 1/2/3 cells carry their own rows; no new duplication |
| Browser journey (real app, AI OFF) | `frontend/e2e/lesson-persistence-journey.js` → **70/70** |
| Curriculum workspace acceptance | `npm run e2e:workspace` → **75/75** |
| Frontend typecheck | `npx tsc --noEmit` → clean |
| Frontend build | `npm run build` → clean |
| Old-vs-new pipeline diff (deploy marker) | same docx + same 2 selected codes through isolated instances of `6189b6a` and `HEAD`: objectives **"Learners can Discuss the formation…"** vs **"Learners can Explain the formation…"** — deterministic, idempotent to re-check (`already_counted` billing) |

**Local environment note (reported, not hidden):** the local Free-Tier
lesson quota for `accept.teacher@schemeknit.test` was exhausted (5/5 for
period 2026-10) by repeated acceptance runs, which disabled the workspace
journey's *Confirm & Generate* button (stated disable with on-page reason —
correct product behaviour). The local dev counter for that one test account
was reset to 0/5 in `backend/teachflow.db` (local fixture only) and the
journey then passed **75/75**. No product code, no entitlement logic and no
production data were touched.

### 5b. PRODUCTION (deployed app, `schemeknit-frontend/-api.onrender.com`)

**Deploy status: the deployed build does NOT contain this change set.**
After pushing `a08e838` and `a38e35c` to `main`, the live backend was polled
for ~55 minutes with the deploy-marker generation (same scheme, same two
codes, re-billing suppressed by `already_counted`). The marker never moved
off the baseline. There is no deploy hook in the repo or `.env`, no CI
workflow, and no Render dashboard access from this environment (the
environment limitation already recorded in
`docs/RENDER_DEPLOYMENT_FIX_REPORT.md` — a redeploy must be triggered from
the Render dashboard, owner-side). **A production run of our code is
therefore blocked on an owner-side redeploy; everything below was verified
against the build currently deployed.**

What IS verified on the live environment (dedicated test accounts created
through the app's own registration flow; no customer data touched; no
quota/payment/entitlement state modified):

| Check | Result |
|---|---|
| API health | `GET /api/health` → **200**, `{"status":"healthy","service":"SchemeKnit","version":"1.0.5"}` |
| Frontend | `GET /` → **200** |
| Registration + login | `POST /api/auth/register/individual` → **200**; `POST /api/auth/login` → **200** (one transient **500** on `register` during a cold start, resolved on retry 20 s later — the known Render cold-start auth blip; four further registrations 200) |
| Full generation flow (API) | upload → detection (single subject, Science/Basic 9) → weeks → `POST /api/generation/{id}/generate` (AI OFF, 2 selected codes) → lessons: **all 200**, deterministic lesson JSON returned |
| Curriculum workspace acceptance | `npm run e2e:workspace` (production URLs, dedicated account) → **75/75 checks passed** |
| Browser persistence journey | `node e2e/lesson-persistence-journey.js` (production URLs, self-registering account) → **68/70**; the 2 failures are `workspace reflects the Through lines chosen before generation` and `Deep Hope set before generation survives into the workspace` — exactly the WAPEF pre-generation save-boundary defect fixed later by `2bf2b9a`, i.e. stale-build symptoms (local run of the same script: **70/70**) |

**Deploy marker (why the deployed build is pre-Priority-2).** The same
scheme (`BASIC 9 SCIENCE SCHEME OF LEARNING.docx`) and the same two selected
codes (`B9.1.1.1.2`, `B9.1.2.1.1`) were generated on an isolated instance of
`6189b6a`, on an isolated instance of `HEAD`, and on production:

| Source | Objective produced |
|---|---|
| `6189b6a` baseline (local, isolated DB) | "Learners can **Discuss** the formation of binary chemical compounds Describe the characteristics …" |
| `HEAD` = `a38e35c` (local, isolated DB) | "Learners can **Explain** the formation of binary chemical compounds Describe the characteristics …" |
| **Production (deployed build)** | "Learners can **Discuss** the formation …" — identical to the `6189b6a` baseline |

Production additionally shows two pre-Priority-2 signatures in the same
lesson JSON: `lesson_topic` is still the strand + sub-strand concatenation
("Diversity of Matter - Materials") instead of the indicator-derived topic,
and `main_activities` has no `PHASE 1 · STARTER` / `PHASE 3 · PLENARY`
boundary rows (the Priority 2 timing invariant's rows) — so the deployed
backend predates Priority 2 entirely.

**Observation (deployed build, reported not changed).** The marker account
was charged 2 lessons per run in the generation response, yet
`GET /api/generation/quota` on production reported
`used: 0, remaining: 5` after four stored lessons. On current code (local
instance of `HEAD`) the same endpoint reports `used: 2` immediately after
two lessons. The deployed build's quota ledger therefore reports differently
from this branch; no production state was altered to probe further.

---

## 6. Known limits & recommendations (Priority 3 input)

1. **Rubric verb inventory** (section 4) — the single biggest remaining lever
   on the two corpora; rubric-side only.
2. **Bounded variants** — 4th+ identical starter in one batch re-uses the
   last variant; 4th+ revisit of one code cycles 3 addenda. By design.
3. `subject_pedagogy_fit`/`phase2` moved −0.0x on the expanded corpus: the
   new PHE/early-childhood preferences re-shuffle some pattern-step wording;
   monitor in Priority 3's scoring loop rather than hand-tuning here.
4. GES export cell resource duplication ("x2" in `export_inspect.py`) is a
   template-merge behaviour predating this pass (source list + activity
   materials rendered together); it is informational and unchanged here.
5. **Production deploy**: the deployed Render build predates Priority 2 and
   cannot be updated from this environment (no deploy hook / CI / dashboard
   access — owner-side redeploy required). Until then, production evidence
   covers the deployed build only; the marker in 5b re-checks our code for
   free (`already_counted`) the moment a redeploy lands.
6. **Deployed-build quota observation** (5b): production reported
   `used: 0/5` after four stored lessons on the marker account, while
   current code reports usage immediately. Reported, not changed — production
   state was not touched.
7. No vector store, no paid dependency, no second lesson model, no AI call was
   added. Zeli remains optional everywhere.

---

## 7. Files changed

| File | Change |
|---|---|
| `backend/src/curriculum/activity_library.py` | 9 → 28 structures, `activity_types` field + scoring, assessment bank +22/−1 dead key |
| `backend/src/curriculum/indicator_interpreter.py` | phe + early_childhood strategies, 20+ subject mappings, preference fix, space artifact |
| `backend/src/curriculum/lesson_builder.py` | `_learner_phrase`, dangling-tail trim, distinct step fallbacks, repeat stage/addenda, starter variants, resource realism |
| `backend/src/curriculum/variation.py` | `LessonFingerprint.indicator_code` + extraction |
| `backend/src/engines/allocation_engine.py` | INDICATOR_CODE_RE-aware description/source/strip |
| `backend/tests/test_priority21_hardening.py` | **new** — 73 tests |
| `backend/tests/benchmark_hardening.py` | **new** — frozen expanded + messy corpora |
| `docs/benchmark/hardening_{before,after}.json` | **new** — snapshots |
| `docs/DETERMINISTIC_LESSON_AUTHORING.md` | Part 7 — hardening section |
| `docs/DETERMINISTIC_LESSON_HARDENING_REPORT.md` | this document |

---

## Appendix — production verification record

Environment: `https://schemeknit-frontend.onrender.com` (frontend),
`https://schemeknit-api.onrender.com` (API, `version 1.0.5`), 2026-10-07.
All accounts created through `POST /api/auth/register/individual` on the live
app; none pre-existed; no customer data read or written; no quota, payment or
entitlement state modified from outside the product.

| Account (dedicated test) | Used for |
|---|---|
| `p21.prod.marker@schemeknit.test` | API marker generations (upload → generate → lessons); re-run ~15× for the deploy poll |
| `persist.teacher.<timestamp>@schemeknit.test` | persistence journey (self-registered by the script) |
| `p21.workspace.prod@schemeknit.test` | workspace acceptance (login flow) |
| `p21.retry*/probe.*@schemeknit.test` | transient-500 retry probes (registration only) |

Commands:

```bash
# marker (deploy status) — local: "Explain", production: "Discuss"
backend/venv/Scripts/python <temp>/marker_driver.py \
  https://schemeknit-api.onrender.com p21.prod.marker@... 'MarkerProd#2026' out.json

# browser journeys against the deployed app
TF_WEB_URL=https://schemeknit-frontend.onrender.com \
TF_API_URL=https://schemeknit-api.onrender.com \
node e2e/lesson-persistence-journey.js          # 68/70 (2 = stale-build WAPEF checks)

TF_WEB_URL=... TF_API_URL=... \
TF_TEACHER_EMAIL=p21.workspace.prod@schemeknit.test \
TF_TEACHER_PASSWORD='Workspace#2026' \
npm run e2e:workspace                           # 75/75
```

Results: health 200 · register/login 200 (one transient 500, retry OK) ·
full generation flow 200 · workspace acceptance **75/75** · persistence
journey **68/70** (stale-build symptoms, see 5b) · deploy marker =
**pre-Priority-2 build** after ~55 minutes of polling across pushes
`a08e838` and `a38e35c` → owner-side redeploy required (blocker, reported).
