# AI Provider Configuration

This is the canonical provider configuration for SchemeKnit/TeachFlow after the
DeepSeek/Groq hardening. It does not change production credentials.

## Selection model

| Purpose | Provider | Configuration |
|---|---|---|
| Generate with Zeli (primary) | `deepseek` | `ZELI_PROVIDER=deepseek`; `ZELI_MODEL=deepseek-flash`; `DEEPSEEK_API_KEY` (or `ZELI_API_KEY`) |
| Generate with Zeli (fallback) | `groq` | `ZELI_FALLBACK_PROVIDER=groq`; `GROQ_MODEL=openai/gpt-oss-120b`; `GROQ_API_KEY` |
| Standard AI enrichment | `groq` | `AI_MODE=groq`; uses the standard `GROQ_*` configuration |

The two paths are independent:

- `AI_MODE` controls only the optional enrichment layer in Standard generation.
- `ZELI_PROVIDER` / `ZELI_FALLBACK_PROVIDER` control whole-lesson Zeli
  generation.
- A missing DeepSeek key does **not** cause a silent switch to Groq. Zeli
  reports `MISSING_KEY` / `unavailable` and returns a teacher-safe `503` before
  creating a job or charging quota.
- A runtime DeepSeek failure that is eligible for fallback may use Groq once.
  The lesson then records `ai_provider=groq` and the actual Groq model.

## Required variable names

| Variable | Required | Notes |
|---|---|---|
| `DEEPSEEK_API_KEY` | Yes for primary | Server-only secret. Never expose to the browser. |
| `ZELI_PROVIDER` | Yes | Defaults to `deepseek`. Must be a named provider. |
| `ZELI_FALLBACK_PROVIDER` | Optional | Defaults to `groq`; empty disables fallback. Must differ from the primary. |
| `ZELI_MODEL` | Optional | Defaults to `deepseek-flash`. |
| `ZELI_BASE_URL` | Optional | Defaults to `https://api.deepseek.com`. |
| `GROQ_API_KEY` | Yes for fallback / enrichment | Server-only secret. |
| `GROQ_MODEL` | Yes for fallback / enrichment | Currently `openai/gpt-oss-120b`, validated against Groq. |
| `GROQ_BASE_URL` | Optional | Defaults to `https://api.groq.com/openai/v1`. |
| `AI_MODE` | Yes for Standard enrichment | Intended value `groq`. |
| `ZELI_ENABLED` | Optional | `false` hides Zeli without affecting Standard generation. |

Do not put real values in `.env.example`, source files, tests, browser code or
logs. The repository's `.env.example` contains placeholders only.

## Fallback policy

One bounded fallback attempt is allowed for:

- network/connection failures,
- provider timeouts and HTTP 408,
- HTTP 429,
- HTTP 5xx,
- malformed JSON, schema-invalid output, empty output,
- a quality-gate rejection of provider-generated content.

Fallback is **not** allowed for:

- missing or invalid provider credentials,
- HTTP 401/403 provider authentication failures,
- an unknown/invalid model,
- invalid user input, missing curriculum, parser errors, database errors,
  export errors, or unrelated application errors.

A fallback attempt uses the same strict lesson validator, schema checks,
curriculum mapping and quality gate as the primary. A fallback HTTP 200 alone is
not success. Both providers failing produces a teacher-safe error with no
lesson, no lesson unit and no AI request credit.

## Local configuration cleanup

The local `backend/.env` had duplicate `AI_MODE` entries (`OFF`, then `groq`).
It now contains exactly one `AI_MODE=groq`, one
`ZELI_FALLBACK_PROVIDER=groq`, `PAYSTACK_ENABLED=false` and
`PAYSTACK_MODE=test`. The `.env` file remains untracked and is not printed in
reports.

## Related documents

- `docs/ZELI_ENVIRONMENT.md` — detailed Zeli variables and transport semantics.
- `docs/ai/GENERATION-CREDIT-AND-CACHE-POLICY.md` — charging behaviour.
- `docs/ai/DEEPSEEK-GROQ-CURRICULUM-MATRIX.md` — live provider evidence.
