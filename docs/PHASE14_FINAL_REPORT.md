# Phase 14 — Final Report (Sections A–P)

**Project:** SchemeKnit (repo folder: `TeachFlow`)  
**Date:** 2026-09-22  
**Branch:** `main` @ `d12eaf936f6cf765c522203b6c7d3969bbfef394`  
**Remote:** `https://github.com/Delkay-byte/SchemeKnit.git` (in sync with `origin/main`)

---

## A. Executive Summary

Phases 1–13 are complete. The generation stack now treats the uploaded/approved curriculum as the authority, enforces **ONE INDICATOR = ONE TEACHING PERIOD = ONE LESSON PLAN**, ships a server-side Free Tier (5 lesson plans / calendar month + 5 lifetime AI credits), supports Gemini/Groq named providers with deterministic fallback, runs an 18-family quality gate, and accepts real Ghanaian Basic 7/8/9 documents.

| Dimension | Status |
|-----------|--------|
| Backend suite | **1078 passed, 11 skipped, 0 failed** (206.84s, 2026-09-22) |
| Frontend build | **OK** (`npm run build`, type-check included) |
| Git | `7f50bda` + `d12eaf9` pushed; `main == origin/main` |
| Security scan | Clean (no secrets in tracked files; `.env` gitignored) |
| Live Render | API `200` (`version 1.0.5`), frontend `200` — **deploy SHA not exposed** |
| Live AI providers | Gemini `auth_failed` (key rotated); Groq key **not set** |

**Verdict:** Ready for owner-side credential fill-in and Render redeploy confirmation. No code blockers remain in-repo.

---

## B. Objectives & Scope

**North star:** Turn a teacher’s real scheme into indicator-accurate lesson plans.

In scope delivered:
1. Curriculum-IR-constrained generation (not free-form AI).
2. Free Tier 5/month quota, server-authoritative, atomic, idempotent.
3. Generic document ingestion (structure-aware, not filename-matching).
4. Named AI providers (Gemini, Groq) + mock/Ollama/OpenAI/OpenCode Zen.
5. Quality gate that blocks/flags weak lessons.
6. Real-document acceptance (Basic 7/8/9 PDFs + Basic 9 DOCX).
7. Security audit + deployment verification + this report.

Out of scope / frozen:
- Approved lesson-plan template/export structure (not redesigned).
- Payment/licensing product decisions (existing entitlements kept).

---

## C. Architecture — Curriculum Authority

```
Upload (PDF/DOCX)
  → parsers (semantic headers; statuses: extracted | multiple |
             needs_confirmation | low_confidence | extraction_failed)
  → Curriculum IR (strand / standard / indicator codes)
  → allocation: ONE INDICATOR → ONE TEACHING PERIOD → ONE LESSON
     (surplus indicators CARRY FORWARD; never silently dropped/duplicated)
  → generation pipeline
       mode OFF      → deterministic lesson_builder (no network)
       mode BASIC/ENHANCED/named → resolve_provider_mode → get_provider
  → AI content (optional enrichment only; same canonical schema)
  → quality gate (18 check families)
  → Free Tier reserve/release (usage ledger)
  → LessonPlan + export (DOCX/PDF/XLSX/ZIP)
```

Key invariants (code):
- `backend/src/usage_quota.py:9` — commercial model comment.
- `backend/src/engines/allocation_engine.py:9` — allocation rule.
- `backend/src/engines/ai_provider.py:1-13` — AI never required; provider choice never changes curriculum authority, quota, gate, structure, or allocation.
- `backend/src/curriculum/quality_gate.py` — fail/warn/pass battery; `strand_match` compares `source_strand` (Phase 7 fix).

---

## D. Generation Quality (indicator accuracy)

