# AI Entitlement Acceptance

Status: **PASS**

## What was verified

The commercial AI entitlement system (`src/entitlements.py:ai_entitlement()`)
correctly gates access to AI providers based on school licensing status.

### Denial conditions (all pass)

| Condition | Expected | Result |
|-----------|----------|--------|
| Suspended license | 403 | PASS |
| Expired license | 403 | PASS |
| No membership at all | 403 | PASS |
| Free-tier school (no AI entitlement) | 403 | PASS |

### Bypass prevention (Ollama)

Installing a local Ollama provider does **not** grant AI access. The
entitlement check runs **before** any provider is constructed, so the
presence of a local Ollama instance is irrelevant — the school must still
hold an active, paid AI license.

### AI OFF mode

When `ai_mode=OFF` is set in the generation config, the entitlement check is
skipped entirely. The backend generates a full deterministic lesson plan
without calling any AI provider. This is the expected commercial behaviour:
AI OFF is free; AI ON requires a paid license.

### Test coverage

27 tests in `tests/test_ai_production.py` cover all entitlement paths,
including:

- Active / suspended / expired license transitions
- Ollama bypass prevention
- AI OFF bypass confirmation
- Code-replay rejection (reusing an already-redeemed activation code)
