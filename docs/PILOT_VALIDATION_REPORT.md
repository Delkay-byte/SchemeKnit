# PILOT VALIDATION REPORT — Final Production Smoke

**Date:** 2026-10-09  
**Source:** smoke at 2121a2c (app code identical to P4 commit ae84f19); quota incident fix `70738f8` (see §3)  
**Production deployed commit:** UNKNOWN (behaviour markers provenance → ae84f19-era)  
**Account:** dedicated synthetic teacher `smoke-eec8aa17@example.com` (created via normal registration flow, earlier same session; token never recorded)  
**Script/results:** `prod_smoke.py` + `smoke_results.json` (temp, not committed)

## 1) Runtime journey (API-level, AI OFF) — ALL PASSED
health 200 (v1.0.5, 1.24 s) → login 200 → upload 200 (2.29 s; 15 weeks, 20 codes) → detection `single` Science/Basic 9 → weeks 200 → Autopilot `ready` (22 pending, selected 5 quota-capped, 17 quota_skipped, 0 blockers) → generate 200 (3.6 s, job `b8dd26a9-…`, `quality` returned) → persistence (structured lesson) → reload 200 same topic → DOCX 200 valid ZIP 38 729 B (all content checks) → PDF 200 valid 2 pages 5 381 B (all content checks). Frontend 200.

## 2) P4 deterministic quality gate — DEMONSTRATED IN PRODUCTION
- Metrics block on every accepted run (`first_pass_rate`, `teacher_ready_rate`, `mean_score 71.0`, repair/rebuild counters) — keys exist only in ae84f19; score identical to local deterministic run.
- **Hard rejection executed:** `B9.1.1.2.1` → 500 with exact gate text `… Rejections: {'generic_objective': 1}.`; deterministic repeat; **nothing persisted**, **0 quota consumed** (message + lesson list verified).
- Accept-only persistence: 6 accepted lessons stored; rejected indicator absent.
- Marker PASS: current P2 verb-led objective; `has_stale_discuss_objective=false`; `topic_is_strand_concat=false`.

## 3) Quota — FAILED at smoke time (RED criterion); root-caused and fixed in `70738f8` (pending deploy)
`used=0/remaining=5` forever (quota endpoint, Autopilot, generate responses) after **6 accepted distinct lessons against limit 5**; enforcement never bound. **Root cause (evidenced):** on the production stack (PostgreSQL + psycopg3 + SQLAlchemy 2.0.35) `INSERT … ON CONFLICT DO NOTHING` reports `rowcount == -1`, so `_insert_ignore` misread every insert as already-counted, the guarded increment never ran, and the counter/limit guard never engaged — reproduced locally (quota suite 9/12 failed on PG pre-fix; local SQLite green because SQLite's rowcount is truthful). **Fixed** in `70738f8` (RETURNING-based insert detection + regression suite; full suite 2374 passed, PG targeted runs green). Owner-side: deploy `70738f8`, verify via Render logs `generation_completed quota_used=`, `usage_periods`/`usage_units` rows, and the backfill SQL. Detail: docs/QUOTA_ACCOUNTING_INCIDENT.md.

## 4) Registration
Works — dedicated account created via `POST /api/auth/register/individual` (200 on warm retry; the earlier 500 was a transient Render cold-start blip, local repro 200). See docs/pilot/production-version.md.

## 5) Not tested / partial (honest disclosure)
- Rebuild path (≤2): NOT TESTED (never triggered, `mean_rebuilds=0`).
- Mixed accept+reject single run: PARTIAL (single-code runs; total-rejection exercised twice).
- P1 4-indicators/2-periods edge: PARTIAL (not exercised in production; local coverage only).
- WAPEF scheme flow: NOT TESTED (smoke scheme non-WAPEF; reason: no WAPEF fixture uploaded this stage).
- Browser UI interaction: PARTIAL (frontend 200; journey verified via API only).
- Deployed commit: UNKNOWN — provenance only behavioural (P4 gate strings/fields).

## 6) Answers to final questions
1. upload→downloadable minimal intervention: **GREEN** (DOCX+PDF valid with content in production).
2. deterministic lessons usable without Zeli: **GREEN** (production lessons structured, marker PASS, gate enforced).
3. production behaves like current main: **AMBER → GREEN-pending-deploy** (generation/gate behaviour matches ae84f19 exactly; quota defect root-caused as a driver-stack bug present in main itself — fixed in `70738f8`, not yet deployed; deployed SHA still unverifiable).
4. ready for broader teacher pilot: **NO-GO** (quota cap unenforceable = RED; deploy `70738f8`, verify counter, then re-run quota smoke first).

**"Has P4's deterministic quality gate been demonstrated in the actual production application, and does the complete AI-OFF upload-to-export journey work?"**  
**YES and YES** — the gate's metrics, hard-rejection path (with `generic_objective`), accept-only persistence and deterministic marker were all observed in production, and upload→generate→persist→reload→DOCX/PDF completed end-to-end. Caveat: at smoke time the Free Tier quota accounting was broken in production (6 accepted on a 5/month limit); root cause found and fixed in `70738f8`, pending deploy.

**Overall decision: RED / NO-GO** — GREEN for journey + P4; RED on quota accounting until `70738f8` is deployed and verified (fix committed this stage; smoke stage itself made no code changes).
