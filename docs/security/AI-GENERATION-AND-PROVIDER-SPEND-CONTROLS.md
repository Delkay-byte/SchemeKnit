# AI Generation and Provider Spend Controls

Status: **IMPLEMENTED AND LOCALLY VERIFIED** (production activation uses the
owner's existing Render environment values; no live provider call was made from
this workstation).

## 1. Generation entry-point inventory

Every server path that can reach a real AI provider is listed here. The
authenticated owner is always derived from the access token, never from the
request body.

| Entry point | Route | Provider call | Ownership / entitlement gate | Credit / spend gate |
|---|---|---|---|---|
| Fresh generation (Standard / Zeli) | `POST /api/generation/{scheme_id}/generate` | Zeli (DeepSeek + bounded Groq fallback) or the configured V2 provider | `require_teacher_workflow`, scheme ownership, `require_ai_entitlement` before any provider | Lesson-plan credit reservation, AI generation credit on success, per-account generation budget, provider spend reservation |
| Job resume | `POST /api/generation/{scheme_id}/generate/resume` | Same as fresh generation, only for planned-but-unproduced occurrences | Job and scheme ownership; job snapshot | Reuses the original job's credit identity; provider spend is accounted per actual attempt |
| Quality-gate fallback | inside fresh generation | Groq (one bounded call) | Same request | Same provider spend reservation; no second teacher credit |
| Optional V2 enrichment | `GenerationPipeline._enrich_with_ai` | Configured provider | Same generation request | Provider spend reservation per lesson; deterministic content remains on a block |
| Section regeneration | `POST /api/ai-regeneration/regenerate-section` | Configured named provider | Lesson ownership + `require_ai_entitlement` | AI generation credit only on success; provider spend per attempt |
| Lesson enrichment | `POST /api/ai-regeneration/enrich-lesson` | Configured named provider | Lesson ownership + `require_ai_entitlement` | AI generation credit only on success; provider spend per attempt |
| Ollama empty-output retry | inside section regeneration | Ollama (one bounded retry) | Same request | A separate provider attempt is recorded |
| Enrichment validation retry | inside lesson enrichment | Configured provider (one bounded retry) | Same request | A separate provider attempt is recorded |

No administrative endpoint invokes a provider directly. The old free/local
Ollama route still passes the same commercial entitlement gate; a local model is
never a bypass.

Cache-first behaviour is unchanged: a Zeli cache hit makes no provider call and
consumes no teacher credit or provider spend.

## 2. Three separate layers

**Layer A — request abuse.** `security.AUTHENTICATED_BUDGETS` limits requests per
authenticated account (Part 1). These are not spending limits.

**Layer B — teacher entitlement.** `require_ai_entitlement` runs before any
provider is constructed. Lesson-plan credits are reserved atomically before
generation and committed only for accepted lessons (`credits.py`). One
successful request consumes one AI generation (`entitlements.consume_ai_generation`,
idempotent on the job/request id). Failures, cache hits and deterministic
fallbacks consume none. A DeepSeek failure followed by a successful Groq
fallback charges the teacher once.

**Layer C — provider cost.** `src/ai_spend.py` reserves a conservative estimate
in a shared database counter before each real provider attempt, then settles the
actual reported usage. A hard cap stops new billable attempts.

## 3. Provider usage accounting

Each attempt writes one `ai_provider_usage` row with:

- provider, model, SchemeKnit request/job id, unique attempt id;
- input, cached-input and output tokens (actual, or conservatively estimated);
- `usage_source` (`actual`, `estimated`, `none`) and pricing schedule version;
- cost in micro-USD plus a rendered USD value;
- outcome (`success`, `failure`, `schema_invalid`);
- timestamp and optional teacher id.

`attempt_id` is unique. Replaying the same settlement cannot double-count an
attempt. DeepSeek and Groq are recorded separately, so a failed primary call and
a successful fallback both appear in the cost ledger while the teacher is
charged once.

DeepSeek records the API's `prompt_tokens`, `completion_tokens` and
`prompt_cache_hit_tokens`/`prompt_cache_miss_tokens`. Groq records
`prompt_tokens`, `completion_tokens` and cached prompt tokens. Providers without
a usage payload are accounted from the configured maximum request size.

### Pricing source and date

Pricing schedule `2026-10-31`, USD per 1,000,000 tokens:

| Provider | Input (cache miss) | Cached input | Output |
|---|---:|---:|---:|
| DeepSeek `deepseek-flash` | 0.30 | 0.006 | 1.20 |
| Groq `openai/gpt-oss-120b` | 0.15 | 0.075 | 0.60 |
| Unknown provider (conservative) | 1.00 | 0.50 | 3.00 |

