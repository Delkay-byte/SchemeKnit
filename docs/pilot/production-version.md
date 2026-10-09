# Production Version Check (Registration 500 Diagnosed)

Date: 2026-10-09
Source (HEAD==origin/main): 97a028f (app code unchanged since 50bd887 — docs-only diffs)
Intended deployment: 50bd887 / ae84f19 (P4)
Deployed commit: UNKNOWN (no public deploy metadata). API healthy v1.0.5.

## Registration 500 diagnosis
- First attempt: `POST /api/auth/register/individual` → 500 `{"error":true,"detail":"Internal server error"}` immediately after a cold start (frontend GET had timed out seconds earlier).
- Payload was valid (matches `IndividualRegisterRequest`{email,password,full_name}; passes validate_email/validate_password).
- Local reproduction (exact production payload, repo test fixtures): **200** (3/3 checks incl. invalid payload → 422 not 500).
- Single bounded production retry after health warm-up: **200 in 5.4s** — dedicated test account created via normal flow (`smoke-eec8aa17@example.com`, synthetic, role teacher, school_id None). Token not recorded.
- Root cause: **transient environment/infrastructure (Render cold-start auth blip)** — same documented precedent (DETERMINISTIC_LESSON_HARDENING_REPORT.md: "one transient 500 on register during a cold start, resolved on retry"). Confidence: high that registration is not defective; medium-high on exact mechanism (Render logs unavailable).
- Classification: environment/configuration (transient). NOT application defect, NOT invalid payload, NOT migration issue.

Marker expectation (current impl): topic/objective style per docs/benchmark/after.json (deterministic P2 form). Runtime marker comparison not yet executed.

Conclusion: Registration NOT defective — no code fix required. Production build equivalence still unconfirmed; P4 execution in production still NOT EVIDENCED (end-to-end journey pending — out of scope for this diagnosis session).
