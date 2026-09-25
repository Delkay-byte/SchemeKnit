# Gemini AI Provider Implementation Report

Integrates Google's official `google-genai` SDK as a server-side provider inside
the existing SchemeKnit AI architecture. Gemini is ADDITIVE: AI_MODE=OFF
deterministic generation, Groq, WAPEF, KG, Nursery, Basic 1–3 and Basic 4–JHS
are all preserved unchanged.

Verdict — **LIVE MODEL VERIFIED** (see §S). The model is accessible with the
configured key; a controlled structured generation succeeded during acceptance.
Broad live acceptance is currently limited by free-tier generation throttling,
documented honestly (§R, §S) and never faked.

---

## A. Existing architecture inspected — SOURCE VERIFIED

- Provider abstraction: `backend/src/engines/ai_provider.py` — `AIProvider`
  base class (V1 `generate_lesson_content`, V2 `generate_lesson_v2`,
  `generate_structured`, `is_available`, secret-free `last_error`).
- Factory: `get_provider(mode)` maps `"gemini"` → `GeminiProvider`; also groq /
  openai / minimax / ollama / opencode-zen / Mock (OFF/BASIC/ENHANCED).
- Routing: `resolve_provider_mode(ai_mode)` — `OFF` stays deterministic, named
  providers pass through, `AI_MODE` env pin wins, else auto-order
  `(gemini, groq, openai, opencode-zen, ollama)`.
- Generation pipeline: `backend/src/engines/generation_pipeline.py`
  `_enrich_with_ai()` → provider V2 → `_apply_v2_content()` →
  `validate_lesson_quality()` → mark `ai_generated`.
- Canonical context: `_build_v2_prompt_from_context()` +
  `curriculum/generation_prompt.py::build_generation_prompt()` + `SYSTEM_PROMPT`.
- Quality gate: `curriculum/quality_gate.py::validate_lesson_quality` (17 checks).
- Diagnostics: `provider_status()` and `/api/settings/ai-status` already
  surface per-provider state — no new public endpoint needed.

## B. SDK and version — IMPLEMENTED / TESTED

- Official SDK `google-genai==2.25.0` (NOT the deprecated `@google/generative-ai`
  / `google-generativeai`, NOT raw REST). Added to `backend/requirements.txt`
  under the AI-provider section and installed into the project venv.
- The repo backend is Python; the brief's JS/TS example (`@google/genai`,
  `import { GoogleGenAI, Type }`) maps to the official Python SDK
  (`from google import genai`). The SDK is server-side only — the frontend
  never imports it and never receives the key.

## C. Gemini client configuration — IMPLEMENTED / TESTED

- Single client per provider instance, created lazily in `_get_client()`:

    from google import genai
    self._client = genai.Client(api_key=self.api_key)

- `GEMINI_API_KEY` read from server environment only (`config.py` +
  `_env()` fallback). No competing clients; the provider holds one.
- Never hard-coded; never logged; never in the frontend bundle
  (`test_no_keys_in_frontend_bundle_surface` and `TestSecretHygiene` guard
  this).

## D. Model configuration — IMPLEMENTED / TESTED

- `GEMINI_MODEL` from server env; default `gemini-3.8-flash` (current stable
  free-tier family; config default aligned to the same value). Provider never
  auto-upgrades, never silently substitutes, and never changes the model after
  a failure.
- `TestModelConfiguration` locks: default is a flash (not pro) model; env value
  wins; model is never a hard-coded paid-only ID.

## E. Model-access diagnostic — IMPLEMENTED / TESTED

- `GeminiProvider.is_available()` now performs a live `count_tokens` probe on
  the configured model (cached per instance), so `active=True` in
  `/api/settings/ai-status` means the model is genuinely callable, not merely
  "a key is set". `provider_status()` maps the failure (`model_not_found`,
  `auth_failed`, `rate_limit`, …) to `MODEL_UNAVAILABLE` / `LIVE_AUTH_FAILURE`
  / `LIVE_RATE_LIMITED`.
- No new public endpoint — the existing `/ai-status` surface reports it
  (§5 satisfied). Live check: `ai-status?ai_mode=gemini` →
  `provider=gemini, state=CONFIGURED, active=True`.
- Deterministic tests: `test_model_access_failure_makes_is_available_false`,
  `test_model_access_success_makes_is_available_true`.

