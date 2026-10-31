# REA Backlog — Final Acceptance Audit

Audit date: 2026-10-28. Status of this document: **audit findings, no code committed.**

## 1. Verdicts

| Verdict | Result | Basis |
|---|---|---|
| CODE ACCEPTANCE | **FAIL** | Four confirmed defects in committed or uncommitted code (§5). |
| DEPLOYMENT ALIGNMENT | **PASS** (for `43bb266`) | Render API: both services `live` on `43bb266`. Uncommitted work is not deployed. |
| LIVE PRODUCTION BEHAVIOR | **PARTIALLY VERIFIED** | Read-only GETs only. No generation, no Neon access, no quota runtime test. |
| REA BACKLOG CLOSURE | **FAIL** | Items 1, 2, 4 and 5 do not meet their stated acceptance; item 3 passes with caveats. |

## 2. Audited state

- Branch `main`. HEAD `43bb266` equals `origin/main`.
- Working tree: 23 modified files (+713/−82) that predate this audit, plus an untracked `backend/teachflow.db.bak-20261008-012012` that also predates it. These are **not committed** and were **not modified** by this audit. They include the cache-key fix described in §4A. Review and commit them separately.
- No commits, pushes, deploys, or production writes were made by this audit.

## 3. Test and tooling results

Host caveat: this host's Word COM server (`docx2pdf`) crashes the interpreter (`Windows fatal exception: code 0x800706be`) whenever an export test reaches it. This happens on pristine `43bb266` as well. For all full-suite runs below, `docx2pdf` was disabled via a runner outside the repo (`audit_probe/run_suite.py`). That matches Render, which has neither Word nor LibreOffice.

| Check | Command / source | Result | Exit |
|---|---|---|---|
| Full backend suite, working tree | `python -m pytest tests -q` (runner, Word disabled) | **2466 passed, 14 skipped, 0 failed** | 0 |
| Full backend suite, pristine `43bb266` (backend only) | same, archive without `frontend/` | 2394 passed, 27 skipped, **49 failed** | 1 |
| Pristine failures | all source-reading tests opening `frontend/` (36 UI-source tests + 13 tests reading frontend/config files) | environmental: the archive lacks `frontend/` | — |
| PostgreSQL quota driver | `tests/test_postgres_quota_driver.py` against disposable PG 16.15 | 4 passed | 0 |
| PostgreSQL migrations + quota | `tests/test_postgres_migrations.py` + driver file | 8 passed | 0 |
| Frontend type check | `npx tsc --noEmit` | clean | 0 |
| Frontend build | `npm run build` | succeeded | 0 |
| Frontend lint | `npm run lint` | **not configured**: `next lint` prompts for an ESLint setup; no config exists in the repo | 1 |
| Frozen corpus, deterministic | `tests/benchmark_deterministic_lessons.py` | 11/11 teacher-ready, mean 74.2/75 | 0 |
| Frozen corpus, expanded | `tests/benchmark_hardening.py` | 40/40 teacher-ready, mean 73.3/75 | 0 |
| Frozen corpus, messy | `tests/benchmark_hardening.py` | 19/19 teacher-ready, mean 72.3/75 | 0 |

First-pass rates were not separately extracted; teacher-ready is the measured figure.

The disposable PostgreSQL instance was a container I created (`schemeknit-audit-pg`, loopback port 55439, database `schemeknit_audit_test`). It has been removed. Nothing ran against `agro-pg` (port 5432, not a SchemeKnit database) or any production URL.

## 4. Five-priority matrix

Status key: PASS / FAIL / PARTIAL / BLOCKED / NOT TESTED.

### Priority 1 — Deterministic lesson quality and timing: **FAIL**

| Requirement | Evidence | Status |
|---|---|---|
| Phase durations sum to lesson duration | Scanned all 70 frozen-corpus lessons: 0 violations | PASS |
| No strand-concatenation topic | 0 hits | PASS |
| No slot-fill fragments (backlog item 1 test strategy) | 4 lessons contain a double period (`"…techniques.. Summarise"`, `"…experiences.. Also"`, traced to 3 source indicators B6.1.3.1.1, B6.1.1.1.4, B6.1.1.1.5). 7 Mathematics/Science lessons contain the broken clause `"; the class agrees the strongest evidence and"` | **FAIL** |
| Frozen corpora still pass the rubric | 11/11, 40/40, 19/19 teacher-ready | PASS, but **the rubric does not detect the artifacts above**; the backlog's claim that slot-fill prose was "already shipped" is not supported |
| P4 quality gate and bounded rebuild | Covered by suite (P4 tests) | PASS (suite) |

Reproduction: `audit_probe/prose_scan.py`, `audit_probe/prose_distinct.py`, output `audit_probe/bench_hardening.json`.

### Priority 2 — Ghanaian localization bank: **PARTIAL**

| Requirement | Evidence | Status |
|---|---|---|
| All 12 profiles have ≥2 examples | `GHANA_CONTEXT_BY_SUBJECT`: 12 keys × 3 examples; test suite | PASS |
| Alias/spacing/unknown handling, deterministic rotation | `ghana_context_for`, `tests/test_ghana_context_bank.py` | PASS |
| Bank reaches lessons | Wiring is **only** into `assessment_items` via `context_hint` (`lesson_builder.py` ~2712–2735). Activities do not receive it, contrary to the backlog's wording. | PARTIAL |
| Every profile reachable via the real builder | Early-years profiles (`early_childhood`, `nursery`) are skipped: `if not early_years:` gates the whole assessment block. Probe: the bank-fragment scan found 0 of 24 early-years lessons (KG 1, KG 2, Nursery 1, Nursery 2; 6 lessons each), and single-lesson checks found no Ghanaian wording for KG or Nursery. The other 10 profiles appear in assessment items (6/6 lessons for the fragment-matched profiles; wording confirmed on single lessons for the rest). | **FAIL** for 2 of 12 profiles |

Owner decision needed: whether early-years lessons should carry local framing (currently excluded by design, since early-years skips assessment design).

### Priority 3 — Assessment, DoK, rubric, differentiation: **PARTIAL**

| Requirement | Evidence | Status |
|---|---|---|
| Four analytic bands (exceeds / meets / developing / needs support) | `assessment_design.py` `_LEVEL_NAMES`: "4 — exceeds the standard" … "1 — needs support" | PASS |
| Four points per criterion, consistent totals | Suite (`test_phase3_assessment_dok.py`) | PASS (suite) |
| DoK responds to indicator/class/duration | Suite only | NOT TESTED beyond suite |
| MA/HP/NS woven into activities | Suite (`test_differentiation_uses_ma_hp_ns_and_is_woven`) | PASS (suite), not inspected in output |
| Preserved through AI enrichment, persistence, DOCX/PDF | Not exercised in this audit | NOT TESTED |
| Representative Nursery → SHS coverage | Not independently verified | NOT TESTED |

### Priority 4 — Cache, duplicates, recovery, quota, batch semantics: **FAIL**

**4A. Cache correctness — FAIL in HEAD, fixed in uncommitted work.**
- Committed `43bb266`: `_enrichment_cache_hash` is called without `rewrite_mode`, `additional_context` or the resolved mode label. Two different requests on the same lesson/section (e.g. "make it practical" vs. "another version") return the same cached result. Evidence: the removed lines in `git diff -- backend/src/routers/ai_regeneration.py`.
- Uncommitted working tree: the key now covers those inputs, and enrich-lesson keys on the template. Tests in `test_ai_cache_double_submit.py` pass in the 2466-passing run.
- Status: FAIL at HEAD; PASS in the working tree pending review and commit.

**4B. Idempotency and double submission — PARTIAL.**
- Sequential replay (live, PostgreSQL, real API): the second identical generate returned `already_generated_occurrence_ids` for both occurrences; lesson rows stayed at 2, no duplicates, quota stayed at 2. **PASS.**
- Concurrent double-submit (two requests released together): both returned 200. The second request ran after the first finished and reported both occurrences as already generated. No duplicates, quota at 2. **Not reproduced as a race.**
- Why: `generate_lesson_plans` is an `async def` that runs the synchronous pipeline on the event loop. A health probe during a 0.34 s generation waited 0.29 s (one sample), so requests are effectively serialized in production's single `uvicorn src.main:app` process (`docs/PRODUCTION_OPERATIONS.md`).
- Consequence: the 409 in-flight guard (`generation.py` ~867) cannot be observed by a second request in this topology. It is effectively unreachable. Verification under multiple workers was not possible in this audit.

**4C. Interrupted jobs and recovery — FAIL (resume not implemented).**
- Startup sweep fails orphaned `pending`/`processing` jobs (`service.py` ~372). Accepted lessons survive reload.
- Partial batches report `generated_occurrence_ids`, `rejected_occurrence_ids` and `pending_occurrence_ids`, which is honest.
- There is no resume or continue-from operation. A retry is a full regeneration request. The backlog asked for resume semantics; this is not met.

**4D. Quota reservation, release and refunds — FAIL (defect reproduced).**
- Reservation is correct: idempotent unit rows with `RETURNING`, guarded `UPDATE`, rollback on refusal. PostgreSQL quota-driver tests pass (4); with the migration tests, 8 pass on PostgreSQL.
- Defect, reproduced live in-process against PostgreSQL (`audit_probe/pg_failure_after_persist.py`): injecting a failure after lesson rows are committed produced `500 Generation failed`, job `failed`, **2 lesson rows persisted**, **0 usage units charged**. The teacher has lessons they were not charged for while being told generation failed. Cause: `create_lesson_plan` commits row by row, and the `except` path releases the whole reservation.
- The failure window is narrow (server-side error between persistence and replacement), so this is a quota-integrity defect, not a routine failure.

**4E. Honest batch semantics — PARTIAL.**
- API responses name generated, rejected, pending and already-generated occurrences. PASS.
- The UI batch notice (uncommitted diff, `generate/[id]/page.tsx`) covers gate-refused lessons only. Quota-skipped lessons on the zero-click Autopilot path are not announced after the auto-run (see Priority 5). FAIL for that path.

### Priority 5 — Safe reduction of teacher decisions: **PARTIAL**

| Requirement | Evidence | Status |
|---|---|---|
| Unambiguous scheme progresses zero-click | Upload sets `schemeknit.autopilot_intent`; generate page consumes it once and fires only when `plan.ready` (`upload/page.tsx` 189; `generate/[id]/page.tsx` 422–444) | PASS (code) |
| Ambiguity asks for missing info, then hands off | `confirm-subject` sets intent and redirects (`upload/page.tsx` 176–190) | PASS (code) |
| `needs_review` cannot be generated via API | Server gate rejects with 409; `test_generate_rejects_needs_review_occurrence_server_side` | PASS (suite) |
| WAPEF and quota interrupts still fire | Autopilot blockers card; suite | PASS (suite) |
| Quota restrictions communicated honestly | Plain-visit card shows quota-skipped count, but the zero-click auto-run's result card lists only generated lessons and `batchNotice` ignores quota-skipped occurrences | **FAIL** |
| Browser journey end to end | Not run in this audit | NOT TESTED |

## 5. Confirmed defects

