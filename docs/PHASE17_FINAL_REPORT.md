# Phase 17 — Final Report (Sections A–R)

**Project:** SchemeKnit (repo folder: `TeachFlow`)
**Date:** 2026-09-23
**Branch:** `main` @ `139b4eb5cf15e7dfaf8cd1f86072f7307cd7faf1` (base HEAD — this report describes the changes committed on top as `60fe769`)
**Remote:** `https://github.com/Delkay-byte/SchemeKnit.git`

---

## A. Executive Summary

Phase 17 ("PRODUCTION PROVIDER VALIDATION + END-TO-END TEACHER ACCEPTANCE") validates the live provider surface (Gemini/Groq), runs the real teacher journey through the actual UI/API (upload → allocate → generate → export → entitlements), audits lesson quality for boilerplate weaknesses, and hardens the generation/export engine wherever acceptance testing found real defects.

| Dimension | Status |
|-----------|--------|
| Backend suite | **1096 passed, 10 skipped, 0 failed** (201.12s, 2026-09-23) |
| Frontend type-check / build | **OK** (`npx tsc --noEmit` exit 0; `npm run build` exit 0) |
| Backend startup | **OK** — local `/api/service-status` healthy (v1.0.5); `.env` restored to `AI_MODE=OFF` after Run B |
| Teacher journey E2E | **Run A (AI_MODE=OFF): 34/34**; **Run B (AI_MODE=groq): 21/21** |
| Live providers | Gemini `LIVE_AUTH_FAILURE` (`auth_key_rejected` — key rejected, owner re-mint required); **Groq live & passing** (`openai/gpt-oss-20b`, `TestLiveGroq` 3.61s) |
| Provider parity (17D) | Math **98.8**, Science **98.8**, Social **100.0** — indicator identity identical across `llama3.1` / `gemma3:4b` / `groq` (3/3); Gemini legs honestly BLOCKED |
| 20-lesson review (17I) | **20/20 exact identity, 0 contaminated** |
| Engine defects found & fixed | Quality-gate dropped-`e` verb pattern + `"use"` measurable; activity dedupe + duration fit; **ZIP Pro-gate missing on the active `/download-url` path** (entitlement bypass — fixed); custom structure/term context parity on zip/docx |
| Live Render (17M) | API `/api/health` **200** `v1.0.5`, `/api/service-status` **200** healthy (`maintenance.active=false`), frontend **200** — deploy SHA still not exposed |

**Verdict:** Acceptance is green end-to-end on the real app with both deterministic and live-Groq paths. Remaining items are owner-side (Gemini key re-mint, Render redeploy confirmation) — see **P**.

---

## B. Objectives & Scope

**North star:** prove with the running product that a teacher can go from a real PDF scheme to governed lesson plans — right indicator, honest quotas, enforced entitlements, real exports — through providers that actually work; any engine weakness found along the way gets fixed in the engine, not papered over in the UI.

In scope delivered this phase:
1. **17A** environment record (keys presence-only, models, modes, CORS, DB, Ollama).
2. **17B** Gemini live auth: probe all surfaces, diagnose honestly, rename the misleading diagnostic.
3. **17C** Groq live: diagnose retired default model, fix `GROQ_MODEL`, land a passing live test.
4. **17D** provider parity across subjects (OFF/llama3.1/gemma3:4b/groq; Gemini blocked rows recorded).
5. **17E** end-to-end teacher journey through the real UI (signup → upload → confirm subject → approve → generate → export → lessons).
6. **17F** allocation integrity inside that journey (one indicator → one period → one lesson; preview truthfulness).
7. **17G** free-tier behavior: 5 lesson units/calendar month (idempotent, atomic, hard-capped) and 5 lifetime AI credits (consume only on real AI success).
8. **17H** export validation (DOCX/XLSX/PDF/ZIP) including entitlement gating — the active-path ZIP bypass was found and fixed here.
9. **17I** 20-lesson review for identity/contamination.
10. **17J** boilerplate/quality audit with engine fixes (dropped-`e` verbs, `"use"`, activity dedupe, duration fit) — **no thresholds lowered, no checks deleted**.
11. **17K** failure-safety evidence (existing hardening suite + real live incidents).
12. **17L** observability audit (structured logging, no secrets in logs).
13. **17M** live Render verification; **17N** whole-suite regression; **17O** this report.

