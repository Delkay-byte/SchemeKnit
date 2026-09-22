# Phase 15 — Final Report (Sections A–R)

**Project:** SchemeKnit (repo folder: `TeachFlow`)  
**Date:** 2026-09-22  
**Branch:** `main` (start `af9efe2`)  
**Remote:** `https://github.com/Delkay-byte/SchemeKnit.git`

---

## A. Executive Summary

Phase 15 validated live AI providers, ran real-document parse + live generation (Ollama/`llama3.1`), produced manual indicator-fidelity acceptance records for four Ghanaian scheme documents, mapped failure-mode test coverage, and re-ran the full build/test/deploy checks.

| Dimension | Status |
|-----------|--------|
| Backend suite | **1078 passed, 11 skipped, 0 failed** (~278s, 2026-09-22) |
| Frontend type-check | **OK** (`npx tsc --noEmit`) |
| Frontend build | **OK** (earlier `npm run build`) |
| Live Render API | `/api/health` **200** healthy, `version 1.0.5` |
| Live Render frontend | **200** |
| Gemini live | `auth_failed` — owner must update `GEMINI_API_KEY` in `backend/.env` (never paste into chat) |
| Groq live | `GROQ_API_KEY` empty / not configured |
| Ollama live | available; harness used model **`llama3.1`** |
| Security scan | Clean (no secret literals outside test assertions / Phase 14 report text; `backend/.env` gitignored) |
| Lint | `ruff` **not installed** locally (`No module named ruff`) — noted, not a code failure |
| Deploy SHA | **Not verifiable** from health endpoints (no SHA field) |

**Verdict:** Ready for owner credential fill-in (Gemini/Groq) and Render redeploy confirmation. In-repo code is green; no test failures.

---

## B. Objectives & Scope

**North star:** excellent generation from a teacher’s real scheme — right lesson, right indicator, right teaching period. Fix the generation engine when real docs reveal weaknesses; do not build unrelated product surface.

In scope this phase (15A–15R): live provider validation, real-doc parse + live generation, 15N acceptance records, failure-mode coverage map, quota/security/pedagogy mark-off, full build/test/deploy checks, this report.

Out of scope: dashboard/billing/branding/admin features; owner-side key rotation (blocked on credentials).

---

## C. Environment & Secrets Contract (15A–15B)

- `backend/.env` loaded via `src.config.load_dotenv` (confirmed present; gitignored).
- Redacted presence only: `GEMINI_API_KEY` **CONFIGURED** (len 53), `GROQ_API_KEY` **EMPTY**, `AI_MODE=OFF`, `GEMINI_MODEL=gemini-2.5-flash`, `GROQ_MODEL=llama-3.3-70b-versatile`.
- No key values, prefixes, or lengths of secrets printed beyond configured/missing/len for Gemini as previously authorized redaction contract.
- `backend/.env.example` has no real keys (`test_env_example_has_no_real_keys`).

---

## D. Live Provider Validation (15C–15D)

| Provider | Result |
|----------|--------|
| Gemini | `auth_failed` / HTTP 401 `ACCESS_TOKEN_TYPE_UNSUPPORTED` — credentials rejected; skip path in `TestLiveGemini` |
| Groq | unavailable — `GROQ_API_KEY` not set; skip path in `TestLiveGroq` |
| Ollama | `is_available=True`, models present incl. `llama3`, `llama3.1`, `gemma3:4b`, … |

Finding: `resolve_provider_mode("ENHANCED")` → `gemini` (key-present heuristic, no auth probe); pipeline falls back per-lesson to deterministic. Documented, not changed this phase.

---

## E. Provider Invariants (15E)

- 56 tests green across `test_gemini_groq_providers.py`, `test_generation_v2_integration.py`, `test_ai_enriched_generation.py`, `test_production.py` (subset reconfirmed in full suite).
- Invariants hold: provider choice never alters curriculum authority, allocation, quality gate, or quota.

---

## F. Real-Document Parse (15F)

