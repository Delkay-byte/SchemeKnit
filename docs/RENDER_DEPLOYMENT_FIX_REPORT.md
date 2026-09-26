# Render Deployment Fix — Dependency Conflict Report

**Date:** 2026-09-26
**Trigger:** Render build failed in `cd backend && pip install -r requirements.txt`
with `ResolutionImpossible`, because `httpx==0.27.2` conflicts with
`google-genai==2.25.0` (requires `httpx>=0.28.1,<1.0.0`).
**Verdict:** FIXED — clean-environment install of `backend/requirements.txt`
succeeds with `pip check` clean; backend suite 1377 passed / 12 skipped;
all 14 frontend regression gates green.

---

## 1. Dependency-graph inspection (before editing)

Repo-wide search results for `httpx==`, `httpx>=`, `httpx<`, `import httpx`:

| Location | Finding |
|---|---|
| `backend/requirements.txt:42` | `httpx==0.27.2` — **the conflicted pin** (comment: "HTTP client (for AI providers)"; pinned since the original public-preview deploy, no version-specific rationale) |
| `desktop/build-requirements.txt:38` | `httpx==0.27.2` — desktop package set contains **no** `google-genai`, so no conflict there; left unchanged |
| `backend/src/email_service.py:39,89` | Only direct source usage: `httpx.Client(timeout=30.0)` — a stable API across 0.27 → 0.28 |
| `backend/tests/test_gemini_groq_providers.py:223` | Uses `httpx.ConnectTimeout` (exists in 0.28.1; SDK surfaces transport errors as httpx types) |
| `backend/tests/test_real_ai_provider.py:10` | `import httpx` (live-provider guards) |
| Lock files / render.yaml / Procfile / Dockerfile | **None exist** — Render resolves directly from `requirements.txt`, no other httpx pin anywhere in deployment config |

## 2. Second conflict discovered (clean-env test, as anticipated)

With `httpx==0.28.1` the first conflict cleared, but the mandatory clean-environment
install immediately exposed a **second genuine conflict**:

    google-genai 2.25.0 depends on pydantic<3.0.0 and >=2.12.5
    pydantic==2.9.2 (pinned)  →  ResolutionImpossible

Root cause of the miss: the local `backend/venv` had **drifted** from
`requirements.txt` during the Gemini phase — it already ran
`httpx 0.28.1`, `pydantic 2.13.5`, `pydantic-settings 2.15.0` (pip upgraded
transitives when `google-genai` was installed), while `requirements.txt` still
claimed `0.27.2` / `2.9.2` / `2.5.2`. All prior test runs therefore passed in an
environment the deployment file could not reproduce — precisely the
"accidental local environment" failure mode. No lock file existed to catch the drift.

## 3. Final change (smallest safe, deterministic pins)

`backend/requirements.txt` — exactly two pins, nothing else touched:

| Pin | Before | After | Why |
|---|---|---|---|
| `httpx` | `==0.27.2` | **`==0.28.1`** | Minimum version satisfying `google-genai`'s `httpx>=0.28.1,<1.0.0`; also the exact version the existing suites were validated against; exact pin keeps the file deterministic |
| `pydantic` | `==2.9.2` | **`==2.13.5`** | Minimum for `google-genai` is `>=2.12.5`; `2.13.5` is the exact version every prior suite ran green on (tested, not merely minimum-untested); compatible with `fastapi 0.141.1` (`pydantic>=2.9.0`) and `pydantic-settings 2.5.2` (`pydantic>=2.7.0`) |

Deliberately **not** changed:

- `google-genai==2.25.0` — kept (no downgrade to preserve old pins).
- `pydantic-settings==2.5.2` — pip-compatible with pydantic 2.13.5; avoided an
  unnecessary upgrade; the clean-env full suite (below) proves the combination
  `pydantic 2.13.5 + pydantic-settings 2.5.2` is green.
- No other package upgraded; no `--no-deps`, no `--break-system-packages`;
  application code untouched (dependency-only remediation).
- `desktop/build-requirements.txt` — no conflict there (no `google-genai`).

## 4. Clean-environment install (Render-faithful) — PASS

Fresh venv (created from system Python 3.13.13; Render's Python 3.11 pin lives in
its dashboard, not the repo — dependency resolution is identical for these wheels),
then the exact deployment command:

    python -m venv <fresh> && <fresh>/python -m pip install -r backend/requirements.txt
    → exit 0, "Successfully installed … httpx-0.28.1 … pydantic-2.13.5 … google-genai-2.25.0 …"

| Check | Result |
|---|---|
| `pip install -r requirements.txt` (clean venv, pip 26.0.1) | **SUCCESS**, no `ResolutionImpossible` |
| `pip check` | **"No broken requirements found"** (exit 0) |
| `httpx` version | `0.28.1` — satisfies `>=0.28.1,<1.0.0` |
| `google-genai` version | `2.25.0` |
| `import google.genai` | **OK** |
| `from src.engines.ai_provider import GeminiProvider` | **OK** |
| Isolation proof | `sys.prefix` = clean venv; `httpx`/`pydantic` loaded from venv `site-packages` (no shared/local state) |