| Mechanism | Evidence |
|-----------|----------|
| Indicator-scoped generation | `TermConfig.selected_indicator_codes`; pipeline filters (`generation_pipeline.py:83`); router re-validates selection vs quota (`routers/generation.py:242-301`) |
| Deterministic baseline | `curriculum/lesson_builder.py` + `pedagogy.py` + `indicator_interpreter.py` |
| AI as enrichment only | Structured JSON schema; `_apply_v2_content`; failures leave deterministic content intact (`test_ai_failure_hardening.py`) |
| Quality V3 tests | `test_generation_quality_v3.py` — lesson carries exactly the uploaded indicator; objective is learner-centred and about the indicator |
| Anti-hallucination | `no_invented_references`, `no_invented_codes`, `boilerplate_detection` in quality gate |

---

## E. Free Tier & Quota

**Rules** (`backend/src/usage_quota.py`, `entitlements.py`):

| Rule | Implementation |
|------|----------------|
| Allowance | `FREE_TIER_LESSON_PLANS_PER_MONTH = 5` |
| AI credits | `FREE_TIER_AI_GENERATIONS = 5` (lifetime, separate concept) |
| Period | Server clock only → `YYYY-MM`; new month = new row (no cron) |
| Atomicity | Insert unit rows + single guarded `UPDATE units_used + N <= limit` |
| Idempotency | Unit key `{scheme_id}:{indicator_code}` — regenerate same month = 0 extra |
| Failure | `release_lesson_units` returns reserved units; failures never consume |
| Ollama | Cannot bypass — quota checked before provider work |

**Frontend** (`frontend/src/app/generate/[id]/page.tsx`):
- Pre-selects up to `lesson_quota.remaining` indicators.
- Hard-caps selection at remaining allowance.
- Shows “X of 5 used · Y remaining” and upsell to Teacher Pro.
- Unselected indicators stay in the scheme for later months.

**Tests:** `test_monthly_quota.py` (reset, 6th blocked, failure release, concurrency guard), `test_free_tier_ai_lifetime.py`, `test_individual_teacher_plan.py` (`lesson_quota_remaining == 5` / `0`).

---

## F. Generic Document Ingestion

- Parsers understand **structure** (headers, column order, semantic week/strand/indicator fields), not one file’s filename.
- Detection statuses surfaced honestly: `multiple`, `needs_confirmation`, `low_confidence`, `extraction_failed` (`routers/documents.py:30-35`).
- Generation blocked on `extraction_failed` (`routers/generation.py:182`).
- Tests: `test_generic_ingestion.py` (241 lines — alternate schools/headers/column order), `test_multi_subject_detection.py`, `test_detection_improvements.py`.
- Real fixtures in `backend/real_documents/`:
  - `BASIC 7 TERM 1.pdf`
  - `BASIC 8 TERM 1.pdf`
  - `BASIC 9 TERM 1.pdf`
  - `BASIC 9 MATH SCHEME OF LEARNING.docx`
  - `BASIC 9 SCIENCE SCHEME OF LEARNING.docx`

---

## G. AI Providers

| Provider | Class | Availability | Notes |
|----------|-------|--------------|-------|
| Mock | `MockProvider` | always | Deterministic; `is_available() == True` by design |
| Gemini | `GeminiProvider` | `GEMINI_API_KEY` | REST, header auth, `responseMimeType: application/json`, default `gemini-2.5-flash` |
| Groq | `GroqProvider` | `GROQ_API_KEY` | Bearer auth, default `llama-3.3-70b-versatile` |
| OpenAI | `OpenAIProvider` | `OPENAI_API_KEY` | default `gpt-4o-mini` |
| OpenCode Zen | `OpenCodeZenProvider` | `OPENCODE_ZEN_API_KEY` | free models |
| Ollama | `OllamaProvider` | local probe | last in auto order |
| MiniMax | `MiniMaxProvider` | key | registered named provider |

**Resolution** (`resolve_provider_mode`):
1. `OFF` → never reaches a provider.
2. Named mode or pinned `AI_MODE` env wins when AI on.
3. Else auto: `gemini → groq → openai → opencode-zen → ollama` (first available).
4. None available → return original `BASIC`/`ENHANCED` → Mock/deterministic.

