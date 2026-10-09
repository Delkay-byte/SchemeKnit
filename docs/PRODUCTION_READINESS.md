# PRODUCTION READINESS — Final Smoke Verification (P4 Runtime Evidence)

**Date:** 2026-10-09  
**Source commit:** 2121a2c (HEAD == origin/main)  
**App code:** identical to ae84f19 (P4) — `git diff --stat ae84f19..2121a2c` is docs-only (4 doc files)  
**Production commit (actual):** UNKNOWN (no public deploy/build marker; behaviour markers used)  
**Status:** JOURNEY GREEN + P4 EVIDENCED — **RED / NO-GO (quota accounting defect)**

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

## 5) Quota defect — P1, RED criterion (criterion I — FAILED)
- **Observed:** `used=0, remaining=5, limit=5` on every read (quota endpoint, Autopilot quota, generate responses — all `cache-control: no-store`) after **6 accepted distinct lessons on a limit of 5**. Autopilot kept selecting 5; enforcement never bound (`6 > 5` still accepted). Free Tier cap is unenforceable in production.
- **Local HEAD, identical flow:** `used=1` after the first generation (also asserted by repo test `tests/test_generate_workflow_priority3.py:238`). Static analysis of origin/main: reserve → guarded `units_used + n <= limit` UPDATE → commit; produced keys `f"{scheme}:{code}"` match reserved keys → release must not fire → counter must increment. The observed production state is **impossible under this source with the observed data**.
- **Inference:** the deployed build's quota subsystem (or the production DB contents) differs from origin/main; deployed SHA unverifiable, so the discrepancy cannot be closed from public metadata.
- **Owner-side verification (required):** (1) Render logs — `generation_completed` events carry `quota_used=N`; a logged `0` after accepted runs proves server-side read of 0 (not response shaping), (2) DB rows `usage_periods` / `usage_units` for the test user (email in pilot/production-version.md; user `c11bde4c-…`), (3) confirm deployed commit == `2121a2c`.
- No source changes made this stage (verification-only); no quota data tampered.

## 6) Not tested / partial (production, reported honestly)
- **Bounded rebuild (≤2):** NOT TRIGGERED — all runs `mean_rebuilds=0` → NOT TESTED.
- **Mixed accept+reject in one multi-code run:** NOT EXERCISED (single-code runs only; total-rejection path exercised) → PARTIAL.
- **P1 edge (4 indicators / 2 periods exact):** not exercised in production (covered by local tests) → PARTIAL.
- **WAPEF:** smoke scheme is non-WAPEF → NOT TESTED (no WAPEF fixture uploaded this stage).
- **Browser UI journey:** not executed; frontend serves 200, journey verified at API level → PARTIAL.

## 7) GO/NO-GO
**NO-GO / RED.** The complete AI-OFF upload→export journey works and P4 is demonstrated end-to-end in production (§3, §4) — but quota accounting/enforcement is incorrect (§5), which is a RED criterion by itself: 6 lessons accepted against a monthly limit of 5 with the counter permanently at 0. Remediation is owner-side (deploy/DB verification + quota fix), then re-run this smoke.