Out of scope / frozen: dashboard/billing/branding/admin work; payment/product decisions; export document structure redesign.

---

## C. Architecture — Teacher Journey + Provider Resolution (as exercised)

```
/signup (server-validated identity)
  → /upload (PDF/DOCX; multi-subject confirmation gate)
  → /review/{scheme_id} ("Approve & Configure")
  → /generate/{scheme_id}
      Preview Allocation → quota line (server-authoritative) + pre-select = remaining
      Confirm & Generate → POST /api/generation/{id}/generate
          order: identity resolve → require_ai_entitlement → create_job
                 → delete+reserve lesson units → pipeline → consume AI credit
          provider: job ai_mode × global AI_MODE pin
            OFF job      → deterministic builder (never a provider call)
            ENHANCED job + pin OFF      → auto order → gemini (key present)
                                          → 401 auth_key_rejected → per-lesson
                                            deterministic fallback, NO credit burned
            ENHANCED job + pin named    → that provider (Run B: AI_MODE=groq)
  → job lessons (ai_generated true/false per enrichment success)
  → exports via POST .../download-url (one-time token) → GET .../downloads/{token}
      DOCX / XLSX / PDF ungated for Free Tier; ZIP gated (can_export_zip → 403)
  → /lessons list + /lessons/{id} detail
```

Entitlement facts verified live: lesson quota **5/calendar month** (atomic ledger, idempotent per `(scheme_id, indicator_code)`, failures release units, pre-check before job creation); AI credits **5 lifetime** (`require_ai_entitlement` runs **before** quota pre-check; consumed **only** when `ai_mode != OFF AND ai_enrichment_succeeded > 0`).

---

## D. Provider Validation — Environment, Gemini, Groq, Parity (17A / 17B / 17C / 17D)

### D.1 Environment (17A, presence-only)
| Item | Value |
|------|-------|
| `GEMINI_API_KEY` | present — **rejected live** (`LIVE_AUTH_FAILURE`) |
| `GEMINI_MODEL` | `gemini-2.5-flash` (unchanged; do not downgrade) |
| `GROQ_API_KEY` | present (56 chars; value never printed) |
| `GROQ_MODEL` | now `openai/gpt-oss-20b` (was retired `llama-3.3-70b-versatile`; recorded as `env.groq_model_previous`) |
| `AI_MODE` | `OFF` (Run B temporarily `groq`, restored `OFF` and verified via `get_settings().AI_MODE`) |
| DB / CORS / PORT | `sqlite` / includes `http://localhost:3000` / 8000 |
| Ollama (host) | `llama3.1:latest` reliable; `gemma3:4b` flaky (`empty_response`/`malformed_json`); `qwen3:8b` times out |
| Shell-env tokens (`ANTHROPIC_AUTH_TOKEN`, `CLOUDFLARE_API_TOKEN`) | present but **no providers exist for them — out of scope** |

`src/config.py` calls `load_dotenv(override=False)` at import, so `.env` values (including `GROQ_MODEL`) reach `os.environ` and the provider layer.

### D.2 Gemini (17B) — honest failure, diagnostic corrected
Every live probe surface returns **401 `ACCESS_TOKEN_TYPE_UNSUPPORTED`** → `last_error="auth_key_rejected"` → `provider_status = LIVE_AUTH_FAILURE` (probe recorded into the acceptance artifact, ~0.6s). Phase 16's interpretation ("key *format* unsupported — mint a legacy standard key") was **wrong**: Google's current AI-Studio authorization keys ARE the supported credential via `x-goog-api-key`; a 401 means *this key string was rejected* (invalid/truncated/expired/scoped elsewhere). The code comment and diagnostic were renamed `auth_key_type_unsupported` → `auth_key_rejected` (status mapping updated) so the owner action is unambiguous: **verify or re-mint the key in AI Studio, restricted to the Gemini API**. Test `test_auth_key_rejected_diagnostic_not_format_unsupported` locks the new contract. `TestLiveGemini` skips `auth_key_rejected` (expected, honest).

