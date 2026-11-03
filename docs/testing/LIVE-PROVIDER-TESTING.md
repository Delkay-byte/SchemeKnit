# Live Provider Testing

Date: 2026-11-03

## 1. Separation

| Marker | Purpose | Where it runs |
|---|---|---|
| (none) | deterministic provider tests with mocked HTTP | normal `backend` CI job |
| `live_provider` | real Gemini/Groq calls | `live-providers` job, `workflow_dispatch` only |

Normal CI runs:

```bash
cd backend
python -m pytest -q -m "not live_provider"
```

Live run:

```bash
cd backend
GEMINI_API_KEY=... GROQ_API_KEY=... \
  python -m pytest -q -m live_provider tests/test_gemini_groq_providers.py
```

The live job reads repository secrets and never prints key values. Missing keys
make the individual test skip; configured-but-rejected credentials now **fail**
rather than skip.

## 2. Investigation of the previous flake

The full 2026-11-02 suite showed two live-provider failures; both passed on
focused rerun. Re-execution during this hardening:

| Run | Result | Duration |
|---|---|---|
| Focused rerun 1 | 1 passed, 1 skipped | 129 s (Gemini 124 s) |
| Focused rerun 2 | 2 passed | 174 s |

Evidence points to external latency/throttling rather than application
regression:

- unit provider tests use mocked HTTP and pass deterministically;
- the live tests call the real provider endpoints;
- Gemini’s `count_tokens`/generation call dominated runtime, consistent with
  free-tier queueing/retry;
- the same test passes with no code change;
- no provider implementation file changed in this branch.

The tests already classify:
- auth/model rejection → fail (credentials must be fixed);
- transient 429/5xx after provider retries → skip with the provider error code;
- empty successful response → fail.

## 3. Retry reporting

The provider client retries bounded transient failures internally. The live
tests expose the terminal `last_error` in the skip/fail message so a reviewer
can distinguish `rate_limit`/`http_5xx` from a bad key or malformed result.
Each live test result reports its wall-clock duration via pytest.

## 4. Security

- Keys come only from environment/secrets.
- No key is printed, asserted or written to logs.
- The existing test already asserts `.env.example` never contains key prefixes.
- Bounded HTTP timeouts remain in the provider implementation.

## 5. Limitations

- The live workflow needs repository secrets configured by the owner.
- Provider free-tier quotas can still make the live job slow (2–3 minutes per
  provider) or skip a transient throttle. That is reported, not hidden.
- A skipped live test is not counted as a passing provider integration.
