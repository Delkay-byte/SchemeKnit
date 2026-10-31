# Staging Readiness Report

Date: 2026-10-31
Branch: `hardening/deepseek-groq-staging-20261030`
Status: **READY FOR STAGING REVIEW**

No staging or production deployment was performed.

## Code readiness

| Item | Result |
|---|---|
| Reconciliation | `0f054de` merges `origin/main` (`0b3c292`) with preserved DeepSeek work |
| Local preservation commit | `0cb4d8e` |
| Full backend suite | **2,876 passed, 21 skipped, 0 failed, 0 errors** |
| Frontend type check | `npx tsc --noEmit` passed |
| Frontend production build | `npm run build` passed |
| Backend compile | `python -m compileall -q src tests` passed |
| `git diff --check` | passed |
| Backend lint | not configured; `next lint` prompts for setup, so no lint claim is made |

### Production code changes

| File | Reason |
|---|---|
| `backend/src/config.py` | `ZELI_FALLBACK_PROVIDER` validation |
| `backend/src/engines/zeli_generation.py` | DeepSeek primary + one bounded Groq fallback, cache-hit flag, sanitized attempts, prompt v5 |
| `backend/src/engines/generation_pipeline.py` | Fallback metadata, quality-gate fallback, provider class assignments/assessment items, resource/provenance mapping |
| `backend/src/curriculum/generation_prompt.py` | Scientific-category rule; class assignment and assessment-item schema |
| `backend/src/parsers/docx_parser.py` | Multi-code/range/duplicate-code parser fixes |
| `backend/src/auth.py` | Missing credentials return 401 + challenge |
| `backend/src/ai_resource_text.py` | Comma-preserving resource/indicator normalizers |
| `backend/src/service.py` | Resource normalization at edit boundary |
| `backend/src/routers/generation.py` | Actual provider/fallback reporting; cache-aware AI credit; quality fallback hook |
| `backend/.env.example` | Placeholder-only fallback configuration |

Test-only changes: `backend/tests/conftest.py`, `test_final_web_ux.py`,
`test_zeli_deepseek_config.py`, `test_zeli_generation_method.py`, and new
`test_zeli_fallback.py`, `test_resource_formatting.py`,
`test_zeli_class_assignment.py`.

## Configuration readiness

| Purpose | Value |
|---|---|
| Zeli primary | `ZELI_PROVIDER=deepseek`, `ZELI_MODEL=deepseek-flash` |
| Zeli fallback | `ZELI_FALLBACK_PROVIDER=groq`, `GROQ_MODEL=openai/gpt-oss-120b` |
| Standard enrichment | `AI_MODE=groq` |
| Secrets (names only) | `DEEPSEEK_API_KEY`, `GROQ_API_KEY` |
| Local safety flags | `PAYSTACK_ENABLED=false`, `PAYSTACK_MODE=test` |

Missing primary credentials produce a visible `MISSING_KEY` / 503 before any
job or quota. They do not silently switch to Groq. Missing Groq credentials
simply make fallback unavailable; the primary error is preserved.

## Database readiness

- No new migration is introduced by this hardening.
- Existing migrations through `v043_webhook_recovery.py` are unchanged.
- New provider/fallback metadata is stored inside the existing
  `generation_jobs.config_snapshot` JSON; no schema change.
- Existing lessons remain readable; new class-assignment/assessment-item fields
  are optional and older rows keep their existing values.
- Backup before any later deployment: database snapshot plus the branch commit.
- Rollback: redeploy the previous commit; no down-migration is required.

## Staging smoke-test checklist

1. Deploy branch to staging after owner authorization.
2. Confirm health endpoint returns 200.
3. Generate one lesson with Zeli; confirm `ai_provider=deepseek`,
   `ai_model=deepseek-flash`, `fallback_used=false`.
4. Force a controlled DeepSeek timeout at the provider boundary; confirm Groq
   success, `ai_provider=groq`, actual Groq model, `fallback_used=true`.
5. Confirm a failed generation consumes zero lesson units and zero AI credits.
6. Confirm successful fallback consumes exactly one lesson unit and one AI
   request credit.
7. Replay the same inputs from cache; confirm zero additional AI credits and
   zero additional lesson units.
8. Confirm lesson reload returns the actual provider and model.
9. Edit a lesson; confirm the edit survives reload.
10. Export DOCX and PDF; confirm 200 and real file signatures.
11. Confirm login/logout and revoked-session access return 401.
12. Confirm payment routes remain disabled/test-only and no live transaction is
    possible.
13. Confirm `PAYSTACK_ENABLED=false` and `PAYSTACK_MODE=test` in staging.

## Approval criteria

Approve production only after:

- owner review of the branch diff,
- staging smoke checks above pass,
- one staging DeepSeek generation and one controlled fallback are verified,
- no new failures in the staging run,
- rollback commit is recorded.

## Rollback

Redeploy the prior production commit and keep the database unchanged. This work
adds no migration and no destructive data change. Provider configuration can be
reverted by restoring the previous environment values; do not restore any real
secret into source control.