## 5. Backend startup from the clean environment — PASS

The local `:8000` API was restarted using **the clean-env interpreter** and the
normal production-style command (`python run.py --host 127.0.0.1 --port 8000`):

- log: `SchemeKnit started`, `GET /api/health → 200`
- `{"status":"healthy","service":"SchemeKnit","version":"1.0.5"}`

All frontend gates below then ran against this deployment-faithful backend.

## 6. Backend tests (clean env) — PASS

Full suite executed **inside the clean venv**:

    1377 passed, 12 skipped (313s) — identical to the pre-change baseline (1377/12)

Zero failures, no new skips. Covers Gemini provider tests (client init, model
config, structured output, malformed response, timeout/retry, auth errors,
model-access diagnostics), auth/session, WAPEF, KG, Nursery, Basic 1–3,
generation, export, and the httpx-touching HTTP/integration tests
(`test_web_acceptance_http`, provider transport tests). No test was weakened.

## 7. httpx 0.27.2 → 0.28.1 compatibility — PASS

- Only direct usage is `httpx.Client(timeout=30.0)` + standard request methods
  (`email_service.py`) — no removed-argument APIs (`proxies=`, `app=`) in use.
- `httpx.ConnectTimeout` and friends used by tests exist unchanged in 0.28.1.
- `google-genai`'s own transport is 0.28-compatible by declared requirement.
- Empirically: the entire backend suite plus all gates ran green **on httpx
  0.28.1** (both in the pre-existing drifted venv and the new clean venv).

## 8. Frontend / full regression (against the clean-env backend) — PASS

| Gate | Result |
|---|---|
| `npx tsc --noEmit` | exit 0 |
| `npm run build` | exit 0 |
| app-ui | 53/0 |
| app-chrome | 72/0 |
| app-surfaces | 109/0 |
| app-closure | 94/0 |
| login-grid | 476/0 |
| deep-journey | 21/0 |
| download (bundled) | 14/14 |
| tab-isolated-auth | 43/43 |
| Basic 1–3 acceptance | 55/0 |
| WAPEF acceptance | 32/0 |
| KG acceptance | 31/0 |
| Nursery acceptance | 130/0 |
| hero-v3 (at `:3999`) | 151/0 |
| auth-role-design (at `:3999`) | 131/0 |

## 9. Deployment relationship (documented)

    google-genai==2.25.0
      ├─ requires httpx >=0.28.1,<1.0.0   → requirements pin httpx==0.28.1
      ├─ requires pydantic >=2.12.5,<3.0  → requirements pin pydantic==2.13.5
      └─ (pydantic-settings 2.5.2 only needs pydantic>=2.7.0 → unchanged)

    fastapi==0.141.1  requires pydantic>=2.9.0        → satisfied by 2.13.5
    pydantic-settings==2.5.2 requires pydantic>=2.7.0 → satisfied by 2.13.5

## 10. Live Render verification

- Pre-push probe of `https://schemeknit-api.onrender.com/api/health` timed out
  (cold/starting service at probe time).
- The fix was pushed to `origin/main` (`7796f31` + `ae57e5b`); Render rebuilds by
  running the same `pip install -r requirements.txt` that now succeeds in the
  clean local environment (§4) — the exact failure point is reproduced and fixed.
- Post-push probes (both successful):
  - `GET https://schemeknit-api.onrender.com/api/health` → **200**
    `{"status":"healthy","service":"SchemeKnit","version":"1.0.5"}`
  - `GET https://schemeknit-api.onrender.com/api/service-status` → **200**
    healthy, `maintenance.active=false`
  - `GET https://schemeknit-frontend.onrender.com` → **200** (app HTML)
- **ENVIRONMENT LIMITATION:** no Render deploy hook exists in the repo or
  `.env`, and Render dashboard access is not available from this environment,
  so a fresh deployment cannot be triggered programmatically here — the redeploy
  must be triggered/confirmed from the Render dashboard (owner-side), same as in
  earlier phase reports. Deploy SHA is not exposed by any endpoint, so
  commit-level currency of the running build cannot be asserted from outside;
  the honest signals available are: push landed on `main`, the exact build
  step now passes in a faithful clean environment, and the live service reports
  healthy with maintenance off.

## 11. Files changed

| File | Change |
|---|---|
| `backend/requirements.txt` | `pydantic==2.9.2 → 2.13.5`, `httpx==0.27.2 → 0.28.1` (+ comment noting the google-genai constraint) |

No application code, tests, frontend, database, or auth/session/Gemini logic
modified.
