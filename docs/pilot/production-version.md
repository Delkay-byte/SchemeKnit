# Production Version Check (Registration Diagnosed + Runtime Verified)

Date: 2026-10-09
Source (HEAD==origin/main): 2121a2c (app code byte-identical to P4 commit ae84f19 — `git diff --stat ae84f19..2121a2c` docs-only)
Intended deployment: ae84f19+ (P4)
Deployed commit: UNKNOWN (no public deploy metadata). API healthy v1.0.5; frontend 200.

## Registration 500 diagnosis
- First attempt: `POST /api/auth/register/individual` → 500 `{"error":true,"detail":"Internal server error"}` immediately after a cold start (frontend GET had timed out seconds earlier).
- Payload was valid (matches `IndividualRegisterRequest`{email,password,full_name}; passes validate_email/validate_password).
- Local reproduction (exact production payload, repo test fixtures): **200** (3/3 checks incl. invalid payload → 422 not 500).
- Single bounded production retry after health warm-up: **200 in 5.4s** — dedicated test account created via normal flow (`smoke-eec8aa17@example.com`, synthetic, role teacher, school_id None). Token not recorded.
- Root cause: **transient environment/infrastructure (Render cold-start auth blip)** — same documented precedent (DETERMINISTIC_LESSON_HARDENING_REPORT.md: "one transient 500 on register during a cold start, resolved on retry"). Confidence: high that registration is not defective; medium-high on exact mechanism (Render logs unavailable).
- Classification: environment/configuration (transient). NOT application defect, NOT invalid payload, NOT migration issue.

## Runtime verification (same session, final smoke)
- Full journey PASSED (upload → detection → Autopilot → AI-OFF generate → persist → reload → DOCX/PDF): detail in docs/PRODUCTION_READINESS.md §3.
- **P4 execution EVIDENCED**: `quality` metrics on accepted runs; hard-rejection path fired (`generic_objective`, exact gate message, nothing persisted, 0 quota); accept-only persistence; deterministic marker PASS (no stale Discuss objective, no strand-concat topic).
- Marker expectation confirmed at runtime: topic/objective follow the current deterministic P2 form (e.g. objective "Learners can Identify by name binary chemical compounds and discuss their use").
- **Quota DEFECT found**: counter stuck at `used=0/remaining=5` across 6 accepted lessons (limit 5); enforcement never bound. **Root-caused (evidenced):** production stack (PostgreSQL + psycopg3 + SQLAlchemy 2.0.35) reports `rowcount == -1` for `INSERT … ON CONFLICT DO NOTHING`, so `_insert_ignore` misread every insert as already-counted and the guarded increment never ran — reproduced locally (quota suite 9/12 failed on PG pre-fix). Fixed in `70738f8` (RETURNING-based detection + regression suite). Owner-side: deploy `70738f8`, Render logs `generation_completed quota_used=`, usage tables, backfill SQL. Detail: docs/QUOTA_ACCOUNTING_INCIDENT.md.

Conclusion: Registration NOT defective (no code fix). Build-equivalence is behaviourally established for the generation/gate subsystem (P4 markers match ae84f19 exactly); deployed SHA still unexposed. P4 IS evidenced in production. The quota defect is a driver-stack bug present in main itself — root-caused and fixed in `70738f8` (pending deploy + verification) → overall stays RED/NO-GO until the fixed build is deployed and the counter is observed correct.
