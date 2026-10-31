# DeepSeek / Groq Hardening Report

Date: 2026-10-30
Branch: `hardening/deepseek-groq-staging-20261030`

## Scope

Reconciled the preserved DeepSeek verification work with `origin/main`,
resolved the seven known baseline failures, added bounded Groq fallback,
cleaned provider configuration, fixed resource formatting, added
provider-authored class assignments and assessment items, established cache /
credit policy, and verified a six-case curriculum matrix plus one live Groq
fallback.

## Provider architecture

- Primary Zeli provider: **DeepSeek** (`deepseek-flash`, official
  `https://api.deepseek.com`).
- Fallback: **Groq** (`openai/gpt-oss-120b`), configured by
  `ZELI_FALLBACK_PROVIDER=groq` and standard `GROQ_*` variables.
- Standard enrichment: **Groq** via `AI_MODE=groq`.
- Fallback is one attempt, at the provider/content boundary:
  `DeepSeek → Groq → teacher-safe error`.
- No MOCK provider is used as an automatic production fallback.

## Eligibility

Fallback is allowed for network/connection failures, timeouts/408, 429, 5xx,
malformed/schema-invalid output, empty output and a quality-gate rejection.
Fallback is refused for missing/invalid credentials, 401/403, unknown model,
invalid request, parser/database/application errors and missing curriculum.

## Provenance

Every lesson records the provider and model that actually produced it. The
generate response and job snapshot also record:

- primary provider/model,
- fallback provider/model when used,
- fallback-used flag,
- sanitized primary error code,
- cache-hit count,
- external-call count,
- per-attempt sanitized records.

A DeepSeek-generated lesson can never be labelled Groq, and vice versa.

## Code changes

| Area | Change |
|---|---|
| `src/config.py` | Added `ZELI_FALLBACK_PROVIDER` validation (empty or named, not equal to primary). |
| `src/engines/zeli_generation.py` | Independent fallback credentials, bounded fallback orchestration, cache-hit flag, sanitized attempts, prompt v5. |
| `src/engines/generation_pipeline.py` | Fallback metadata, quality-gate fallback for rejected lessons, provider-authored class assignment/assessment items, resource normalization, AI provenance. |
| `src/curriculum/generation_prompt.py` | Scientific-category rule; class_assignment and assessment_items schema/rules. |
| `src/parsers/docx_parser.py` | Multi-code cell and range handling; duplicate-code NameError fix. |
| `src/auth.py` | Missing credentials return 401 + `WWW-Authenticate`, not 403. |
| `src/ai_resource_text.py` | New comma-preserving resource normalizer. |
| `src/service.py` | Resource normalization at the teacher-edit boundary. |
| `src/routers/generation.py` | Actual-provider reporting, fallback metadata, cache-aware AI credit, quality fallback hook. |
| `tests/test_final_web_ux.py` | Download test double matches production `context` argument. |

## Resource formatting

`normalize_resource_items` treats list structure, newlines and semicolons as
delimiters. Commas inside one description are preserved. The API serializer,
DB-to-model conversion and teacher-edit save path use the same normalizer.
Duplicates are removed case-insensitively and whitespace is normalized.

Example preserved intact:
`Samples of table salt, water, and baking soda (for observation only)`.

## Class assignment and assessment items

The provider schema now asks for:

- a specific, teacher-ready `class_assignment`, and
- concrete `assessment_items` with prompt, expected evidence, marking guidance
  and misconception.

Whole-lesson Zeli mapping uses them when present; older/cached lessons without
them keep their existing deterministic fields, so backward compatibility holds.

## Live verification

- **Real DeepSeek:** six-case KG/primary/JHS matrix, all HTTP 200, all
  persisted, all DOCX/PDF exports 200.
- **Real Groq fallback:** controlled DeepSeek timeout at the provider
  boundary; real Groq generated and persisted one Basic 9 Science lesson
  (`ai_provider=groq`, `ai_model=openai/gpt-oss-120b`,
  `fallback_used=true`, `primary_error=timeout`). HTTP 200, DOCX/PDF 200.
- **Mock-based tests:** fallback eligibility, both-fail, auth-no-fallback,
  cache and credit cases use controlled provider doubles. They are not claimed
  as live provider verification.

## Known limitations

- KG source schemes do not declare a subject; the matrix uses the curriculum
  learning area “Our World Our People” for the All About Me / My Family
  strands.
- Basic 6 Term 1 is a mixed-subject source document. The matrix selects the
  source indicator and subject explicitly; it does not claim the document is
  single-subject.
- Rubric scores are lower for some KG/English lessons because the shared
  rubric rewards repeated indicator words and generic science-process markers.
  The gate accepted those lessons and the content is curriculum-correct; the
  score is reported transparently rather than tuned.
- The display serializer for `indicators` still splits semicolons in legacy
  text fields. Persisted source indicators remain intact in the database.