| Fixture | detection_status | subject | weeks | notes |
|---------|------------------|---------|-------|-------|
| BASIC 7 TERM 1.pdf | `multiple` | Science | 15 | target Science |
| BASIC 8 TERM 1.pdf | **`extraction_failed`** | — | — | **SKIP live gen** (12.1 MB) |
| BASIC 9 TERM 1.pdf | `multiple` | Science | 15 | |
| BASIC 9 MATH … .docx | `single` | Mathematics | 15 | |
| BASIC 9 SCIENCE … .docx | `single` | Science | 15 | |

Related suites (prior + full run): parse/acceptance green.

---

## G. Live Generation (15G)

Harness: `backend/_phase15_live_gen.py` (temp; deleted before commit).

**Engine fixes applied this phase (generation quality, not product features):**

1. **`allocate` / `generate_lesson_plans` call signatures** in harness corrected to match engine API: `allocate(weeks, calendar, config)` and `generate_lesson_plans(coverage, config, scheme_id)` (was `TermConfig has no attribute days`).
2. **Scheme metadata onto `TermConfig`:** copy `scheme.class_level` / `scheme.subject` enums when not Unknown (enum `.value` strings; raw `str(enum)` rejected by pydantic).
3. **Ollama `num_predict` 800 → 2048** (`ai_provider.py`): full V2 lesson JSON truncated mid-object at 800 tokens on real-doc prompts (B9 PDF ended at `"Complete a worksheet on` → unparseable → empty with `last_error=None`). Root-caused via raw `_generate` probe; fixed provider, not harness-only.
4. Harness pins **`llama3.1`** (default `llama3` timed out 180s / returned unparseable output on V2 prompt).
5. One retry on empty content for non-determinism.

**Live run result (after num_predict fix):**

| Doc | Outcome |
|-----|---------|
| B7 PDF | quality_gate=**warn** score=**97** failures=**0** warnings=3 |
| B8 PDF | SKIP `extraction_failed` |
| B9 PDF | quality_gate=**warn** score=**93** failures=**0** warnings=6 |
| B9 Math DOCX | quality_gate=**warn** score=**94** failures=**0** warnings=6 |
| B9 Science DOCX | quality_gate=**warn** score=**96** failures=**0** warnings=4 |

No quality-gate failures on any generated lesson.

---

## H. Failure-Mode Coverage Map (15H) — 11 required modes

| # | Failure mode | Covered by | Status |
|---|--------------|------------|--------|
| 1 | Wrong subject | `test_generic_ingestion.py` (`unknown_subject…not_fabricated`, `two_subject…confirmation`), `test_multi_subject_detection.py`, `test_real_document_acceptance.py` (`03_no_english_leakage`, `06_subject_variation`), `test_docx_parser.py::test_subject` | Covered |
| 2 | Wrong class level | `test_detection_improvements.py`, `test_generic_ingestion.py` (`unknown_class…`, `filename…class_mismatch`), `test_docx_parser.py::test_class_level` | Covered |
| 3 | Wrong term | `test_docx_parser.py::test_term` (×2), special-week classification (`classify_revision/assessment/sba`) | Covered (parser-side; term not a generation input beyond calendar) |
| 4 | Wrong week | `test_docx_parser.py` sequential week numbers + `test_indicator_allocation.py::test_week_numbers_preserved`, `test_carry_forward_allocation.py` (source vs teaching week) | Covered |
| 5 | Wrong indicator | `test_curriculum_v2.py::test_indicator_code_mismatch_fails`, `test_generation_quality_v3.py::test_offscreen_indicator_fails_exactness` / `test_lesson_carries_exactly_the_uploaded_indicator`, `test_real_acceptance_quality_gate.py::test_rejects_missing_indicator` | Covered |
| 6 | Duplicated indicator/lesson | `test_indicator_allocation.py::test_no_duplicate_primary_indicator`, `test_duplicate_indicator_detected`; `test_carry_forward_allocation.py::test_no_indicator_dropped_or_duplicated`; `test_monthly_quota.py::test_duplicate_request_does_not_double_consume` | Covered |
| 7 | Dropped indicator | `test_carry_forward_allocation.py::test_no_indicator_dropped_or_duplicated`, `test_indicator_allocation.py::test_missing_indicator_detected`, `test_no_compression_of_indicators` | Covered |
| 8 | Carry-forward error | `test_carry_forward_allocation.py` (carry source/teaching week, conflict, determinism, no-backwards) | Covered |
| 9 | Generic objectives/activities/resources | `test_curriculum_v2.py::test_vague_objectives_warn`, `test_generic_assessment_warns`; `test_generation_v2_integration.py::test_quality_gate_rejects_generic_assessment`, `…_catches_vague_objectives`, `…_resources_are_realistic` (v3); `test_generation_quality_v3.py::test_resources_are_realistic` | Covered |
| 10 | Assessment misalignment | `test_curriculum_v2.py::test_missing_assessment_fails`, `test_generic_assessment_warns`; `test_real_acceptance_quality_gate.py::test_rejects_empty_assessment` | Covered |
| 11 | Hallucinated content / boilerplate / next-indicator contamination | `test_generation_v2_integration.py::test_quality_gate_catches_invented_references`; `test_curriculum_v2.py::test_invented_page_references_warn`; `test_real_science_acceptance.py::test_no_invented_curriculum_codes`; `test_no_synthetic_content.py` (blank ≠ filler); `test_generation_quality_v3.py::test_previous_and_next_context_used` + `test_offscreen_indicator_fails_exactness` (contamination boundary); `test_ai_failure_hardening.py` empty-response / quality-gate-failure paths | Covered |