### D.3 Groq (17C) — fixed and live
Root cause: default `llama-3.3-70b-versatile` was retired (shutdown 2026-08-16). Fixes: `src/config.py` default → `openai/gpt-oss-20b`; `backend/.env.example` → same; local `backend/.env` `GROQ_MODEL` line rewritten in place (UTF-8, no BOM); `TestLiveGroq` skip list extended with `model_not_found`/`http_404` and a clearer blocked message (no test pins the retired model). Result: **`TestLiveGroq::test_one_indicator_structured_generation` passes live (3.61s, real generation)**; `providers.groq = {key: true, model: openai/gpt-oss-20b, status: CONFIGURED, probe_ok: true}`.

### D.4 Provider parity (17D) — 3 runnable providers, identity-identical
Parity legs ran the production prompt/gate path per subject with deterministic recovery (`rate_limit` → 70s backoff, recorded honestly; clean legs skipped on re-run).

| Subject | Mean gate score | `llama3.1` identity | `gemma3:4b` identity | `groq` identity |
|---------|-----------------|---------------------|----------------------|-----------------|
| Mathematics | **98.8** | ✓ | ✓ | ✓ |
| Science | **98.8** | ✓ | ✓ | ✓ |
| Social Studies | **100.0** | ✓ | ✓ | ✓ |

All three providers: `identity_identical: true`. Gemini legs remain **BLOCKED rows only** (key rejected) — recorded as blocked, never faked. Set of 20 indicators: **20/20, 0 contaminated**.

---

## E. End-to-End Teacher Journey (17E / 17G / 17H)

Harness: `frontend/e2e/phase17-teacher-journey.js` (committed; `npm run e2e:phase17:chrome|edge`). Fresh unique teacher per run, real Chromium against local Next (3000) + uvicorn (8000), responses/payloads captured by counter, results written to `backend/temp/phase17_e2e_{A,B}.json`.

### E.1 Run A — `AI_MODE=OFF` (auto → Gemini 401 → deterministic fallback): **34/34**
Narrative highlights: signup → baseline `0 of 5` + credits `5/0`; B7 PDF upload → multi-subject confirmation → Science (17 indicators) → approve; ENHANCED pre-selects exactly remaining (5 of 17); single-indicator generate consumes **1** unit with `ai_credits_remaining=null` (fallback, credit untouched) and `ai_generated=[false]`; idempotent regen of same code keeps `used=1`; +4 distinct units → `4 of 5`; swap in distinct 5th → **5 of 5, 0 remaining**; DOCX (38380 B) / XLSX (5454 B) / PDF (88106 B, real `%PDF`) all reach disk; **ZIP → controlled "ZIP export is available with Teacher Pro"** (see G); lessons list (7 rows) + detail (`Week 1 • Lesson 1`, curriculum context, plan); exhaustion UI disables **all 17** checkboxes + Generate; API replay of a generate POST → **403** with the teacher-facing quota message; final ledger `used=5, remaining=0`; **credits still 0 used**; no page exceptions, no unexpected failing requests.

Harness fixes made along the way (test-side, not product): React pre-hydration click caused a native form GET (`/signup/`) — added `waitForHydration`; log-launch durability — servers now started detached via direct binaries.

### E.2 Run B — `AI_MODE=groq` (live AI credit lifecycle): **21/21**
Sequence after backend restart with `.env AI_MODE=groq` (settings verified `AI_MODE=groq`, `GROQ_MODEL=openai/gpt-oss-20b`):
- Gen 1 (ENHANCED, 1 indicator): live Groq, `ai_generated=[true]`, unit 1, credits **5 → 4**.
- Regens 2–5: credits **4 → 3 → 2 → 1 → 0** (`seq=[4,3,2,1,0]`, `paced_retries=1`).
- 6th ENHANCED: **403** before any job creation — "You've used all 5 free AI generations included with the Free Tier. This is a one-time lifetime allowance…"; ledger exactly **5/5 used**.
- OFF after exhaustion still generates (unit stays 1 — same indicator idempotent; credits untouched/null).
- DOCX export from the OFF job reaches disk (38367 B).

**Honest first attempt:** the initial Run B burst produced `seq=[4,3,2,null,null]` — Groq's free tier allows ≈3 requests per ~60s window (logs: three `ai_generation_consumed` events 4s apart, then enrichment attempts with **no consume** — deterministic fallback, **no credit burned**, exactly the designed honesty). The harness was given a 70s pace-retry; the successful run needed exactly one retry. This is free-tier rate limiting, correctly absorbed by the engine, not a code defect.

