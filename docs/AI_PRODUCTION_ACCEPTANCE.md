# AI Production Acceptance

Date: 2026-09-16. AI is OPTIONAL: TeachFlow is fully usable deterministically with AI OFF.

## Architecture (pre-existing, verified — not reinvented)
- `engines/ai_provider.py`: `AIProvider` ABC + `Mock/Gemini/OpenAI/MiniMax/Ollama` providers,
  `get_provider(mode)`. Keys server-side only (`GEMINI_API_KEY`, `OPENAI_API_KEY`,
  `MINIMAX_API_KEY`, `OLLAMA_BASE_URL`/`OLLAMA_MODEL` env). No AI secrets in the
  frontend bundle (verified: only `NEXT_PUBLIC_API_URL` in client code).
- `POST /api/ai/regenerate-section`: owner-checked, section-allowlisted, enrichment cache,
  503 when unavailable, previous content preserved on failure.
- Generation-time `BASIC`/`ENHANCED` resolve to the (empty) Mock provider: deterministic
  output is never altered by AI unless a real provider path is used. Documented limitation.
- Bugs fixed this milestone (root-caused via live testing): `_get_section_content`
  crashed on sections without DB columns (`starter_activity`, etc.); Ollama fence-wrapped
  and nested payloads now unwrapped; provider timeout 30s→120s with output cap;
  unclosed-fence stripping; per-section prompting (`section=` kwarg, Ollama only).

## Enabled journey (Ollama local, qwen2.5-coder, CUDA) — PASS
Teacher → lesson → Suggest assessment → ~2–60s → clean text inserted → teacher edits →
Save → refresh retains → DOCX export contains AI+edited text (verified by file inspection:
marker found in output). Enrichment cache row written; audit event logged.

## Failure behavior — PASS
Provider down → controlled "not available/failed" message, lesson untouched (browser-verified).
Malformed/short responses → 500 with "Previous content preserved", original intact.
No secrets in UI, errors, or logs (tested). 503 contract unit-tested with stubs.

## Disabled behavior — PASS
AI OFF (default): every core journey in every milestone ran with no provider present.
Generation skips enrichment entirely when `ai_mode == OFF`. Upload/review/approve/edit/
export never touch providers.

## Limitations
- Only Ollama verified live (local, no key needed). Gemini/OpenAI/MiniMax need keys and
  were not live-tested; their code paths are unchanged.
- `BASIC`/`ENHANCED` generation modes currently enrich nothing (Mock). Honest status:
  real AI assistance = section regeneration via Ollama; generation-time enrichment is
  a no-op pending provider wiring (not claimed otherwise).
- qwen2.5-coder is a code model; prose quality is serviceable, not tuned. Model choice
  is env-configurable (`OLLAMA_MODEL`).

## Tests
12 AI tests (`test_ai_production.py`): payload robustness, 503/400/404 contracts,
secret-freedom, Mock mapping, env configuration.
