# PRODUCTION READINESS — Final Smoke Verification (P4 Runtime Evidence)

**Date:** 2026-10-09, updated 2026-10-15 (Phase 8 engineering close-out), updated 2026-10-16 (production read-only verification — no code change)  
**Source commit:** 2121a2c → fix `70738f8` (quota incident — see §5) → local engineering Phases 1–8 on main (see §8)  
**App code:** identical to ae84f19 (P4) at the 2121a2c stage — `git diff --stat ae84f19..2121a2c` is docs-only (4 doc files)  
**Production commit (actual):** **`3ef1a41`** — owner-approved one-time backend deploy `dep-db8aftlg1s2s739kr47g`, live 2026-10-15T10:18:21Z (contains quota fix `70738f8`; deploy record + ancestor check + 2026-10-16 content verification: deployed `usage_quota.py`/`entitlements.py` byte-identical to local main's). Local main is deliberately AHEAD of the deployed commit (Phases 1–7 engineering, §8) and is NOT deployed — no production deploy without explicit owner approval.  
**Status:** JOURNEY GREEN + P4 EVIDENCED + quota fix DEPLOYED + deployed content VERIFIED (2026-10-16, read-only) — **RED / NO-GO until (a) the §13h live denial test passes on the deployed build, (b) the §13e historical reconciliation is approved and applied, and (c) an owner decision is made on Proposal 2/§13g** (full report: docs/QUOTA_ACCOUNTING_INCIDENT.md §13d–§13h)

## 1) Source baseline
- At the 2121a2c smoke stage: HEAD == origin/main == 2121a2c; P4 (quality gate A–X, repair, rebuild ≤2, rubric, WAPEF saved-selection-only, accept-scoped replacement, quota 0/1, calibration) fully included.
- Local reference at Phase 8 close-out (2026-10-15): full backend suite **2419 passed / 16 skipped**; PG quota driver gate **22 passed**; Phase 7 multi-subject export fidelity **13 passed**; frozen corpora **11/11 + 40/40 + 19/19 teacher-ready, first-pass 100%** (docs/benchmark/final_gate_metrics_2026-10-15.json). Frontend unaffected by Phases 4–7 (backend-only).

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
- **Deployed 2026-10-15 (owner-approved one-time deploy):** manual deploy `dep-db8aftlg1s2s739kr47g` = commit `3ef1a41` (contains `70738f8`), live 10:18Z; pre-deploy PG gate 22 passed; `/api/health` 200 (liveness only). **Still required before GO:** the §13h live denial test (approval + owner-held token; generation POSTs excluded from this side) and the §13e historical reconciliation — SQL **hardened 2026-10-16** (server-side `RAISE EXCEPTION` preconditions/post-conditions, exact-orphan narrowed deletion, guarded rollback; §13e Proposal 1 and §13g Proposal 2 remain separate approvals) and validated on a disposable local PostgreSQL with synthetic data (`backend/validate_quota_repair_sql.py`; incident doc §13e/§13g verification tables; current revision: **11/11 cases**, full-row logical fingerprint, rollbacks preserve captured original period timestamps — see post-session note below) — **not executed against production, awaiting explicit owner approval**.
- **Production read-only verification 2026-10-16 (zero writes, zero POSTs — Render API + three `READ ONLY` DB probes, all rolled back):** deployed `usage_quota.py` content-verified (RETURNING-based `_insert_ignore`; `usage_quota.py`/`entitlements.py` byte-identical `3ef1a41..217a32c`); incident account re-validated (7 units / 6 persisted lessons / 1 orphan `B9.1.1.2.1` / counter `0` — §13e still exactly correct, expected `used=6`); **production-wide finding: all 15 `usage_periods` rows hold `units_used = 0` against 166 ledger rows (14 affected accounts), 164 units matched to lessons, 2 orphans total** — defect was not incident-only; 0 generation jobs since the deploy (fixed code never exercised). Inventory + wider proposal: incident doc §13f–§13g. Detail: docs/QUOTA_ACCOUNTING_INCIDENT.md §13f.
- Prior smoke stage made no source changes; no quota data tampered.

## 6) Not tested / partial (production, reported honestly)
- **Live quota denial (403) in the production runtime:** NOT EXECUTED — plan and exact payload prepared (incident doc §13h); requires owner approval + owner-held token → NOT TESTED.
- **Reserve-path race guard (concurrent reservation):** NOT TESTED live (unreachable in a single denial test); covered by local PG concurrency tests only → PARTIAL.
- **Bounded rebuild (≤2):** NOT TRIGGERED — all runs `mean_rebuilds=0` → NOT TESTED.
- **Mixed accept+reject in one multi-code run:** NOT EXERCISED (single-code runs only; total-rejection path exercised) → PARTIAL.
- **P1 edge (4 indicators / 2 periods exact):** not exercised in production (covered by local tests) → PARTIAL.
- **WAPEF:** smoke scheme is non-WAPEF → NOT TESTED (no WAPEF fixture uploaded this stage).
- **Browser UI journey:** not executed; frontend serves 200, journey verified at API level → PARTIAL.

## 7) GO/NO-GO
**NO-GO / RED — until (a) the §13h live denial test passes on the deployed build, (b) the §13e historical reconciliation is approved and applied (`used=6`, over-limit block until 2026-11-01), and (c) the owner decides on Proposal 2/§13g (the other 14 period rows, all stuck at `used=0` — §13f).** Deployed build: live Render deploy `dep-db8aftlg1s2s739kr47g` = commit `3ef1a41` (contains quota fix `70738f8`), verified by deploy record + ancestor check + 2026-10-16 content verification; health 200. The complete AI-OFF upload→export journey and P4 end-to-end behavior already passed on this code lineage (§3, §4). The admission path was read end-to-end and shown to be write-free up to the pre-check 403 (incident doc §13h) — but a denial request has NOT been sent: remaining gaps are owner-gated (approval of one denial POST with an owner-held token, and approval of the §13e/§13g SQL), not open code defects. Until §13e/§13g run, every free account's stored counter truthfully reads 0 and the cap under-binds production-wide.

## 8) Engineering close-out record (Phases 1–8, local main, 2026-10-15)

Local main carries post-deploy engineering that is intentionally NOT deployed (deploy requires explicit owner approval). Every phase is a separate commit with committed evidence:

| Phase | Commit | Outcome |
|---|---|---|
| 0 Quota incident closure | `e5499fc`, `e7941f8` | Deployed commit established; owner-approved one-time deploy of `3ef1a41` live 2026-10-15; §13c–§13d evidence recorded; §13e backfill prepared, NOT executed (HOLD) |
| 1 Verb correction verification | `c9412b0`, `5a7698c` | Shared indicator-action inventory fixes false rejections; all ten flagged verb families verified; no additional rubric change |
| 2 Current baseline | `59af277`, `a66cd64` | Current-code baseline 100% teacher-ready (11/40/19); P2.1-era 31/40+12/19 delta reconciled (same fixtures/harness; only the Phase 1 fix differs) |
| 3 DoK assessment + rubrics | `8974da3` | Deterministic Depth-of-Knowledge assessment items + conditional analytic rubric on the canonical lesson model; read-only frontend display; migration v033 |
| 4 Differentiation / Ghana / realism | `b16b42a` | Frozen corpora improved with zero regressions (activity_specificity +0.27/+0.34/+0.58, resource_realism +0.18/+0.23/+0.27); DOCX hygiene defects (bare brackets, rubric tables breaking form topology) fixed |
| 5 Reuse/retry/recovery | `923d5ff` | Five NO-GAP/OBSERVATION findings; one demonstrated gap fixed — orphaned `pending` jobs (process death) now fail at startup (age-thresholded sweep) |
| 6 Zeli/P4 call-graph audit | `d9c230d` | "post-AI" wording verified accurate; Zeli-separation rules hold in code; documented no-change |
| 7 Final benchmark + export fidelity | `bdfc661` | 100% teacher-ready held (11/40/19, first-pass 100%); six-subject DOCX/PDF export fidelity suite 13 passed |
| 8 Production readiness docs | (this commit) | This document + pilot/production-version.md brought to the deployed-state truth; NO-GO restated on the two owner-gated items |

Verification at close-out: full backend suite 2419 passed / 16 skipped; PG driver gate 22 passed; Phase 7 export fidelity 13 passed; frozen corpora artifacts committed under docs/benchmark/. No production data was mutated at any point in Phases 1–8; historical quota reconciliation remains HOLD pending explicit owner approval (exact SQL, expected results, rollback plan: docs/QUOTA_ACCOUNTING_INCIDENT.md §13e).

Post close-out (2026-10-16, evidence-only session): production re-verified read-only — deployed content matches the tested fix; §13e re-validated against live rows; production-wide counter defect (15/15 period rows at 0) and 2 total orphans established; exact SQL proposals (§13e, §13g) and live denial test plan (§13h) prepared; zero production writes, zero production POSTs, no deploy, no code change (docs-only commit).

Post close-out, hardening session (2026-10-16, still no production writes/POSTs/deploys): §13e/§13g SQL rewritten with unconditional server-side enforcement (comment-free `RAISE EXCEPTION` guards — an operator cannot "forget" a precondition check), exact-orphan narrowed deletion, `GET DIAGNOSTICS` row-count enforcement, per-row/per-month post-conditions, and rollback scripts that refuse (never overwrite) on any drift; both proposals + rollbacks validated (initially **10/10**, superseded by the revision below) on a disposable local PostgreSQL against synthetic production-shaped data (`backend/validate_quota_repair_sql.py`, loopback-only). Synthetic validation is not production verification; §13e and §13g remain unexecuted and separately owner-gated; RED/NO-GO unchanged.

Post hardening, integrity session (2026-10-16, still no production writes/POSTs/deploys): rollback integrity gap closed — both repairs now capture each affected `usage_periods.updated_at` as explicit `P1_ORIGINAL_PERIOD` / `P2_ORIGINAL_PERIOD` NOTICE packets before mutating, and both rollbacks restore those exact values (refusing to proceed without a complete, consistent capture); state comparison strengthened from a limited aggregate fingerprint to a **full-row logical fingerprint** over every column of all four synthetic-schema tables; validator re-run **11/11 cases** (each rollback restores the complete original fingerprint incl. per-row timestamps; single-field mutations of previously-uncovered columns change the fingerprint; bad/duplicated/missing captured packets are refused with the database unchanged). Limitation stated in the incident doc: scripts verify packet internal consistency but cannot detect a mistyped-yet-plausible packet value — the operator must copy raw NOTICE output verbatim. §13e and §13g remain unexecuted and separately owner-gated; RED/NO-GO unchanged.
