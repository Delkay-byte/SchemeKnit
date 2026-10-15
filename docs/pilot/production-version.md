# Production Version Check (Registration Diagnosed + Runtime Verified)

Date: 2026-10-09
Source (HEAD==origin/main): 2121a2c (app code byte-identical to P4 commit ae84f19 — `git diff --stat ae84f19..2121a2c` docs-only)
Intended deployment: ae84f19+ (P4)
Deployed commit: **`3ef1a41a7c8013f1c66ece15ba130495665926e0`** — owner-approved one-time backend deploy `dep-db8aftlg1s2s739kr47g`, live `2026-10-15T10:18:21Z` (pre-deploy PG quota gate 22 passed; deploy record + `git merge-base --is-ancestor 70738f8 3ef1a41` confirm the quota fix is in the deployed tree; `/api/health` 200 liveness-only). Earlier state (historical): live deploy was `50bd887` (2026-10-08, pre-fix). Runtime enforcement check (§12.3) and historical reconciliation (§13e, awaiting owner approval) still outstanding → NO-GO. Detail: docs/QUOTA_ACCOUNTING_INCIDENT.md §13c–§13e.

## Registration 500 diagnosis
- First attempt: `POST /api/auth/register/individual` → 500 `{"error":true,"detail":"Internal server error"}` immediately after a cold start (frontend GET had timed out seconds earlier).
- Payload was valid (matches `IndividualRegisterRequest`{email,password,full_name}; passes validate_email/validate_password).
- Local reproduction (exact production payload, repo test fixtures): **200** (3/3 checks incl. invalid payload → 422 not 500).
- Single bounded production retry after health warm-up: **200 in 5.4s** — dedicated test account created via normal flow (`smoke-eec8aa17@example.com`, synthetic, role teacher, school_id None). Token not recorded.
- Root cause: **transient environment/infrastructure (Render cold-start auth blip)** — same documented precedent (DETERMINISTIC_LESSON_HARDENING_REPORT.md: "one transient 500 on register during a cold start, resolved on retry"). Confidence: high that registration is not defective; medium-high on exact mechanism (Render logs unavailable).
- Classification: environment/configuration (transient). NOT application defect, NOT invalid payload, NOT migration issue.

## Runtime verification (same session, final smoke)
- Full journey PASSED (upload → detection → Autopilot → AI-OFF generate → persist → reload → DOCX/PDF): detail in docs/PRODUCTION_READINESS.md §3. Re-run evidence 2026-10-15: on the deployed `3ef1a41` tree the same journey's remaining gaps are only the §12.3 authorized runtime-enforcement check and §13e historical reconciliation (both owner-gated).
- **P4 execution EVIDENCED**: `quality` metrics on accepted runs; hard-rejection path fired (`generic_objective`, exact gate message, nothing persisted, 0 quota); accept-only persistence; deterministic marker PASS (no stale Discuss objective, no strand-concat topic).
- Marker expectation confirmed at runtime: topic/objective follow the current deterministic P2 form (e.g. objective "Learners can Identify by name binary chemical compounds and discuss their use").
- **Quota DEFECT found**: counter stuck at `used=0/remaining=5` across 6 accepted lessons (limit 5); enforcement never bound. **Root-caused (evidenced):** production stack (PostgreSQL + psycopg3 + SQLAlchemy 2.0.35) reports `rowcount == -1` for `INSERT … ON CONFLICT DO NOTHING`, so `_insert_ignore` misread every insert as already-counted and the guarded increment never ran — reproduced locally (quota suite 9/12 failed on PG pre-fix). Fixed in `70738f8` (RETURNING-based detection + regression suite). **Deployed 2026-10-15:** owner-approved one-time deploy `dep-db8aftlg1s2s739kr47g` = `3ef1a41` (contains the fix; deploy record + ancestor check). Outstanding: authorized §12.3 runtime-enforcement verification and §13e historical reconciliation (owner approval required) → overall stays RED/NO-GO on those two gates.

Conclusion: Registration NOT defective (no code fix). Build-equivalence is behaviourally established for the generation/gate subsystem (P4 markers match ae84f19 exactly). The quota defect is a driver-stack bug in main itself — root-caused, fixed in `70738f8`, and DEPLOYED to production on 2026-10-15 (`3ef1a41`). Overall stays RED/NO-GO until (a) an authorized runtime-enforcement check passes on the deployed build and (b) the §13e historical reconciliation is approved and applied.