**Gaps / notes:** No dedicated single test named for “term mismatch in generation config” beyond parser acceptance; no standalone adversarial “next-indicator contamination” assertion beyond offscreen-exactness + prev/next context usage — treated as adequately covered by existing suites for release, listed here for transparency.

---

## I. Quota & Free Tier (15I / 15O mark-off)

- `test_monthly_quota.py` — period key, consume 1–5, 6th blocked, failure release, duplicate no double-consume, regeneration free, concurrent oversubscribe: **green in full suite**.
- `test_free_tier_ai_lifetime.py` — 5 lifetime credits, no reset, idempotent submit, school unlimited: **green**.
- `test_individual_teacher_plan.py` quota/credit paths: **green**.

---

## J. Security & Architecture (15O mark-off)

- `test_security_hardening.py` (path traversal, upload extension, production secrets): **green**.
- `test_architecture_lock.py` (role/dependency boundaries): **green**.
- `test_authorization_idor.py`, `test_authorization.py`: **green**.
- Secret hygiene: `test_no_api_key_literals_in_source` + repo scan `AQ.`/`gsk_`/`sk-proj-` only in assertions and Phase 14 report prose.

---

## K. Quality Gate (15J)

- 18 `_check_*` families; `validate_lesson_quality` → `QualityReport`.
- Live: 0 failures on all 4 generated lessons (warn only: activity keyword overlap / score warnings).
- Unit: `test_curriculum_v2.py` gate cases, `test_generation_quality_v3.py`, `test_real_acceptance_quality_gate.py`: **green**.

---

## L. Pedagogy Profiles (15K)

- 11 profiles; `profile_for_subject` + `test_production.py::test_all_class_levels_have_profiles`, `test_generation_v2_integration.py` subject strategy tests, `test_curriculum_v2.py::test_build_prompt_contains_subject_pedagogy`: **green**.

---

## M. Allocation & Carry-Forward (15L)

- `test_indicator_allocation.py` + `test_carry_forward_allocation.py` + `test_generation_v2_integration.py` carry-forward: **green**.
- Live harness: B7 17 lessons / 0 dupes; B9 PDF 21 / 1 dupe; Math DOCX 22 / 1; Science DOCX 21 / 1 (dupes = coverage-validator signal from real multi-indicator weeks, not dropped indicators).

---

## N. Manual Indicator-Fidelity Acceptance Records (15N)

Factual fields only (no scores). Provider `ollama` / `llama3.1`. Term 1.

### 1. BASIC 7 TERM 1.pdf

| Field | Value |
|-------|-------|
| SOURCE | BASIC 7 TERM 1.pdf |
| CLASS | Basic 7 |
| SUBJECT | Science |
| TERM | Term 1 |
| CURRICULUM WEEK | 1 |
| TEACHING PERIOD | 1 |
| INDICATOR CODE | B7.1.1.1.1 |
| INDICATOR TEXT | Classify materials into liquids, solids and gases |
| PROVIDER | ollama |
| QUALITY GATE | warn (score 97, 0 failures) |
| CURRICULUM FAITHFUL | yes |
| OBJECTIVE ALIGNMENT | yes |
| ACTIVITY ALIGNMENT | yes |
| ASSESSMENT ALIGNMENT | yes |
| RESOURCE ALIGNMENT | yes |
| DIFFERENTIATION | yes |
| CLASSROOM FEASIBLE | yes |
| NOTABLE DEFECTS | none observed |

