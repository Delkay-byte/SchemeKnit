# Generation Credit and Cache Policy

This document is the canonical policy implemented for Zeli whole-lesson
generation after the DeepSeek/Groq hardening. It does not alter historical
transactions.

## Terms

- **Lesson unit**: one accepted, independently teachable indicator-level lesson
  plan. Charged once per `(scheme, indicator code)` in the calendar month.
- **AI request credit**: one successful user-initiated generation request that
  used at least one external AI provider call. Charged once per generation job,
  not once per provider attempt.

## Policy

| Scenario | Lesson units | AI request credits | Persisted lesson |
|---|---:|---:|---:|
| Fresh DeepSeek success | 1 | 1 | Yes |
| DeepSeek fails, Groq succeeds | 1 | 1 | Yes |
| DeepSeek succeeds, content rejected, Groq fallback succeeds | 1 | 1 | Yes |
| Both providers fail | 0 | 0 | No |
| Primary auth/config failure, no fallback | 0 | 0 | No |
| Pure cache replay (no external call) | 0 additional | 0 additional | Existing lesson reused |
| Resume of the same job | 0 additional | 0 additional | Existing/remaining lessons |
| Duplicate new job for the same scheme+indicator | 0 additional lesson unit | 1 (new request) | Yes |

Two provider attempts in one request never charge two AI credits.

## Implementation

- Lesson units are reserved atomically in `usage_quota.reserve_lesson_units` and
  released on failure or for indicators that produced no accepted lesson.
- AI request credits are consumed in `entitlements.consume_ai_generation`,
  idempotent on the job id (`AIUsageEventDB` unique
  `(user_id, request_id)`).
- Zeli cache hits are detected with `provider.last_cache_hit` in
  `zeli_generation.generate_zeli_content`.
- `generation_pipeline` records `_zeli_fresh_calls` (external call count) and
  `_zeli_cache_hits` on the job.
- The generate router charges an AI request credit for Zeli only when at least
  one lesson required an external call:
  `ai_enrichment_succeeded > 0 and _zeli_fresh_calls > 0`.
- A pure replay therefore consumes no AI request credit. A resume with the same
  job id cannot create a second `AIUsageEventDB` row.
- Fallback attempts share the same job id, so two provider attempts in one
  request consume one AI request credit.

## Cache scope and privacy

`zeli_cache_key` includes:

- prompt version,
- generation method (`zeli`),
- actual provider and model,
- every material lesson input: curriculum occurrence, subject/class, strand,
  sub-strand, content standard, indicator, duration, teacher keywords, other
  TLRs, core competencies, references and WAPEF context.

The cache is keyed by content, not by user. A cache row contains no owner or
tenant identity. Ownership is enforced separately when a lesson is persisted and
read: every lesson row is owner-scoped and every API/export read checks the
authenticated owner. A cache hit cannot expose another user's lesson or bypass
entitlement because the caller still reserves/charges through its own ledger and
persists/reads only its own lesson rows.

If cross-tenant cache sharing is ever considered insufficient, add the owner id
to the cache key. That is a deliberate product decision, not done here because
the cache stores provider output for identical curriculum inputs and contains no
personal data.

## Test coverage

- `tests/test_zeli_fallback.py::test_http_fallback_persists_actual_provider_and_charges_once`
- `tests/test_zeli_fallback.py::test_http_both_providers_fail_no_lesson_no_credit`
- `tests/test_zeli_fallback.py::test_http_pure_cache_replay_does_not_charge_ai_credit`
- `tests/test_zeli_generation_method.py::test_resume_does_not_consume_a_second_ai_credit`
- `tests/test_generation_quota_atomicity.py`
- `tests/test_generation_concurrency.py`
- `tests/test_ai_cache_double_submit.py`

## Reconciliation with customer-facing material

`docs/COMMERCIAL_MODEL.md` and `docs/PAYSTACK_SUBSCRIPTIONS.md` define the
catalogue (Free 2 credits/month, Flexible Pack 20, Teacher Monthly 40, Teacher
Term Pass 160). This policy does not change those packages or historical
balances. It clarifies that one request is one AI credit, cache replay is free,
and a provider fallback does not double-charge.