**Env** (`backend/.env`, gitignored):

```
AI_MODE=OFF
GEMINI_API_KEY=<set, length 53>
GEMINI_MODEL=gemini-2.5-flash
GROQ_API_KEY=<EMPTY — owner must add>
GROQ_MODEL=llama-3.3-70b-versatile
```

`backend/.env.example` is fully redacted (tracked, clean).

**Tests:** `test_gemini_groq_providers.py` — unit coverage for modes, parsing, diagnostics, header-not-query auth, no key literals in source; `@pytest.mark.live` tests skip on `auth_failed` / missing key.

**Current live status:** Gemini returns `last_error=auth_failed` (key invalid/rotated). Groq untested live (no key). Both are **operator actions**, not code defects.

---

## H. Quality Gate

`backend/src/curriculum/quality_gate.py` — check families:

| Category | Checks |
|----------|--------|
| Curriculum | `indicator_code_match`, `subject_match`, `strand_match` (Phase 7: compares `source_strand`) |
| Objectives | `has_objectives`, `objectives_learner_can`, `objectives_measurable`, `objectives_measurable_verb`, `objectives_quality` |
| Activities | `has_main_activities`, `activity_{i}_detail`, `timing_valid` |
| Assessment | `has_assessment`, `assessment_specific` |
| Coherence | `has_starter`, `has_conclusion`, `phase_coherence`, `assessment_alignment` |
| Practicality | `practical_resources`, `class_size_feasible`, `differentiation_usefulness` |
| Anti-hallucination | `no_invented_references`, `no_invented_codes` |
| Advanced | `indicator_exactness`, `subject_appropriateness`, `class_level_appropriateness`, `cognitive_demand`, `boilerplate_detection`, `required_fields`, `internal_contradiction`, `irrelevant_content` |

Statuses: `pass` / `warn` / `fail`. A `fail` surfaces as `quality_gate_failed` (never silently returned as good) — `test_ai_failure_hardening.py`.

---

## I. Real-Document Acceptance

| Suite | Covers |
|-------|--------|
| `test_real_document_acceptance.py` | Basic 7 + Basic 9 PDF: multi-subject detect, parse, allocate, generate, quality gate (0 failures asserted) |
| `test_real_acceptance_quality_gate.py` | Full pipeline PDF → IR → allocate → mock V2 → gate; BASIC 9 multi-subject (English + Science); malformed-input gate |
| `test_real_science_acceptance.py` | Basic 9 Science DOCX end-to-end + `validate_generated` |
| `test_real_ai_provider.py` | Real-doc path with provider abstraction (CWD-independent `REAL_DOCS`) |
| `test_ai_enriched_generation.py` | Basic 7 enriched path + anti-repetition |
| `test_web_acceptance_http.py` | HTTP upload→approve→generate→edit→export |

All use `REAL_DOCS = Path(__file__).parent.parent / "real_documents"` (fix in `d12eaf9` — no longer CWD-dependent).

BASIC 9 multi-subject: detection + separate English/Science lesson generation + per-subject quality-gate runs (`test_real_document_acceptance.py` ~245–418).

---

## J. Security Audit