### 2. BASIC 8 TERM 1.pdf

SKIP — `detection_status=extraction_failed` (no lesson generated).

### 3. BASIC 9 TERM 1.pdf

| Field | Value |
|-------|-------|
| SOURCE | BASIC 9 TERM 1.pdf |
| CLASS | Basic 9 |
| SUBJECT | Science |
| TERM | Term 1 |
| CURRICULUM WEEK | 1 |
| TEACHING PERIOD | 1 |
| INDICATOR CODE | B9.1.1.1.1 |
| INDICATOR TEXT | Identify by name binary chemical compounds and discuss their use |
| PROVIDER | ollama |
| QUALITY GATE | warn (score 93, 0 failures) |
| CURRICULUM FAITHFUL | yes |
| OBJECTIVE ALIGNMENT | yes |
| ACTIVITY ALIGNMENT | partial |
| ASSESSMENT ALIGNMENT | partial |
| RESOURCE ALIGNMENT | yes |
| DIFFERENTIATION | yes |
| CLASSROOM FEASIBLE | yes |
| NOTABLE DEFECTS | activity keyword overlap weak; objective/assessment keyword overlap weak |

### 4. BASIC 9 MATH SCHEME OF LEARNING.docx

| Field | Value |
|-------|-------|
| SOURCE | BASIC 9 MATH SCHEME OF LEARNING.docx |
| CLASS | Basic 9 |
| SUBJECT | Mathematics |
| TERM | Term 1 |
| CURRICULUM WEEK | 1 |
| TEACHING PERIOD | 1 |
| INDICATOR CODE | B9.1.1.1.1 |
| INDICATOR TEXT | Express integers to a given number of significant and decimal places. |
| PROVIDER | ollama |
| QUALITY GATE | warn (score 94, 0 failures) |
| CURRICULUM FAITHFUL | yes |
| OBJECTIVE ALIGNMENT | yes |
| ACTIVITY ALIGNMENT | partial |
| ASSESSMENT ALIGNMENT | partial |
| RESOURCE ALIGNMENT | yes |
| DIFFERENTIATION | yes |
| CLASSROOM FEASIBLE | yes |
| NOTABLE DEFECTS | activity/assessment keyword overlap weak |

### 5. BASIC 9 SCIENCE SCHEME OF LEARNING.docx

| Field | Value |
|-------|-------|
| SOURCE | BASIC 9 SCIENCE SCHEME OF LEARNING.docx |
| CLASS | Basic 9 |
| SUBJECT | Science |
| TERM | Term 1 |
| CURRICULUM WEEK | 1 |
| TEACHING PERIOD | 1 |
| INDICATOR CODE | B9.1.1.1.1 |
| INDICATOR TEXT | Identify by name binary chemical compounds and discuss their use |
| PROVIDER | ollama |
| QUALITY GATE | warn (score 96, 0 failures) |
| CURRICULUM FAITHFUL | yes |
| OBJECTIVE ALIGNMENT | yes |
| ACTIVITY ALIGNMENT | yes |
| ASSESSMENT ALIGNMENT | yes |
| RESOURCE ALIGNMENT | yes |
| DIFFERENTIATION | yes |
| CLASSROOM FEASIBLE | yes |
| NOTABLE DEFECTS | activity keyword overlap weak |

---

## O. Observations on Generation Quality (engine, not product)

Observed on real docs (not blocking):

1. **Keyword-overlap “partial” alignment** on some Science/Math activities — quality gate warns; curriculum fields remain scheme-authoritative (`_apply_v2_content` does not overwrite them).
2. **`resolve_provider_mode` name-only key check** — dead Gemini selection then silent deterministic fallback; candidate follow-up (probe or prefer last-known-good provider).
3. **Ollama default model `llama3` unsuitable for full V2 JSON** — harness pins `llama3.1`; consider documenting `OLLAMA_MODEL=llama3.1` in `.env.example` (not changed to avoid surprising prod defaults without owner sign-off).
4. **`coverage_dupes` = 1** on three B9 fixtures — allocation over multi-indicator weeks reports a duplicate signal worth a follow-up audit (not dropped indicators; lesson counts match indicator splits).