DeepSeek figures are the PEAK rate from
<https://api-docs.deepseek.com/quick_start/pricing>; off-peak is half, so peak is
the conservative choice. Groq figures are from
<https://console.groq.com/docs/model/openai/gpt-oss-120b>.

## 4. Budgets and hard stop

Defaults (all configurable in Render; no redeploy-time secret):

| Setting | Default | Meaning |
|---|---:|---|
| `AI_SPEND_CONTROL_ENABLED` | `true` | Master switch for provider spend controls |
| `AI_MONTHLY_BUDGET_USD` | `10.00` | Hard monthly provider ceiling |
| `AI_DAILY_BUDGET_USD` | `2.00` | Optional daily guard; `0` disables |
| `AI_DEEPSEEK_MONTHLY_BUDGET_USD` | `8.00` | Per-provider monthly cap; `0` disables |
| `AI_GROQ_MONTHLY_BUDGET_USD` | `2.00` | Per-provider monthly cap; `0` disables |
| `AI_BUDGET_WARNING_THRESHOLD` | `0.80` | One owner warning at 80 % of the monthly cap |
| `AI_MAX_INPUT_CHARS` | `60000` | Oversized prompts are rejected before provider invocation |
| `AI_MAX_OUTPUT_TOKENS` | `2000` | Clamps every provider completion budget |
| `AI_MAX_CONCURRENT_PER_TEACHER` | `2` | Per-account in-flight provider calls |
| `AI_GLOBAL_MAX_CONCURRENT` | `8` | Global in-flight provider calls |

The counters live in `ai_spend_counters` (integer micro-USD) and are updated
with guarded SQL, so two workers cannot both spend the remaining budget. The
owner lowers or raises a budget by changing the environment value; an existing
configured limit is never silently raised by code.

Hard-stop behaviour:

1. A new attempt reserves estimate; if the estimate does not fit, it is denied
   before the provider is constructed or called.
2. Already-started work is allowed to finish and settle.
3. Teachers receive: "AI generation is temporarily paused. No lesson plans were
   saved and no lesson-plan quota was used..." — no provider or credential
   detail.
4. `ai_budget_stop` is logged; the warning threshold emits `ai_budget_warning`.
5. Generation resumes automatically when the day/month period rolls over or the
   owner changes the budget.
6. No fallback is attempted after a budget block, because the second provider
   would also be blocked.

## 5. Resource-consumption limits

- Prompt text is bounded by `AI_MAX_INPUT_CHARS` (HTTP 413 before any call).
- Completion tokens are bounded by `AI_MAX_OUTPUT_TOKENS`, including the
  previously hard-coded Groq/Gemini/OpenAI/OpenCode budgets.
- DeepSeek/Groq transport timeouts and bounded retries remain in force.
- Per-teacher and global concurrent provider calls are guarded by shared
  database counters with expiry-based recovery after a crash.
- Upload body/file limits remain in `MAX_UPLOAD_SIZE_MB` and the existing
  DOCX/PDF validation (completed further in the storage workstream).
- Job deduplication and stale-job reconciliation are unchanged.

## 6. Owner visibility

`GET /api/platform-admin/ai-spend` (platform admin only) returns the current
budget status and provider usage totals for the month. It contains no prompt,
response, credential, teacher identity or raw provider diagnostic.

## 7. Tests

`backend/tests/test_ai_spend_controls.py` proves:

- peak-price cost calculation for DeepSeek/Groq and cached input;
- actual usage recorded and settled;
- duplicate settlement is idempotent;
- DeepSeek failure + Groq success are recorded separately with no duplicate
  teacher-credit event;
- cache hit creates no spend row;
- an auth failure that makes no HTTP call costs nothing;
- an exhausted budget blocks before the provider and before the fallback;
- per-teacher concurrency is bounded and independent per account;
- oversized input is rejected before provider invocation;
- the owner summary is secret-free.

Existing suites cover credit reservation, failure refunds, cache replay,
fallback single-charge, resume and generation concurrency. Targeted run:
`290 passed, 2 skipped` across the AI/generation/credit suites.

## 8. Residual limitations

- The default budgets are a conservative starting point, not the owner's actual
  purchased DeepSeek balance. The owner may adjust the environment values.
- Provider-reported usage is used when present. A failure with no usage payload
  is accounted at the maximum configured request size (deliberately
  conservative, never free).
- Retries inside the provider HTTP client are one provider attempt record; if
  the provider bills a failed retry, the conservative estimate covers it.
- No live provider request was made during this local verification.