| Area | Status | Evidence |
|------|--------|----------|
| Secrets in git | **Clean** | Pattern scan: no `sk-`/`AIza`/`AQ.`/`gsk_` literals outside gitignored `.env` |
| `.env` ignored | **Yes** | `.gitignore:14` → `.env`, `backend/.env` |
| `.env.example` | **Redacted** | Empty key slots only |
| Secrets never in browser | **Pass** | `test_ai_production.py::test_no_keys_in_frontend_bundle_surface` |
| Platform Admin isolation | **Pass** | `require_platform_admin` on payments/platform_admin; architecture lock rejects role crossover (`test_architecture_lock.py`) |
| Path traversal / upload | **Pass** | `test_security_hardening.py` — `sanitize_filename`, `safe_join`, MIME/ext checks |
| Rate limiting | **Pass** | `RateLimiter` window/isolation tests |
| IDOR / tenancy | **Pass** | `test_authorization_idor.py`, `test_school_isolation.py` |
| Production config fail-safe | **Pass** | Default secrets rejected when `DEBUG=false` |
| Password / reset tokens | **Pass** | `test_auth_lifecycle.py` — single-use, user-bound, expiring |
| PDF converter absence | **Controlled 503** | Never raw 500; message names LibreOffice |

---

## K. Deployment Verification

| Check | Result |
|-------|--------|
| `GET https://schemeknit-api.onrender.com/api/health` | **200** `{"status":"healthy","service":"SchemeKnit","version":"1.0.5"}` |
| `GET https://schemeknit-frontend.onrender.com` | **200** |
| Deployed commit SHA | **Not exposed** by health payload |
| Can we claim Render has `7f50bda`/`d12eaf9`? | **No** — unverifiable from public endpoints |

**Honest statement:** Both services are up at version 1.0.5. Whether Render has rebuilt on the latest pushed commits is **unknown** until a SHA (or a behavioral probe unique to the new code) is observed.

---

## L. Test Results

### Full backend suite (re-run 2026-09-22)

```
1078 passed, 11 skipped, 0 failed  (3362 warnings, 206.84s)
```

### Frontend

```
npm run build → BUILD_OK
  ✓ Compiled successfully
  ✓ Linting and checking validity of types
  ✓ Generating static pages (35/35)
```

(`npx tsc` alone was unavailable — TypeScript not on global npx path — but Next’s build type-check is clean.)

### Lint / typecheck (backend)

- `ruff` / `mypy` **not installed** in this environment — not run.
- `from src.main import app` imports OK (verified earlier).

### Skips (11)

Primarily `@pytest.mark.live` provider tests (Groq missing key; Gemini auth) and fixture-gated real-doc tests when a file is absent (files present locally; live tests skip on credential errors by design).

### Known intermittent flake

`test_export_download.py` PDF path invokes `docx2pdf` → Word. During this run Windows raised `0x800706be`/`0x800706ba` inside the converter thread; **suite still finished 0 failed** (conversion path handled). On machines without Word/LibreOffice, layer-1 tests assert controlled 503 instead.

### New/updated test files this effort

| File | Role |
|------|------|
| `test_gemini_groq_providers.py` | Provider unit + isolated live (443 lines) |
| `test_monthly_quota.py` | Calendar quota atomicity (178 lines) |
| `test_generic_ingestion.py` | Structure-agnostic parsing (241 lines) |
| `test_generation_quality_v3.py` | Indicator-accurate quality (274 lines) |
| `test_real_*` | Real-doc acceptance (CWD-independent paths) |
| `pytest.ini` | Registered `live` marker |

---

## M. Commits & Change Log

| Commit | Message | Scope |
|--------|---------|-------|
| `7f50bda` | feat: Generation V3 providers (Gemini/Groq), free-tier selection UI, quality-gate fix, BASIC 8 acceptance | 49 files, +4322/−482 |
| `d12eaf9` | fix: stabilize test suite — CWD-independent real-doc paths, isolated provider fallback, live-marker registration | 5 files, +14/−8 |

Combined `7f50bda^..HEAD`: **52 files, +4331/−485** (backend engines/parsers/quota/tests + frontend generate UI).

Notable source deltas in `7f50bda`:
- `ai_provider.py` +783 lines rewrite
- `quality_gate.py` +322
- `usage_quota.py` +282 (new)
- `lesson_builder.py` +290, `pedagogy.py` +590 (new)
- `docx_parser.py` +301
- `generation.py` +210
- `entitlements.py` +101
- migration `v020_usage_periods.py` (new)
- frontend `generate/[id]/page.tsx` +148

