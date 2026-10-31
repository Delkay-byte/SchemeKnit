# Zeli environment configuration

Zeli is SchemeKnit's teacher-facing whole-lesson generation method. Its engine
is **DeepSeek** (OpenAI-compatible chat completions). Every value below is read
**server-side only** from the backend process environment; none may be exposed
through `NEXT_PUBLIC_*`, browser responses, logs or error messages.

Source of truth: `backend/src/config.py` (`Settings`), consumed by
`backend/src/engines/zeli_generation.py` and
`backend/src/engines/ai_provider.py` (`DeepSeekProvider`).

## Variables

| Variable | Default | Validation | Consumed by / effect |
|---|---|---|---|
| `ZELI_ENABLED` | `true` | Boolean | `zeli_generation.zeli_availability()` / `get_zeli_provider()`. `false` hides the method and rejects generation with 503 before any quota. Standard generation is unaffected. |
| `ZELI_PROVIDER` | `deepseek` | Must be a member of `NAMED_PROVIDERS` (`gemini`, `groq`, `deepseek`, `openai`, `minimax`, `ollama`, `opencode-zen`); lowercased/trimmed | Selects the primary provider class. `groq` keeps the previous integration and uses `GROQ_*`; any mismatch is `INVALID_CONFIG`. |
| `ZELI_FALLBACK_PROVIDER` | `groq` | Empty, or a member of `NAMED_PROVIDERS`; must differ from `ZELI_PROVIDER` | Secondary provider for ONE bounded attempt after an eligible primary failure (network, timeout, 429/5xx, malformed/schema-invalid output, or quality-gate rejection). Empty disables fallback. It always uses its own provider configuration (`GROQ_*` for Groq) and never receives the primary key. Missing/invalid primary credentials do NOT trigger fallback. |
| `ZELI_MODEL` | `deepseek-flash` when provider is `deepseek` (blank falls back) | Trimmed string | Model id in every request body and in the cache key. |
| `ZELI_BASE_URL` | `https://api.deepseek.com` (blank falls back) | Trimmed string | Base for `POST {base}/chat/completions`. |
| `ZELI_API_KEY` | empty | Trimmed string; never logged | Highest-precedence credential. Falls back to `DEEPSEEK_API_KEY` (provider `deepseek`) or `GROQ_API_KEY` (provider `groq`). |
| `DEEPSEEK_API_KEY` | empty | Trimmed string; never logged | DeepSeek credential when `ZELI_API_KEY` is blank. A Groq key is never used for DeepSeek and vice versa. |
| `ZELI_TEMPERATURE` | `0.3` | Float, `0.0`–`2.0` | Sent as `temperature` **only** when supported. Omitted when `ZELI_THINKING_MODE=enabled` or the model id names a reasoner (`*-reasoner`, `*-r1`). |
| `ZELI_MAX_TOKENS` | `2000` | Integer, `1`–`8192` | Sent as the API's `max_tokens` (completion budget). `max_completion_tokens` is never sent. |
| `ZELI_THINKING_MODE` | `disabled` | `enabled` \| `disabled` \| `auto` (case-insensitive; empty = `auto`) | `enabled`/`disabled` send `thinking: {"type": ...}`. `auto` omits the parameter. `enabled` also suppresses `temperature`. |
| `ZELI_CONNECT_TIMEOUT_SECONDS` | `10` | Float, `1`–`60` | First element of the `(connect, read)` timeout tuple passed to `requests.post`. |
| `ZELI_READ_TIMEOUT_SECONDS` | `90` | Float, `1`–`600` | Second element of the timeout tuple. |
| `ZELI_MAX_RETRIES` | `2` | Integer, `0`–`5` | Bounded retries for **transient** failures only (429, 500/502/503/504, timeouts/connection errors). Exponential back-off with jitter, capped at 8 s. Auth (401/403), invalid request (400/422), unknown model (404) and insufficient balance (402) are never retried. |

`ZELI_ENABLED`, `ZELI_PROVIDER` and the tuning values are validated by pydantic
at process start. An invalid value stops the backend from booting rather than
starting in an ambiguous state. A **missing key** does not stop the backend:
`zeli_availability()` reports `available: false` / `MISSING_KEY`, and the
generate route returns **503 before** creating a job, consuming lesson quota or
consuming an AI credit.

## Precedence summary

1. `ZELI_API_KEY` (if non-empty) wins for the primary provider.
2. Primary provider `deepseek`: `DEEPSEEK_API_KEY`.
3. Primary provider `groq`: `GROQ_API_KEY`.
4. Blank `ZELI_MODEL` / `ZELI_BASE_URL` resolve to the provider defaults.
5. The fallback is resolved independently from `ZELI_FALLBACK_PROVIDER`
   (default `groq`) and always uses that provider's own `GROQ_MODEL` /
   `GROQ_BASE_URL` / `GROQ_API_KEY`. It never inherits the primary key.

## Example (placeholders only)

```dotenv
ZELI_ENABLED=true
ZELI_PROVIDER=deepseek
ZELI_FALLBACK_PROVIDER=groq
ZELI_MODEL=deepseek-flash
ZELI_BASE_URL=https://api.deepseek.com
ZELI_API_KEY=
DEEPSEEK_API_KEY=
ZELI_TEMPERATURE=0.3
ZELI_MAX_TOKENS=2000
ZELI_THINKING_MODE=disabled
ZELI_CONNECT_TIMEOUT_SECONDS=10
ZELI_READ_TIMEOUT_SECONDS=90
ZELI_MAX_RETRIES=2
```

Never commit a real key. Local `.env` values are not inherited by Render; set
`DEEPSEEK_API_KEY` in the Render backend service's environment (not the
frontend), then redeploy only when deployment is authorized.

## Observability

`DeepSeekProvider.last_usage` records, after a successful call:

- `provider`, `model`
- `input_tokens`, `output_tokens`, `total_tokens`
- `cached_input_tokens` (`prompt_cache_hit_tokens`)
- `uncached_input_tokens` (`prompt_cache_miss_tokens`)
- `duration_seconds`

When the provider omits `usage`, `last_usage` stays `None` and generation is
unaffected. No API key, header, prompt body or response body is stored there.
