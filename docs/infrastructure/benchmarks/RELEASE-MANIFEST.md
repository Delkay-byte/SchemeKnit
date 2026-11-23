# SchemeKnit release candidate manifest

Baseline commit: `23009667ccc385feb4438a8988ab70392edc1642`
Status: local, uncommitted release candidate. No push, CI or deploy.

## Generation changes

- `backend/src/engines/generation_pipeline.py` — bounded per-parent worker pool,
  per-worker provider/session ownership, curriculum-order merge, per-lesson
  timings, provider-429 retries, shared-permit queueing.
- `backend/src/engines/generation_concurrency.py` — provider ceilings and
  effective worker calculation.
- `backend/src/ai_spend.py` — database-leased provider/global/teacher permits,
  SQLite write guard, permit release on success and failure.
- `backend/src/engines/zeli_generation.py` — provider error codes, cache read
  transaction release.
- `backend/src/routers/generation.py` — durable live unit progress, generated
  and processing counters, generation timings, Zeli-unavailable logging.
- `backend/src/database.py` — SQLite WAL, busy timeout and connection timeout.
- `backend/src/config.py`, `backend/.env.example` — concurrency defaults and
  bounds.

## Frontend

- `frontend/src/app/(app)/generate/[id]/page.tsx` — live parallel progress text
  and actual-count completion messages.

## Tests and benchmarks

- `backend/tests/test_generation_parallel_pipeline.py`
- `backend/tests/test_global_concurrency_limits.py`
- `backend/tests/benchmark_generation_parallel.py`
- `docs/infrastructure/benchmarks/generation-parallel.json`
- `docs/infrastructure/benchmarks/generation-parallel.md`

## Settings

| Setting | Default | Range / cap |
|---|---:|---|
| `GENERATION_MAX_CONCURRENCY` | 3 | 1–8 |
| `GENERATION_CONCURRENCY_WAIT_SECONDS` | 120 | 5–900 |
| `AI_MAX_CONCURRENT_PER_TEACHER` | 2 | controls effective worker count |
| `AI_GLOBAL_MAX_CONCURRENT` | 8 | database lease |
| `GENERATION_PROVIDER_CONCURRENCY` | built-in map | Groq 3, DeepSeek 3, Gemini 1, OpenAI 4, Ollama 1 |

Effective default on the current configuration: 2 workers (teacher AI cap).

## Database / migrations

No schema change and no migration. The new provider permit uses the existing
`ai_spend_counters` table (`scope = concurrency_provider`, `provider = <name>`).
Existing rows and limits remain valid.

## Verification summary

- Backend: 3313 passed, 25 skipped, 0 failed.
- Frontend: TypeScript clean, 15 DOCX tests, 101 UX tests, 11 security tests,
  0 lint errors, production build passed.
- All four previously failing DOCX/ZIP structural tests now pass.
- No credential literal found in changed or untracked files.