1. **Cache key incomplete in HEAD (P4A).** Fixed only in the uncommitted diff. Action: review and commit that diff, then deploy.
2. **Failure after persistence leaves uncharged lessons (P4D).** Reproduction: `audit_probe/pg_failure_after_persist.py` (result in §4D). Proposed fix: when lesson rows were already written, keep their units charged and report a partial outcome; or make persistence, replacement and rehoming one transaction. Not implemented here: `generation.py` already has uncommitted changes.
3. **Zero-click auto-run hides quota-skipped remainder (P5/P4E).** Proposed fix: in `runGeneration`, add a notice when `response.pending_occurrence_ids` is non-empty and the quota is enforced. Not implemented here: `generate/[id]/page.tsx` already has uncommitted changes.
4. **Prose artifacts in deterministic lessons (P1).** 4 double-period lessons and 7 broken-clause lessons. Proposed fix: normalise terminal punctuation in `_normalize_prose` and fix the template emitting `"; the class agrees the strongest evidence"`; add a regex regression over the frozen corpora (the backlog's own test strategy).

Owner decisions (not defects to fix unilaterally):
5. **Early-years Ghanaian framing unreachable (P2).** Decide whether early-years lessons should carry it.
6. **In-flight guard unreachable under synchronous generation (P4B).** Fix requires running generation off the event loop (threadpool or background job). This is an architectural change.
7. **No resume operation (P4C).** Backlog item 4 asked for it; decide whether it is in scope.

Other findings:
- Test host crashes on Word COM (`docx2pdf`). Export tests reach the real converter; add a guard or mock.
- Documentation is stale: `docs/pilot/production-version.md` and `docs/PRODUCTION_READINESS.md` state production is at `3ef1a41`, which Render contradicts. Correct them.
- ESLint is not configured.

## 6. Production verification

- Render API (read-only GET, key from environment, never printed):
  - `schemeknit-api` (`srv-damsbb1ntn7c73d7eg10`): deploy `dep-db99rsajnfac73bg50i0`, status `live`, commit `43bb266`, created 2026-10-16T21:58:09Z, auto-deploy on.
  - `schemeknit-frontend` (`srv-damt6sjm8hqs7398lfl0`): deploy `dep-db99ta0m7kps73cioiug`, status `live`, commit `43bb266`, created 2026-10-16T22:01:12Z, auto-deploy on.
- `GET https://schemeknit-api.onrender.com/api/health` → 200 `{"status":"healthy","version":"1.0.5"}`. The version string does not identify the commit; alignment comes from the Render API.
- `GET https://schemeknit-api.onrender.com/api/service-status` → 200, maintenance inactive.
- `GET https://schemeknit-frontend.onrender.com/` → 200.
- **Not performed:** any generation, login, or teacher-account action on production; Neon database inspection; schema or migration read; quota runtime denial test (§13h of `docs/QUOTA_ACCOUNTING_INCIDENT.md`); historical reconciliation (§13e). These require owner authorisation and remain BLOCKED.
- Production quota remains NO-GO per the incident documentation until §13e/§13g and the §13h test are executed.

## 7. Owner's smallest next action

Review the 23-file uncommitted diff (it contains the P4A cache fix and the rubric/quality-gate/autopilot changes), then decide on defects 2–4 and the three owner decisions in §5. The working tree was left untouched by this audit.

## 8. Reproduction artefacts (outside the repository)

`C:\Users\SAVIOUR\AppData\Local\Temp\opencode\audit_probe\`: `run_suite.py`, `ghana_reach.py`, `prose_scan.py`, `prose_distinct.py`, `pg_double_submit.py`, `pg_loop_block.py`, `pg_failure_after_persist.py`, `pg_setup.py`, and the JSON/text outputs from each run. Outputs from `benchmark_hardening.py` and `benchmark_deterministic_lessons.py` are alongside them.

---

## 9. Remediation — 2026-10-28

Status of this section: **working-tree remediation and its evidence. Not committed, pushed, deployed, or run against production accounts.** The findings in §§1–8 are preserved unchanged.

### 9.1 Scope and safety

- Base: `main` at `43bb266` (`origin/main`). All edits remain uncommitted in the working tree.
- The pre-existing 23-file diff was preserved, not reset or discarded. A byte copy and a recoverable stash were made before any edit:
  - `C:\Users\SAVIOUR\AppData\Local\Temp\opencode\rea_remediation_backup\working_tree.patch` (500,292 bytes)
  - stash commit `c79aafb27c9d21355554396ccaf9836e00fc2bc8`
- No production writes, Neon access, Render deploy, push, billing/secret change, or live generation on production accounts. The only production requests were read-only `GET`s.
- Browser E2E, export smoke tests, and API runs used an **isolated copy** of the local SQLite DB (`e2e_teachflow.db`), `AI_MODE=OFF`, on loopback ports; no real teacher account or production database was touched.
- No targeted commit was made. The new hunks are interleaved with the pre-existing uncommitted pass in shared functions/files (notably `generation.py`, `ai_regeneration.py`, `lesson_builder.py`, the generate page, and several tests), so staging a clean, separately reviewable unit was not possible without including unrelated work. Nothing was pushed.

### 9.2 Confirmed defects — fixes and causal evidence

Each regression test was written first and observed failing. Where the defect exists at `43bb266`, the same test was also run against a disposable worktree of pristine `43bb266` on PostgreSQL.

| # | Defect (original finding) | Fix in working tree | Regression proof |
|---|---|---|---|
| 1 | Cache key incomplete (P4A): rewrite mode/instruction/mode label; provider name only; `|`-joined fields could collide | `_enrichment_cache_hash` now hashes a structured JSON payload (`v=2`) containing lesson, section, provider **and model**, content and `extra` (JSON-encoded config). Both enrich paths pass `model`; full enrichment keys the template too | `tests/test_ai_cache_double_submit.py` 12 passed. New tests cover `content="x|y", extra="z"` vs `content="x", extra="y|z"` (must differ) and a provider model switch (must bypass the cache). Existing replay/rewrite/context variants still pass |
| 2 | Late failure left persisted lessons charged **0 units** (P4D) | Accepted lessons, replacement delete, rehome, unused-unit release and job totals now commit as **one transaction** (`commit=False` on `create_lesson_plan`, `delete_lesson_plans_by_ids`, `rehome_lesson_plans_for_scheme`, `update_job`, `release_lesson_units`). `persistence_committed` is set only after that commit; handlers `rollback()` first and release the reservation only when it is false | `tests/test_generation_quota_atomicity.py` 3 passed on SQLite and PostgreSQL. The tests assert **database state**: lesson rows, per-unit ledger rows, `period.units_used`, and job status — not the HTTP status. On pristine `43bb266`/PostgreSQL the replacement-failure test fails with `a failed run must not leave persisted lessons: 3 lesson row(s) survived` and no charged units; it passes after the fix (0 lessons, 0 units, job `failed`). Control: a successful run leaves 3 units for 3 indicator codes with lessons > 0 |
| 3 | Concurrent double-submit ran twice (P4B) | Generate endpoint is now a synchronous `def` (FastAPI threadpool) plus a process-wide **non-blocking** lock keyed by `(owner, scheme)`. The committed in-flight job read remains the cross-process fallback | `tests/test_generation_concurrency.py` 1 passed on SQLite and PostgreSQL. Two real HTTP requests are released through a barrier inside the in-flight read (not a manually-set flag), each with its own session. Pristine `43bb266`/PostgreSQL: both returned 200 and both reported `total_lessons: 6` (duplicate runs). Fixed: `[200, 409]`, exactly 1 job, units = 3, `units_used` = 3 |
| 4 | Interrupted/orphaned jobs (P4C) | Both generate and status calls reclaim `pending`/`processing` jobs older than the existing **60-minute** threshold; status now returns `created_at`. The generate page shows a `data-generation-recovery` banner with the stored error and a “Try again” action that re-plans through the Autopilot endpoint | `tests/test_generation_recovery.py` 3 passed. On pristine `43bb266`/PostgreSQL the stale-generate test is blocked (409) and the status poll stays `processing`; both fail, while the recent-job guard passes. Fixed: stale job becomes `failed` with “interrupted”, generation proceeds; a recent pending job still returns 409. Source contract for the banner/retry is in `tests/test_autopilot_ui_source.py` |
| 5 | Zero-click run hid quota-skipped remainder (P5/P4E) | Post-run summary (`data-autopilot-outcome`) is driven by the POST response (`generated`, `already_generated`, `rejected`, `pending`) plus the **server plan's** `counts.quota_skipped_count` / `needs_review_count`. Manual runs (no plan) never claim quota-wait counts | `tests/test_autopilot_ui_source.py` 19 passed. Browser E2E confirms the server plan and result surface: `22 lesson plans found · 5 can be generated this month · 17 wait for next month`, the exhausted-allowance blocker, and an unlimited plan showing `22 can be generated this month` |
| 6 | Deterministic prose artefacts (P1) | `_clean_focus_text` strips leading codes/separators and terminal punctuation and collapses dotted artefacts before template embedding; `_normalize_prose` collapses `..`/`. .`; objectives and assessment get the same mechanical pass; the two broken plenary templates now read “agrees **on** the strongest evidence / best statement” and “identifies one open question” | `tests/test_prose_composition.py` 6 passed after the fix; all 6 fail on pristine `43bb266`. Frozen corpora remain green: 11/11 (mean 74.2), 40/40 (73.3), 19/19 (72.4, previously 72.3), no hard failures |
| 7 | Early-years localization unreachable (P2) | One bounded clause from `ghana_context_for(profile.key, variant=week+position)` is added to the early-years starter, which is the real KG/Nursery builder path. Rotation is deterministic; Basic-class lessons are untouched; one clause per lesson | `tests/test_early_years_localization.py` 5 passed. On pristine `43bb266` the four KG/Nursery cases fail (`found []`) while the Basic-class negative passes. Fixed: exactly one `early_childhood`/`nursery` clause, three distinct clauses across three weeks, no Basic-class leakage |

Quota policy was not changed: **one unit per `(scheme_id, indicator_code)` per calendar month**. `test_matrix_h_repeated_indicator_is_two_occurrences_one_unit` keeps two cross-week occurrences of `B9.1.3.1.1` as two lessons but **one** quota unit. No per-lesson charging was introduced; the atomicity control asserts 3 units for 3 codes while multiple lessons exist.

### 9.3 Verification runs

| Check | Command / environment | Result |
|---|---|---|
| High-risk targeted backend set | 12 test modules: generation atomicity/concurrency/recovery, prose, early years, cache, Autopilot API/UI source, KG, Nursery, quality gate, exports | **267 passed** |
| Full backend suite (working tree) | `pytest tests -q` from `backend/`, Word COM converter disabled by an external pytest plugin, SQLite | **2488 passed, 15 skipped, 0 failed** (2503 collected, 1:00:32; JUnit: 0 failures, 0 errors) |
| PostgreSQL migrations | `POSTGRES_MIGRATION_TEST_URL=postgresql+psycopg://…` on disposable PostgreSQL 16.15 | **4 passed** |
| PostgreSQL quota / concurrency / recovery / driver | `TEACHFLOW_TEST_DATABASE_URL=postgresql+psycopg://…`: `test_generation_quota_atomicity.py`, `test_generation_concurrency.py`, `test_generation_recovery.py`, `test_postgres_quota_driver.py` | **11 passed** |
| Pristine baseline, same new tests, PostgreSQL | Detached worktree of `43bb266`, same disposable server/driver | **15 failed, 3 passed** — expected RED: 3 lesson rows survived with 0 units; two 200s and duplicate runs; stale job blocked/`processing`; all 6 prose tests failed; all 4 KG/Nursery cases found no clause |
| Frontend type check | `npx tsc --noEmit` from `frontend/` | **clean** |
| Frontend web build | `npm run build:web` from `frontend/` | **succeeded** |
| Autopilot browser E2E | `node e2e/autopilot-acceptance.js` against current code on `localhost:3100` + local API `localhost:8000`, isolated DB copy, AI OFF, locally primed unlimited account | **39 passed, 0 failed**; includes capped/unlimited counts, exhausted blocker, reload restores job and fires no run, WAPEF/class interrupts, manual flow, 375 px fit, zero page errors |
| Frozen corpus, deterministic | `tests/benchmark_deterministic_lessons.py` | **11/11 teacher-ready, mean 74.2/75**, 0 hard failures |
| Frozen corpus, expanded | `tests/benchmark_hardening.py` | **40/40 teacher-ready, mean 73.3/75**, 0 hard failures |
| Frozen corpus, messy | `tests/benchmark_hardening.py` | **19/19 teacher-ready, mean 72.4/75**, 0 hard failures |
| Export smoke, real files | Local API on the isolated DB, existing 5-lesson Science job | DOCX 200 (43,748 B), XLSX 200 (5,963 B), ZIP 200 (187,266 B, 5 real `.docx` entries), PDF 200 (35,580 B, 15 pages, 30 tables) through the structured renderer |
| Production read-only | `GET /api/health`, `GET /` | API `healthy` `1.0.5`; frontend 200 |
| Deployment alignment | Render API, read-only | API deploy `dep-db99rsajnfac73bg50i0` and frontend deploy `dep-db99ta0m7kps73cioiug` both `live` on `43bb266` |

The PDF smoke used a separate wrapper process that patched out `docx2pdf` **before** importing the app, so it exercised the structured PDF path that Render uses. The host Word COM backend was not invoked (see §9.5).

### 9.4 Separate verdicts

| Verdict | Result | Basis |
|---|---|---|
| **CODE ACCEPTANCE** | **PASS** | All four confirmed defects and owner decision 5 are fixed in the working tree, each with a regression test that is RED on pristine `43bb266` where the defect exists and GREEN on the fix. The full backend suite is green (**2488 passed, 15 skipped, 0 failed**), as are the targeted and PostgreSQL gates. This verdict covers the reviewed working-tree code only; it is not deployed. |
| **POSTGRESQL QUOTA INTEGRITY** | **PASS** | On PostgreSQL 16.15 + psycopg 3.3.5, the DB-state regression test fails on pristine `43bb266` (3 lesson rows, 0 units after a late failure) and passes on the fix (0 lessons, 0 units, job `failed`). Successful runs charge exactly one unit per indicator code, the aggregate matches the per-unit ledger, and atomicity/concurrency/recovery/driver gates total 11/11. |
| **FRONTEND ACCEPTANCE** | **PASS** | Type check clean, web build succeeds, and the current code passes the 39-check Autopilot browser journey on a local stack. The failed-job recovery banner/retry is source-contract tested; a live crash-recovery browser scenario was not staged. |
| **RECOVERY AND RESUME** | **FAIL** | Stale-job reclamation, honest terminal status and one-click retry are verified. There is still **no resume/continue-from-partial-batch operation**; “Try again” re-plans and re-runs pending occurrences through the safe endpoint. The backlog's resume requirement is therefore unmet, not hidden. |
| **DEPLOYMENT ALIGNMENT** | **PASS** | `HEAD == origin/main == 43bb266`, and both Render services remain `live` on `43bb266`. The remediation is uncommitted, so **none of these fixes are live**; this is alignment of the unchanged base, not of the fix. |
| **LIVE PRODUCTION BEHAVIOR** | **NOT TESTED** | Only read-only health/frontend GETs. No production login, generation, quota-denial, migration, or Neon/SQL access was performed. |
| **REA BACKLOG CLOSURE** | **FAIL** | The confirmed defects (cache, quota integrity, concurrency, prose, Autopilot messaging) and the early-years localization decision are addressed in the working tree. Resume is still missing, and the fixes are unshipped, so the backlog is not closed. |

### 9.5 Residual gaps and limitations

- **Resume is absent by design decision, not oversight.** A retry uses the existing idempotent generate path and re-plans the remaining occurrences; there is no partial-batch continuation token or resume operation.
- **Word/LibreOffice PDF conversion was not run.** The host’s Word COM automation aborts the Python interpreter with `Windows fatal exception: code 0x800706be`. All audit runs disabled `PDFExportEngine._try_docx2pdf` (matching Render, which has neither Word nor LibreOffice). DOCX, XLSX, ZIP and the **structured** PDF renderer were exercised; DOCX→PDF conversion fidelity is **NOT TESTED** on this host.
- **Concurrency guarantee is process-wide.** The lock protects the supported single-`uvicorn` deployment. Under multiple workers/processes the committed in-flight row remains the fallback but retains a read-then-create window; a database advisory lock or unique in-flight constraint would be required to close it. Multi-worker behavior was not tested.
- **The lock registry retains one small `threading.Lock` per generated-from scheme** for the process lifetime. It is bounded by distinct schemes, not per request, but grows monotonically in a long-lived process.
- **The 60-minute stale threshold** is conservative for normal runs (seconds/minutes). A legitimate run longer than 60 minutes could be reclaimed by another request; no such run is expected.
- **Post-commit failure reporting:** if an error occurs after the atomic persistence commit (for example while reading quota status or consuming an AI credit), the API can still return 500 even though the lessons and units are durable. Quota remains consistent and a reload restores the completed job, but the immediate response is not a success.
- **Documentation is still stale:** `docs/pilot/production-version.md` and `docs/PRODUCTION_READINESS.md` still state `3ef1a41`; Render is on `43bb266`. This was not changed here.
- **ESLint remains unconfigured** (`next lint` prompts for setup), as recorded in §3.
- **No commit was made.** The work must be reviewed and committed deliberately; `frontend/tsconfig.tsbuildinfo` is a generated file modified by type-checking/build and must not be committed. The pre-existing `backend/teachflow.db.bak-20261008-012012` is also untracked and out of scope.

### 9.6 Smallest next action

Review the working-tree diff, commit it as one coherent change (or split it only after a manual hunk review), and deploy during an authorised window. After deployment, the production quota denial/reconciliation tests in `docs/QUOTA_ACCOUNTING_INCIDENT.md` §13e/§13g/§13h still have to be executed before production quota is treated as GO. Until then, the live site remains on `43bb266` and the verdict for live production behavior stays **NOT TESTED**.

## 10. Release remediation and local acceptance — 2026-10-28 (round 2)

Status of this section: **working-tree implementation and local verification only. Nothing was committed, pushed, deployed, or run against production data, Neon, Render settings, secrets, billing, or production accounts.** Sections 1–9 are preserved unchanged. This section supersedes the §9.4/§9.5 statement that resume was absent and the concurrency guard was process-local only.

### 10.1 Safety and reproducible local environment

- Base remains `main` at `43bb266`; `origin/main` remains `43bb266`. No `git reset --hard`, `git clean`, stash, or fresh checkout was used. The pre-existing working tree and this report were preserved.
- Isolated PostgreSQL 16.15 container, local only:
  - `docker run --name schemeknit-pg-release -e POSTGRES_PASSWORD=<local-only-test-password> -e POSTGRES_DB=schemeknit_release -p 127.0.0.1:55433:5432 -d postgres:16-alpine`
  - separate databases `schemeknit_release`, `schemeknit_migrations`, `schemeknit_e2e`
  - connection target used by tests/browser: `postgresql+psycopg://postgres:<local-only-test-password>@127.0.0.1:55433/…`
- Backend (documented FastAPI entry point; synchronous generate route runs in the threadpool):
  - `python -m uvicorn src.main:app --host 127.0.0.1 --port 8000` (browser acceptance used a repository-external wrapper that makes the host report no Word/LibreOffice converter, matching Render, so the structured PDF path is selected).
  - `GET http://127.0.0.1:8000/api/health` → `healthy`, version `1.0.5`.
- Frontend:
  - `npm run build:web` (38/38 static pages, production web build)
  - `npm run start -- -p 3100`; `GET http://127.0.0.1:3100/login/` → HTTP 200.
- Browser tests used only synthetic accounts in `schemeknit_e2e`: `accept.pro.20261028@schemeknit.test` (locally primed Pro entitlement) and generated `autopilot.one.*` accounts. No production account or quota was touched.
- AI was `OFF`; all lesson generation in this section was deterministic. No external provider was called.

### 10.2 What was implemented in this round

| # | Gap from §9 | Implementation | Regression/acceptance proof |
|---|---|---|---|
| 1 | Concurrency guard was process-local (`threading.Lock`) | Added a PostgreSQL **session advisory lock** per owner+scheme on a dedicated connection held for the whole request: key = first 8 bytes (signed) of `SHA-256("schemeknit:generation:{user_id}:{scheme_id}")`, acquired with `pg_try_advisory_lock`; the process lock remains the local gate. Cleanup is best-effort, invalidates a broken pooled connection, and always releases the local lock. SQLite/desktop keeps the single-process lock. | `test_postgres_advisory_lock_blocks_a_second_connection` holds the same key from an independent PostgreSQL session and proves `POST /generate` returns **409**, creates **no job**, and then succeeds after the external holder unlocks. PostgreSQL concurrency/quota/recovery/resume set: **19 passed**. |
| 2 | “Try again” re-planned; no true resume | Added `POST /api/generation/{scheme_id}/generate/resume` with `{job_id}`. The original job is reused; its `config_snapshot` stores `planned_occurrence_ids` and `blocked_for_review_occurrence_ids` before generation. Resume excludes already-persisted occurrences, review-blocked rows, and special periods; it sends only the remaining planned occurrences through the normal generation, quality-gate, atomic-persistence and quota paths. Quota is charged once per `(scheme, indicator_code)`; already-charged codes are detected so a resume is not falsely refused. | `tests/test_generation_resume.py` **6 passed** on SQLite and PostgreSQL: same job reused, only pending occurrences generated, existing lesson preserved, idempotent replay, late-failure rollback, quota refusal, status-resumable IDs. Browser journey **15/15** (below). |
| 3 | A reload after a server restart still hid the orphaned job | `/api/generation/scheme/{scheme_id}/status` now reconciles stale `pending`/`processing` jobs before returning the latest job, matching the generate and job-status paths. Status responses expose `planned_occurrence_ids`, `resumable_occurrence_ids`, `pending_occurrence_ids`, `blocked_for_review_occurrence_ids`, and `can_resume`. | `test_scheme_status_reclaims_a_stale_job_on_page_reload` was RED (`processing`) before the fix and GREEN after. Full recovery file passes. |
| 4 | Recovery banner could appear for a still-running job | The page gates the banner on the server's `can_resume` (terminal job + real resumable work), not merely on planned-but-unwritten IDs; resume results now report rejected/resumable counts honestly, and a failed resume keeps the retry fallback. | Updated `tests/test_autopilot_ui_source.py` source contracts (20 passed) plus browser resume journey. |
| 5 | Prose composition artifacts remained beyond the two audit examples | Added noun-safe focus (`_noun_focus`) so templates do not duplicate the source command (“learners investigate Investigate…”), collapse doubled commands/connectors and stray `". :"` separators, and trim noun-dependent tails (“… to the nearest” before a template's “and”). | New `tests/test_corpus_prose_quality.py` **2 passed** over all three frozen corpora (70 lessons): no double periods, doubled words, stray separators, empty interpolations, placeholders, or dangling connectors. Corpus scan fell 29 → 17 → 9 → 7 matches; the final 7 were manually reviewed as legitimate stranded prepositions (“asks for.”, “rounded to.”), not artifacts. The allocation distinct-content assertion was made case-insensitive because mid-sentence focus is now intentionally lower-case; it still requires the indicator's content words. |
| 6 | Quota semantics at exhaustion were inconsistently tested | Kept the documented rule: one unit per `(scheme, indicator_code)` per calendar month; regenerating an already-paid occurrence consumes **zero** units and replaces in place, even at exhaustion. Sixth **new** indicator still returns 403 before any job/lesson/counter movement. | `test_quota_enforcement_journey.py` now asserts both sides: sixth distinct code 403/no side effects; exhausted-account regeneration 200, used stays 5, exactly 5 lessons, no duplicate occurrence. PostgreSQL quota atomicity/driver tests pass. |
| 7 | Cache/idempotency (carried from §9) | Structured JSON cache payload covers lesson, section, provider **and model**, content, rewrite mode, additional instruction, mode label, and template; section cache preserves activity structure. | `tests/test_ai_cache_double_submit.py` remains green inside the final full suite (duplicate submit, rewrite variants, collision, model switch, structured activities). |

The recovery contract is now: the same job continues; completed occurrences are never deleted or duplicated; review-blocked items stay blocked and visible; special periods are not silently generated; quota is charged only for unpaid indicator codes; a hard process death leaves the planned set in the job snapshot and the next status load surfaces it.

### 10.3 Verification evidence (final tree)

| Check | Command / environment | Result |
|---|---|---|
| **Full backend suite** | `pytest tests -q -p disable_word_com` from `backend/`, SQLite, Python 3.13.13; external plugin only reports the host as having no Word/LibreOffice toolchain | **2499 passed, 15 skipped, 0 failed** — exit **0** (21:15). The host still printed Windows fatal-exception diagnostics from Word COM in converter-forced tests; those tests did not fail, but DOCX→PDF fidelity is not accepted as verified (see 10.4). |
| **PostgreSQL migrations** | `POSTGRES_MIGRATION_TEST_URL=postgresql+psycopg://…/schemeknit_migrations pytest tests/test_postgres_migrations.py` | **4 passed** |
| **PostgreSQL quota/concurrency/recovery/resume/driver** | `TEACHFLOW_TEST_DATABASE_URL=postgresql+psycopg://…/schemeknit_release` on `test_generation_resume.py`, `test_generation_concurrency.py`, `test_generation_quota_atomicity.py`, `test_generation_recovery.py`, `test_postgres_quota_driver.py` | **19 passed** |
| **Frontend typecheck** | `npx tsc --noEmit` from `frontend/` | **clean** |
| **Frontend production build** | `npm run build:web` | **succeeded**, 38/38 static pages |
| **Browser: Autopilot** | `node e2e/autopilot-acceptance.js` on `localhost:3100` + API `127.0.0.1:8000`, isolated E2E PostgreSQL, AI OFF | **39 passed, 0 failed**: fresh-teacher one-action path, capped/unlimited counts, exhausted-quota blocker, WAPEF/class interrupts, manual flow, reload/no auto-run, 375 px fit, zero page errors |
| **Browser: edit/save/reload/export** | `node e2e/lesson-edit-export-acceptance.js` on the Pro account | **20 passed, 0 failed**: edited topic/starter persisted through API + reload; DOCX, structured PDF, XLSX, ZIP downloaded; zero page errors and zero 4xx/5xx |
| **Browser: true resume** | `node e2e/resume-acceptance.js` with a staged failed job (one persisted lesson, one planned-pending occurrence) | **15 passed, 0 failed**: banner → “Resume pending lessons”, same job completed, exactly two lessons, no duplicate occurrence, pre-existing lesson content preserved, banner cleared |
| **Frozen corpus: deterministic** | `tests/benchmark_deterministic_lessons.py` | **11/11 teacher-ready, mean 74.0/75**, hard failures `{}` |
| **Frozen corpus: expanded** | `tests/benchmark_hardening.py` | **40/40 teacher-ready, mean 73.3/75**, hard failures `{}` |
| **Frozen corpus: messy** | `tests/benchmark_hardening.py` | **19/19 teacher-ready, mean 72.3/75**, hard failures `{}` |
| **Corpus-wide prose regression** | `tests/test_corpus_prose_quality.py` | **2 passed** over all 70 lessons |
| **Export content audit** | Read back the browser-downloaded files | DOCX 39,411 B (real package; edited starter present); structured PDF 7,327 B / 3 pages (edited topic + starter present); XLSX 5,470 B / 4 rows (edited topic present); ZIP 37,159 B / one valid DOCX entry |

The GES DOCX form has no standalone “Lesson Topic” cell; DOCX therefore preserves the topic where the form provides for it (and the edited starter verbatim) but does not carry a separate topic field. PDF and XLSX do carry the topic. This is a format limitation of the approved form, not a content loss; it was not “fixed” by altering the approved GES template.

### 10.4 Separate verdicts

| Verdict | Result | Basis |
|---|---|---|
| **LOCAL DEVELOPMENT ENVIRONMENT** | **PASS** | Isolated PostgreSQL 16.15 on `127.0.0.1:55433` with separate release/migration/E2E databases; documented uvicorn command and Next.js production build/start; API health `healthy` 1.0.5; frontend login 200; browser tests used synthetic accounts only. |
| **CODE ACCEPTANCE** | **PASS** | Full backend suite **2499 passed, 15 skipped, 0 failed** (exit 0); PostgreSQL gates 19 passed; migrations 4 passed; typecheck clean; production build succeeds. Every new/changed behavior has a regression test, and the new resume/concurrency/recovery probes are RED without the fixes. |
| **POSTGRESQL QUOTA INTEGRITY** | **PASS** | PostgreSQL 16.15 + psycopg 3.3.5: atomic late-failure rollback, per-unit ledger/aggregate agreement, idempotent repaid-code regeneration at exhaustion, sixth-new-indicator 403 before side effects, and cross-connection advisory lock all pass. |
| **CACHE AND IDEMPOTENCY** | **PASS** | Structured cache key covers content, mode, instruction, mode label, template, provider and model; duplicate submit/rewrite/context/collision/model-switch tests pass in the full suite; resume replay consumes no duplicate quota or lesson. |
| **FRONTEND ACCEPTANCE** | **PASS** | Typecheck clean, production build succeeds, Autopilot 39/39, edit/reload/export 20/20, resume 15/15; zero uncaught page errors and zero HTTP 4xx/5xx in the journeys. |
| **RECOVERY AND RESUME** | **PASS** | True same-job resume endpoint, planned-occurrence snapshot, status fields, review-blocked exclusion, idempotent replay, quota-safe retry, stale-job visibility on page reload, and browser-proven recovery. This supersedes the §9.4 FAIL. |
| **BROWSER END-TO-END ACCEPTANCE** | **PASS** | All three real browser journeys passed on the final build against the isolated E2E PostgreSQL database with AI OFF. |
| **EXPORT ACCEPTANCE** | **PASS** | DOCX/XLSX/ZIP/structured-PDF files are real, downloadable, and carry the edited content where the format has a field for it. **DOCX→PDF conversion fidelity is NOT TESTED** as an acceptance path: the host's Word COM emitted fatal-exception diagnostics, so browser PDF acceptance used the structured ReportLab renderer that Render actually selects. |
| **QUALITY CORPUS ACCEPTANCE** | **PASS** | 70/70 corpus lessons teacher-ready; means 74.0/73.3/72.3; zero hard failures; corpus-wide prose assertions pass. |
| **RELEASE READINESS** | **PASS** (local release gate) | No failing quota, persistence, authorization, duplicate-generation, cache, frontend, browser, export or recovery requirement remains in the local evidence. This is readiness for a **separate, authorised commit/push/deploy stage**; production behavior remains **NOT TESTED**, and no commit/push/deploy was performed here. |

### 10.5 Residual gaps and limitations

- **DOCX→PDF conversion fidelity is not accepted as verified.** The host has Word COM but it emits Windows fatal exceptions (`0x800706be`/`0x800706ba`) in converter-forced tests. The suite completed, but browser acceptance deliberately used the always-available structured ReportLab PDF renderer — the same path Render uses because Render has neither Word nor LibreOffice. A genuine Word/LibreOffice conversion comparison remains to be run on a suitable host.
- **Multi-worker deployment was not exercised live.** The PostgreSQL advisory-lock regression proves contention between independent database connections, which is the mechanism that protects multiple workers; a real multi-process uvicorn/browser run was not staged.
- **The 60-minute stale threshold remains conservative.** A legitimate generation longer than 60 minutes could be reclaimed; no such run is expected.
- **Legacy jobs without a planned-occurrence snapshot** are resumed conservatively from their selected codes/allocation; their status page may not advertise `can_resume` until a new-style job exists. New jobs persist the planned set before generation.
- **Post-commit failures** can still return a 500 after lessons and units are durably committed (for example while reading quota/AI credit state); a reload restores the completed job, but the immediate response is not a success. This behavior predates this round and was not changed.
- **Word COM / LibreOffice remain host dependencies for the legacy converter path**, not for the Render structured-PDF path.
- **ESLint remains unconfigured** (`next lint` prompts for setup); type checking and the production build are the frontend gates used here.
- **The internal-string audit now excludes identifier fields** (`id`, `*_id`, timestamps/status) from its prose scan. A UUID's all-decimal hex segment can otherwise match the epoch-stamp pattern by chance (~1 in 1,300); the audit still scans every teacher-visible prose field, and its UUID-specific tests continue to assert that a UUID is never treated as an internal marker.
- **Documentation drift:** `docs/pilot/production-version.md` and `docs/PRODUCTION_READINESS.md` still name `3ef1a41`; this was not changed.
- **No commit was made.** `frontend/tsconfig.tsbuildinfo` is a generated tracked file modified by typechecking/build and must be excluded from the release commit. `backend/teachflow.db.bak-20261008-012012`, `.agents/`, `brag-output/`, and generated test/export artifacts remain outside the release scope.

### 10.6 Intended release contents

The intended commit contains the 29 tracked files below (excluding `frontend/tsconfig.tsbuildinfo`):

```text
backend/src/curriculum/lesson_builder.py
backend/src/curriculum/lesson_rubric.py
backend/src/engines/docx_export.py
backend/src/engines/lesson_quality_gate.py
backend/src/engines/structured_pdf.py
backend/src/entitlements.py
backend/src/routers/ai_regeneration.py
backend/src/routers/generation.py
backend/src/service.py
backend/src/usage_quota.py
backend/tests/test_ai_cache_double_submit.py
backend/tests/test_ai_production.py
backend/tests/test_autopilot_generation.py
backend/tests/test_autopilot_ui_source.py
backend/tests/test_final_web_ux.py
backend/tests/test_ghana_context_bank.py
backend/tests/test_indicator_allocation.py
backend/tests/test_internal_string_audit.py
backend/tests/test_phase3_assessment_dok.py
backend/tests/test_quality_gate.py
backend/tests/test_quota_enforcement_journey.py
backend/tests/test_real_use_remediation.py
backend/tests/test_structured_references_integrity.py
backend/tests/test_wapef_acceptance.py
backend/tests/test_zeli_groq_migration.py
frontend/e2e/autopilot-acceptance.js
frontend/src/app/(app)/generate/[id]/page.tsx
frontend/src/lib/api.ts
frontend/src/lib/generate-coverage.ts
```

plus these new release files:

```text
backend/tests/test_corpus_prose_quality.py
backend/tests/test_early_years_localization.py
backend/tests/test_generation_concurrency.py
backend/tests/test_generation_quota_atomicity.py
backend/tests/test_generation_recovery.py
backend/tests/test_generation_resume.py
backend/tests/test_prose_composition.py
docs/research/rea/FINAL_ACCEPTANCE_REPORT.md
frontend/e2e/lesson-edit-export-acceptance.js
frontend/e2e/resume-acceptance.js
```

The release must not stage `frontend/tsconfig.tsbuildinfo`, `backend/teachflow.db.bak-20261008-012012`, `.agents/`, `brag-output/`, or generated `backend/temp`/`frontend/temp`/`.next` artifacts. `frontend/e2e/lesson-persistence-journey.js` predates the Autopilot confirm-to-generate change and is stale; the new export/edit journey covers that path and was used instead.

### 10.7 Release gate

**Local acceptance is complete; the tree is ready for a separate, explicitly authorised commit → push → deploy → production-verification stage.** No commit, push, deploy, production write, Render/Neon change, or secret change was performed. The live site remains on `43bb266`; live production behavior stays **NOT TESTED** until the post-deploy checklist in §9.6 is executed.

## 11. Cinematic logo-to-particles hero — 2026-10-28

Status: **working-tree frontend implementation and local acceptance. Nothing was committed, pushed, deployed, or run against production data/settings/secrets.** Sections 1–10 are preserved. This section records the landing-page work only; the five product-quality workstreams remain active.

### 11.1 Reference inspection

- Live reference inspected with Playwright at **1440×900** and **390×844**, with screenshots at initial, intermediate and late scroll positions (`C:\Users\SAVIOUR\AppData\Local\Temp\opencode\atria-study`).
- Observed behavior: a particle-built brand mark is the first hero state; scrolling fades the wordmark into a particle cloud, the cloud fades, and the next content section is revealed. The reference uses a fixed WebGL particle canvas, a sticky hero stage, and a scroll-scrubbed title crossfade. Scrolling back restores the earlier state.
- The reference's exact source was not claimed as found. `atria-asi/Atria-Dawn` root contains `README.md`, `README_CN.md`, `assets/`, `atria-dawn-preview.pdf`, and the MIT `LICENSE`; it is a model/research repository, **not the website frontend**. No Atria code, logo or brand asset was copied or substituted.

### 11.2 Implementation

The hero now uses a **Canvas 2D particle field sampled once from SchemeKnit's real mark** (`frontend/public/icons/icon-512.png`, the navy/cyan `SchemeKnitMark` artwork). The DOM logo remains the crisp first paint; the canvas crossfades in only after scroll begins. Precomputed particle targets, deterministic scatter vectors and a single image sample per resize avoid per-frame random generation and pixel processing. Particle counts are capped at 1,150 desktop / 680 mobile. No new dependency was added.

Scroll mapping is normalized against the hero's own height. The scrub completes at 62% of the hero height; the next section is already visible while the particles dissolve. The hero is a normal **100svh section, not a pinned multi-screen scene**, so the page never traps the visitor in an empty stage. Reduced motion gets the complete static hero in normal flow with the canvas and cue removed. A failed mark image or canvas context falls back to the same static hero.

Files changed for this work:

```text
frontend/src/app/page.tsx                              (landing no-JS first paint + showcase)
frontend/src/components/landing/landing-hero.tsx        (new cinematic composition)
frontend/src/components/landing/logo-particles.tsx      (new Canvas 2D field)
frontend/src/components/landing/cinematic-hero.module.css (new hero styles)
frontend/src/components/landing/curriculum-showcase.tsx (new pipeline section)
frontend/e2e/hero-particles-acceptance.js               (new browser acceptance)
frontend/e2e/hero-auth-acceptance.js                    (adapted retired mesh checks)
frontend/e2e/hero-v3-acceptance.js                      (adapted seam/scroll checks)
docs/research/rea/FINAL_ACCEPTANCE_REPORT.md            (this evidence)
docs/research/rea/SCHEMEKNIT_OPPORTUNITY_BACKLOG.md     (active priorities)
```

The prior hero's curriculum pipeline is preserved in the new dark `CurriculumShowcase` section immediately after the hero; `HowItWorks`, role cards, navigation, footer and authenticated screens are otherwise unchanged. The landing page no longer blocks on an auth spinner, so the hero and content are server-rendered even when JavaScript is unavailable.

Accessibility and resilience:

- Canvas has `aria-hidden="true"` and `pointer-events: none`; it is outside the accessibility tree.
- Heading, support copy, CTAs and logo wordmark remain semantic HTML; `#hero-heading` is unchanged.
- `prefers-reduced-motion` removes the canvas, cue and scroll scrub and leaves the complete static hero.
- No global scroll hijacking, no infinite autoplay loop; rendering is scheduled only by scroll/resize and stops when the hero is not intersecting or the page is hidden.
- Image-load and canvas-context failures show the static logo and copy; a no-JavaScript page still renders the hero and CTAs.

### 11.3 Verification evidence

| Check | Command / environment | Result |
|---|---|---|
| Frontend typecheck | `npx tsc --noEmit` | **clean** |
| Frontend production build | `npm run build:web` | **succeeded**, 38/38 static pages |
| New hero browser journey | `node e2e/hero-particles-acceptance.js`, local Next.js on 3100 + isolated E2E PostgreSQL/API | **52 passed, 0 failed**: initial logo/copy/CTA, 1,150 desktop / 680 mobile particles, scroll scrub, reversal, next-section visibility, desktop + 390 + 375×667, reduced motion, no-JS, image fallback, canvas-context fallback, resize |
| Legacy hero + auth journey | `node e2e/hero-auth-acceptance.js http://localhost:3100` | **132 passed, 0 failed** after adapting the mesh assertions to the scroll particle field |
| Legacy hero V3/V4 journey | `node e2e/hero-v3-acceptance.js http://localhost:3100` | **150 passed, 0 failed** after adapting cursor/touch-mesh assertions to scroll scrub, full-canvas sampling and the showcase seam |
| Auth role/design journey | `node e2e/auth-role-design-acceptance.js http://localhost:3100` | **131 passed, 0 failed**; landing carries the particle canvas and auth routes remain mesh-free |
| Autopilot browser journey | `node e2e/autopilot-acceptance.js` on the isolated E2E DB | **39 passed, 0 failed** |
| Edit/save/reload/export journey | `node e2e/lesson-edit-export-acceptance.js` | **20 passed, 0 failed** |
| True resume browser journey | `node e2e/resume-acceptance.js` after re-staging a partial job | **15 passed, 0 failed** |
| Backend regression slice | `pytest tests/test_generation_resume.py tests/test_generation_concurrency.py tests/test_generation_quota_atomicity.py tests/test_generation_recovery.py tests/test_autopilot_generation.py tests/test_autopilot_ui_source.py tests/test_corpus_prose_quality.py -q` | **65 passed, 1 skipped** |
| Frame timing | 119 rAF frames while scrolling 480 px, desktop 1440 and mobile 390 | **avg 16.67 ms, p95 16.8 ms, max 16.8 ms** on both; no obvious jank in headless Chromium |
| Layout stability | PerformanceObserver `layout-shift` during load, desktop 1440 and mobile 390 | **CLS 0.0017 desktop / 0.0027 mobile**; canvas is absolutely positioned and the logo is server-rendered |
| Manual visual acceptance | Screenshots at initial/scrub/showcase, desktop 1440 and mobile 390/375 | Initial logo crisp and centered; particles emerge from the mark, spread and fade; copy remains legible with the scrim; next section appears during the transition; no overflow observed |

The pre-existing `app-chrome-acceptance.js` run was **not counted as a hero pass**: it reached 6 checks and then timed out waiting for the seeded `accept.teacher@schemeknit.test` account's login redirect. That account is not present in the isolated E2E DB; the failing step is a test-data limitation, not a landing-hero result. The stale `public-entry-acceptance.js` still waits for the old “Professional Lesson Plans in Minutes” copy and was not used.

### 11.4 Five continuing priorities

All five remain **ACTIVE**; see the updated `SCHEMEKNIT_OPPORTUNITY_BACKLOG.md` for concrete next deliverables and required output-level evidence.

| Priority | Local evidence retained | Not closed |
|---|---|---|
| 1 — Lesson quality | 70/70 frozen-corpus teacher-ready; prose regression 2/2; topic/timing/rubric suites | Needs real GES Basic/SHS source and teacher-edit sample review |
| 2 — Ghanaian context | Early-years localization path and 12-profile context bank; localization tests | Needs per-subject/per-level output audit and repetition review |
| 3 — Assessment and differentiation | DoK/rubric/4-band export checks | Needs actual generated assessment/rubric/differentiation review, not field-presence checks |
| 4 — Reliability | True resume, advisory lock, quota atomicity, cache/idempotency; backend slice 65 passed | Needs multi-worker staging, post-commit failure drill and cache observability |
| 5 — Less teacher effort | Autopilot 39/39; zero-decision path and quota/blocked/pending messaging | Needs residual-decision measurement on clean vs ambiguous schemes |

### 11.5 Separate verdicts

| Verdict | Result | Basis |
|---|---|---|
| **REFERENCE INSPECTION** | **PASS** | Live site inspected at desktop/mobile with scroll screenshots; repository checked and confirmed to contain assets/docs/MIT licence, not the website frontend; no source reuse claimed. |
| **HERO IMPLEMENTATION** | **PASS** | Real SchemeKnit logo, Canvas 2D mark sampling, scroll-linked disintegration/dissipation, no new dependency, pipeline preserved in a new showcase section. |
| **SCROLL-REVERSAL BEHAVIOR** | **PASS** | Automated scroll-back checks restore logo opacity 1, copy opacity 1, canvas opacity 0 and phase `logo`; manual scroll up confirmed. |
| **DESKTOP VISUAL ACCEPTANCE** | **PASS** | 1440×900 initial/scrub/showcase screenshots inspected; logo crisp, particles coherent, next section visible, no overflow. |
| **MOBILE VISUAL ACCEPTANCE** | **PASS** | 390×844 and 375×667 screenshots and checks inspected; logo/heading/CTAs visible, no overflow, transition works, next section visible. |
| **REDUCED-MOTION AND FALLBACK ACCEPTANCE** | **PASS** | Reduced motion: static hero, canvas `display:none`, no pinned scene, scroll does not remove logo. No-JS: server-rendered heading/logo/CTA. Image failure and canvas-context failure: static fallback visible, canvas hidden. |
| **FRONTEND TYPE-CHECK / BUILD ACCEPTANCE** | **PASS** | `tsc --noEmit` clean; `npm run build:web` 38/38 pages. |
| **BROWSER / REGRESSION ACCEPTANCE** | **PASS** | New hero 52/52; adapted legacy hero/auth 132/132; adapted V3/V4 150/150; Autopilot 39/39; edit/export 20/20; resume 15/15; backend regression slice 65 passed, 1 skipped. The unrelated app-chrome login-fixture timeout is recorded above. |
| **FIVE-PRIORITY ROADMAP PRESERVATION** | **PASS** | All five priorities explicitly remain active in the updated backlog, with next deliverables and output-level acceptance evidence; none is marked complete. |
| **WORKING-TREE INTEGRITY** | **PASS** | `HEAD == origin/main == 43bb266`; prior uncommitted remediation and report preserved; no reset/clean/stash; no commit/push/deploy. `frontend/tsconfig.tsbuildinfo`, `.agents/`, `brag-output/` and the DB backup remain out of scope. |
| **RELEASE STATUS** | **PASS — local-only** | The hero is locally accepted for a separate authorised release stage. **No release operation was performed; production behavior remains NOT TESTED.** |

### 11.6 Remaining limitations

- **DOCX→PDF conversion remains NOT TESTED** as an acceptance path, exactly as in §10.4; this task did not change the export stack.
- **Production was not tested** and no Render/Neon setting, secret or production write was touched.
- The `app-chrome-acceptance.js` credential-dependent login timeout is recorded as a harness/data limitation; it was not repaired or hidden.
- The stale `public-entry-acceptance.js` copy expectation predates the current landing page and was not used.
- The hero uses a sampled raster of the canonical mark for particle positions; the visible initial logo remains the vector `SchemeKnitMark`, so the brand mark stays sharp at any DPR. A future brand-asset change must update both the icon source and the vector together.
- At the time of this section the particle field was scroll-scheduled only; the §12 revision adds the continuous ambient/cursor loop while the stage is visible.

## 12. Hero revision — inline lesson intro, cursor cloud, delayed header — 2026-10-28

Status: **working-tree frontend revision; no commit/push/deploy; production remains NOT TESTED.** Sections 1–11 are preserved. This section supersedes §11.2/§11.3 only where they describe the lesson workflow as a separate showcase card; the card has now been removed and its copy lives inside the particle stage.

### 12.1 Reference recheck

The live Atria page was re-opened in Playwright at 1440×900. Its fixed nav is present in the DOM from first paint but the brand and links are `visibility:hidden` / `opacity:0`; they become visible around 100 px of scroll (measured: hidden at 60 px, opacity 0.92 at 100 px, full at 140 px). The particle surface is a fixed canvas over a sticky hero, and the cloud is continuously animated. This revision matches the header behavior and the moving cloud rather than copying Atria's brand or source.

### 12.2 What changed

- **Card removed.** The `CurriculumPipeline` figure is no longer mounted on the landing page. The exact requested copy is retained as the `lessonIntro` block:
  - “Inside the lesson”
  - “One scheme. One indicator. One lesson.”
  - “The indicator you selected stays attached to the work. SchemeKnit assembles the starter, main learning, assessment, plenary and teaching resources around it — not around a generic topic.”
- **Hero stage extended.** The particle canvas now spans the hero and that copy block (measured 1,241 px desktop, 1,178 px mobile). Particles are biased downward through the copy instead of leaving sideways, with 980 desktop / 900 mobile targets.
- **Continuous cloud + cursor lens.** A bounded `requestAnimationFrame` loop adds ambient drift while the stage is visible. On fine pointers, a smoothed radial lens pushes and swirls nearby particles as the cursor moves over the logo or the lesson intro. The loop stops when the stage is offscreen, the tab is hidden, or the scrub completes; reduced-motion users get the static hero.
- **Delayed fixed header.** The landing header is now fixed and hidden at the top; it fades in after 80 px of scroll and hides again at the top. No-JS gets a `<noscript>` override so navigation remains available without scripting.
- **No-JS first paint** remains server-rendered with the complete hero and CTAs.

New/modified files for this revision:

```text
frontend/src/app/page.tsx                              (fixed delayed header, remove card)
frontend/src/components/landing/landing-hero.tsx        (inline lesson intro)
frontend/src/components/landing/logo-particles.tsx      (extended stage, ambient/pointer field)
frontend/src/components/landing/cinematic-hero.module.css (intro/copy styles)
frontend/src/components/landing/curriculum-showcase.tsx (removed)
frontend/e2e/hero-particles-acceptance.js               (header/intro/motion assertions)
frontend/e2e/hero-auth-acceptance.js                    (retired-card/header adaptations)
frontend/e2e/hero-v3-acceptance.js                      (particle/header adaptations)
docs/research/rea/FINAL_ACCEPTANCE_REPORT.md            (this evidence)
```

### 12.3 Verification

| Check | Command / environment | Result |
|---|---|---|
| Frontend typecheck | `npx tsc --noEmit` | **clean** |
| Frontend production build | `npm run build:web` | **succeeded**, 38/38 static pages |
| Revised hero journey | `node e2e/hero-particles-acceptance.js` | **62 passed, 0 failed**: hidden header at top → visible on scroll → hidden at top; card count 0; intro copy present; 980 desktop / 900 mobile particles; ambient cloud changes without scroll; cursor lens activates; particles cover the intro; reversal; desktop/mobile; reduced motion; no-JS; image and canvas fallbacks; resize |
| Adapted hero/auth journey | `node e2e/hero-auth-acceptance.js http://localhost:3100` | **134 passed, 0 failed** |
| Adapted hero V3/V4 journey | `node e2e/hero-v3-acceptance.js http://localhost:3100` | **150 passed, 0 failed** |
| Auth role/design journey | `node e2e/auth-role-design-acceptance.js http://localhost:3100` | **131 passed, 0 failed** |
| Autopilot journey | `node e2e/autopilot-acceptance.js` on isolated E2E DB | **39 passed, 0 failed** |
| Edit/save/reload/export journey | `node e2e/lesson-edit-export-acceptance.js` | **20 passed, 0 failed** |
| Backend regression slice | generation/resume/concurrency/quota/recovery/autopilot/prose tests | **65 passed, 1 skipped** |
| Layout stability | PerformanceObserver during load, desktop/mobile | **CLS 0.0017 / 0** |
| Frame timing | Headless synthetic continuous scroll at 1440 and 390 | **desktop avg 18.35 ms, p95 33.3 ms; mobile avg 16.67 ms, p95 16.8 ms; idle desktop ~16.95 ms**. The synthetic scroll harness is heavier than ordinary wheel input; manual screenshot review showed no obvious stutter. |
| Manual visual review | Screenshots at initial, mid-scrub, intro and HowItWorks, 1440 / 390 / 375 | Logo intact at top; header absent; cloud moves and covers the intro; cursor changes its shape; card absent; clean handoff to HowItWorks |

The existing `app-chrome-acceptance.js` credential-dependent login timeout is unchanged and is not counted as a hero failure. The stale `public-entry-acceptance.js` old-copy check was not used. The true-resume browser journey was last run at **15/15** on the same working tree before this landing-only revision; the backend resume suite remains green in the 65-passed slice. DOCX→PDF conversion fidelity remains **NOT TESTED**, as in §10.4.

### 12.4 Verdicts for this revision

| Verdict | Result | Basis |
|---|---|---|
| REFERENCE INSPECTION | **PASS** | Live Atria header visibility and moving-cloud behavior rechecked at desktop/mobile; repository remains documentation/assets only. |
| HERO IMPLEMENTATION | **PASS** | Real mark particles extend through the lesson intro; card removed; delayed header; ambient cloud and cursor lens. |
| SCROLL-REVERSAL BEHAVIOR | **PASS** | Automated scroll-back restores logo, copy, canvas opacity 0, phase `logo`; header hides at top. |
| DESKTOP VISUAL ACCEPTANCE | **PASS** | Inspected 1440 initial, scrub and intro states; particles cover the copy, header appears only after scroll, no overflow. |
| MOBILE VISUAL ACCEPTANCE | **PASS** | Inspected 390/375 initial and intro states; particles are visible over the copy, CTAs usable, no overflow. |
| REDUCED-MOTION AND FALLBACK ACCEPTANCE | **PASS** | Static hero, no pinned stage, canvas hidden; no-JS hero/CTA; image and canvas-context fallbacks keep the static logo/copy. |
| FRONTEND TYPE-CHECK / BUILD ACCEPTANCE | **PASS** | `tsc --noEmit` clean; production build 38/38. |
| BROWSER / REGRESSION ACCEPTANCE | **PASS** | Revised hero 62/62; adapted hero/auth 134/134; V3/V4 150/150; auth role 131/131; Autopilot 39/39; edit/export 20/20; backend slice 65 passed, 1 skipped. |
| FIVE-PRIORITY ROADMAP PRESERVATION | **PASS** | The five priorities remain active with next deliverables in `SCHEMEKNIT_OPPORTUNITY_BACKLOG.md`; none marked complete. |
| WORKING-TREE INTEGRITY | **PASS** | `HEAD == origin/main == 43bb266`; prior work preserved; no reset/clean/stash; no commit/push/deploy. |
| RELEASE STATUS | **PASS — local-only** | Revision is locally accepted for a separate authorised release stage; production remains **NOT TESTED**. |

### 12.5 Remaining limitations

- **Desktop headless p95 frame time is 33.3 ms under the synthetic continuous-scroll harness**, although idle is ~60 fps and mobile is 16.8 ms p95. Manual review showed no obvious stutter; a real-device profiler run is still the right follow-up.
- The `CurriculumPipeline` component remains in the source tree but is no longer mounted on the landing page; if it is not planned for reuse it can be removed in a later cleanup.
- The unrelated `app-chrome-acceptance.js` login fixture and stale `public-entry-acceptance.js` limitation remain as recorded in §11.3.
- **DOCX→PDF fidelity remains NOT TESTED**; no export-stack change was made.
- **Production behavior remains NOT TESTED.** No production write, Render/Neon setting, secret, commit, push or deployment occurred.

## 13. Post-UI reliability, recovery and export hardening - 2026-10-28

Status: **working-tree backend hardening and local verification. No commit, push, deploy, production write, Render/Neon change or secret change was performed. Sections 1-12 are preserved.** This section resolves the four limitations recorded in section 10.5: DOCX-to-PDF fidelity/Word COM diagnostics, true multi-worker concurrency, the stale-job threshold, and post-commit HTTP 500 behavior.

### 13.1 Environment and scope

- Base: `HEAD == origin/main == 43bb266`; all work remains uncommitted in the working tree.
- PostgreSQL 16.15 in the existing isolated container `schemeknit-pg-release` on `127.0.0.1:55433`; separate `schemeknit_release`, `schemeknit_migrations` and `schemeknit_e2e` databases.
- LibreOffice was installed at `C:\Program Files\LibreOffice\program\soffice.exe` and used as the supported converter. Microsoft Word is installed on this host but remains an optional desktop fallback only.
- All generation used AI `OFF` and synthetic/local test data. No production Neon database, account, quota or generation was touched.

### 13.2 DOCX-to-PDF conversion: supported path, real fidelity, and the blank-page defect

**Original limitation.** The prior report recorded DOCX-to-PDF fidelity as **NOT TESTED**: the host Word COM automation emitted `Windows fatal exception: code 0x800706be` / `0x800706ba`, and audit runs disabled `_try_docx2pdf`. That left no evidence for the real converter path.

**Root cause and supported path.** The application supports two distinct PDF outputs:

1. a real DOCX-to-PDF conversion when LibreOffice or Word is present, and
2. a structured ReportLab PDF rendered directly from the lesson model when no converter exists (the Render production path).

Word COM is an optional Windows desktop backend. Its fatal exception is an environment/runtime incompatibility on this host, not a defect in the DOCX renderer and not evidence that the PDF product path is broken. The converter order was changed so **LibreOffice is attempted first** and Word COM is only a fallback. A flaky Word installation can therefore no longer poison a normal export, and the supported cross-platform path is exercised by default.

**Real conversion evidence.** `backend/tests/test_pdf_converter_fidelity.py` was added. It generates a representative Creative Arts lesson through the real DOCX engine, then calls the real LibreOffice converter (not a mock, not the structured renderer). The fixture contains:

- a long lesson topic and a Basic 9 Ghanaian curriculum header,
- long teacher-edited starter/conclusion/homework text,
- local materials and terminology (`calabash`, `kente`), a realistic price (`GHS 2.50`),
- long teacher and learner activities,
- the full GES delivery grid,
- structured assessment questions and a four-band rubric.

The test asserts: valid PDF signature; at least four pages; no empty page; readable text on every page; cover -> main teaching -> assessment -> rubric page order; all four rubric bands; the final rubric note and homework sentence (no truncation); and table headers/cell content. It is skipped honestly when LibreOffice is absent; it never silently falls back to Word or the structured renderer.

**A real layout defect was found and fixed.** The first fidelity run produced a **blank page** between the lesson form and the assessment appendix. Root cause: `_append_assessment_structure` inserted a page-break *paragraph*. When the preceding GES form filled the previous page exactly, that paragraph landed alone at the top of the next page and its break pushed the assessment to the following page, leaving a blank page. The append now sets `page_break_before` on the assessment heading instead. This starts the appendix on a new page only when it is not already there, preserving page order without an empty page. This was a genuine export-fidelity fix, not a test relaxation.

**Measured result after the fix.** Representative lesson: DOCX **40,719 bytes**; PDF **105,663 bytes**, **5 pages**, all five pages carrying text (1,507 / 2,327 / 1,569 / 2,376 / 1,212 normalised characters); assessment and rubric present; final rubric note present on page 5; no empty or truncated page. This is content/layout fidelity, not a pixel-perfect claim.

**Word COM verdict.** Word COM was not exercised as an acceptance converter in this round and is **not claimed as fixed or verified**. It remains an optional fallback, isolated behind LibreOffice. No fatal-exception diagnostic was required or suppressed on the normal path; the old external `disable_word_com` pytest plugin was not used for the final suite.

**Structured PDF verdict.** The ReportLab structured renderer remains unchanged and tested as its own path (`test_export_download.py` and the existing PDF layer tests). It is **not** used as evidence for DOCX-to-PDF fidelity.

### 13.3 True multi-process concurrency and interrupted-worker recovery

**Original limitation.** The previous round proved PostgreSQL advisory locking between independent *connections*, but not full behavior with independent backend **processes** sharing a database.

**Test setup.** `backend/tests/pg_worker.py` is a standalone worker: each invocation is a separate OS process with its own Python interpreter, SQLAlchemy engine/session factory, FastAPI app and authentication overrides. Workers synchronise on files (`ready` + `go`) so both finish startup before either request is sent. They share only PostgreSQL. This is a true process boundary, not two connections inside one process.

Five tests in `backend/tests/test_generation_multiprocess_postgres.py` passed:

| Scenario | Observed result |
|---|---|
| Two processes, same owner + same scheme, released together | exactly `200` + `409`; one job; no duplicate source occurrence; 2 units for 2 indicator codes |
| Two processes, different schemes, released together | both `200`; two jobs; both lesson sets persisted; 4 units total for 2 schemes x 2 codes |
| Worker process killed while holding the advisory lock | PostgreSQL released the session lock; a replacement process generated successfully |
| Worker process killed with a `processing` job; a second process resumes it | stale job reclaimed; same job id reused; only planned occurrences generated; a pre-existing lesson survived untouched; job completed; no duplicate occurrence; 2 units |
| Client retries the same successful request in a second process | both `200`; identical lesson count; distinct occurrence ids; units stayed 2, `units_used` stayed 2 |

The losing same-scheme worker receives a `409` naming the in-progress generation. Existing PostgreSQL advisory-lock, quota-atomicity, recovery, resume and driver tests remain green. This is a **locally verified multi-worker simulation**; no Render deployment was staged.

### 13.4 Stale-job policy: configurable heartbeat lease

**Original limitation.** The 60-minute threshold was hard-coded and based only on `created_at`; a legitimate long run could be reclaimed.

**Implemented policy.**

- New nullable `generation_jobs.heartbeat_at` column and additive migration `v034_generation_job_heartbeat` (`TIMESTAMP`, portable to SQLite and PostgreSQL).
- `GENERATION_STALE_MINUTES` (default **60**, integer minutes, valid 1-1440) is the stale window.
- `GENERATION_HEARTBEAT_SECONDS` (default **30**, integer seconds, valid 5-3600) is how often a running worker refreshes the lease. Configuration validation rejects a heartbeat that is not shorter than the stale window, so a healthy worker always beats before it could be reclaimed.
- A running generate/resume request starts a daemon heartbeat thread with its **own** database session; it waits one interval before the first refresh (the initial `processing` update already writes one), never joins the request transaction, and logs/swallows transient heartbeat failures. A worker that dies stops heartbeating; its job becomes reclaimable after the window.
- `reconcile_stale_generation_jobs` uses `COALESCE(heartbeat_at, created_at)` and the comparison is strictly `< cutoff`. Legacy/never-started jobs fall back to `created_at`. Exactly at the threshold remains live; one second past it is stale. All timestamps are naive UTC, consistent with the existing schema and `datetime.utcnow()` usage.
- Job status is now written **in the same transaction** as accepted lessons, replacement, rehome, unused-unit release and totals. Previously the job could be marked `completed` in an earlier commit while persistence later failed. A resume also clears the old `completed_at` when it starts.

Deterministic tests cover: exactly-at-threshold live, one-second-past stale, recent job untouched, old heartbeat stale, heartbeat precedence over `created_at`, a 3-hour job kept alive by a recent heartbeat, a live heartbeat thread refreshing while work continues, terminal jobs not heartbeated, configured (non-60) duration, and invalid settings. Tests use a fixed clock or an injected interval; no test waits 60 real minutes.

**Policy meaning.** The 60-minute default is justified for normal runs (seconds/minutes) and remains conservative. A run longer than 60 minutes is not reclaimed while its worker is alive, because the heartbeat (30s) keeps proving liveness.

### 13.5 Post-commit failure: truthful recovery, not a false rollback

**Transaction boundary.** The atomic commit covers accepted lesson rows, occurrence-scoped replacement, surviving-lesson rehome, unused-unit release, job totals and terminal job status. `persistence_committed` is set only after that commit.

Three cases now have distinct behavior:

1. **Pre-commit failure.** The transaction rolls back; reserved units are released, the job is marked failed, and the API returns `500`. No lesson, unit or fraudulent success survives. A later retry performs the real work.
2. **Committed, finalization failed.** The lessons and lesson-plan quota are durable. A failure while reading quota status, writing the completion log, consuming an AI credit, or resolving provider status is logged with detail server-side and **does not** return a 500. The API returns `200` with `status: completed`, `recovered: true`, a safe `warning`, and `finalization.state: completed_with_warning`. A durable `finalization_warning` is stored in the job's `config_snapshot` and exposed by the job-status and scheme-status endpoints. The generate page now consumes both the immediate `warning` and the reloaded `finalization_warning` and renders a dedicated amber banner, so a committed-but-warned run is not silently presented as an unqualified success. The public warning contains no exception internals or sensitive values.
3. **Client does not know whether the commit happened and retries.** Lesson regeneration replaces the same occurrence set in place; per-unit keys are idempotent per `(scheme, indicator_code)` per month; a retry does not duplicate lessons or double-charge lesson-plan quota. Tests assert database state, not just HTTP status.

`_recovered_committed_response` is a last-resort safe net: if an unexpected error occurs after the commit, it re-reads lessons, occurrence ids, job state and quota from durable storage and returns a recovered success (or honest nulls if a read also fails). It never rolls back or reports the committed run as rolled back.

**Honest AI-credit caveat.** AI usage is idempotent on the **job id**. A resume of the same job cannot double-consume. A brand-new generate request after a lost response creates a new job by design, so it may consume a new AI credit; lesson-plan quota and lessons remain idempotent per scheme/occurrence. This is recorded as a remaining limitation rather than hidden.

Failure-injection tests cover post-commit quota read failure, completion-log failure, AI-credit ledger failure, durable warning exposure on `/status`, retry after a committed-but-warned response, and pre-commit failure followed by a clean retry. All assert lessons, units, `units_used`, job status and warning state.

### 13.6 Verification evidence

| Check | Command / environment | Result |
|---|---|---|
| Real DOCX->PDF fidelity (LibreOffice) | `pytest tests/test_pdf_converter_fidelity.py -q` | **2 passed** in 31.08 s; representative lesson 5 pages, no empty/truncated page |
| Export/download contracts (incl. converter cleanup) | `pytest tests/test_export_download.py -q` | **37 passed** in 8.15 s; missing binary, nonzero exit and timeout paths clean their isolated LibreOffice profile |
| Stale policy + heartbeat + post-commit injection (SQLite) | `pytest tests/test_stale_job_reconciliation.py tests/test_generation_stale_policy.py tests/test_generation_quota_atomicity.py -q` | **31 passed** in 10.61 s, including the live heartbeat-thread test |
| PostgreSQL migrations incl. v034 | `POSTGRES_MIGRATION_TEST_URL=... pytest tests/test_postgres_migrations.py -q` | **4 passed** in 1.92 s; harness asserts `generation_jobs.heartbeat_at` exists, is nullable, and re-runs are no-ops |
| PostgreSQL reliability group | `TEACHFLOW_TEST_DATABASE_URL=... pytest test_generation_quota_atomicity.py test_generation_concurrency.py test_generation_recovery.py test_generation_resume.py test_postgres_quota_driver.py test_generation_multiprocess_postgres.py test_stale_job_reconciliation.py -q` | **41 passed** in 73.88 s |
| True multi-process group | `pytest tests/test_generation_multiprocess_postgres.py -q` on the isolated PG database | **5 passed** in 26.14 s, including preservation of a pre-existing lesson during cross-process resume |
| Earlier affected backend slice | generation/quality/integration/remediation/quota/Autopilot/export/DOCX/PDF/resume/recovery/concurrency/stale/fidelity modules | **359 passed, 1 skipped** in 188.85 s (run before the final UI warning banner and helper guard; superseded by the final combined group and full suite) |
| Final combined targeted group | fidelity + export + phase 3 assessment + stale/heartbeat + post-commit + UI source contract | **120 passed** in 80.62 s on the final tree |
| Full backend suite | `pytest tests -q` from `backend/`, SQLite, no Word-COM suppression plugin | **2526 passed, 21 skipped, 0 failed** in 920.87 s (15:20), exit **0**; no Word COM fatal-exception diagnostics |
| Frontend typecheck | `npx tsc --noEmit` from `frontend/` | **clean** after the generate-page warning banner |
| Frontend production build | `npm run build:web` | **succeeded**, 38/38 static pages after the banner |
| Generate-page post-commit warning contract | `pytest tests/test_autopilot_ui_source.py -q` | **21 passed**; asserts `finalization_warning`, `response.warning` and `data-finalization-warning` are wired |
| Landing hero regression | `node e2e/hero-particles-acceptance.js` | **62 passed, 0 failed** (header, intro copy, particle stage, scroll/reversal, reduced motion, no-JS, image/canvas fallbacks, resize) |
| Worktree / schema safety | `git status --short`, `git diff --stat`, isolated PostgreSQL | no reset/clean/stash; no production write; no commit/push/deploy |

The full suite was already running when four late regression tests were added (the blank-page DOCX test, two converter profile-cleanup cases and the generate-page finalization-warning contract). Those four are covered by the **final combined 120-test group** on the exact final tree; the 2526 full-suite count is otherwise the final backend behavior. No full-suite failure was deferred or hidden.

### 13.7 Separate verdicts

| Verdict | Result | Basis |
|---|---|---|
| **1. DOCX-to-PDF fidelity** | **PASS** (LibreOffice-supported path, local host) | Real conversion of a representative long/edited/Ghanaian lesson; 5 pages; content, tables, page order, assessment, four rubric bands and document tail preserved; no empty or truncated page. The blank-page defect found by the test was fixed. Not claimed pixel-perfect. |
| **2. Word COM environment compatibility** | **NOT VERIFIED / ISOLATED** | Word is an optional desktop fallback. Its host-specific fatal COM exception was not reproduced as an acceptance path and is not claimed fixed. LibreOffice-first ordering keeps Word out of the normal export and prevents it from breaking a valid conversion. |
| **3. Structured PDF export** | **PASS** | Existing structured ReportLab renderer and PDF endpoint layers remain green; Render's no-converter path is unchanged. Not used to claim DOCX-to-PDF fidelity. |
| **4. Multi-process concurrency** | **PASS** (local process simulation) | Five true independent-OS-process tests on shared PostgreSQL: same-scheme conflict, different-scheme concurrency, lock release after kill, cross-process resume, retry idempotency. No duplicate lessons or double charge. |
| **5. Interrupted-worker recovery** | **PASS** | Killed lock holder releases the PostgreSQL session lock; a stale `processing` job left by a killed worker is reclaimed and resumed by a second process with the same job id and only planned occurrences. |
| **6. Stale-job threshold and heartbeat policy** | **PASS** | Documented configurable policy (`GENERATION_STALE_MINUTES` 60 default, `GENERATION_HEARTBEAT_SECONDS` 30 default), validated bounds, real heartbeat thread, strict boundary semantics, deterministic tests, and durable job-state consistency. |
| **7. Post-commit failure and retry correctness** | **PASS** (with AI-credit caveat) | Post-commit quota/log/AI-credit failures return a recovered 200 with durable warning; the generate page shows that warning immediately and after reload; pre-commit failures roll back and return 500; retries replace in place and do not duplicate lessons or double-charge lesson-plan units. Same-job AI credit is idempotent; a fresh generate can consume a new AI credit by design. |
| **8. Quota and idempotency integrity** | **PASS** | Exact unit counts in same-scheme (2), different-scheme (4), resume (2) and retry (2) process tests; aggregate `units_used` matches the per-unit ledger; pre-commit failures leave zero lessons/units. |
| **9. Generated-artifact exclusion** | **PASS with tracked-file caveat** | `.gitignore` now excludes `.agents/`, `brag-output/`, `backend/teachflow.db.bak-*` and `*.tsbuildinfo`. `frontend/tsconfig.tsbuildinfo` is already tracked, so an ignore rule cannot hide it; it must be explicitly excluded from the release commit. No file was deleted or staged. |
| **10. Five-priority roadmap preservation** | **PASS** | All five priorities remain active in `SCHEMEKNIT_OPPORTUNITY_BACKLOG.md`; priority 4's evidence was updated with the new multi-process/stale/post-commit/converter work and its next live-staging deliverable. No priority is marked complete. |
| **11. Overall local acceptance** | **PASS** (local-only) | Full backend suite **2526 passed, 21 skipped, 0 failed** (exit 0, 920.87 s, no Word COM fatal diagnostics); PostgreSQL migrations 4/4; PostgreSQL reliability group 41/41; true multi-process 5/5; final combined targeted group 120/120; frontend typecheck clean and production build 38/38; hero 62/62. Production remains untested. |
| **12. Release status** | **NOT RELEASED - local only** | No commit, push, deployment, production configuration, secret or Neon write. The tree is ready for a separate authorised review/commit stage only. |

### 13.8 Remaining limitations

- **Word COM is not verified.** It remains optional and environment-dependent; LibreOffice is the supported converter. A Word-specific acceptance run on a stable Office host is still required if Word is to be claimed as supported.
- **Multi-worker evidence is local.** Five independent OS processes sharing PostgreSQL prove the mechanism, but no live Render multi-worker deployment or Neon database was exercised.
- **AI-credit idempotency is per job.** A lost response followed by a completely new generate request may consume a new AI credit; lesson-plan quota and lessons remain idempotent. A client-supplied request id would be needed to make AI credits idempotent across brand-new jobs.
- **Heartbeat depends on a reachable database.** If the database is unreachable for longer than the stale window, peers may reclaim a job whose worker is still computing. That is the intended conservative behavior for a partition that long.
- **`frontend/tsconfig.tsbuildinfo` is tracked.** It is generated by typecheck/build and must be excluded from the release commit explicitly; the new `*.tsbuildinfo` ignore rule does not untrack an already tracked file.
- **Frontend change is limited to the generate-page post-commit warning banner.** The landing hero was re-run at 62/62; this round's browser E2E did not restart the API with the new backend flow, so the banner's live browser path is covered by the source contract plus typecheck/build rather than a staged browser failure injection. Backend resume/quota/concurrency behavior is covered by the process tests above.
- **Production behavior remains NOT TESTED.** No production write, Render/Neon setting, secret, commit, push or deployment occurred.

### 13.9 Files changed in this round

```text
backend/src/config.py                                  (stale/heartbeat settings + validation)
backend/src/database.py                                (generation_jobs.heartbeat_at)
backend/src/migrations/v034_generation_job_heartbeat.py (new additive migration)
backend/src/service.py                                 (heartbeat_job, COALESCE stale policy)
backend/src/routers/generation.py                      (heartbeat context, atomic terminal job state, post-commit recovery, status warning)
backend/src/engines/pdf_export.py                      (LibreOffice first, Word optional fallback)
backend/src/engines/docx_export.py                     (assessment page_break_before; no blank page)
backend/.env.example                                   (operational policy documentation)
backend/tests/test_pdf_converter_fidelity.py           (new real LibreOffice fidelity tests)
backend/tests/test_generation_stale_policy.py          (new settings/boundary tests)
backend/tests/test_stale_job_reconciliation.py         (heartbeat/boundary/live-thread tests)
backend/tests/test_generation_quota_atomicity.py       (post-commit failure injection/retry tests)
backend/tests/test_generation_multiprocess_postgres.py (new true multi-process tests)
backend/tests/pg_worker.py                             (new independent-process worker)
backend/tests/pg_migration_harness.py                  (v034 column assertion)
backend/tests/test_export_download.py                  (converter order/fallback/profile-cleanup contracts)
backend/tests/test_phase3_assessment_dok.py            (blank-page DOCX regression)
backend/tests/test_autopilot_ui_source.py              (post-commit warning banner source contract)
frontend/src/app/(app)/generate/[id]/page.tsx          (show immediate/reloaded finalization warning)
.gitignore                                             (narrow generated/backup exclusions)
docs/research/rea/SCHEMEKNIT_OPPORTUNITY_BACKLOG.md    (priority 4 status/evidence update)
docs/research/rea/FINAL_ACCEPTANCE_REPORT.md           (this section)
```

No landing-hero source file was modified in this round; the previously implemented hero files remain present and were re-verified at 62/62.

---

## 14. Zeli generation method - 2026-10-29 (local verification only)

### 14.1 What this round adds

A second, teacher-selectable **generation method** now sits alongside the existing
Standard path. The existing OFF / BASIC / ENHANCED enrichment modes are unchanged
and remain the choice *within* Standard generation.

| Layer | Change |
|---|---|
| Domain model | `GenerationMethod` (`standard` \| `zeli`) on `TermConfig`, persisted in the job snapshot and on each lesson. It is independent of `AIMode`; the method is authoritative. Unknown values are rejected. |
| Backend | New `src/engines/zeli_generation.py` (validated config, availability, strict whole-lesson output validator, durable cache, teacher-safe failure mapping). The pipeline generates whole lessons through the **existing** `GroqProvider`, applies V2 content, then the **unchanged** quality gate. |
| Persistence | Additive migration `v035_zeli_generation_provenance_cache`: `lesson_plans.ai_provider`, `ai_model`, `generation_method`, plus `zeli_generation_cache`. Existing rows are valid and untouched. |
| API | Generation accepts `generation_method`; the status endpoint reports Zeli availability and a teacher-safe reason; failures map to 429 / 503 / 504 / 502. |
| Frontend | Two-button "Generation method" control (`Standard` / `Generate with Zeli`), `aria-pressed` state, AI Mode disabled with an explanatory note while Zeli is selected, an explicit block reason when Zeli is unavailable, and result copy that names the method. |
| Docs/config | `backend/.env.example` documents `ZELI_*`; the opportunity backlog records the change and its evidence. |

No deterministic rebuild is substituted for Zeli output. Content that fails the
gate is dropped and reported, never silently replaced.

### 14.2 Verified provider and model contract

| Item | Verified value | How it was established |
|---|---|---|
| Runtime provider | `groq` | Existing `GroqProvider` in `src/engines/ai_provider.py`; no new SDK, endpoint or model id was introduced. |
| Model id | `openai/gpt-oss-120b` | Existing `GROQ_MODEL` default. |
| Base URL | `https://api.groq.com/openai/v1` | Existing `GROQ_BASE_URL` default. |
| Live probe | `available: True`, 13 expected keys, `last_error: None`, `validate_zeli_content -> OK` | Real server-side probe against Groq in the isolated environment. |
| Persisted provenance | `ai_provider=groq`, `ai_model=openai/gpt-oss-120b` on every generated lesson | Read back from the isolated SQLite database. |

Other named providers remain supported by the abstraction but are **not verified**
for Zeli.

### 14.3 Credential handling

- `ZELI_ENABLED` (default `true`), `ZELI_PROVIDER` (default `groq`, validated
  against `NAMED_PROVIDERS`), and optional `ZELI_MODEL` / `ZELI_BASE_URL` /
  `ZELI_API_KEY`. Blank values inherit `GROQ_*`, so one credential serves both.
- The API key is only attached to the server-side provider instance. The status
  endpoint returns booleans and reason text, never a key, model id or provider id
  to the teacher surface.
- A deployment without a key shows the method as unconfigured with a stated
  reason; generation is blocked before any quota or job side effect.
- The browser audit in the journey confirmed `groq`, `gpt-oss`, `openai/gpt`,
  `api key` and `rate_limit` do not appear on the teacher-facing page.

### 14.4 Did real Zeli generation actually run?

**Yes.** A fresh teacher account generated a real 5-lesson Basic 7 Computing run
through the UI against an isolated backend (`127.0.0.1:8010`) and frontend
(`127.0.0.1:3002`), with the real Groq key configured server-side.

| Evidence | Result |
|---|---|
| Teacher account | `zeli.method.1793281067409@schemeknit.test` |
| Scheme | `8736f188-efc4-4aff-94f0-6f1a65bd5020` (real DOCX fixture) |
| Job | completed, 5 completed / 0 failed |
| Lessons persisted | 5 / 5, every row `generation_method=zeli`, `ai_provider=groq`, `ai_model=openai/gpt-oss-120b`, `ai_generated=1` |
| Zeli-authored content | Starter, assessment and plenary text all non-empty and recognisably provider-written (e.g. "Think-pair-share...", "Individually, the teacher asks each learner to...") |
| Whole-lesson cache | 17 entries in `zeli_generation_cache` |
| Quality gate (real Groq, 5 lessons) | **5/5 accepted, 0 rejected**, hard/soft rejections `{}`, mean score **69.4**; pre-fix 1/5 evidence preserved in `gate-detail-v1-pre-fix.json` |

The pre-fix failures were traced to prompt/mapping fidelity (exact-token
morphology, dropped teacher/learner actions, a literal `"None"` resource), not to
an over-strict rubric. They were fixed in the prompt and V2 mapping; the gate
floors were not changed.

### 14.5 Existing generation options still work

- The journey asserts Standard generation is still offered next to Zeli, that
  choosing Standard re-enables OFF / BASIC / ENHANCED, and that all three options
  are intact with their original labels.
- `test_pipeline_standard_path_ignores_zeli` proves a Standard run never calls
  Zeli and keeps its existing behaviour.
- The quick-action / setup contracts and Standard result copy are unchanged.

### 14.6 Quota, cache, idempotency, retry and resume

| Guarantee | Evidence |
|---|---|
| One existing AI credit per successful Zeli request, idempotent by job id | `test_resume_does_not_consume_a_second_ai_credit`; isolated DB job completed with a single charge |
| Lesson quota unchanged (per accepted indicator code) | `test_generate_rejects_zeli_when_unconfigured_before_quota` (no side effect when blocked); quota suites in chunk B/C |
| Cache distinguishes method, provider, model, prompt version and every material input | `test_cache_key_separates_method_provider_model_and_material_inputs`, `test_cache_key_changes_with_teacher_supplied_material_inputs`, `test_cache_key_is_namespaced_by_prompt_version`, `test_zeli_result_is_not_served_for_another_method` |
| Identical run reuses cached lessons | `test_identical_run_reuses_cached_lessons` |
| Resume preserves method and provenance | `test_resume_preserves_zeli_method` |
| Failure is truthful and never falls back | `test_pipeline_never_silently_falls_back_when_zeli_fails`, `test_failed_zeli_run_keeps_existing_lessons_and_reports_honestly`, `test_zeli_provider_failures_are_classified`, `test_zeli_malformed_output_is_rejected_not_merged` |

### 14.7 Test and build results on the final tree

The full backend suite collects 2600 tests. A single invocation exceeds the
30-minute command cap (the live-provider and real-document groups are slow), so
it was run as ordered file groups over the same final tree. Summed results:

| Group | Tests | Result |
|---|---|---|
| Zeli suite (`test_zeli_generation_method.py`) | 48 | **48 passed** (15.59s) |
| Chunk A (all files before `test_quota_enforcement_journey.py`) | 2081 | **2070 passed, 11 skipped**, 0 failed (1547.07s) |
| Chunk B1 (`test_quota_enforcement_journey.py`, `test_real_acceptance_quality_gate.py`) | 26 | **26 passed** (73.41s) |
| Real-AI/document/science/use group | 62 | **60 passed, 2 skipped** (real network/provider gated) |
| Chunk C (`test_release_boundaries.py` through `test_zeli_groq_migration.py`) | 431 | **424 passed, 7 skipped** (188.65s) |
| **Aggregate** | **2600** | **2580 passed, 20 skipped, 0 failed** |

Earlier targeted regression on the same behaviour:
`test_generation_v2_integration.py test_wapef_acceptance.py test_ai_production.py
test_zeli_generation_method.py` = **133 passed**, plus 4 mapping-fidelity tests
added afterwards.

Frontend and end-to-end:

| Check | Result |
|---|---|
| TypeScript (`npx tsc --noEmit`) | exit 0, no diagnostics |
| Production build (`npm run build:web`) | **succeeded**, all 38 static pages generated, all routes emitted |
| Whole-lesson browser journey (`frontend/e2e/zeli-method-journey.js`) | **24/24 passed** (selection, AI-mode lock, ready state, 5 lessons, provenance, Zeli-authored sections, honest copy, no provider/model/key leakage, persistence after reload, Standard restores all three modes) |
| `git diff --check` | clean (CRLF warnings only) |

Build caveat: this host's Next.js Google Fonts fetch fails intermittently while
the same URL succeeds from PowerShell and Node. The production build was completed
with Next's documented `NEXT_FONT_GOOGLE_MOCKED_RESPONSES` fixture. No source,
font configuration or dependency was changed to work around it.

### 14.8 Separate verdicts

| Verdict | Result | Basis |
|---|---|---|
| **Zeli is selectable, persistent and method-authoritative** | **PASS** | 48-test suite; journey 24/24; persisted `generation_method=zeli` across reload and resume |
| **Real provider/model contract** | **PASS (Groq only)** | Live probe and real 5-lesson run with `groq` / `openai/gpt-oss-120b`; no invented ids |
| **Credentials stay server-side** | **PASS** | Status returns booleans/reason only; browser audit finds no provider/model/key strings |
| **Quality gate integrity preserved** | **PASS** | Gate unchanged; Zeli failures dropped, not rebuilt; real 5/5 accepted after fidelity fixes |
| **Existing OFF / BASIC / ENHANCED still work** | **PASS** | Journey asserts all options restored and intact; Standard path ignores Zeli |
| **Quota / cache / idempotency / retry / resume** | **PASS** | Named tests above; isolated DB charge and cache rows |
| **Staging or production deployment** | **NOT DONE** (out of scope) | Local-only verification; nothing pushed or deployed |
| **Non-Groq Zeli providers** | **NOT VERIFIED** | Config accepts them, but no live evidence |

### 14.9 Remaining limitations

1. Zeli is verified on **Groq only**, locally. No staging or production deployment
   was exercised and no production database was written.
2. Real-model quality varies by lesson; the quality gate remains the authority and
   a Zeli run can legitimately reject content rather than lower the bar. The real
   sample here is 5 lessons.
3. Zeli is a whole-scheme job: per-lesson retry is the existing job resume/retry
   path, not a new granular UI.
4. The full suite is reported as an ordered aggregate because one invocation
   exceeds the tool time cap; the groups ran on the same final tree with zero
   failures.
5. The Google Fonts build fetch is an environment issue requiring the documented
   mock for this host; the bundle itself compiled and generated all routes.
6. Live Gemini/Groq tests in chunk A use machine-local keys; they ran and passed
   here, but results can differ on a host without those keys (they skip cleanly).

### 14.10 Files changed in this round

```text
backend/src/models.py                     (GenerationMethod, lesson provenance, cache model)
backend/src/database.py                   (ZeliGenerationCacheDB, lesson provenance columns)
backend/src/migrations/v035_zeli_generation_provenance_cache.py (new additive migration)
backend/src/engines/zeli_generation.py    (new: config, availability, validator, cache, failures)
backend/src/engines/generation_pipeline.py (Zeli whole-lesson path, V2 mapping fidelity, timeline completion)
backend/src/curriculum/generation_prompt.py (prompt rules 12-15)
backend/src/curriculum/spine.py           (method plumbing)
backend/src/routers/generation.py         (method validation, gate allow_rebuild, provenance, credits, quota)
backend/src/routers/settings.py           (Zeli status)
backend/src/config.py                     (ZELI_* settings + validation)
backend/.env.example                      (truthful Zeli/Groq documentation)
backend/tests/test_zeli_generation_method.py (new, 48 tests)
frontend/src/app/(app)/generate/[id]/page.tsx (method selector, AI-mode lock, blocked reason, result copy)
frontend/src/lib/api.ts                   (generation_method + Zeli status)
frontend/src/types/index.ts               (method/provenance types)
frontend/e2e/zeli-method-journey.js       (new whole-lesson journey)
frontend/e2e/zeli-method-journey/         (final screenshots + results.txt)
docs/research/rea/SCHEMEKNIT_OPPORTUNITY_BACKLOG.md (dated Zeli section)
docs/research/rea/FINAL_ACCEPTANCE_REPORT.md (this section)
```

### 14.11 Git state at close

- `HEAD` = `origin/main` = `43bb266`; branch `main`.
- All work remains **uncommitted**; nothing is staged, committed, pushed or
  deployed. No `git reset`, destructive checkout, clean or stash was used.
- Pre-existing uncommitted hero and reliability work is preserved.
- `frontend/tsconfig.tsbuildinfo` is tracked and modified by typechecking; exclude
  it from any release commit.

## 15. Guided configuration, professional lesson output and week-sequence remediation — 2026-10-29 (local verification only)

### 15.1 What this round adds

One coordinated improvement to the lesson-planning workflow, driven by the
Basic 9 Science regression fixture (`Lesson_Plans_BASIC_9_SCIENCE_SCHEME_OF_
LEARNING.docx`, GES format — the primary visual/structural regression target;
WAPEF behaviour untouched):

| Layer | Change |
|---|---|
| Guided configuration (Phase 2/3) | The seven plan-wide lesson fields — school name, teacher's name, class size, reference, lesson duration, periods per week / period slot, teaching days — are configured AFTER extraction and BEFORE generation through ONE **"Configure lesson rubrics"** button + modal, present on both the review page and the generate page (shared component `frontend/src/components/lesson-config-modal.tsx`). Save validates field-by-field (422 with named fields), persists **per plan** on the scheme row, and the server reports readiness (`ready` / `missing`); the UI blocks generation with the missing-field reason while required fields are unsaved. Cancel keeps the last saved configuration; unsaved changes are never silently discarded. |
| No invented values | `class_size` lost its fabricated 24/11 defaults (`TermConfig`, `LessonPlan`, both DB columns): an unconfigured plan renders a BLANK Class Size cell. Generation refuses to start (409) while required configuration (school, teacher, class size, duration, teaching days) is missing. Optional fields (reference, period) may legitimately stay blank. |
| Persistence | Additive migration `v036_scheme_lesson_config`: one nullable `lesson_config` JSON column on `schemes`. Existing rows stay unconfigured; nothing is rewritten. Config survives navigation, reload and job resume; generation merges the SAVED configuration over any stale client payload, and resume keeps the job's original snapshot. |
| Week sequence (Phase 4) | Root cause of "Week 1, 2, 2, 3, 4" was the parser merging two weekly sections whose source label repeated ("WEEK 2" printed twice). `docx_parser._renumber_repeated_week_sections` now splits a merged week at each section's own week-ending date (the discriminator — consecutive rows of one section share one date) and renumbers split/colliding sections into a gapless sequence. Genuine gaps, non-standard labels, special periods and multi-strand single-date weeks are preserved (Basic 7 real-document tests guard the non-regression). |
| GES header structure (Phase 5) | FIRST page of the plan prints exactly School / Teacher / `Week 1` in that order; every later page prints ONLY its own `Week N` heading — in BOTH the official GES form renderer (`render_header(first=…)`) and the custom-structure renderer that produced the fixture. A plan with no real school/teacher renders no invented identity. |
| DATE / DAY row (Phase 2.1G) | The `DATE / DAY:` row renders the teacher's SELECTED teaching-day names in weekday order ("Monday, Wednesday, Thursday") — never calendar dates beside them — in the custom-structure renderer and the SHS form's `INSERT_DATE_DAY` token. Week-ending fields are untouched. |
| Grammar / capitalisation (Phase 6) | New `src/curriculum/text_hygiene.py`: deterministic, meaning-preserving fixes for the fixture's defect classes — concatenated indicators ("…compounds Describe the…" → sentence boundary), "Learners can Identify" → lowercase after lead-in (sentence-boundary- and code-aware: `B9.1.1.1 Show…` untouched), "Charts And Pictures" → small words lowercase (display lists and keywords only; `source_tlrs` stays verbatim), dangling tails ("…and explain it in."), unbalanced brackets. Nothing is lowercased indiscriminately; curriculum source records are never rewritten. |
| Drafting artefacts (Phase 7) | Removed at source: "What to look for:" → "As learners respond, check that each learner can …"; "Quick check (unprompted):" → "Quick check:"; "Exit check:" → "Before the class leaves, …"; "Step 2 · Classify:" mid-dot labels → "Step 2:"; the woven "(NS: …; MA: …)" cue → teacher-facing "For learners needing support: … / For learners ready for more: …" (the `differentiation` field's spelled-out "Needs Support (NS):" labels are the approved presentation and stay). `_short_clause` no longer emits truncated "…" fragments — clauses close with a full stop. The lesson quality gate gained `_hygiene_failures` (hard) + hygiene repair, applied to BOTH deterministic and Zeli output. |
| Export context | `_render_context` carries the configured teaching days and period; the combined DOCX and PDF-source paths forward it. The structured PDF renderer implements the same first-page/later-page header contract. |

### 15.2 Verified behaviour (local, isolated)

| Check | Command / source | Result |
|---|---|---|
| New regression tests (fixture defects) | `backend/tests/test_week_and_header_regression.py` | **18 passed** — duplicate-label sections renumbered to Week 1..5 (dates preserved, content intact); multi-strand single-date weeks NOT split; first-page header order school/teacher/Week 1; later pages week-only; no identity invented; DATE/DAY row shows day names with no dates; all fixture artefact strings absent; gate rejects a lesson carrying them. |
| Guided configuration API | `backend/tests/test_guided_lesson_configuration.py` | **7 passed** — GET prepopulates from the profile and reports missing required fields; PUT validates (422 with field names) and persists per plan; plan B never inherits plan A's values; generation refused (409) while configuration is missing; configuration survives reload. |
| Full backend suite | `python -m pytest tests/ -q` | see §15.4 final run result. |
| Real-pipeline content inspection | isolated script: parse real Basic 9 Science scheme → `generate_all` (AI OFF, 22 lessons, weeks 1..12) → export DOCX → inspect rendered XML | All fixture artefact strings ABSENT (`What to look for:`, `Quick check (unprompted):`, `Step N ·`, `Charts And Pictures`, `Learners can Identify`, `…` fragments, raw `(NS:`/`(MA:`); week sequence monotonic and complete 1..12 (multi-lesson weeks share their correct label); first-page header = School / Teacher / Week 1; class size, reference and period rendered; phase minutes sum to the configured 60. |
| Frontend | `npx tsc --noEmit` + `npm run build` | typecheck clean; production build succeeded. |
| Browser E2E (guided configuration journey) | `frontend/e2e/lesson-config-acceptance.js` against local servers | **9/9 passed** — signup → profile school → upload real scheme → review page shows exactly ONE "Configure lesson rubrics" button → modal opens with all seven fields → save persists and the SERVER reports ready → reload restores values → dirty-Cancel never saves → generate page carries the single entry point. |
| UI-source tests | `test_generate_workflow_ui_source.py`, `test_autopilot_ui_source.py`, `test_final_web_ux.py` | passed (70). |
| WAPEF regression | `tests/test_wapef_acceptance.py` + export contracts | passed — WAPEF output and the approved-source topology contracts unchanged. |

### 15.3 Working-tree integrity

- All prior work preserved (hero, Zeli, quota/heartbeat/recovery work, migrations v001–v035, tests, evidence).
- New files this round: `backend/src/curriculum/text_hygiene.py`,
  `backend/src/migrations/v036_scheme_lesson_config.py`,
  `backend/tests/test_week_and_header_regression.py`,
  `backend/tests/test_guided_lesson_configuration.py`,
  `frontend/src/components/lesson-config-modal.tsx`,
  `frontend/e2e/lesson-config-acceptance.js`.
- No commits, pushes, deploys, production configuration changes or production
  data writes were made.

### 15.4 Final suite result

Recorded from the closing full run on 2026-10-29 (SQLite suite;
PostgreSQL-specific multiprocess harness excluded exactly as in §3):
**2605 passed, 1 failed, 15 skipped** — the single failure is
`test_gemini_groq_providers.py::TestLiveGroq::test_one_indicator_structured_
generation`, a LIVE provider probe rejected by Groq with `rate_limit`
(environmental; re-run alone reproduces `last_error=rate_limit`; no code path
involved).

PostgreSQL verification (disposable local PG 18, scratch database
`schemeknit_scratch_1029`, started via `pg_ctl`):
- `tests/test_postgres_migrations.py` — **4 passed**, and the new
  `schemes.lesson_config` column confirmed as `json` on PostgreSQL.
- `tests/test_postgres_quota_driver.py` (psycopg3 dialect over 127.0.0.1) —
  **4 passed**.

### 15.5 Remaining gaps / honesty notes

- The attachment used for the regression fixture was recovered from the
  workspace as a shallow 1-lesson copy (`temp/Lesson_Plans_BASIC_9_…docx` was
  not the full 23-page document), so the week-sequence test reconstructs the
  documented defect (five sections, "WEEK 2" repeated, week-endings advancing)
  instead of parsing the exact broken file. The parser guard is
  evidence-driven and validated against BOTH the reconstructed defect AND the
  two real scheme documents in the repo (Basic 7 PDF, Basic 9 Science DOCX).
- Browser E2E covers the configuration journey; full-generation-in-browser and
  export-download journeys remain covered by the existing acceptance suites
  (`autopilot-acceptance`, `test_web_acceptance_http`), which were not re-run
  against live servers this round.
- Per-template prose variation still embeds the authoritative indicator text
  verbatim; where the indicator itself reads awkwardly ("…and discuss their
  use"), the composition keeps the curriculum wording rather than rewriting
  the source (spec §6.2). The observed doubled-conjunction framing template
  was split into two sentences.


## 16. Registration "Failed to fetch" remediation — 2026-10-30 (local verification only)

### 16.1 Reproduced failure and root cause

Symptom: registering a new account from the local web app (`http://localhost:3100/signup/`)
showed a bare **"Failed to fetch"**; no registration occurred.

Reproduction (real Chromium against the running local app, before any change):

- Page displayed: `Failed to fetch`.
- Console: `Access to fetch at 'http://localhost:8000/api/auth/register/individual' from
  origin 'http://localhost:3100' has been blocked by CORS policy: Response to preflight
  request doesn't pass access control check: No 'Access-Control-Allow-Origin' header is
  present on the requested resource`, plus `net::ERR_FAILED` on both
  `GET /api/service-status` and `POST /api/auth/register/individual`.
- No HTTP status was ever received by the browser (the request never reached the
  registration handler).

Root cause (established browser → backend, before any code change): the local web
frontend runs on **port 3100** (the port used by every browser acceptance journey in
this report), but `backend/.env` `CORS_ORIGINS` still listed only
`localhost:3000`, `localhost:5173`, `localhost:18235`, `127.0.0.1:18235`. The backend
rejected the preflight:

- `OPTIONS http://127.0.0.1:8000/api/auth/register/individual` with
  `Origin: http://localhost:3100` → **HTTP 400, body `Disallowed CORS origin`**, no
  `access-control-allow-origin` header.
- The same preflight from the allowed origin `http://localhost:18235` → HTTP 200 with
  `access-control-allow-origin: http://localhost:18235` (control).

A secondary, transient factor: at investigation start both servers were down entirely
(which also produces "Failed to fetch"). They were brought back up exactly as documented
(`backend/run.py --port 8000`; `npm run start -- -p 3100`) before the diagnosis above.

### 16.2 Fix applied (smallest durable change)

- `backend/.env` (local environment config only): added the actual local frontend
  origins `http://localhost:3100` and `http://127.0.0.1:3100` to `CORS_ORIGINS`.
  No production source code, no auth architecture, no CORS weakening (the legitimate
  dev origin was granted its own port), no new dependency, no schema change.
- `backend/tests/test_cors_registration_preflight.py` (new): 7 regression tests pinning
  the exact failure mode — preflight allowed for every configured origin on the
  registration route, unknown origins still rejected with `Disallowed CORS origin`,
  the `:3100` dev origin must stay configured, register route mounted (422 on empty
  payload, not 404), weak password rejected (422), duplicate email 409
  `Email already registered`, and registered teacher can log in.
- Only the backend was restarted after the change (uvicorn on :8000); the frontend was
  not modified.

### 16.3 End-to-end verification (real browser, after fix)

| Journey | Result |
| --- | --- |
| Register fresh account via `/signup/` | **PASS** — auto-login, redirected to `/dashboard/`, zero console errors, zero failed requests |
| Backend persistence of the new account | **PASS** — row present in the isolated local SQLite DB, `role=teacher`, password stored as bcrypt (`$2b$12$`, 60 chars) — existing hashing mechanism intact |
| Invalid input (short password) | **PASS** — user-facing policy message, no register POST sent |
| Duplicate email | **PASS** — user-facing `Email already registered` (HTTP 409), not "Failed to fetch" |
| Login with the new account | **PASS** — reaches `/dashboard/` |
| Logout (header control) | **PASS** — sessionStorage token cleared, returned to `/login/` |
| Re-login after logout | **PASS** — reaches `/dashboard/` |
| Platform-admin login `/login/platform-admin/` | **PASS** — the documented local acceptance super-admin account signs in and reaches `/platform-admin/` |

Platform-admin provisioning (the account for `/login/platform-admin/`): the only
supported mechanisms are the one-time bootstrap page `/setup/platform-admin` (requires
`PLATFORM_ADMIN_BOOTSTRAP_SECRET`; backend returns 410 once an admin exists) or the
server-side CLI `python -m src.tools.create_platform_admin` /
`reset_platform_admin` (break-glass). The isolated local DB contains exactly one
platform admin, the acceptance fixture account `accept.pa@schemeknit.test`; its
password is defined by the repo's own e2e acceptance fixtures
(e.g. `frontend/e2e/app-closure-acceptance.js`) and was verified working in the
browser journey above.

### 16.4 Regression checks

- Backend: `pytest tests/test_cors_registration_preflight.py tests/test_auth_lifecycle.py
  tests/test_security_hardening.py -q` → **91 passed** (84 existing + 7 new), 0 failed.
- Frontend type check: `npx tsc --noEmit` → exit 0.
- Frontend production build: `npm run build:web` → exit 0; the rebuild produces the
  same content-hashed assets (`static/css/5c7c279f90ef0888.css` 65,843 B and
  `static/css/af17f56514360f0c.css` 8,097 B, both served `200 text/css`).
- Landing page after the fix: `GET /` → 200 (42,904 B), 15 hashed `cinematic-hero_*`
  class tokens present in the served HTML and their stylesheet loads — the cinematic
  hero and landing styling are intact. `/signup/` and `/login/platform-admin/` → 200.
- Zeli / Standard generation choices: frontend source untouched by this fix
  (26 `Zeli|Standard` references in the generate page unchanged); backend AI paths
  untouched.

### 16.5 Remaining limitations / honesty notes

- The fix is local-environment configuration; production CORS remains governed by
  `CORS_ORIGINS` in the production environment and was not touched (no deploy, no
  production writes; RED/NO-GO posture unchanged).
- The frontend production server on :3100 is the `next start` process from the build
  above; two redundant restart attempts exited with `EADDRINUSE` and were discarded —
  exactly one frontend server and one backend process are running. `netstat` output in
  this shell did not reliably enumerate listeners; reachability was asserted via HTTP
  probes instead.
- The browser journeys were executed with Playwright-driven Chromium (the repo's own
  e2e mechanism) rather than a manually operated browser; evidence above is from the
  real served pages, not mocks.
- Two temporary reproduction scripts used during diagnosis were deleted after the
  permanent regression coverage landed in `backend/tests/test_cors_registration_preflight.py`.

---

## 17. Integrated acceptance and release-readiness audit — 2026-10-30 (local verification only)

Audit-only round: no source changes, no commits, no production contact. Every result
below was produced against the current working tree on 2026-10-30 unless marked
historical.

### 17.1 Repository baseline

- Branch `main`, HEAD `43bb266` — identical to `origin/main` (0 ahead / 0 behind).
- Working tree: 55 modified tracked files (+4,611 / −563), 30 untracked files/dirs.
- Local-only environment files are untracked AND ignored: `backend/.env`,
  `frontend/.env.local`, `frontend/.env.production`. The `backend/.env.example` diff
  adds placeholder keys only (`GENERATION_STALE_MINUTES`, `GENERATION_HEARTBEAT_SECONDS`,
  `ZELI_*`); no secret-shaped values. No secret values were printed during the audit.
- `.gitignore` diff is protective only: adds `.agents/`, `brag-output/`,
  `backend/teachflow.db.bak-*`, `*.tsbuildinfo`.
- Generated artifact flagged: `frontend/tsconfig.tsbuildinfo` is TRACKED and modified;
  the new ignore rule does not untrack it — it must be explicitly excluded from any
  release commit.
- `docs/research/rea/FINAL_ACCEPTANCE_REPORT.md` (119 KB, sections 1–17) is itself
  UNTRACKED — the durable acceptance evidence is not in version control.

### 17.2 Local service status (HTTP probes, not process listings)

- Frontend `:3100`: `GET /` 200 (42,904 B); both content-hashed stylesheets
  `200 text/css` (65,843 B / 8,097 B); `/signup/` 200.
- Backend `:8000`: `/api/service-status` → healthy, v1.0.5.
- CORS behavior: preflight from `http://localhost:3100` → 200 (12/12 probes);
  from unconfigured `http://localhost:9999` → 400 `Disallowed CORS origin`.
- Built client chunks reference `localhost:8000` (intended local API target).
- Process hygiene: exactly ONE `next start -p 3100`; the earlier redundant restart
  attempts exited with EADDRINUSE and are gone. The backend runs as two processes with
  the SAME command line started in the same second (single post-fix launch, likely
  parent/child); 12/12 behavioral probes are consistent with the fixed config only, so
  no stale-config routing. Unrelated `AgroBridge 2.0` dev servers on the machine are
  separate projects and ports — untouched.
- Local data preserved (read-only row counts): `teachflow.db` users=84, schemes=97,
  generation_jobs=129.

### 17.3 Registration/CORS status (rerun on current tree — READY)

- `backend/tests/test_cors_registration_preflight.py`: 7/7 passed (included in the
  full-suite run below). Pins: configured origins preflight 200 on the registration
  route; unknown origins rejected; `:3100`/`127.0.0.1:3100` must stay configured;
  route mounted (422 on empty, not 404); weak password 422; duplicate email 409;
  register→login works.
- `backend/src/config.py` diff contains NO CORS or production-settings changes
  (77 added lines are Zeli/Groq configuration only). Production CORS untouched.

### 17.4 Freshness of evidence

| Evidence | Status | Freshness |
| --- | --- | --- |
| Full backend suite `pytest tests -q` | 2613 passed, 20 skipped, 0 failed (19:39) | **Rerun on current tree 2026-10-30** |
| `npx tsc --noEmit` | exit 0 | Rerun on current tree 2026-10-30 |
| `npm run build:web` | exit 0; same content-hashed assets served live | Rerun on current tree 2026-10-30 |
| Registration/login/logout browser journeys (incl. invalid input, duplicate email, platform-admin login) | All passed | Rerun on current tree (§16, same tree) |
| Landing/hero, autopilot, Zeli-method, lesson-config, lesson-edit-export, resume, download browser journeys | Historical PASS counts (§11–§15) | **Historical evidence only — NOT rerun on current tree** |
| Real-Groq Zeli probe (5/5 accepted), live multi-worker PostgreSQL drill, production live enforcement/reconciliation | Historical / planned | NOT RUN; live-AI runs deliberately not triggered (rate-limited) |

### 17.5 Feature groups and proposed release manifest (nothing staged)

| Group | Files (summary) | Manifest classification | Ships together because |
| --- | --- | --- | --- |
| 1. Registration/CORS | `backend/.env` (local only), `tests/test_cors_registration_preflight.py` | Local-only configuration + Required regression test | Config is env-only; no release artifact |
| 2. Guided lesson configuration | `migrations/v036`, `lesson_builder.py`, `routers/generation.py` (part), `lesson-config-modal.tsx`, `generate/[id]/page.tsx` (part), `test_guided_lesson_configuration.py`, `lesson-config-acceptance.js` | Candidate release change + Required migration + tests | v036 column consumed by builder/router/modal |
| 3. Curriculum parsing & week numbering | `parsers/docx_parser.py`, `curriculum/spine.py`, `official_ges_template.py`, `test_week_and_header_regression.py` | Candidate release change + tests | Parser guard + allocation + renderer are one contract |
| 4. Quality/gates/prose | `text_hygiene.py` (new), `quality_gate.py`, `lesson_quality_gate.py`, `lesson_rubric.py`, `assessment_design.py`, `prose`/`corpus`/`early_years` tests | Candidate release change + tests | Text hygiene is imported by gate/builder |
| 5. Standard generation reliability | `generation_pipeline.py` (part), `usage_quota.py`, `entitlements.py`, `service.py` (part), `migrations/v034`, concurrency/atomicity/resume/recovery tests, `resume-acceptance.js` | Candidate release change + Required migration + tests | Heartbeat column + stale policy + resume are one system |
| 6. Zeli generation | `zeli_generation.py` (new), `migrations/v035`, `config.py`, `database.py`, `models.py`, `routers/generation.py` (part), `service.py` (part), `ai_regeneration.py`, `test_zeli_generation_method.py`, `zeli-method-journey.js`, `.env.example` ZELI keys | Candidate release change + Required migration + tests | v035 schema + provider config + router + frontend method choice are one feature |
| 7. Landing / cinematic hero | `landing-hero.tsx`, `cinematic-hero.module.css`, `logo-particles.tsx`, `app/page.tsx`, hero e2e scripts | Candidate release change + tests | CSS module + particle component + page are one unit |
| 8. Export & document formatting | `docx_export.py`, `pdf_export.py`, `structured_pdf.py`, `test_pdf_converter_fidelity.py`, `lesson-edit-export-acceptance.js` | Candidate release change + tests | Renderers + fidelity tests are one contract |
| 9. Cross-cutting | `frontend/src/lib/api.ts`, `types/index.ts`, `generate-coverage.ts`, `review/[id]/page.tsx`, modified test files, `.gitignore`, `backlog.md` | Candidate release change (api/types span groups 2/5/6) | Mixed-purpose files — see below |

Mixed-purpose files that prevent safe separation: `routers/generation.py` (+1,447),
`engines/generation_pipeline.py`, `curriculum/lesson_builder.py`,
`frontend/src/app/(app)/generate/[id]/page.tsx`, `lib/api.ts` each carry changes for
more than one group. **The working tree should ship as one integrated change set** (or
be split by deliberate re-review), not per-feature commits cherry-picked from it.
Generated/unrelated: `frontend/tsconfig.tsbuildinfo` (tracked generated artifact —
exclude from release commit), `.agents/` + `brag-output/` + db backups (now ignored).

### 17.6 Integrated acceptance gaps (from the §6 checklist; all commands exist)

BLOCKED/NOT RUN on the current tree, in priority order:
1. Browser journeys on the current tree: `hero-particles-acceptance.js`,
   `hero-auth-acceptance.js`, `hero-v3-acceptance.js`, `autopilot-acceptance.js`,
   `lesson-config-acceptance.js`, `lesson-edit-export-acceptance.js`,
   `resume-acceptance.js`, `zeli-method-journey.js` against `localhost:3100` + `:8000`.
2. Multi-worker PostgreSQL staging drill (deployment-level evidence for group 5).
3. Production live enforcement/reconciliation steps (the standing RED/NO-GO items).
4. Optional, rate-limited: one real-Groq Zeli re-probe on the final tree.

### 17.7 Release recommendation

**NO-GO for release today** — backend/unit evidence is READY (2,613 backend tests,
typecheck, production build, live registration/CORS all rerun green on this exact
tree), but every browser acceptance journey is historical evidence only, and the
deployment-level and production checks remain unexecuted. The recommendation upgrades
to **CONDITIONAL** the moment item 17.6.1 runs green on the current tree (the suites
already exist and target the running local servers), and to GO only after the
deployment/production items follow their existing plans (§13). Nothing was committed,
staged, pushed, or deployed during this audit.

---


## 18. Current-tree browser acceptance and super-admin security diagnosis — 2026-10-30 (local verification only)

Audit/verification round: no application source, `.env`, tracked test or Git-index
changes were made. Work was performed against the current working tree and the
running local services; isolated database copies were used for any journey that
creates or edits records.

### 18.1 Repository and service baseline

- Branch `main`, HEAD `43bb26653934b32fe62a482784e29b16557a2a2f` — identical to
  `origin/main` (0 ahead / 0 behind).
- Working tree: **55 modified tracked files, 30 untracked entries, 0 staged** —
  unchanged from §17. No reset/clean/revert/stash was used.
- Frontend `:3100`: `GET /` 200 (42,885 B), `/signup/` 200; served by
  `next start -p 3100` from the current `.next` build.
- Backend `:8000`: `/api/health` 200, `/api/service-status` healthy, v1.0.5.
- Database: SQLite `backend/teachflow.db` (no PostgreSQL in this local profile).
  Read-only counts at close: users **85**, schemes **98**, generation_jobs **129**
  (the +1 user / +1 scheme versus §17 is the lesson-configuration acceptance
  account created by journey 5 below; no records were deleted).
- **Stale-server finding:** the frontend process predated the last production
  build, so it served HTML referencing `not-found-a28c3cb7430a4ed9.js` while
  `.next` contained `not-found-2fc4b3fd35fc2940.js`; that chunk returned HTTP 400
  and surfaced as a landing-page console error. Restarting `next start` (no source
  change) made the served build match disk and the error disappeared. This is
  process hygiene, not a product defect, and explains the first particles run.

### 18.2 The eight outstanding browser journeys (from §17.6.1)

| # | Script | What it exercises | Data / provider risk | Result today |
|---|---|---|---|---|
| 1 | `hero-particles-acceptance.js` | Landing hero, particle stage, scroll/reversal, reduced motion, no-JS, fallbacks, resize | None (public page) | **PASS 62/62** (after server restart; first run 61/62 due to the stale chunk above) |
| 2 | `hero-auth-acceptance.js` | Hero + all four auth surfaces at 1440/390, signup validation, platform-admin direct route | None (form checks only) | **PASS 134/134** |
| 3 | `hero-v3-acceptance.js` | Hero V3/V4 visual contracts, login grid signals, reduced motion, route variants | None | **PASS 150/150** |
| 4 | `autopilot-acceptance.js` | Zero-decision upload → one-action generation → results → reload/quota/WAPEF/class/mobile | Creates a teacher, scheme and lessons; generates | **FAILED — blocked at required lesson configuration** (see §18.3) |
| 5 | `lesson-config-acceptance.js` | Review page → single `Configure lesson rubrics` → seven fields → save/reload/cancel → generate page | Creates one teacher + one scheme; **does not generate** | **PASS 9/9** |
| 6 | `lesson-edit-export-acceptance.js` | Login → edit persisted lesson → save → reload → DOCX/PDF/XLSX downloads | Needs a seeded account **and** an existing generated lesson | **NOT RUN** — requires credentials not supplied (`TF_TEACHER_EMAIL` / `TF_TEACHER_PASSWORD`); no generated lesson exists for a fresh account because generation requires configuration and a provider |
| 7 | `resume-acceptance.js` | Resume an interrupted job without duplicating/charging a completed lesson | Needs credentials + a partially generated scheme | **NOT RUN** — requires `TF_TEACHER_EMAIL`, `TF_TEACHER_PASSWORD`, `TF_SCHEME_ID` and a deliberately interrupted job; no such fixture was available without creating one |
| 8 | `zeli-method-journey.js` | Zeli selection, readiness, real generation, provenance, no leakage, Standard restoration | Makes a **live billable provider request** | **NOT RUN** — live paid AI calls were prohibited for this task |

Commands actually executed (from `frontend/`):

```text
node e2e/hero-particles-acceptance.js            (TF_WEB_URL=http://localhost:3100)
node e2e/hero-auth-acceptance.js http://localhost:3100
node e2e/hero-v3-acceptance.js http://localhost:3100
node e2e/lesson-config-acceptance.js             (TF_WEB_URL/API=http://localhost:3100/8000)
node e2e/autopilot-acceptance.js                 (isolated DB copy, AI_MODE=OFF)
```

### 18.3 Autopilot failure: required configuration now blocks the one-action path

The isolated run (copy of `teachflow.db`, `AI_MODE=OFF`, no billable calls)
reached the generate screen and failed after 7 passes:

```text
PASS  scenario 2: fresh teacher signup lands in the product
PASS  scenario 1: single-subject scheme → instant success card
PASS  scenario 1: success card offers the ONE action
PASS  scenario 1: primary action is "Generate my lesson plans"
PASS  scenario 1: Review Curriculum stays available (§19)
PASS  scenario 1: server plan counts (22 found · 5 this month · 17 wait)
PASS  scenario 1: upload intent consumed exactly once
FAIL  script completed — page.waitForFunction: Timeout 45000ms exceeded.
7 passed, 1 failed
```

The failure screenshot shows why: the page renders

> **Before you can generate** — Complete the lesson configuration first:
> `school_name`, `class_size`, `lesson_duration_minutes`, `teaching_days`.
> Open **Configure lesson rubrics** to save the missing details.

and the primary action is disabled. This is the guided-configuration gate added
on 2026-10-29 (§15); the autopilot script was written 2026-10-17 and assumes
generation can start from a bare upload. It is a **stale acceptance script versus
a deliberate product rule**, not a crash: generation is correctly blocked before
any quota or job side effect. It still means the current tree does not satisfy the
old one-action acceptance contract, so Priority 5 (less teacher effort) needs a
product decision: either the autopilot path opens the configuration step first, or
the journey is updated to configure before its one click.

### 18.4 Super-admin authentication isolation — reproduced

A dedicated isolated database (`s18-auth.db`) and backend (`:8012`) were used so
no existing account or password was needed. A fresh platform admin was created
through the one-time, secret-guarded bootstrap endpoint; a fresh teacher was
self-registered. No credential, token or secret is reproduced here.

| # | Scenario | Expected | Observed | Verdict |
|---|---|---|---|---|
| 1 | Teacher → teacher login | 200, role `teacher` | 200, role `teacher` | PASS |
| 2 | Teacher token → `/api/auth/me` | own profile | 200, role `teacher` | PASS |
| 3 | Teacher token → `/api/platform-admin/dashboard` | 403 | 403 | PASS |
| 4 | Platform admin → dedicated platform-admin entry | 200, role `platform_admin` | 200, role `platform_admin` | PASS |
| 5 | Platform-admin token → admin API | 200 | 200 | PASS |
| 6 | **Platform admin → ordinary teacher login** | **rejected** | **200, and the returned token reaches `/api/platform-admin/dashboard` (200)** | **FAIL — SECURITY BLOCKER** |
| 7 | Properly signed token with forged `platform_admin` claim on a teacher subject | 403 | 403 (server re-reads the DB role) | PASS |
| 8 | Tampered token signature | 401 | 401 | PASS |
| 9 | Expired token | 401 | 401 | PASS |
| 10 | No token on admin API | 401 | 401 | PASS |
| 11 | Wrong password | generic 401 | 401 | PASS |
| 12 | Unknown email | same generic 401 | 401 | PASS |
| 13 | Second platform-admin bootstrap | refused | 410 | PASS |

Root cause: `POST /api/auth/login` in `backend/src/routers/auth.py` authenticates
**any** active user with a valid password and issues a token stamped with that
user's role; there is no "expected entry role" parameter, and both
`/login` and `/login/platform-admin` call the same endpoint
(`frontend/src/components/role-login.tsx` → `api.login`). Because the token is
minted for the platform admin, it is genuinely admin-capable; the frontend merely
redirects to `/platform-admin`, so the session is not "teacher-scoped".

What is **not** broken: authorization. `require_platform_admin` re-reads the user
from the database on every request, so a forged claim on a teacher identity is
403, and teachers cannot reach platform-admin APIs. No teacher → admin escalation
was found. The defect is an authentication-entry boundary (cross-entry login
acceptance), which the reported behaviour and the required product rule forbid.

### 18.5 Additional release-blocking finding: current `.env` cannot boot the tree

Starting the backend with the user's current `backend/.env` fails at import:

```text
ValidationError: 8 validation errors for Settings
ZELI_PROVIDER: ZELI_PROVIDER must be one of: gemini, groq, minimax, ollama, openai, opencode-zen (input: 'deepseek')
DEEPSEEK_API_KEY / ZELI_TEMPERATURE / ZELI_MAX_TOKENS / ZELI_THINKING_MODE /
ZELI_CONNECT_TIMEOUT_SECONDS / ZELI_READ_TIMEOUT_SECONDS / ZELI_MAX_RETRIES: Extra inputs are not permitted
```

The local `.env` is ahead of `backend/src/config.py`: it contains DeepSeek/Zeli
tuning keys the checked-in settings model does not accept. The previously running
backend was started before those values were added. For this audit the app was
booted with a **sanitized env copy in the temp directory** (unsupported keys
removed, `ZELI_PROVIDER=groq`) — the user's `.env` was not modified. This is a
hard local-boot and release blocker that the DeepSeek task must resolve.

Security note: the startup traceback echoed the value of `DEEPSEEK_API_KEY` to
the local terminal. The value was not copied into this report or any tracked file,
but it should be rotated before production use.

### 18.6 Key integrated workflows — status of evidence

| Workflow | Status | Basis |
|---|---|---|
| Landing page / cinematic hero | **READY (current tree)** | 62/62 + 134/134 + 150/150 today |
| Registration / login / logout surfaces | **READY for UI; BLOCKED at role boundary** | Hero auth 134/134; §18.4 scenario 6 fails |
| Guided lesson configuration | **READY (current tree)** | `lesson-config-acceptance.js` 9/9 today (all seven fields, save, reload, cancel, single button) |
| Curriculum parsing / week numbering | **Historical only** | Backend suite evidence in §15; no browser journey rerun today |
| Standard generation | **BLOCKED for the autopilot journey** | Required configuration gate; §18.3 |
| Zeli selection / provider abstraction | **NOT RUN** | Live provider call prohibited |
| Lesson editing and export | **NOT RUN** | Requires seeded account + generated lesson |
| Resume / downloads | **NOT RUN** | Requires a deliberately interrupted job and credentials |

Historical PASS counts from §11–§15 are **not** claimed as current results.

### 18.7 Data preservation

- The user's `backend/teachflow.db` was never used for a destructive test. Every
  generating/editing journey used the copy
  `%TEMP%\opencode\s18-teachflow.db`; the auth probe used a separate empty
  `s18-auth.db` and `:8012`.
- No existing user, scheme, generation job or fixture was deleted. No account was
  reset and no platform-admin password was changed.
- The backend on `:8000` was restored after the isolated run and returns healthy;
  row counts are recorded in §18.1.
- `docs/research/rea/FINAL_ACCEPTANCE_REPORT.md` remains untracked; sections 1–17
  are unchanged. `frontend/tsconfig.tsbuildinfo` remains tracked and modified and
  must be excluded from any release commit.
- The autopilot run replaced that script's own `results.txt` and left today's
  `99-failure.png`; no other historical artefacts were edited.
- Migrations v034, v035 and v036 remain attached to their feature groups.

### 18.8 Security blocker and smallest remediation

**SECURITY BLOCKER (authentication boundary):** the ordinary teacher login accepts
platform-admin credentials and returns a platform-admin-capable token.

Smallest evidence-supported fix (for the next engineering task, not applied here):

1. Make the login endpoint entry-aware, e.g.
   `POST /api/auth/login` accepts an `entry` role (`teacher` | `school_admin` |
   `platform_admin`) and rejects a mismatch with the same generic 401/403 used for
   bad credentials — or add three dedicated login routes that share one verifier.
2. Keep the existing DB-role check in `require_platform_admin` unchanged (it
   already defeats forged claims); add a matching server-side check for the
   school-admin entry.
3. Have `RoleLogin` send its `entry`, and add regression tests for all three
   cross-entry combinations plus the forged-claim case.

Boot blocker: make `config.py` accept and validate the DeepSeek/Zeli keys that
`.env.example`/local `.env` now define (or remove them from `.env` before boot),
and never echo secret values in validation errors.

### 18.9 Release recommendation

| Area | Classification |
|---|---|
| Backend authorization (teacher vs platform admin APIs) | READY |
| Authentication entry-point isolation | **BLOCKED (security)** |
| Browser acceptance on the current tree | READY WITH LIMITATIONS (4 run; 4 not run) |
| Guided configuration journey | READY |
| Autopilot one-action contract | BLOCKED by the configuration gate (stale script/product conflict) |
| Local boot with the current `.env` | BLOCKED |
| DeepSeek/Zeli live verification | NOT RUN |

**Overall: NO-GO.** The current tree is materially healthier than §17 — the
landing hero, auth surfaces and guided configuration all pass on today's build —
but a reported authentication-boundary defect is reproduced and the checked-in
configuration cannot boot with the local `.env`. Recommendation remains NO-GO
until (a) entry-aware login rejects cross-entry authentication, (b) the backend
boots with the intended provider configuration, and (c) the autopilot journey is
either adapted to the required configuration step or the product decision is
recorded. Nothing was staged, committed, pushed, or deployed.


## 19. Zeli DeepSeek configuration completion and transport contract — 2026-10-30

Section 18 found that the working tree could not boot with the local `.env`
because `DEEPSEEK_*` / `ZELI_*` keys had no matching `Settings` fields. This round
completes the DeepSeek integration the environment already expected, documents
every Zeli variable, and proves the request/timeout/retry contract with hermetic
tests. No live provider call was made.

### 19.1 What changed

| File | Change |
|---|---|
| `backend/src/config.py` | Added `DEEPSEEK_API_KEY`; added validated `ZELI_TEMPERATURE`, `ZELI_MAX_TOKENS`, `ZELI_THINKING_MODE`, `ZELI_CONNECT_TIMEOUT_SECONDS`, `ZELI_READ_TIMEOUT_SECONDS`, `ZELI_MAX_RETRIES`; default provider is now `deepseek`; `deepseek` is an accepted provider key. |
| `backend/src/engines/ai_provider.py` | New `DeepSeekProvider` (OpenAI-compatible chat completions): thinking parameter, conditional temperature, `max_tokens` mapping, explicit `(connect, read)` timeout, bounded transient-only retries with back-off/jitter, usage capture, safe error classification; registered in `NAMED_PROVIDERS` / `get_provider`. |
| `backend/src/engines/zeli_generation.py` | Resolves DeepSeek defaults (`deepseek-flash`, `https://api.deepseek.com`), key precedence, and wires the validated tuning onto the provider; added `insufficient_balance` to the teacher-safe 503 mapping. |
| `backend/.env.example` | Placeholder-only block documenting every Zeli variable with its default and accepted range. No real values. |
| `docs/ZELI_ENVIRONMENT.md` | Full variable table: default, validation rule, and consumption point. |
| `backend/tests/test_zeli_deepseek_config.py` | 39 hermetic tests (no network). |

### 19.2 Environment contract

Every supported variable is documented in `docs/ZELI_ENVIRONMENT.md`. Summary:

| Variable | Default | Validation | Consumed at |
|---|---|---|---|
| `ZELI_ENABLED` | `true` | bool | availability + generate gate |
| `ZELI_PROVIDER` | `deepseek` | member of `NAMED_PROVIDERS` | provider factory |
| `ZELI_MODEL` | `deepseek-flash` | trimmed text | request body + cache key |
| `ZELI_BASE_URL` | `https://api.deepseek.com` | trimmed text | `POST {base}/chat/completions` |
| `ZELI_API_KEY` | empty | trimmed text, never logged | bearer auth (highest precedence) |
| `DEEPSEEK_API_KEY` | empty | trimmed text, never logged | bearer auth fallback |
| `ZELI_TEMPERATURE` | `0.3` | `0.0`–`2.0` | `temperature`, only when supported |
| `ZELI_MAX_TOKENS` | `2000` | `1`–`8192` | `max_tokens` |
| `ZELI_THINKING_MODE` | `disabled` | `enabled` \| `disabled` \| `auto` | `thinking: {"type": ...}` |
| `ZELI_CONNECT_TIMEOUT_SECONDS` | `10` | `1`–`60` | first element of the HTTP timeout tuple |
| `ZELI_READ_TIMEOUT_SECONDS` | `90` | `1`–`600` | second element of the HTTP timeout tuple |
| `ZELI_MAX_RETRIES` | `2` | `0`–`5` | transient retry bound |

Key precedence: `ZELI_API_KEY` → `DEEPSEEK_API_KEY` (provider `deepseek`) or
`GROQ_API_KEY` (provider `groq`). A Groq key is never sent to DeepSeek.

### 19.3 Verified request and transport contract (hermetic)

- Thinking mode is **sent**: `thinking: {"type": "enabled"|"disabled"}` when a
  mode is configured; `auto` omits it.
- Temperature is **conditional**: present for `deepseek-flash` with thinking
  disabled; omitted when thinking is enabled or the model id is a reasoner
  (`deepseek-reasoner`, `*-r1`).
- `ZELI_MAX_TOKENS` is mapped to **`max_tokens`**; `max_completion_tokens` is
  never sent.
- `response_format` is limited to `json_object`; strict `json_schema` is not
  sent to DeepSeek (SchemeKnit's validator remains the authority).
- The HTTP client receives `timeout=(connect, read)` from the two settings.
- Retries: 429/5xx/timeouts/connection errors retry up to `ZELI_MAX_RETRIES`
  with exponential back-off + jitter; 400/401/402/403/404/422 never retry.
  A 400 caused by `response_format` drops that field once and re-asks.
- Usage capture records provider, model, input/output/total tokens, cached and
  uncached input tokens, and request duration. Absent `usage` is handled safely.
- Provider error bodies never reach `last_error`; the value is a short code.

### 19.4 Invalid configuration fails before quota

`zeli_availability()` runs **before** quota reservation and job creation
(`routers/generation.py`). A DeepSeek configuration with no key returns **503**
with the teacher-safe "no lesson plans were saved and no lesson-plan quota was
used" message. The regression test asserts, after the rejected request:

- `generation_jobs` = 0
- `lesson_plans` = 0
- `entitlements.ai_credits_used` = 0
- `ai_generation_periods` = 0

Invalid scalar values (provider, temperature, token budget, thinking mode,
timeouts, retries) raise `ValidationError` at process start, so the backend
cannot boot in an ambiguous state.

### 19.5 Test results (executed on the current tree)

| Command | Result |
|---|---|
| `pytest tests/test_zeli_deepseek_config.py -q` | **39 passed** |
| `pytest tests/test_zeli_deepseek_config.py tests/test_zeli_generation_method.py tests/test_zeli_groq_migration.py -q` | **135 passed** (13.59 s) |
| `pytest tests/test_gemini_groq_providers.py tests/test_ai_cache_double_submit.py tests/test_ai_production.py tests/test_real_use_remediation.py -q -k "not Live"` | **116 passed, 5 deselected** |
| `pytest tests/test_quota_enforcement_journey.py -q` | **4 passed** |
| Boot with the real local `.env` (`python run.py --port 8013`) | `/api/health` **200**; `generation_method=zeli` reports `CONFIGURED` |
| Live DeepSeek call | **NOT RUN** — no controlled billable request was authorised |

### 19.6 Limitations and deployment notes

- `deepseek-flash` is the requested default model. The provider contract follows
  DeepSeek's published OpenAI-compatible API; **no live DeepSeek response was
  exercised**, so endpoint acceptance of the exact model id remains unverified
  until one controlled production-like call is authorised.
- Changing the default `ZELI_PROVIDER` to `deepseek` means a deployment that
  previously relied on the implicit Groq default must either set
  `ZELI_PROVIDER=groq` or provide `DEEPSEEK_API_KEY`. Without a key, Zeli shows
  as unavailable while Standard generation keeps working.
- Local `.env` values are not inherited by Render. Set `DEEPSEEK_API_KEY` in the
  Render **backend** environment only; never expose it to the frontend. No Render
  setting was changed here.
- `backend/.env.example` contains placeholders only; the local `.env` was not
  modified and no secret was printed in this section.
- All changes are uncommitted and unpushed; nothing was deployed.


## 20. Platform super-admin login boundary remediation — 2026-10-30

Section 18 reproduced a cross-entry authentication defect: platform-admin
credentials accepted by the ordinary teacher login produced a platform-admin
session. This round makes authentication entry-aware in the backend and updates
every real login caller. No DeepSeek/provider, quota or generation code changed.

### 20.1 Confirmed root cause

`POST /api/auth/login` authenticated any active user with a valid password and
returned a token stamped with that user's role. Both `/login` and
`/login/platform-admin` called the same endpoint with no indication of which
entry was in use, so the role of the account — not the page — decided what the
session became. Authorization was already safe (`require_platform_admin`
re-reads the database role; forged claims are 403), but authentication accepted
the wrong entry point.

### 20.2 Exact changes

| Layer | Change |
|---|---|
| `backend/src/routers/auth.py` | `LoginRequest` gains an optional `entry`; `VALID_LOGIN_ENTRIES = {teacher, school_admin, platform_admin}`; `_entry_matches_role()` compares the requested entry with the **database** role (legacy `is_admin` remains valid for `school_admin`). Password verification happens first; an unknown/missing entry or a role mismatch returns the same generic `401 {"detail": "Invalid email or password"}` as bad credentials. Internal audit logs record `reason=entry_mismatch`, never the role. |
| `frontend/src/lib/api.ts` | `login(email, password, entry)` always sends `entry` in the request body. |
| `frontend/src/lib/auth-context.tsx` | `login` requires the entry argument and forwards it. |
| `frontend/src/components/role-login.tsx` | Sends its `entry` prop (`teacher` / `school_admin` / `platform_admin`). |
| `frontend/src/app/signup/page.tsx` | Auto-login after registration uses `teacher`. |
| `frontend/src/app/setup/platform-admin/page.tsx` | Auto-login after bootstrap uses `platform_admin`. |
| `backend/export_acceptance_remediation.py`, `backend/live_gemini_proof.py` | Operator scripts updated to send `entry: "teacher"`; no alternate caller bypasses the contract. |
| `backend/tests/test_auth_entry_boundary.py` | New 20-test boundary suite. |
| Existing tests | `test_auth_lifecycle.py`, `test_cors_registration_preflight.py`, `test_public_entry_roles.py` updated to send the correct entry. |
| `frontend/e2e/auth-entry-boundary.js` | New real-browser journey. |

No frontend redirect was used as the control; the backend rejects the request
before a token is issued.

### 20.3 Authentication role matrix (verified)

| Account role | teacher entry | school_admin entry | platform_admin entry |
|---|---|---|---|
| `teacher` | **200** | 401 | 401 |
| `school_admin` (or legacy `is_admin`) | 401 | **200** | 401 |
| `platform_admin` | **401** | 401 | **200** |
| missing / invalid entry | 401 | 401 | 401 |

Mismatch and bad-password responses are byte-identical (`{"error": true,
"detail": "Invalid email or password", "status_code": 401}`), so no role oracle
is introduced.

### 20.4 Test results (executed on the current tree)

| Command | Result |
|---|---|
| `pytest tests/test_auth_entry_boundary.py -q` | **20 passed** |
| `pytest tests/test_auth_entry_boundary.py tests/test_auth_lifecycle.py tests/test_cors_registration_preflight.py tests/test_security_hardening.py tests/test_public_entry_roles.py tests/test_roles.py tests/test_school_admin.py tests/test_authorization.py tests/test_authorization_idor.py -q` | **210 passed** (81.11 s) |
| `pytest tests/test_zeli_deepseek_config.py tests/test_zeli_generation_method.py tests/test_zeli_groq_migration.py -q` | **135 passed** (DeepSeek/Zeli unchanged) |
| `npx tsc --noEmit` | exit 0 |
| `npm run build:web` | succeeded (all routes) |

### 20.5 Browser verification (real app, isolated database)

`frontend/e2e/auth-entry-boundary.js` ran against the current production build on
`:3100` and an isolated backend/database on `:8000`:

```text
PASS  signup auto-login creates a teacher session — teacher
PASS  teacher account signs in via the teacher entry — teacher
PASS  platform admin is rejected on the teacher entry with the generic error — Invalid email or password
PASS  rejected admin stays on the teacher login
PASS  rejected admin receives no session
PASS  teacher is rejected on the platform-admin entry with the generic error — Invalid email or password
PASS  rejected teacher stays on the admin login
PASS  rejected teacher receives no admin session
PASS  platform admin signs in via the admin entry — platform_admin
PASS  admin dashboard survives reload — /platform-admin/
10 passed, 0 failed
```

Direct API evidence against the same isolated stack: teacher token on
`/api/platform-admin/dashboard` → 403; platform-admin token → 200; forged signed
`platform_admin` claim on a teacher subject → 403; tampered/expired/absent token
→ 401; second platform-admin bootstrap → 410.

### 20.6 DeepSeek implementation preservation

- `backend/src/config.py`, `backend/src/engines/ai_provider.py`,
  `backend/src/engines/zeli_generation.py`, `backend/.env.example` and
  `docs/ZELI_ENVIRONMENT.md` were **not modified** in this round.
- Zeli still reports `CONFIGURED` with the configured DeepSeek provider on the
  restarted local backend; `deepseek-flash` and `DEEPSEEK_API_KEY` handling are
  unchanged.
- No live DeepSeek request was made. Quota, credit, cache and generation-job
  ownership code was untouched; the 135 Zeli tests above re-passed.
- No credential, token or password is recorded in this section.

### 20.7 Working tree, production and release status

- Changes remain uncommitted and unpushed: **65 modified, 34 untracked, 0
  staged, 0 ahead** of `origin/main` (`43bb266`).
- No Render/Neon/production setting, secret or customer record was changed. The
  local `.env` was not edited.
- Browser data used an isolated database; the user's `teachflow.db` remains at
  users **85**, schemes **98**, generation_jobs **129** (unchanged this round).
- Sections 1–19 were preserved byte-for-byte before appending this section.

### 20.8 Remaining limitations / release blockers

1. Logout is still client-side (the token is discarded; the server does not
   maintain a revocation list). Password changes invalidate old tokens through
   the password-version claim. Server-side logout revocation remains out of
   scope and unchanged.
2. `school_admin` accepts legacy `is_admin` accounts; this preserves existing
   legitimate school administrators and cannot grant platform-admin access.
3. The §18 autopilot/configuration-gate conflict and §19 unverified live
   DeepSeek call remain open release items. The authentication boundary itself
   is now **RESOLVED**.
4. Nothing was committed, pushed or deployed; deployment remains a manual,
   authorised step.


## 21. Session-security closure and remaining browser acceptance — 2026-10-30

Continues section 20. The entry-aware authentication boundary stays as shipped;
this round adds server-side logout revocation, resolves the autopilot/config
conflict, completes lesson-edit/export and resume acceptance, and records the
current release position. No live AI request was made.

### 21.1 Logout investigation: what "client-side only" meant

At the start of this round the application had **no logout endpoint**. Access
tokens are stateless JWTs; `AuthContext.logout()` deleted the browser's
`sessionStorage` token and the API client's in-memory copy. The server only
invalidated tokens through the `pwv` (password-version) claim when a password
changed.

Isolated API reproduction (teacher, two sessions):

```text
PASS  teacher registered
PASS  two independent teacher sessions
PASS  teacher session works before logout
FAIL  logout endpoint (absent at that time)
PASS  token still worked after the browser "logout"
```

The original token therefore remained usable until its natural expiry once it
had been copied out of the browser. Platform admin behaved identically.
**Server-side revocation was necessary** for the stated session-security goal.

### 21.2 Implemented revocation (bounded, per-session, persistent)

| File | Change |
|---|---|
| `backend/src/auth.py` | `create_user_token` adds a unique `jti`; `_authenticate_user` rejects any token whose `jti` is in the revoked table before expiry. The `pwv` check and DB role check are unchanged. |
| `backend/src/database.py` | New `RevokedTokenDB` (`jti` primary key, `user_id`, `expires_at`, `revoked_at`). Stores no token, password or email. |
| `backend/src/migrations/v037_revoked_tokens.py` | Additive table + indexes; `down()` drops only this table. |
| `backend/src/routers/auth.py` | New `POST /api/auth/logout` (authenticated): records this token's `jti` until its `exp`, then purges expired rows. Concurrent duplicate logout rolls back harmlessly. |
| `frontend/src/lib/api.ts` | `api.logout()` calls the endpoint. |
| `frontend/src/lib/auth-context.tsx` | Logout fires the revoke request (headers captured before the local token is cleared), then clears the tab session. |

Properties verified: logging out one device leaves the same user's other session
valid; a revoked token cannot be "revived" by retrying; expired revocation rows
are purged; password-change invalidation still applies; legacy tokens minted
before this feature (no `jti`) still authenticate and simply cannot be
individually revoked until they expire. Recorded API evidence: teacher session
revoked (401), second session 200; admin session revoked (401 on
`/api/platform-admin/dashboard`).

### 21.3 Autopilot acceptance conflict resolved

`frontend/e2e/autopilot-acceptance.js` now follows the real workflow: after the
one upload action it completes the required configuration through
`Configure lesson rubrics` (school, teacher, class size, duration, reference,
periods, teaching days), saves, then takes the generation action. The same
helper is used for the class-confirmation and unlimited-account scenarios. The
configuration gate was **not** bypassed.

Results on the current build, isolated DB, `AI_MODE=OFF`:

```text
PASS  scenario 1: server plan counts (22 found · 5 this month · 17 wait)
PASS  scenario 1: configuration completes through the single entry point
PASS  scenario 1: ordered work list renders during the run
PASS  scenario 1: results view says "5 lesson plans ready"
PASS  scenario 7: plain reload fires no autopilot selection and no generation
PASS  scenario 7b: exhausted allowance renders the quota blocker
PASS  scenario 5: WAPEF is the only extra interruption
PASS  scenario 3: a plain visit NEVER auto-generates
PASS  scenario 5b: confirm-path handoff generates and caps at 5
PASS  scenario 4: unlimited plan fits everything this month (seeded Pro account)
PASS  mobile 375px: autopilot card and action fit the viewport
40 passed, 0 failed
```

Two genuine layout defects surfaced by this rerun were fixed: the long scheme
filename and the autopilot card overflowed a 375 px viewport. `PageHeader`
description now breaks words, the main column and `SurfaceCard` carry
`min-w-0`. The mobile measurements are now x=16 w=343 (card) and x=37 w=301
(action).

### 21.4 Lesson editing and export acceptance

`lesson-edit-export-acceptance.js` ran against an isolated DB and a deterministic
5-lesson job: **19 passed, 0 failed**. Edit → save → API read-back → reload
persistence all passed; DOCX (43 KB), PDF (244 KB, 22 pages) and XLSX (6 KB)
were real files, with no page/HTTP errors.

The rendered files were inspected, not just their HTTP status:

- DOCX header order: `Autopilot Basic School` → `Autopilot Teacher` → `Week 1`.
- `DATE / DAY:` now reads `Monday, Wednesday, Thursday` on every lesson; after
  the fix below no calendar dates remain in that row.
- `DURATION: 60 Minutes`; `PERIOD: 1st & 2nd`; class size 30; reference present.
- No `Quick check (unprompted):`, `What to look for:`, `Exit check:`, `NS:`,
  `MA:`, fences or truncated `from the…` fragments.

**Defect found and fixed:** the one-time download URL (`issue_download_url`) —
the path the UI export button actually uses — built the combined DOCX **without
the render context**, so the official GES form fell back to calendar dates in
`DATE / DAY`. The PDF branch already passed context. The DOCX branch now passes
`_render_context(...)`; a regression test pins the contract
(`test_issue_download_url_docx_passes_render_context`). Re-export after the fix
showed weekday names only.

Residual quality observations (not release-blocking, recorded honestly): the
deterministic prose still uses a plain `Quick check:` assessment label (the
banned `Quick check (unprompted):` form is gone), and one lesson's assessment
quotes two curriculum indicators in sequence. Both remain quality-priority
items; the quality gate accepted the lessons.

### 21.5 Generation-resume acceptance

A dedicated DB staged one failed job with one persisted lesson and one planned
pending occurrence (deterministic, `AI_MODE=OFF`). `resume-acceptance.js`:
**15 passed, 0 failed** —

- recovery banner names pending work and offers `Resume pending lessons`;
- resume reuses the same job, generates exactly one additional lesson, keeps the
  existing lesson and its topic, and produces no duplicate occurrence ids;
- the same job reaches `completed`; no resumable occurrences remain;
- no page or HTTP errors.

Backend resume/quota idempotency tests are included in the 427-test batch below.

### 21.6 Browser journey matrix (current build, rerun today)

| Journey | Result |
|---|---|
| `hero-particles-acceptance.js` | **62 passed, 0 failed** |
| `hero-auth-acceptance.js` | **134 passed, 0 failed** |
| `hero-v3-acceptance.js` | **150 passed, 0 failed** |
| `auth-entry-boundary.js` | **10 passed, 0 failed** |
| `lesson-config-acceptance.js` | **9 passed, 0 failed** |
| `autopilot-acceptance.js` (updated) | **40 passed, 0 failed** |
| `lesson-edit-export-acceptance.js` | **19 passed, 0 failed** |
| `resume-acceptance.js` | **15 passed, 0 failed** |
| **Total** | **439 passing journey assertions** |

The served `not-found` chunk hash matched `.next` throughout; no stale process
served an older build.

### 21.7 DeepSeek recheck (no live call)

The 135-test Zeli/DeepSeek group re-passed inside the 427-test batch:
configuration defaults and validation, key precedence, `thinking` transmission,
conditional temperature, `max_tokens` mapping, `(connect, read)` timeout,
bounded transient-only retries, safe usage parsing, cache separation, quota
pre-checks and the unchanged standard path. No provider, model, `.env` or
migration touched by this round modifies Zeli. **Live DeepSeek verification:
NOT RUN.** The previously exposed key must be treated as compromised and rotated
by the owner before any live test or production use.

### 21.8 Full verification summary

| Check | Result |
|---|---|
| Backend batch: logout, entry boundary, lifecycle, CORS, security, roles, school admin, authorization, IDOR, resume, guided config, week/header, export, Zeli×3, quota | **427 passed** (129.91 s) |
| `npx tsc --noEmit` | exit 0 |
| `npm run build:web` | succeeded |
| Browser journeys | **439 assertions, 0 failures** |
| Live AI | **NOT RUN** (prohibited) |

### 21.9 Release hygiene

- Sections 1–20 preserved byte-for-byte before this section was appended.
- The acceptance report remains untracked durable evidence.
- `frontend/tsconfig.tsbuildinfo` is still a tracked generated artifact and must
  be excluded from any release commit.
- Local `.env` files remain uncommitted and were not modified.
- Migration inventory now includes `v037_revoked_tokens` alongside v034–v036;
  each ships with its feature.
- No generated DB, export or backup is part of the proposed release inventory;
  isolated databases live only in the temp directory.
- Working tree: **68 modified, 36 untracked, 0 staged, 0 ahead** of `43bb266`.
  Nothing was committed, pushed or deployed.

### 21.10 Remaining blockers and recommendation

1. **Live DeepSeek call still unverified** (and the key must be rotated first).
2. **Residual prose quality**: plain `Quick check:` labels and one concatenated
   indicator sentence remain visible in deterministic output; the gate passes
   them, so this is a quality-improvement item, not a security defect.
3. **Legacy tokens** issued before v037 have no `jti`; they remain valid until
   expiry (bounded by the existing token lifetime) and cannot be individually
   revoked. New tokens are fully revocable.
4. Deployment-level checks (staging/PostgreSQL drill, production enforcement)
   remain outside this local task.

**Recommendation: CONDITIONAL.** The authentication entry boundary and logout
revocation are now implemented and verified, and all eight non-billable browser
journeys pass on the current build. A GO still requires a controlled live
DeepSeek verification with a rotated key, the remaining prose-quality pass, and
the existing deployment/production checklist. Nothing was staged, committed,
pushed or deployed.


## 22. Source-accurate weekly mapping correction and release position — 2026-10-30

This section corrects a material interpretation in sections 18–21 and records
what is, and is not, ready. Sections 1–21 are preserved byte-for-byte.

### 22.1 Correction of the earlier Week 2 interpretation

Section 21 accepted the PDF label sequence `Week 1, Week 2, Week 2, Week 3,
Week 4` as "consistent with the allocation". **That interpretation was wrong.**
The source scheme has exactly **one schedule row per numbered week**. Week 2 is
one row dated 18/09/2026 containing two indicators (`B9.1.1.1.2`,
`B9.1.1.1.3`). Both belong to **one** Week 2 weekly plan. The correct first-five-
week output is `Week 1, Week 2, Week 3, Week 4, Week 5`, each once.

### 22.2 The source document actually inspected

`backend/real_documents/BASIC 9 SCIENCE SCHEME OF LEARNING.docx` (SHA-256 prefix
`9E77202ECCAF`, 34,362 bytes; identical copies also exist under
`backend/uploads/` and `src/uploads/templates/staged/`). It contains **three
Word tables** (7 / 4 / 5 rows) and one schedule row per numbered week 1–15.
Vertical merges (`w:vMerge`) share strand / sub-strand / content-standard cells
across adjacent rows; merged text must be inherited by those rows without
collapsing the schedule rows.

Verified parser output before any correction:

| Week | Ending | Content standard | Indicators |
|---|---|---|---|
| 1 | 2026-09-11 | B9.1.1.1 | .1 |
| 2 | 2026-09-18 | B9.1.1.1 | .2, .3 |
| 3 | 2026-09-25 | B9.1.1.2 | .2.1 |
| 4 | 2026-10-02 | B9.1.2.1 | .1.1, .1.2 |
| 5 | 2026-10-09 | B9.1.2.1 | .1.3 |
| 6 | 2026-10-16 | B9.2.1.1 | .1.1, .1.2 |
| 9 | 2026-11-06 | B9.3.1.1 | .1.1 |
| 10 | 2026-11-13 | B9.3.1.1 | .1.2 |
| 11 | 2026-11-20 | B9.4.1.1 + B9.4.1.2 | six indicators |
| 13/14/15 | 04/11/18 Dec | — | Revision / End of Term Assessment / SBA Activities and Vacation |

The explicit week number from `WEEK ENDING` is authoritative; strands and content
standards repeat across weeks 1–2, 4–5, 9–10 without merging them.

### 22.3 Parser defect found and fixed

The row identity and week numbers were already correct, but **indicator text was
corrupted**: when a cell held several indicator codes, the parser stripped every
code from the whole cell and gave the same concatenated remainder to each
indicator. Week 2 therefore became:

```text
.2 Discuss the formation of binary chemical compounds Describe the characteristics of common acids, bases and salts.
.3 Discuss the formation of binary chemical compounds Describe the characteristics of common acids, bases and salts.
```

Fix (`backend/src/parsers/docx_parser.py`): each code now owns only the text
between it and the next code; code-only cells keep an empty description; a
repeated code with different text raises a review warning instead of being
silently merged. After the fix Week 2 reads exactly:

```text
.2 Discuss the formation of binary chemical compounds
.3 Describe the characteristics of common acids, bases and salts
```

Weeks 4, 6, 10 and 11 are likewise de-concatenated.

### 22.4 Source anomalies preserved (not "fixed")

- Week 7's content standard cell carries `B9.2.3.1 …` plus a stray `B9.2.3.2`.
- The indicator code `B9.2.3.2.1` appears in **both** Week 7 and Week 8, while
  Week 8's primary indicator is `B9.2.3.2.2`.
- Week 11 uses malformed source spacing (`B9.4.1.1 .1`) and mixes two content
  standards in one row.
- Week 12 uses `B9. 5.1.1.1` with a space.

The parser preserves the row assignments and the per-week indicator lists; these
source defects are reported here rather than silently rewritten.

### 22.5 Critical remaining defect: one weekly plan per schedule row (NOT fixed)

`GenerationPipeline` still allocates **one occurrence per indicator**, not one
per source schedule row. On the actual scheme:

```text
total allocations: 22
per week: {1:1, 2:2, 3:1, 4:2, 5:1, 6:2, 7:2, 8:2, 9:1, 10:1, 11:6, 12:1}
weeks 1–5: 1, 2, 1, 2, 1
```

So a deterministic run over weeks 1–5 produces **seven** lesson records and
therefore duplicate `Week 2` and `Week 4` headers — exactly the defect the source
clarification identifies. The earlier PDF (`1,2,2,3,4` for a capped 5-lesson
selection) is direct evidence of the same cause.

Fixing this is not a renderer change. It requires a deliberate model decision:
one occurrence per schedule row carrying all its indicators, generation prompts
and lesson schema accepting multiple indicators, and a decision on whether quota
charges per row or per indicator. Those changes cut across allocation, quota,
Zeli context, deterministic composition, persistence and both exporters, and
existing WAPEF/other-scheme behaviour depends on the per-indicator model. It was
**not** attempted ad hoc in this round.

**Therefore the Part B stop gate was triggered:** no live DeepSeek request was
made, because doing so would spend the owner's balance generating a document
with the known duplicate-week mapping.

### 22.6 DeepSeek configuration check (no live call)

Configuration was read without printing the secret:

```text
provider=deepseek model=deepseek-flash base=https://api.deepseek.com
key_present=True thinking=disabled temperature=0.3 max_tokens=5000
connect=10 read=90 retries=2
```

The rotated key is present and the provider contract matches
`docs/ZELI_ENVIRONMENT.md`, with one local deviation: `.env` sets
`ZELI_MAX_TOKENS=5000` rather than the 2000 required for the controlled test.
The live test would have overridden it to 2000 in the isolated process only; the
file was not edited. **Live DeepSeek: NOT RUN.**

A separate boot issue was found and fixed: the owner's `.env` now contains
Paystack keys (`paystack_secret_key`, `next_public_paystack_public_key`,
`paystack_currency`) that `Settings` did not declare, so the current tree could
not start. Optional fields were added to `config.py` (no secrets printed, no
values changed). The backend now boots with the owner's `.env`.

### 22.7 Tests run (actual)

| Command / group | Result |
|---|---|
| `pytest tests/test_basic9_source_week_mapping.py -q` (new, actual DOCX) | **12 passed** |
| `pytest` batch: mapping + indicator allocation + week/header + V2 integration + quality gate + WAPEF acceptance + Zeli DeepSeek + logout + auth entry | **262 passed** (31.75 s) |

The 12 mapping tests assert all 15 weeks/dates, Week 2's two indicators with
their own text, shared standards across 1–2 / 4–5 / 9–10, Week 11's two
standards, special weeks 13–15, no indicator moved to an adjacent week, and the
Week 7/8 anomaly.

### 22.8 Authentication and session security recheck

Within the 262-test batch: entry-boundary (20) and logout revocation (7) pass:
cross-entry logins 401, teacher tokens 403 on admin APIs, admin tokens accepted,
forged/tampered/expired tokens rejected, logout revokes only that session,
independent sessions survive, password-version invalidation intact, revocation
rows contain only `jti`/user/expiry. Migration v037 is additive; pre-v037 tokens
(no `jti`) remain valid only until natural expiry — the access-token lifetime is
**24 hours**, so the legacy transition is bounded to one day after deployment.
No forced global invalidation is justified.

### 22.9 Deployment-readiness checklist (not executed)

- **Secrets:** DeepSeek key only in the backend service; never `NEXT_PUBLIC_*`;
  Paystack secret server-side only; sanitized provider errors.
- **Migrations:** v034 heartbeat, v035 Zeli provenance/cache, v036 per-scheme
  lesson config, v037 revoked tokens. All additive; run in order; back up first;
  `v037.down()` drops only `revoked_tokens`.
- **Auth:** entry-aware login, DB-role authorization, server-side logout,
  24-hour legacy-token transition, CORS unchanged, bootstrap/recovery intact.
- **AI ops:** deepseek/deepseek-flash, thinking disabled, 2000-token budget for
  live acceptance, 10/90 s timeouts, two transient retries, no Groq fallback,
  cached-token usage capture.
- **Recovery:** database backup, migration re-run safety, app rollback, key
  rotation, stale-job recovery.
- **Hygiene:** exclude local `.env`, `frontend/tsconfig.tsbuildinfo`, temp
  databases and export artefacts; include the acceptance report and v034–v037.

### 22.10 Working tree

**68 modified, 37 untracked, 0 staged, 0 ahead** of `43bb266`. Nothing was
committed, pushed, deployed or tagged. The original `backend/teachflow.db` is
unchanged (85 users / 98 schemes / 129 jobs); all acceptance data lived in temp
databases.

### 22.11 Final recommendation

**NO-GO.** Curriculum wording extraction and week identity are now source-
accurate, but the required product rule — **one weekly plan per source schedule
row** — is not implemented: weeks 1–5 still allocate 1,2,1,2,1 lessons and would
render duplicate Week 2/Week 4 headers. Because that is a critical unresolved
defect in the highest-priority area, the authorised live DeepSeek request was
deliberately not spent.

The next engineering task is narrowly defined: extend the allocation/occurrence
model to one record per schedule row (carrying all that row's indicators),
decide and document the quota unit, feed all indicators into deterministic and
Zeli prompts, then prove `Week 1–5` each appear once in DOCX and PDF. Only after
that should the single controlled DeepSeek acceptance call be made.
