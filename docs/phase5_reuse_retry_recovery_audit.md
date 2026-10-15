# Phase 5 — Reuse / retry / recovery audit (2026-10-15)

Read-only audit of the generation path (`routers/generation.py`,
`engines/lesson_quality_gate.py`, `engines/generation_pipeline.py`,
`usage_quota.py`, `service.py`, `main.py`), followed by one demonstrated-gap
fix. Full-suite regression green after the fix.

## Findings

| # | Area | Verdict | Evidence |
|---|---|---|---|
| 1 | Draft reuse in the quality gate | **NO-GAP** | `_run_quality_gate` callers pass teacher review drafts loaded fresh from the DB (`generation.py:921–935`); drafts are re-applied on every rebuild candidate (`generation.py:2168`) and used as the WAPEF-loss canonical (`2132–2133`, `2169–2171`). Prior attempt output is retained: the repaired original stays in the candidate pool (`2139–2142`) and `pick_best` selects among all passing candidates (`2187–2206`, deterministic tie-break `lesson_quality_gate.py:599–615`). |
| 2 | Retry semantics | **NO-GAP** | 1 mechanical repair pass (content-preserving, in-place, `lesson_quality_gate.py:423–495`); ≤ `MAX_REBUILD_ATTEMPTS = 2` pattern-rotation rebuilds with tried patterns excluded (`generation.py:2144–2185`, `lesson_quality_gate.py:527–535`); deterministic and bounded; final failure drops the lesson (old row survives, quota unit released) and only a 100 % rejected batch fails the request (`generation.py:938–954`, `2207–2231`; pinned `test_quality_gate.py:675–750`). |
| 3 | Batch recovery / quota interaction | **NO-GAP** | Quota is reserved atomically up-front (whole batch admitted or refused before any generation, `usage_quota.py:204–227`) — "quota runs out mid-batch" cannot occur. Per-lesson failure is fail-open (`generation.py:2118–2231`); AI enrichment fails open per lesson (`generation_pipeline.py:506–558`). Units for non-produced codes are released; failures consume nothing (`generation.py:1032–1039`, `1123–1136`; pinned `test_monthly_quota.py`, PG driver suite 22 passed). |
| 4 | Duplicate generation / idempotency | **OBSERVATION (no change)** | No explicit double-submit guard, but sequential duplicates converge by design (replacement keyed to accepted occurrences; pinned `test_generate_workflow_priority3.py:210–238`, `test_generation_workflow_regression.py:66–72`) and every ledger is idempotent (lesson unit keys unique per scheme:code; AI credit per request_id). Only a multi-worker concurrent double-generate is unprotected; its blast radius is transient lesson duplication already healed by the next run — a proper fix needs a lock/unique constraint, beyond minimal scope. |
| 5 | Crash recovery | **GAP → FIXED** | A hard process death mid-generation skips the endpoint's exception handlers (which explicitly guarantee "never leave it pending forever", `generation.py:1126–1128`) and the job stayed `pending` forever — shadowing `GET /scheme/{id}/status` (newest job first, `service.py:364–367`) and the job history. |
| 6 | Lesson reuse across runs | **NO-GAP** | Accept-scoped replacement, survivor re-homing to the new job, teacher edits preserved outside the selection (`generation.py:911–1008`, `service.py:602–633`; pinned `test_generate_workflow_priority3.py:275+`). A gate-dropped lesson keeps its existing row (`960–964`). |

## Fix (the single code change of this phase)

`DataService.reconcile_stale_generation_jobs` (`service.py`) fails
non-terminal (`pending`/`processing`) jobs older than 60 minutes with
"Generation was interrupted by a server restart. Please generate again.",
wired into the app lifespan (`main.py`) after migrations, non-fatal on error,
logging a count when it acts. The age threshold keeps a multi-worker peer's
live run safe on any shared deployment; on the single-process Render deploy a
non-terminal job at startup is by definition orphaned. Lesson rows and quota
units are untouched — a rerun already converges and unit keys are
idempotent (findings 3 and 6). The frontend only restores `completed` jobs
(`generate/[id]/page.tsx:249`), so no UI change was needed.

Tests: `tests/test_stale_job_reconciliation.py` — stale pending → failed with
message; recent pending + terminal jobs untouched; `processing` orphans
fail; lesson rows survive reconciliation.

## Verification

- New + generation/gate suites: 69 passed.
- HTTP workflow / quota / autopilot / AI-hardening batch: 75 passed.
- PG quota driver gate (docker postgres:16): 22 passed (pre-existing).
- Full backend suite after Phase 4: 2419 passed / 16 skipped (Phase 5 adds
  only isolated code on top; targeted batches above re-green).
- No production data touched; no thresholds, floors or fixtures changed.