---

## P. Build / Test / Deploy Checks (15P)

| Check | Command / URL | Result |
|-------|---------------|--------|
| Full pytest | `python -m pytest tests/ -q` | **1078 passed, 11 skipped** |
| Frontend tsc | `npx tsc --noEmit` | **OK** |
| Backend import | `python -c "import src…"` | OK (earlier) |
| API health | `GET /api/health` | **200** `{"status":"healthy","service":"SchemeKnit","version":"1.0.5"}` |
| Frontend | `GET /` | **200** |
| `ruff` | `python -m ruff` | **Not installed** |
| Deploy SHA | health payload | **Not exposed** — redeploy verification requires owner Render dashboard |

Notes: `docx2pdf`/`docx2pdf` conversion in `test_web_acceptance_http`/`pdf_export` produced Windows fatal exception noise during suite but **tests still completed green** (1078/11). Deprecation warnings only (utcnow, pydantic max_items).

---

## Q. Security Scan (15O)

- `git grep` patterns `AQ.` / `gsk_` / `sk-proj-`: hits only in `test_gemini_groq_providers.py` assertions and `docs/PHASE14_FINAL_REPORT.md` prose (documentation of findings, not credentials).
- `backend/.env` ignored by `.gitignore`.
- `test_production_ui_safety.py` / `test_security_hardening.py` production-secret checks: green.

---

## R. Findings, Owner Actions, Residual Risk

### Fixed this phase (engine)

| ID | Finding | Fix |
|----|---------|-----|
| P15-1 | Harness used wrong `allocate`/`generate_lesson_plans` signatures | Corrected call order + `coverage → plans` |
| P15-2 | `TermConfig` subject/class as `str(enum)` invalid | Propagate scheme enums; print via `.value` |
| P15-3 | Ollama `num_predict=800` truncates V2 JSON → empty gen | **`ai_provider.py` → 2048** |
| P15-4 | Default Ollama model `llama3` timeouts / bad JSON | Harness pins `llama3.1` (recommend env note) |
| P15-5 | Live test env-load order skipped `.env` keys at collection | `import src.config` before `skipif` (already in working tree) |

### Owner actions (blocked on credentials / dashboard)

1. Replace `GEMINI_API_KEY` in `backend/.env` with a working key (never paste into chat).
2. Set `GROQ_API_KEY` in `backend/.env` if Groq live is required.
3. Confirm Render redeploy SHA in dashboard (health endpoints do not expose it).
4. Optional: set `OLLAMA_MODEL=llama3.1` in `.env.example` / prod if Ollama is used.

### Residual risk

- Gemini/Groq live paths unverified until keys updated.
- Render SHA unconfirmed.
- `ruff` unavailable in this environment (not a product defect).
- Activity keyword-overlap warnings on some real lessons (quality gate `warn`, not `fail`).

---

## Sign-off checklist (A–R)

| Sec | Item | Done |
|-----|------|------|
| A | Executive summary | ✓ |
| B | Objectives & scope | ✓ |
| C | Env/secrets contract | ✓ |
| D | Gemini/Groq/Ollama live | ✓ (Gemini/Groq blocked on owner) |
| E | Provider invariants | ✓ |
| F | Real-doc parse | ✓ |
| G | Live generation + engine fixes | ✓ |
| H | 11 failure modes map | ✓ |
| I | Quota / free tier | ✓ |
| J | Security / architecture | ✓ |
| K | Quality gate | ✓ |
| L | Pedagogy | ✓ |
| M | Allocation / carry-forward | ✓ |
| N | 15N acceptance records | ✓ (4 records + B8 skip) |
| O | Security scan | ✓ |
| P | Build/test/deploy | ✓ (SHA unconfirmed; ruff absent) |
| Q | Secret hygiene | ✓ |
| R | Findings + owner actions | ✓ |
