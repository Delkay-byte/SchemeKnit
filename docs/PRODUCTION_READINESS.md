# PRODUCTION READINESS — Final Smoke Verification (P4 Runtime Evidence)

**Date:** 2026-10-09  
**Source commit:** 2121a2c → fix `70738f8` (quota incident — see §5)  
**App code:** identical to ae84f19 (P4) — `git diff --stat ae84f19..2121a2c` is docs-only (4 doc files)  
**Production commit (actual):** UNKNOWN (no public deploy/build marker; behaviour markers used)  
**Status:** JOURNEY GREEN + P4 EVIDENCED — **RED / NO-GO until fix `70738f8` is deployed and verified** (quota accounting defect root-caused; full report: docs/QUOTA_ACCOUNTING_INCIDENT.md)

## 1) Source baseline
- HEAD == origin/main == 2121a2c. P4 (quality gate A–X, repair, rebuild ≤2, rubric, WAPEF saved-selection-only, accept-scoped replacement, quota 0/1, calibration) fully included.
- Local reference: P4 gate 58 passed; WAPEF boundary 11 passed; full non-env suite 2366 passed / 11 skipped; frontend `tsc --noEmit` clean, `next build` passes.

## 2) Production state (runtime, 2026-10-09)
- API health 200 `{"status":"healthy","service":"SchemeKnit","version":"1.0.5"}` (1.24 s cold).
- Frontend `https://schemeknit-frontend.onrender.com` → 200 (HTML served).
- Deployed SHA still UNKNOWN. P4 presence proven behaviourally (see §4): the only commit in any ref containing the observed gate strings/fields is ae84f19.

## 3) End-to-end journey — PASSED (dedicated synthetic test account, AI OFF)
Scheme `backend/real_documents/BASIC 9 SCIENCE SCHEME OF LEARNING.docx`, production scheme_id `ab28233d-f87c-4753-98c1-fbb94acead7f`.

| Step | Result |
|---|---|
| Login | 200 (0.74 s), role teacher |
| Upload + extraction | 200 (2.29 s), 15 weeks / 20 indicator codes |
| Detection | `single`, Science / Basic 9 |
| Weeks | 200, codes `B9.1.1.1.1`… |
| Autopilot | `ready`, 22 pending, **selected 5 (quota-capped)**, 17 quota_skipped, 0 needs_review |
| Generate (AI OFF) | 200 (3.6 s), job `b8dd26a9-918e-4c9d-9090-b10469f2e0f9`, `quality` metrics returned |
| Persistence | lesson stored with structured content, indicator codes |
| Reload | 200, same topic |
| DOCX | 200, valid ZIP (38 729 B), topic/objective/phase/assessment/resources/indicator checks pass |
| PDF | 200, valid `%PDF` (5 381 B, 2 pages), topic/objective/phase/assessment checks pass |
| Quota reads | **DEFECT — see §5** |

## 4) P4 runtime evidence (criterion H — DEMONSTRATED)
1. **Metrics:** every accepted run returns `quality` = `{lessons, accepted, rejected, first_pass, repaired, rebuilt, first_pass_rate, teacher_ready_rate, mean_score, mean_rebuilds, hard_rejections, soft_rejections, repairs}` — these keys exist only in ae84f19 (`git log -S first_pass_rate --all` → ae84f19 only). Observed `mean_score 71.0`, `first_pass_rate 1.0` — identical to local deterministic run (byte-stable scores).
2. **Hard rejection executed in production:** indicator `B9.1.1.2.1` → HTTP 500  
   `"Generation failed: the lesson quality gate rejected every lesson in this run, so nothing was saved and no lesson-plan quota was consumed. … Rejections: {'generic_objective': 1}."`  
   Reproduced deterministically (same input → same rejection, both attempts).
3. **Nothing persisted on rejection:** lesson list after the rejected run excluded `B9.1.1.2.1` (verified); accept-only persistence — 6 accepted lessons persisted, rejected code absent.
4. **Deterministic marker PASS:** objective `Learners can Identify by name binary chemical compounds and discuss their use` (verb-led P2 form); `has_stale_discuss_objective=false`, `topic_is_strand_concat=false` (no pre-P2 "Discuss…" / strand-concat behaviour).