Known UI quirk observed during recon (documented, not "fixed" — secondary UI polish is out of scope): after a failed generate the panel can sit with `allocationConfirmed=true`/`jobId=null` (empty state); a reload recovers; page-load with a completed job shows "Start New Generation" first.

---

## F. Allocation Integrity (17F)

Inside the live journey: Preview Allocation always renders the **server-authoritative** quota line; the scheme reports "17 instructional indicators" for confirmed Science (one indicator → one selectable unit); selecting N indicators and generating yields exactly the lessons for those codes (1 code → 1 lesson; 4 codes → 4 lessons); pre-select tracks `remaining` exactly (5 → 4 → 1); swapping codes moves units only for distinct codes. Allocation engine behavior (carry-forward, duplication guards) remains covered by its existing suite inside the full run (K).

---

## G. Export Validation & Entitlement Gating (17H)

| Format | Run A result | Gate |
|--------|--------------|------|
| DOCX | 38380 B, `PK` container | none (Free Tier allowed) |
| XLSX register | 5454 B, `PK` container | none |
| PDF | 88106 B, real `%PDF` | none (converter present; controlled 503/converter message still the contract when absent) |
| ZIP | **403 controlled message** after fix | `can_export_zip` → "ZIP export is available with Teacher Pro." |

**Defect found and fixed (this phase's biggest catch):** the UI's export buttons all go through `POST /{job_id}/download-url`, but `can_export_zip` was enforced **only** on the legacy `POST /{job_id}/export/zip` route. Free Tier therefore received a **real ZIP** through the active path (verified: `download-url?format=zip` → 200 → token served the 36 KB archive). The gate now runs in `issue_download_url` for `fmt == "zip"` **before any render work**; two tests lock it (`test_zip_download_url_is_pro_gated_for_free_tier` — render must not even run; `test_zip_download_url_issues_token_for_pro_tier`).

Same audit pass restored **legacy-vs-active-path parity**: `/download-url` zip now passes `structure=` + term `context=` (custom template structure was silently ignored on the UI path), and docx honours the custom-structure branch (`export_docx_combined_custom` + term/period render context) exactly like the legacy route. PDF/XLSX paths already matched legacy.

**Environmental note:** Internet Download Manager (`IDMan.exe`) was running on the test host and intercepts `.zip` downloads — it re-GETs the single-use token (observed six `404`s after the first `200`). The app's single-use-token design absorbs this (and is why the entitlement gate must return **403 before issuing a token**). After the fix, Free Tier never reaches a token.

---

## H. 20-Lesson Review & Boilerplate/Quality Audit (17I / 17J)

### H.1 20-lesson review (17I)
Across the parity/recovery set: **20/20 produced lessons preserved exact indicator identity** (`lesson_identity` subject/class/strand/sub-strand/code+text verbatim), **0 contaminated** (no cross-indicator leakage). Sample lesson captured in `backend/temp/phase17_inspect_lesson.json`.

### H.1 Quality-gate audit → engine fixes (17J)
Recurring weaknesses were classified; **no thresholds lowered, no checks deleted**:

| Finding | Class | Fix |
|---------|-------|-----|
| `Objective may lack measurable verb` for **dropped-`e`** forms (`used`, `using`, `stated`, … of e-ending verbs like `use`) | detector gap | `_verb_pattern` now accepts `word+inflection` **or** `word-without-e + (ing\|ed)` for e-ending verbs |
| `"use"` missing from `_MEASURABLE_VERBS` | coverage gap | added `"use"` (whole-word matching from Phase 16 retained) |
| Duplicate activity descriptions trip the boilerplate warning | model noise | `_dedupe_activities` — whitespace/case-insensitive keep-first, **learner/main lists only**, never merges distinct texts |
| Phase durations can exceed the lesson budget (e.g. 80 min of activities in a 45-min lesson → impossible timetable) | model noise | `_fit_activity_durations` — runs **only** when the sum exceeds the budget; proportional integer redistribution via the deterministic builder's `_distribute`; within-budget durations untouched |
| Coherence-overlap WARNs (objective/activity/assessment keyword overlap) | **genuine model-content signal** | kept as warnings — the gate working as designed; not suppressed |

Regression tests added: `test_dropped_e_and_use_objectives_are_measurable`; `test_apply_v2_fits_oversized_durations_to_budget`; `test_apply_v2_keeps_within_budget_durations_untouched`; `test_apply_v2_dedupes_duplicate_activity_descriptions`. **No SYSTEM_PROMPT changes.**

---

## I. Failure Safety (17K)

- Suite: `tests/test_ai_failure_hardening.py` → **19 passed** (empty/malformed/schema-invalid raise in the parser; providers diagnose without raising; enrichment failure never counts as success; deterministic fallback preserves output).
- Real live incidents this phase (not synthetic): Ollama `gemma3:4b` `empty_response` / `malformed_json` (recorded in parity runs); **Groq `rate_limit`** — first Run B burst: 3 successes then failed enrichment with **no credit consumed** (`seq=[4,3,2,null,null]`), engine produced deterministic lessons, teacher journey kept working; parity harness absorbed the same class with 70s backoff.
- Entitlement ordering guarantee re-proven live: exhausted AI → 403 **before** job creation/quota reservation (no orphan jobs, no unit leakage).

---

## J. Observability (17L)

- `src/logging_config.py`: structlog JSON renderer, ISO timestamps, levels; `log_event` / `log_error` / `log_security` audit helpers — no key material in any call signature.
- Live structured events observed during acceptance: `ai_generation_consumed` (with `remaining`), `individual_teacher_registered`, `custom_template_export`, `pdf_export_unavailable`, provider `AI enrichment using provider=… (ai_mode=…)` lines — all key-free.
- Source scan: no key literals (`gsk_` / `AQ…` / `sk-proj-`) — only `_env("…_API_KEY")` lookups; `TestSecretHygiene::test_no_api_key_literals_in_source` green; `.env` confirmed gitignored (`git check-ignore`).
- Runtime-log secret-pattern scan: post-restart logs **0 hits**. One earlier ad-hoc match was observed immediately before a log-rotating restart and could not be re-verified; its most plausible explanation is the loose `AQ{20,}` alternation matching an access-log download-token path (`token_urlsafe(32)` can start `AQ…`), not a key leak — the source-hygiene test remains the authoritative control.

---

## K. Whole-Suite Regression (17N)

Full backend suite: **1096 passed, 10 skipped, 0 failed** (201.12s). Delta vs Phase 16 (1088/11): +7 new tests (diagnostic rename, measurable dropped-`e`, 3× duration/dedupe, 2× zip gate) + `TestLiveGroq` moved skip → live pass. Notable targeted runs during the phase: `test_final_web_ux.py` **27 passed**, `test_ai_failure_hardening.py` **19 passed**, quality-gate/V2-integration batch **189 passed**.

---

## L. Free-Tier & Entitlement Regression

Lesson quota: 5/calendar month, server-authoritative, atomic, idempotent per indicator, failures release — replayed live in Run A (`0→1→4→5`, distinct-code swap, exhaustion hard-cap, API 403). AI credits: 5 **lifetime**, consumed only on real enrichment success (Run B `[4,3,2,1,0]`), untouched by fallback (Run A), 403 message on exhaustion, OFF path never consumes. ZIP entitlement now enforced on **both** export routes (G). Payment/quota unit suites (`test_payment`, `test_monthly_quota`, entitlement tests) green inside the full run.

---

## M. Security Re-Scan

- No `.env`/key files tracked (`git ls-files` clean of secrets; `.env` + `backend/temp/*.json` gitignored).
- No hardcoded provider key patterns in `src` (hygiene test green).
- Download tokens: single-use, user-bound, 120s TTL, opaque (≥32 chars, no path/job leakage) — re-proven by the existing token tests plus the ZIP-gate ordering (403 before token issuance).
- Security/public-entry/export suites green inside the full run (Phase 16's 110-test set included).

---

## N. Validation Gate (17N)

| Check | Result |
|-------|--------|
| Full backend pytest | **1096 passed, 10 skipped, 0 failed** |
| `npx tsc --noEmit` (frontend) | exit 0 |
| `npm run build` (frontend) | exit 0 |
| Backend startup | local `/api/service-status` 200 healthy, v1.0.5; `AI_MODE=OFF` restored |
| Teacher journey E2E | Run A **34/34**, Run B **21/21** |

---

## O. Live Render Verification (17M)

Probed immediately after pushing `60fe769` (no cold-start 503 this time):

| Endpoint | Result |
|----------|--------|
| `https://schemeknit-api.onrender.com/api/health` | **200** `{"status":"healthy","service":"SchemeKnit","version":"1.0.5"}` |
| `https://schemeknit-api.onrender.com/api/service-status` | **200** healthy, `maintenance.active=false` |
| `https://schemeknit-frontend.onrender.com` | **200** (app HTML) |

Render does not expose the deployed commit SHA. Whether the live build already includes `60fe769` is **unverified** — not assumed.

---

## P. Blockers & Owner Actions

| # | Item | Status / Action |
|---|------|-----------------|
| 1 | `GEMINI_API_KEY` rejected live (`auth_key_rejected` → `LIVE_AUTH_FAILURE`) | Owner: verify/re-mint in **AI Studio, restricted to Gemini API**; then Gemini parity legs + live test unblock. Code/diagnostic already correct. |
| 2 | Render deploy SHA not exposed | Owner: confirm a fresh deploy after `60fe769`/report push and re-check `/api/health`; this report marks live currency as *unverified*. |
| 3 | Groq free tier ≈3 requests/~60s window | Operating guidance (not a code defect): pace rapid ENHANCED regenerations (~70s apart); the engine already falls back deterministically and never burns a credit on failure (proved in Run B). |
| 4 | IDMan intercepts ZIP downloads on some hosts | Environmental; app behaviour (403 before token for Free Tier; single-use tokens) is correct. Pro users with IDM get IDM-managed downloads by design (PART 27/28). |

Resolved this phase: **retired Groq default model** (fixed to `openai/gpt-oss-20b`, live test passing); **ZIP entitlement bypass on the UI path** (gate + parity fixes + tests).

---

## Q. Evidence & Artifacts

- `backend/temp/phase17_acceptance_results.json` — 17B/C/D/I/J/K evidence: provider probes/statuses (Gemini `LIVE_AUTH_FAILURE`, Groq `CONFIGURED/probe_ok`), parity matrix + `identity_identical`, set20 20/20, `env.groq_model_previous=retired`.
- `backend/temp/phase17_e2e_A.json` — Run A, 34/34 checks, payloads/quota/credit timeline.
- `backend/temp/phase17_e2e_B.json` — Run B, 21/21 checks, `paced_retries`, credit ledger.
- `backend/temp/phase17_inspect_lesson.json` — lesson sample; `backend/temp/ba/downloads/` — real exported artifacts.
- Server logs: `backend/temp/uvicorn_{out,err}.log`, `next_dev_{out,err}.log`.
- Tests changed: `test_curriculum_v2.py`, `test_generation_v2_integration.py`, `test_final_web_ux.py`, `test_gemini_groq_providers.py`.
- Source changed: `src/curriculum/quality_gate.py`, `src/engines/generation_pipeline.py`, `src/routers/generation.py`, `src/engines/ai_provider.py`, `src/config.py`, `backend/.env.example`.
- Harness (committed): `frontend/e2e/phase17-teacher-journey.js` + `e2e:phase17:*` npm scripts. Temp phase scripts deleted before commit.
- Commit: `60fe769` (engine + gate + provider fixes + tests + harness), pushed to `main`.

---

## R. Verdict

**PRODUCTION PROVIDER VALIDATION + END-TO-END TEACHER ACCEPTANCE is complete and green.** Groq is live-proven through the real app with an honest 5-lifetime-credit lifecycle; the deterministic survival path, atomic 5/month quota, idempotent regeneration, exhaustion hard-caps, and all four export formats were exercised in a real browser and all passed (34/34 + 21/21). The audit found and fixed four genuine engine/entitlement defects (dropped-`e` measurable verbs, `"use"` coverage, activity dedupe/duration fit, and the **ZIP Pro-gate bypass on the active download-url path** plus its legacy-parity gaps), with regression tests for each. Gemini remains honestly blocked on a rejected key (owner re-mint), and Render's deploy SHA remains unverifiable (owner confirm) — neither is a code blocker.