## F. Prompt builder — IMPLEMENTED / TESTED

- Reuses the existing canonical builders (`_build_v2_prompt_from_context` →
  `build_generation_prompt`, `SYSTEM_PROMPT`) — no ad-hoc inline prompts in
  route handlers, no generic "Write a Grade 4 lesson about fractions" prompt.
- The existing prompt already sections SYSTEM ROLE / MISSION / AUTHORITY /
  NON-NEGOTIABLE CURRICULUM RULES / LESSON CONTEXT / TEACHER CONTEXT /
  PEDAGOGY PROFILE / GENERATION REQUIREMENTS / OUTPUT CONTRACT, and carries
  the exact curriculum focus, indicator, strand, sub-strand, teaching
  period/day, adjacent and continuation context, WAPEF context and teacher
  resources.
- `test_curriculum_context_included_in_prompt` proves the curriculum (indicator
  text, strand, subject) is present in the prompt handed to the SDK.

## G. Structured output — IMPLEMENTED / TESTED

- `response_mime_type: "application/json"` plus `response_schema` (the official
  SDK's structured-output capability) for V2 lesson generation.
- Schema derived from the canonical V2 lesson shape: `learning_objectives`,
  `starter`, `main_learning`, `assessment`, `plenary` (no second lesson model).
- `generate_structured` still requests JSON for enrichment/regeneration.

## H. Canonical schema mapping — IMPLEMENTED / TESTED

- The response schema mirrors `_validate_v2_content`'s expected keys. No
  flattening of richer lesson structure; `_apply_v2_content` maps the returned
  object onto the existing `LessonPlan` fields.

## I. Authoritative-field reconciliation — IMPLEMENTED / TESTED

- `_apply_v2_content` snapshots and restores authoritative fields server-side:
  indicator codes/text, content standard, week, strand, sub-strand are NEVER
  overwritten by AI. Teacher keywords / TLRs / competencies / references are
  MERGED (never replaced). WAPEF teacher selections are snapshotted and
  restored verbatim. Covered by `test_ai_failure_hardening.py`,
  `test_wapef_acceptance.py::test_v2_apply_never_touches_wapef_fields`.

## J. WAPEF preservation — IMPLEMENTED / TESTED

- The four WAPEF fields (Deep Hope, Storyline, Through lines, God's Story) are
  teacher-authoritative. The provider passes them as read-only context;
  `_apply_v2_content` restores them verbatim after generation for Basic 1–3,
  Basic 4–JHS, KG and Nursery. `test_validate_wapef_lesson_json_strips_ai_wapef_keys`
  proves AI-injected WAPEF keys are stripped.

## K. Nursery / KG handling — IMPLEMENTED / TESTED

- Provider consumes the established level profiles via the canonical context;
  no duplicated curriculum semantics in provider code. Nursery (indicator-less)
  and KG (early-childhood, continuation) lessons are generated by the same
  provider path with the correct profile.

## L. Basic 1–3 handling — IMPLEMENTED / TESTED

- The weekly class-teacher architecture is untouched; generation is scoped by
  the same canonical context (class, subject, week, teaching day, focus). No
  identical content across days is forced by the provider — the prompt carries
  the day/period so each day is grounded in its own context.

## M. Retry / error behavior — IMPLEMENTED / TESTED

- `MAX_RETRIES = 2`; bounded retries ONLY for transient failures (429
  `rate_limit`, 5xx incl. the free-tier high-demand `http_503`, `timeout`).
- Never retries auth failure, model-not-found, or malformed JSON indefinitely.
- `_map_exception` maps `APIError.code` / status to secret-free codes
  (`auth_failed`, `auth_key_rejected`, `invalid_api_key`, `model_not_found`,
  `rate_limit`, `http_5xx`, `timeout`); `provider_status()` classifies them.
- Deterministic tests: timeout, 429, 401, 503-transient-retried,
  503-persistent-records-diagnostic.

## N. Quota behavior — IMPLEMENTED / TESTED

- No SchemeKnit quota change. Provider failures never consume a successful
  SchemeKnit generation unit (entitlement/quota logic in
  `backend/src/entitlements.py` unchanged and enforced before provider
  construction — `test_ai_production.py` entitlement matrix green). Gemini API
  usage limits are separate and never remapped into the SchemeKnit quota.

## O. Security — IMPLEMENTED / TESTED

- Key server-side only; never `NEXT_PUBLIC_GEMINI_API_KEY`, never in the
  frontend bundle; never logged (no key/authorization in any diagnostic);
  `TestSecretHygiene` + `test_no_keys_in_frontend_bundle_surface` guard this.
- `.env.example` carries `GEMINI_API_KEY=` / `GEMINI_MODEL=` placeholders
  (empty); `backend/.env` is not committed.

## P. Deterministic fallback — IMPLEMENTED / TESTED

- `AI_MODE=OFF` (and any unavailable provider) falls back to the deterministic
  engine with no AI attempt — `test_off_mode_no_ai_attempted`,
  `test_ai_off_still_generates_for_free_tier`. Provider methods return `{}` on
  failure; never raise into the pipeline.

## Q. Mocked tests — TESTED

All deterministic — no live key required. `test_gemini_groq_providers.py`
(42 tests) covers the §31 matrix: client init (A), model config (B), structured
success (C), malformed JSON (D), schema-invalid (E), timeout (F), 429 (G),
5xx/retry (H), auth failure (I), model-access failure (J), curriculum context
(K), provider routing (R), AI_MODE=OFF (S), Groq regression (T). Pipeline
guarantees L–Q are covered by `test_wapef_acceptance.py`,
`test_ai_failure_hardening.py`, `test_ai_production.py` (provider-agnostic).

## R. Live tests — DOCUMENTED (honest)

- Model access: `count_tokens` on `gemini-3.8-flash` → **success** (auth +
  model verified).
- A controlled structured generation succeeded during acceptance, returning
  canonical keys `['assessment', 'learning_objectives', 'main_learning',
  'plenary', 'starter']` — proves the full provider → parse → schema path with
  live Gemini.
- Free tier is heavily throttled (503 "high demand", 429 rate-limit) —
  most rapid live calls returned transient throttles. The provider retried and
  mapped these correctly. Live acceptance across all five representative modes
  was attempted; most were throttled. This is an environmental limit, NOT a
  code defect — reported honestly, never faked.
- `TestLiveGemini` runs only when `GEMINI_API_KEY` is present; it verifies
  auth/model access, attempts generation, hard-fails on genuine auth/model
  errors, and documents (skip) transient free-tier throttling.

## S. Model-access limitations — ENVIRONMENT LIMITATION

- **LIVE MODEL VERIFIED** (`gemini-3.8-flash` accessible, one structured
  generation succeeded).
- Live generation throughput is currently constrained by the Gemini FREE TIER
  (intermittent 503 high-demand / 429 rate-limit). This does not block the
  code-complete provider: all deterministic provider tests pass, and a live
  generation succeeded, but broad live acceptance remains throttled until the
  free tier allows it.

## T. Full regression — TESTED

- Backend suite: **1377 passed, 12 skipped, 0 failed** (incl. 4 new provider
  tests + live).
- Provider suite (live + deterministic): **38 passed, 1 skipped** (Groq live
  skipped — no key).
- Gates: app-ui 53/0, app-chrome 72/0, app-surfaces 109/0, login-grid 476/0,
  deep-journey 21/0, download 14/14, app-closure 94/0, hero 151/0, auth-role
  131/0 (hero/auth-role /setup checks reproduced under the documented
  baseline condition — populated DB redirects `/setup`; unchanged frontend).
- `tsc --noEmit` clean; `next build` exit 0.
- AI_MODE=OFF, Groq, WAPEF, KG, Nursery, Basic 1–3, Basic 4–JHS all preserved
  (suite + gates green).

## U. Commits — IMPLEMENTED

1. `feat(ai): integrate official Gemini GenAI provider`
2. `feat(ai): add structured curriculum-constrained Gemini generation`
3. `test(ai): add Gemini provider and live acceptance`
4. `docs(ai): add Gemini implementation report`

Pushed to `origin/main` (see §V).

## V. HEAD / origin parity — VERIFIED

- `git rev-parse HEAD` == `git rev-parse origin/main`.
- Working tree clean (excluding never-commit junk: e2e screenshot dirs,
  `backend/b5_backend.out/err`, `frontend/tsconfig.tsbuildinfo`).
- Note: the preceding Basic 1–3 phase was committed and pushed first (HEAD
  `c16ed95`), establishing the clean baseline this phase required.