## 5) Quota defect — P1, RED criterion (criterion I — FAILED; root-caused, fixed pending deploy)
- **Observed:** `used=0, remaining=5, limit=5` on every read (quota endpoint, Autopilot quota, generate responses) after **6 accepted distinct lessons on a limit of 5**. Autopilot kept selecting 5; enforcement never bound (`6 > 5` still accepted). Free Tier cap is unenforceable in production.
- **Root cause (evidenced, reproduced locally):** `usage_quota._insert_ignore` decided "inserted" via `rowcount == 1`, but on the production stack (PostgreSQL + psycopg 3.3.5 + SQLAlchemy 2.0.35) the Core `INSERT … ON CONFLICT DO NOTHING` path reports **`rowcount == -1`** for both insert and conflict. Every reservation was misread as `already_counted` → the guarded `units_used + n <= limit` UPDATE never ran → counter stuck at 0 and the limit guard never executed. Reproduced: same reserve call on PG returns `consumed=0, used=0`; quota suite **9/12 failed on PG pre-fix** (SQLite reports a truthful rowcount — hence local green). Direct probe: `rowcount=-1`. Full analysis: docs/QUOTA_ACCOUNTING_INCIDENT.md (§7–§8).
- **Fix (commit `70738f8`):** `_insert_ignore` detects insertion via `RETURNING` (driver-independent) and returns a bool; no policy/ledger/P4/P1 change. Regression: model contract, endpoint journey (5-permit / 6th-403-no-side-effects / read-after-write / Autopilot exhaustion / per-user scope / cross-week idempotency), gate partial+total rejection zero-charge, and a named PostgreSQL driver gate (`tests/test_postgres_quota_driver.py`, incl. concurrency).
- **Verification:** full backend suite `2374 passed, 15 skipped, 0 failed` (SQLite); targeted PostgreSQL runs all green (monthly quota, PG driver gate, endpoint journey, quality gate, priority3 workflow, autopilot, AI ledger). Frontend unaffected.
- **Deployed 2026-10-15 (owner-approved one-time deploy):** manual deploy `dep-db8aftlg1s2s739kr47g` = commit `3ef1a41` (contains `70738f8`), live 10:18Z; pre-deploy PG gate 22 passed; `/api/health` 200 (liveness only). **Still required before GO:** §12.3 runtime enforcement check (no authorized token; generation probes excluded this phase) and the §13e historical reconciliation — proposal prepared (6 chargeable units, orphan rejected-candidate row to drop, expected `used=6`/blocked-until-Nov), **not executed, awaiting explicit owner approval**. Detail: docs/QUOTA_ACCOUNTING_INCIDENT.md §13d–§13e.
- Prior smoke stage made no source changes; no quota data tampered.

## 6) Not tested / partial (production, reported honestly)
- **Bounded rebuild (≤2):** NOT TRIGGERED — all runs `mean_rebuilds=0` → NOT TESTED.
- **Mixed accept+reject in one multi-code run:** NOT EXERCISED (single-code runs only; total-rejection path exercised) → PARTIAL.
- **P1 edge (4 indicators / 2 periods exact):** not exercised in production (covered by local tests) → PARTIAL.
- **WAPEF:** smoke scheme is non-WAPEF → NOT TESTED (no WAPEF fixture uploaded this stage).
- **Browser UI journey:** not executed; frontend serves 200, journey verified at API level → PARTIAL.

## 7) GO/NO-GO
**NO-GO / RED — until (a) the §12.3 runtime enforcement check passes on the deployed build and (b) the §13e historical reconciliation is approved and applied (`used=6`, over-limit block until 2026-11-01).** Deployed build updated 2026-10-15: live Render deploy `dep-db8aftlg1s2s739kr47g` = commit `3ef1a41` (contains quota fix `70738f8`), verified by deploy record + ancestor check; health 200. The complete AI-OFF upload→export journey and P4 end-to-end behavior already passed on this code lineage (§3, §4). Remaining gap is historical data, not code: the affected account's stored counter is still `used=0` until §13e runs, so the free-tier cap is under-enforced for that account this month. No production lesson generation until an approved safe test plan exists. Owner decision required on §13e.