Working tree: only `frontend/tsconfig.tsbuildinfo` modified (build artifact; intentionally unstaged).

---

## N. Known Issues & Risks

| # | Issue | Severity | Owner action |
|---|-------|----------|--------------|
| 1 | Gemini live key `auth_failed` (53-char `AQ.` key invalid/rotated) | High for live AI | Put current key in `backend/.env` `GEMINI_API_KEY` |
| 2 | `GROQ_API_KEY` empty everywhere | High for live AI | Add key to `backend/.env` only — never chat/commit |
| 3 | Render deploy SHA unverifiable | Medium | Expose commit hash in `/api/health` or confirm dashboard deploy |
| 4 | `ruff`/`mypy` absent locally | Low | Install and run before production hardening pass |
| 5 | LibreOffice/Word PDF flake on Windows without Word | Low (controlled 503 in prod) | Ensure LibreOffice on Render/desktop for PDF |
| 6 | `AI_MODE=OFF` in local `.env` | Info | Flip to `gemini`/`ENHANCED` when keys valid |
| 7 | Health says `1.0.5` while report is post-1.0.5 work | Info | Bump version on next deploy |

---

## O. Evidence Index

| Claim | Where to verify |
|-------|-----------------|
| Suite green | `python -m pytest backend/tests -q` → 1078/11/0 |
| Quota semantics | `backend/src/usage_quota.py`, `tests/test_monthly_quota.py` |
| Free Tier constants | `backend/src/entitlements.py:38,47` |
| Provider matrix | `backend/src/engines/ai_provider.py:22-36,797-838` |
| Quality gate + strand fix | `backend/src/curriculum/quality_gate.py:111-131` |
| Indicator selection UI | `frontend/src/app/generate/[id]/page.tsx:141-186,637-713` |
| Real docs | `backend/real_documents/*` + `tests/test_real_*.py` |
| Generic ingestion | `tests/test_generic_ingestion.py` |
| Security | `tests/test_security_hardening.py`, `.gitignore`, `.env.example` |
| Secrets clean | Pattern scan over tracked tree (this session) |
| Live health | `GET /api/health` → 200 v1.0.5 |
| Commits | `git log -2`, `git status -sb` → synced |

---

## P. Recommendations & Next Steps

**Immediate (owner):**
1. Paste a valid `GEMINI_API_KEY` into `backend/.env`.
2. Paste `GROQ_API_KEY=gsk_…` into `backend/.env` (never in chat/git).
3. Set `AI_MODE=gemini` (or leave auto) and re-run:
   `pytest backend/tests/test_gemini_groq_providers.py -m live -v`
4. Redeploy Render; add commit SHA to `/api/health` (or check deploy log) to close the unverified-deploy gap.

**Short term:**
5. Install `ruff` + `mypy`, add to CI; fix any findings.
6. Confirm PDF export on Render (LibreOffice present → not 503).
7. Browser smoke: upload Basic 9 → approve → select ≤5 indicators → generate → export DOCX/PDF.

**Product:**
8. Keep Free Tier messaging aligned: 5 **plans/month** vs 5 **AI credits lifetime** (dashboard already distinguishes).
9. Do not alter frozen approved-template topology.

**Sign-off checklist for Phase 14:**

- [x] Gap report (Phase 1)
- [x] Indicator-selection UI + quota cap (Phase 2)
- [x] Quality-gate strand fix (Phase 7)
- [x] Provider layer Gemini/Groq + env contract (Phase 8)
- [x] Real-document acceptance (Phase 9)
- [x] Provider tests + live marker (Phase 10)
- [x] Security scan clean (Phase 11)
- [x] Deployment HTTP verified; SHA gap documented (Phase 12)
- [x] Suite 1078/11/0 green + commits pushed (Phase 13)
- [x] This A–P report (Phase 14)

---

*End of Phase 14 report.*
