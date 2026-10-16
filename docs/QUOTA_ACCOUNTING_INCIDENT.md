# QUOTA ACCOUNTING INCIDENT — Production Free Tier Counter (October 2026)

**Incident:** production accepted **6 distinct Free Tier lessons against the
monthly limit of 5** while every quota read returned `used=0`.
**Status:** root cause **identified, reproduced, and fixed** in `70738f8`;
pending deployment to production and owner-side verification.
**Detected:** 2026-10-09 during final production smoke (docs commit `51b7987`).
**Severity:** P1 — RED/NO-GO criterion (Free Tier cap unenforceable).

---

## 1) Impact

- Account `smoke-eec8aa17@example.com` (Free Tier) generated **6 accepted
  distinct lessons** in period `2026-10` against `limit=5`; enforcement never
  bound (no 403 at the 6th distinct code).
- Every server-side quota read returned `used=0, remaining=5`: `/quota`,
  `/auth/my-plan`, generate responses, and the Autopilot plan (which kept
  selecting 5 every time).
- The counter could never increment for **any** production user — the Free
  Tier monthly cap was silently unenforceable for the whole deployed build.
- No data loss, no billing impact (Free Tier), no security impact. P4 quality
  gate behaviour was unaffected (gate rejections still persisted nothing).
- Timeline: 2026-10-08/09 smoke discovered the defect (documented, NO-GO);
  2026-10-09 forensic task → root cause reproduced on the production stack →
  fix + regression suite committed as `70738f8`.

## 2) Evidence (from the affected account, read-only)

Latest read-only verification (2026-10-09, no lessons generated):

- `GET /auth/me` → `id=c11bde4c-a9bb-4f41-b96a-921570cf856e`,
  `school_id=null`, `subscription_type=individual`, `role=teacher`.
- `GET /auth/my-plan` → `plan_name="Free Tier"`, `generation_limit=5`,
  `lesson_quota_limit=5`, `lesson_quota_period="calendar_month"`,
  `lesson_quota_period_key="2026-10"`, `lesson_quota_remaining=5`,
  `generations_used=0`, `lesson_quota_unlimited=false`.
- `GET /generation/quota` → `enforced=true, limit=5, used=0, remaining=5,
  period_type=calendar_month, period_key=2026-10, unit=lesson_plan`
  (no `Cache-Control` header observed on this read).
- `GET /generation/schemes/ab28233d-f87c-4753-98c1-fbb94acead7f/lessons`
  → **6 persisted lessons** (accepted codes), rejected code absent.

Prior smoke evidence: generate responses embedded the same `used=0`;
`generation_completed` log events carry `quota_used=N` (owner-side log,
requested — see §4).

## 3) Scope

- **Code defect**, one function: `backend/src/usage_quota.py` —
  affects every production user on the deployed build, every calendar month.
- Not a data-only issue (the anomaly re-derives deterministically from code +
  driver — reproduction below). Not an AI-quota issue: `ai_quota.py` uses the
  guarded **UPDATE** `rowcount`, which psycopg3 reports correctly (verified by
  running the AI suite against PostgreSQL — 27 passed).
- Not frontend, not migration, not deployment-config: `main.py` runs the
  migration runner and `validate_production()` (PostgreSQL required) before
  serving; `v020_usage_periods.py` created both tables with the correct
  unique constraints.
- Production DB state implied by the defect (§7) but **not directly observed**
  — no production DB access (§4).

## 4) Evidence that was NOT available (owner-side requests)

No Render dashboard/log access, no production DB access, deployed SHA
unknown. Minimum owner-side evidence requested:

1. **Render logs**, filter `generation_completed` for user
   `c11bde4c-a9bb-4f41-b96a-921570cf856e`: `quota_used=0` on accepted runs
   proves server-side read of 0 (rules out response shaping).
2. **Read-only SQL** (see §12) on `usage_periods` / `usage_units` for that
   user — confirms the predicted state: period row `units_used=0` plus one
   unit row per reserved code (6 accepted + the gate-rejected code).
3. **Deployed commit SHA** from the Render dashboard, to pin the build
   the smoke exercised.
4. Post-deploy: confirm the redeployed SHA contains `70738f8`.

Until (1)–(3) are provided, production confirmation rests on the safe
functional check in §12 (no new lesson required).

## 5) Identity / period / entitlement verification (§5)

| Fact | Value | Source |
|---|---|---|
| User | `c11bde4c-a9bb-4f41-b96a-921570cf856e` (`smoke-eec8aa17@example.com`) | `GET /auth/me` |
| Scheme | `ab28233d-f87c-4753-98c1-fbb94acead7f` (Basic 9 Science) | journey record |
| Period | `calendar_month` / `2026-10`, server clock | `/quota`, `/my-plan` |
| Entitlement | Free Tier, individual, `school_id=null`, limit 5, enforced, not unlimited | `/my-plan` |
| Same identity across all operations | single bearer token for login→upload→generate→quota reads (JWT `sub` = user id) | smoke session |

## 6) Reconciliation table (evidence only — no new generations)

| # | Occurrence | Event | HTTP | Lesson persisted | Unit row (broken path) | Counter Δ |
|---|---|---|---|---|---|---|
| 1 | `week1:0:B9.1.1.1.1` | generate accepted | 200 | yes | inserted | 0 |
| 2 | `week2:0:B9.1.1.1.2` | accepted (incl. free regen) | 200 | yes (replaced in place) | inserted once; regen conflicted | 0 |
| 3 | `week2:1:B9.1.1.1.3` | accepted | 200 | yes | inserted | 0 |
| 4 | `week4:0:B9.1.2.1.1` | accepted | 200 | yes | inserted | 0 |
| 5 | `week4:1:B9.1.2.1.2` | accepted | 200 | yes | inserted | 0 |
| 6 | `week5:0:B9.1.2.1.3` | accepted | 200 | yes | inserted | 0 |
| 7 | `week3:0:B9.1.1.2.1` | quality-gate hard rejection (`generic_objective`), ≥2 attempts, deterministic | 500 | **no** | inserted on first attempt, **not released** (release only fires when `consumed>0`) | 0 |
| 8 | invalid occurrence id (early probe) | validation reject (before reserve) | 400 | no | none | 0 |

Totals: **6 accepted distinct** vs limit 5; **≥2 rejected** attempts (nothing
persisted); counter reads **0** on every observation. Expected under correct
code: 5 accepted, 6th `403`, `used=5`.

## 7) Root cause (evidenced — reproduced locally on the production stack)

`usage_quota._insert_ignore` executed
`INSERT … ON CONFLICT DO NOTHING` and the caller decided "did I insert?"
with `(res.rowcount or 0) == 1`.

On the production stack (**PostgreSQL + psycopg 3.3.5 + SQLAlchemy 2.0.35**),
SQLAlchemy's **Core** insert path reports **`rowcount == -1`** for that
statement — both on first insert and on conflict (−1 means "not reported"):

```
raw psycopg3      INSERT plain / conflict      -> 1 / 0   (correct)
SA text()         ON CONFLICT (conflict)       -> 0       (correct)
SA Core pg_insert ON CONFLICT (1st / conflict) -> -1 / -1 (broken path)
```

`-1 != 1` → `new_keys` stays empty → `new_count == 0` → the
`already_counted` branch runs: it **commits the unit rows** (the INSERTs
succeeded!) but **skips the guarded UPDATE** (`units_used + n <= limit`) that
both increments the counter and enforces the limit. Consequences, exactly as
observed in production:

- `used` stays 0 forever (all reads 0/5);
- the limit guard never executes → no request is ever refused → 6 accepted on
  a limit of 5;
- Autopilot/server always compute `remaining = 5` → keep selecting 5;
- gate-rejected reservations are never released (`consumed==0` skips the
  release branch) → unit rows accumulate without a counter.

**Local reproduction (pre-fix):** same `reserve_lesson_units` call on
PostgreSQL+psycopg3 → `allowed=True, consumed=0, reason='already_counted',
used=0`; the quota suite failed **9 of 12** tests on PG while passing on
SQLite (SQLite reports a truthful rowcount — which is why the local suite
never caught it). Direct probe printed `rowcount=-1`.

## 8) Hypotheses ruled out (with evidence)

| Hypothesis | Ruled out by |
|---|---|
| `gen_limit=0` / entitlement says unlimited | same-process `/quota` returned `enforced=true, limit=5`; `my-plan` limit 5 |
| Release path always firing (key mismatch) | release keys come from the same `lp.indicator_codes` as reserve keys; release only runs when `consumed>0` (never, under the defect) |
| Deployed build lacks the reserve block | deployed responses contain ae84f19-only gate markers (`quality` metrics, `generic_objective` text); `git show ae84f19:…/generation.py` has the reserve block; only branch `main` exists |
| DB data anomaly (rows pre-existing) alone | would require rows written by some other path; only `generation.py:1003` creates lessons, and the defect itself explains committed rows + counter 0 deterministically |
| Duplicate period rows / missing unique constraint | migration `v020` creates the unique constraint; a duplicate would make the INSERT conflict → 500s (journey returned 200s) |
| Missing tables / migration never ran | every generate + quota read returned 200 |
| Caching / response shaping | the counter is read server-side per request (Autopilot selection counts, generate body, `/quota` all agree); values reflect a server-side 0 |
| Empty `requested_codes` skipping reserve | occurrence selection resolves non-empty codes before reserve; rejected/invalid runs show the pre-check text with real counts |
| SQLite-only local artifact | production is PostgreSQL (`config.validate_production()` refuses sqlite at startup) — reproduced on PG |
| AI quota same defect | `ai_quota` checks only the guarded **UPDATE** rowcount (correct on PG); insert result is discarded; AI suite on PG: 27 passed |

## 9) Fix (committed `70738f8`)

`backend/src/usage_quota.py` — `_insert_ignore` now appends
`.returning(<pk>)` and returns a **bool** (`row present ⇔ row inserted`);
the caller uses that bool instead of `rowcount`. `RETURNING` is
driver-independent (verified on psycopg3, and on SQLite where the suite runs
by default). No second ledger, no policy change: idempotency
(`{scheme_id}:{indicator_code}`), occurrence identity (P1), the 403 pre-check,
gate rejection zero-charge, Autopilot caps, and P4 semantics are untouched.

## 10) Regression coverage (the 14 required cases → tests)

| # | Case | Test |
|---|---|---|
| 1 | five lessons permitted | `test_monthly_quota.py::test_generating_five_consumes_five_sixth_blocked`; journey `test_five_accepted_sixth_403_no_job_no_lesson_no_counter_move` |
| 2 | sixth rejected | same two tests (model `quota_exceeded`; endpoint **403**) |
| 3 | sixth creates no lesson | journey test (lesson list stays 5, occurrence absent, no job) |
| 4 | usage exactly 5 | journey (per-run body + `/quota` after each run) |
| 5 | Autopilot stops at exhaustion | `test_autopilot_generation.py::test_matrix_k…` + journey `test_autopilot_reports_quota_exhausted_after_single_generations` (real exhaustion) |
| 6 | failed generation consumes 0 | `test_quality_gate.py::test_total_rejection_fails_the_run_and_consumes_nothing` (now asserts counter 0, unit rows 0, `/quota` 0) + model release test |
| 7 | gate rejection charges 0, no replace | `test_partial_rejection_charges_accepted_only_and_releases_rejected` (new): rejected lesson absent, its unit released, accepted charged 1 |
| 8 | same-occurrence regeneration free | model `test_regeneration_of_same_indicator_is_free`; priority3 `…used == 1`; journey regen-while-remaining > 0 |
| 9 | repeated codes across weeks = 1 unit, 2 lessons | journey `test_two_occurrences_of_one_code_charge_one_unit` + matrix H |
| 10 | single vs Autopilot consistency | journey exhaustion test (singles) → Autopilot plan reports `quota_exhausted` |
| 11 | monthly boundary | model `test_next_calendar_month_resets_allowance` |
| 12 | read-after-write | journey (body vs `/quota` vs persisted lessons, every run) + PG `test_reserve_increments_and_reads_back_across_sessions` |
| 13 | concurrency | model `TestConcurrentQuota` (sqlite) + PG `test_concurrent_reservations_cannot_oversubscribe_on_postgres` (10 threads, real PG) |
| 14 | entitlement/identity scope | model `test_quota_is_isolated_between_users`; journey `test_quota_is_scoped_to_the_user_not_the_scheme` |

Plus the direct contract test:
`test_insert_ignore_reports_insert_then_duplicate` (True then False, exactly
one row) — the primitive that failed in production.

**Invariants A–I:** A=case 1/4, B=case 6/7, C=case 8/9 + journey regen,
D=case 9, E=case 2/3 (403 before job/persist), F=case 5/10, G=case 13,
H=case 12, I=case 7 (rejected lesson never replaces/persists).

**Production-stack gate:** `backend/tests/test_postgres_quota_driver.py`
runs only when `TEACHFLOW_TEST_DATABASE_URL` points at PostgreSQL (the
conftest-supported switch) and would have failed before the fix:

```
TEACHFLOW_TEST_DATABASE_URL="postgresql+psycopg://…" pytest tests/ -q
```

## 11) Local verification (2026-10-09, after `70738f8`)

- **Full backend suite (default SQLite):** `2374 passed, 15 skipped, 0 failed`
  (~23 min; the 2 `test_real_ai_provider` tests skip without API keys).
- **Targeted PostgreSQL runs** (SQLAlchemy 2.0.35 + psycopg 3.3.5, same
  versions as `requirements.txt`), executed serially:
  quota model 12 ✓, PG driver gate 4 ✓, endpoint journey 4 ✓, quality gate 2 ✓
  (+extended), priority3 workflow 8 ✓, autopilot 81 ✓, AI ledger 27 ✓.
- **Pre-fix baseline on PG:** quota model `9 failed, 3 passed` — now
  `12 passed`.
- Frontend: not affected (no frontend change; no run required).

## 12) Deployment and owner-side remediation (exact steps)

Deployment is an owner decision (read-only Render API status: §13c) — no
deploy has been triggered from this side:

1. **Deploy** commit `70738f8` (Render auto-deploy on push, or manual
   deploy). Confirm the dashboard SHA contains `70738f8`.
2. **Evidence (§4):** capture pre-deploy log lines + the SQL in step 4 for
   the incident record.
3. **Safe functional check** (no new lesson needed): regenerate an existing
   occurrence (e.g. `week1:0:B9.1.1.1.1`) → expect **200 with `used`
   unchanged** (idempotent free regen now reads the ledger correctly).
4. **Read-only verification SQL:**
   ```sql
   SELECT period_key, units_used FROM usage_periods
    WHERE user_id = 'c11bde4c-a9bb-4f41-b96a-921570cf856e'
      AND period_type = 'calendar_month';
   SELECT unit_key, created_at FROM usage_units
    WHERE user_id = 'c11bde4c-a9bb-4f41-b96a-921570cf856e'
    ORDER BY created_at;
   -- Expected on the broken build: period row units_used = 0,
   -- plus one unit row per reserved code (6 accepted + the rejected code).
   ```
5. **Counter remediation (owner decision — recommended for exactness):**
   without action the counter restarts from 0 and permits up to 5 MORE
   distinct lessons this month (self-heals 2026-11-01). **This §12 sketch is
   SUPERSEDED — do not execute it.** It relies on a broad `NOT EXISTS`
   predicate with no server-side guards. The authoritative, hardened
   proposals are §13e (incident account) and §13g (all other accounts),
   each with enforced preconditions, exact-row deletion, row-count
   enforcement and a guarded rollback.
   ```sql
   -- (a) drop the orphan unit row(s) whose lesson was gate-rejected/never persisted
   DELETE FROM usage_units u
    WHERE u.user_id = 'c11bde4c-a9bb-4f41-b96a-921570cf856e'
      AND u.period_type = 'calendar_month' AND u.period_key = '2026-10'
      AND NOT EXISTS (
        SELECT 1 FROM lesson_plans l
         WHERE l.scheme_id = u.scheme_id AND l.owner_id = u.user_id
           AND jsonb_exists(l.indicator_codes::jsonb, split_part(u.unit_key, ':', 2)));
   -- (b) recompute the aggregate from the unit ledger
   UPDATE usage_periods p
      SET units_used = (
        SELECT count(*) FROM usage_units u
         WHERE u.user_id = p.user_id AND u.period_type = p.period_type
           AND u.period_key = p.period_key)
    WHERE p.user_id = 'c11bde4c-a9bb-4f41-b96a-921570cf856e'
      AND p.period_type = 'calendar_month' AND p.period_key = '2026-10';
   -- Expected after backfill: units_used = 6 (over the limit of 5 → new
   -- distinct generations correctly blocked until 2026-11-01; regens free).
   ```
   Repeat for any other account that generated during the incident window
   (`SELECT user_id, count(*) FROM usage_units GROUP BY user_id;`).
6. **Prevention:** add a CI job (none exists in the repo today) that runs the
   suite twice — default SQLite **and**
   `TEACHFLOW_TEST_DATABASE_URL=postgresql+psycopg://…` (services:
   postgres:16) — so the production driver stack is exercised on every push.
   `tests/test_postgres_quota_driver.py` is the named gate.

## 13) Documentation updated (with this file)

- `docs/PRODUCTION_READINESS.md` — §5 rewritten (root cause + fix), §7
  NO-GO now scoped to "deploy + verify".
- `docs/PILOT_VALIDATION_REPORT.md` — quota finding updated from
  "unexplained divergence" to "root-caused code defect, fixed pending deploy".
- `docs/pilot/production-version.md` — same correction.
- This file: `docs/QUOTA_ACCOUNTING_INCIDENT.md`.

## 13b) Independent re-verification (2026-10-15)

Source-level and local-stack re-audit of the fix, outside the incident
session:

- **Source inspection** (`backend/src/usage_quota.py` @ `3ef1a41`):
  `_insert_ignore` detects insertion via `RETURNING` (driver-independent,
  `_pg_insert`/`_sqlite_insert` dialect split; `returns_rows` + `first()`
  guard), reservation counts only newly inserted keys, the guarded
  `units_used + n <= limit` UPDATE enforces the allowance atomically
  (`rowcount != 1` → rollback + `quota_exceeded`), release deletes per-unit
  rows and decrements under a non-negative guard. Failed and P4-rejected
  candidates consume nothing (release only fires when `consumed > 0`);
  a reservation whose unit row already exists charges 0
  (`already_counted`, `consumed == 0`).
  `ai_quota.py`'s ledger path (guarded-UPDATE rowcount) is untouched.
- **Local production-stack rerun** (fresh docker `postgres:16-alpine`,
  SQLAlchemy 2.0.35 + psycopg 3.3.5 = production driver versions):
  `tests/test_postgres_quota_driver.py` **4 passed** (incl. threading
  concurrency), `tests/test_monthly_quota.py` **12 passed**,
  `tests/test_quota_enforcement_journey.py` **6 passed**
  (5-permit/6th-refuse, read-after-write, Autopilot exhaustion,
  per-user scope, cross-week distinct codes, zero-charge release);
  `tests/test_ai_production.py` + `test_quality_gate.py` +
  `test_generation_quality_v3.py` **101 passed** on the same stack.
- **Production probe (read-only):** `GET /api/health` → 200
  `{"status":"healthy","version":"1.0.5"}` — but `APP_VERSION` is a static
  config string (`backend/src/config.py`), so this does NOT identify the
  deployed commit. No Render dashboard/log/DB access; the smoke account's
  token was never recorded, so the §12.3 safe functional check cannot be
  executed from this side. No production lessons generated (per instruction).
- **Conclusion:** fix verified in source and on the production driver stack
  locally; **incident remains OPEN in production** — deployed build still
  unconfirmed as containing `70738f8`. Owner-side steps step 1–5 unchanged;
  status remains RED/NO-GO until §12 is executed and verified.

## 13c) Production deployment status — established 2026-10-15 (Render API, read-only)

A Render API key was available in the engineering session, so the deployed
commit was established directly instead of left "unknown". Only read-only
API calls were made: no deploy triggered, no production writes, no lessons
generated.

- **Service:** `schemeknit-api` = `srv-damsbb1ntn7c73d7eg10`
  (`https://schemeknit-api.onrender.com`, repo `Delkay-byte/SchemeKnit`,
  branch `main`, `autoDeploy=yes`).
- **Live deploy:** `dep-db42gvp42hec73fhbu0g` — commit
  **`50bd8872e2fe73c5e4b459b37ab94bf233434e88`** ("docs: deployment
  activation …"), created `2026-10-08T23:34:23Z`, live since
  `2026-10-08T23:36:19Z`.
- **Verdict:** `50bd887` **predates the quota fix** `70738f8`
  (`2026-10-09T01:44:57Z`) and the incident report `3ef1a41`
  (`2026-10-09T01:48:14Z`). The deployed build does **not** contain the
  fix. It does contain `ae84f19` (P4 gate) and `3ac4480`; it predates
  `9d7e401`, `97a028f`, `2121a2c`, `51b7987`, `70738f8`, `3ef1a41` and the
  later Phase 1/Phase 2 engineering commits.
- **Auto-deploy did not fire:** the deploys list contains **no deploy
  created after `2026-10-08T23:36`**, yet GitHub reports the repo's last
  push at `2026-10-09T01:48:17Z` (the quota-fix push). The fix push
  produced no Render deploy at all — auto-deploy cannot be relied on here;
  a **manual deploy is required**.
- **No Render-hosted database:** the API's database listing is empty, so
  the production database is external to Render and its `usage_periods` /
  `usage_units` rows are not readable from this side. §12.4 (read-only
  SQL) and §12.5 (backfill) remain owner-side.
- **Read-only probe:** `GET https://schemeknit-api.onrender.com/api/health`
  → `200 {"status":"healthy","service":"SchemeKnit","version":"1.0.5"}`
  (after a cold start). `APP_VERSION` is a static config string, so this
  confirms liveness only — not the commit.
- **Historical evidence preserved:** the six accepted lessons with
  `used=0` for `c11bde4c-a9bb-4f41-b96a-921570cf856e` are untouched; no
  production lesson was generated and no row was edited.

**Conclusion — deployed build is stale:** status stays **RED / NO-GO**;
the incident is **not closed**. Owner-side action, in order:

1. Push current `main` (contains `70738f8` and everything since).
2. Trigger a **manual** deploy of `schemeknit-api` (dashboard "Manual
   Deploy", or `POST /v1/services/srv-damsbb1ntn7c73d7eg10/deploys`);
   do not wait for auto-deploy — it demonstrably did not fire.
3. Confirm the dashboard deploy SHA contains `70738f8`.
4. Run the §12.3 safe functional check (free regeneration of an existing
   occurrence → `used` unchanged).
5. Run the §12.4 read-only SQL, then the §12.5 backfill if the owner
   elects exact counter reconciliation.

## 13d) Deployment executed + verified (2026-10-15, owner-approved one-time deploy)

Owner authorization: one backend-only deployment of already-pushed
`origin/main` = `3ef1a41`, after a fresh PostgreSQL quota gate pass; no
local-only commits; no production lessons; no data modification.

- **Pre-deploy gate:** `TEACHFLOW_TEST_DATABASE_URL=postgresql+psycopg://…`
  against docker `postgres:16-alpine` (SQLAlchemy 2.0.52 + psycopg 3.3.5):
  `test_postgres_quota_driver.py` + `test_monthly_quota.py` +
  `test_quota_enforcement_journey.py` → **22 passed** (incl. threading
  concurrency, 5-permit/6th-403, zero-charge release).
- **Deploy:** `POST /v1/services/srv-damsbb1ntn7c73d7eg10/deploys`
  (manual, cache not cleared) → `dep-db8aftlg1s2s739kr47g`, commit
  **`3ef1a41a7c8013f1c66ece15ba130495665926e0`** (message matches the
  incident-report commit), created `2026-10-15T10:16:22Z`,
  **live** `2026-10-15T10:18:21Z`. Single attempt; no retries.
- **Deployed tree contains the fix:** `git merge-base --is-ancestor
  70738f8 3ef1a41` → true. The deployed build includes the quota fix
  (`70738f8`), the P4 gate (`ae84f19`) and everything through `3ef1a41`;
  it does **not** include later local-only engineering commits.
- **Read-only probes:** `GET /api/health` → 200
  `{"status":"healthy",…,"version":"1.0.5"}` (liveness only — static
  `APP_VERSION`); frontend → 200.
- **Status of the four required outcomes:**
  1. Quota fix code deployed: **YES** (deploy record + ancestor check).
  2. Future enforcement through the production runtime: **NOT TESTED** —
     no authorized token for the smoke account; lesson generation and the
     free-regeneration probe were explicitly excluded from this phase.
     Runtime enforcement therefore still needs the §12.3 check (or an
     approved equivalent) before GO.
  3. Historical usage reconciled: **NO** — proposal in §13e, awaiting
     explicit owner approval. No UPDATE/DELETE executed.
  4. Production readiness: **NO-GO** until §13e is approved and applied
     and §12.3 evidence exists.

## 13e) Historical usage reconciliation proposal (APPROVAL REQUIRED — NOT EXECUTED)

Chargeability of the incident-window activity under the established
idempotency/free-regeneration rules (§6 table):

| Event | Rule | Units |
|---|---|---|
| 6 accepted distinct occurrences (`week1:0`, `week2:0`, `week2:1`, `week4:0`, `week4:1`, `week5:0`) | distinct `{scheme_id}:{indicator_code}` → 1 unit each | **6 chargeable** |
| free regeneration of `week2:0` | same occurrence → idempotent, no new unit | 0 |
| P4 hard rejection `week3:0:B9.1.1.2.1` (nothing persisted) | failed/rejected work is zero-charge; unit row released | 0 (orphan row exists only because the broken path never released it) |
| 400 validation reject | rejected before reservation | 0 |

**Proposed correction (HARDENED 2026-10-16 — server-side enforced; NOT
EXECUTED).** Design: every precondition, row count and post-condition is
enforced inside the transaction by `IF … RAISE EXCEPTION` (PL/pgSQL
evaluates these unconditionally at runtime; no configuration disables
them — `ASSERT` is deliberately not relied upon). Any failure aborts the
whole transaction **before** `COMMIT`, so a blind run of the script can
never leave a partially applied repair. The deletion targets the exact
verified orphan by its full identity (`user`, `period_type`, `period_key`,
`unit_kind`, `unit_key`, `scheme_id`, `created_at`) and still requires
the established zero-charge classification (`NOT EXISTS` a persisted
lesson) — never a broad `NOT EXISTS`-only predicate. Mutations and their
enforced checks live in two `DO` blocks; the informational `SELECT`s
after them are for operator review only and cannot affect safety.

**Locking & concurrency.** Phase A takes `FOR UPDATE` on the single
`usage_periods` row of the account+period. The deployed reservation path
(`reserve_lesson_units` in `usage_quota.py`) ends in a guarded
`UPDATE usage_periods SET units_used = units_used + n …` and the release
path (`release_lesson_units`) similarly updates the same row, so our
row lock fully serialises the repair against any concurrent reservation
or release for this account+period. `SET LOCAL lock_timeout = '10s'`
converts a lock conflict into a clean abort instead of a hang.
Remaining assumptions: (1) no DDL on the four tables during the repair;
(2) the operator runs the script start-to-end in ONE session; (3) if any
reservation/release commits between the 2026-10-16 investigation and
execution, the preconditions (counter = 0, exactly 7 units, max
`created_at` unchanged) fail and the transaction stops — requiring fresh
read-only investigation, never a silent weaker repair; (4) session time
zone is UTC (the default of Neon and the docker test image) — the repair
`NOTICE` prints a wall-clock timestamp that the rollback script feeds back
through `timestamp '<REPAIRED_TS>'`, which is interpreted in the session
time zone.

**Execution:** run start-to-end in one session (the repair itself needs
no substitutions). It emits three `NOTICE` packets, all **before**
`COMMIT` — record all three verbatim; they are the complete rollback
packet:

| Packet | Emitted by | Fields | Used by rollback as |
|---|---|---|---|
| `DELETED_ORPHAN …` | Phase B B1 | `id`, `key`, `created_at` | `<ORPHAN_ID>`, `<ORPHAN_CREATED_AT>` |
| `REPAIRED_TS …` | Phase B B2 | repair timestamp | `<REPAIRED_TS>` |
| `P1_ORIGINAL_PERIOD …` | Phase B B4 (after all post-conditions) | `user_id`, `period_key`, `updated_at` (the period row's exact pre-repair timestamp) | `<ORIGINAL_PERIOD_TS>` |

If `COMMIT` does not succeed, or any packet line is missing or
unreadable, **stop and investigate read-only — do not attempt a
best-effort rollback.**

```sql
-- SCRIPT: P1-REPAIR
-- PROPOSAL 1 (§13e) — incident account ONLY. NOT EXECUTED.
-- Scope: usage_units + usage_periods rows of
--   user c11bde4c-a9bb-4f41-b96a-921570cf856e, calendar_month 2026-10.
-- No lesson/scheme/job/entitlement row is inserted, updated or deleted.
-- Phase A locks + verifies every precondition; Phase B deletes the exact
-- verified orphan, repairs the counter, and re-verifies the final state —
-- all server-side. Any failure raises and aborts BEFORE COMMIT.
BEGIN;
SET LOCAL statement_timeout = '60s';
SET LOCAL lock_timeout = '10s';

-- Phase A: lock + preconditions (aborts on any mismatch).

DO $$
DECLARE
  v_uid     constant text      := 'c11bde4c-a9bb-4f41-b96a-921570cf856e';
  v_scheme  constant text      := 'ab28233d-f87c-4753-98c1-fbb94acead7f';
  v_key     constant text      := 'ab28233d-f87c-4753-98c1-fbb94acead7f:B9.1.1.2.1';
  v_created constant timestamp := timestamp '2026-10-09 00:21:16.294309';
  v_newest  constant timestamp := timestamp '2026-10-09 00:22:52.201720';
  v_units   int;
  v_matched int;
  v_ts      timestamp;
BEGIN
  SELECT p.units_used INTO v_units FROM usage_periods p
   WHERE p.user_id = v_uid AND p.period_type = 'calendar_month'
     AND p.period_key = '2026-10' FOR UPDATE;
  IF NOT FOUND OR v_units <> 0 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP001', MESSAGE =
      'precondition failed: period row missing or units_used is not 0';
  END IF;
  SELECT count(*) INTO v_units FROM usage_units
   WHERE user_id = v_uid AND period_type = 'calendar_month' AND period_key = '2026-10';
  IF v_units <> 7 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP001', MESSAGE =
      'precondition failed: expected 7 incident unit rows';
  END IF;
  SELECT count(*) INTO v_matched FROM usage_units u
   WHERE u.user_id = v_uid AND u.period_type = 'calendar_month' AND u.period_key = '2026-10'
     AND EXISTS (SELECT 1 FROM lesson_plans l
                  WHERE l.owner_id = u.user_id AND l.scheme_id = u.scheme_id
                    AND jsonb_exists(l.indicator_codes::jsonb, split_part(u.unit_key, ':', 2)));
  IF v_matched <> 6 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP001', MESSAGE =
      'precondition failed: expected 6 lesson-matched incident units';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM usage_units u
     WHERE u.user_id = v_uid AND u.period_type = 'calendar_month' AND u.period_key = '2026-10'
       AND u.unit_kind = 'lesson_plan' AND u.unit_key = v_key AND u.scheme_id = v_scheme
       AND u.created_at = v_created
       AND NOT EXISTS (SELECT 1 FROM lesson_plans l
                        WHERE l.owner_id = u.user_id AND l.scheme_id = u.scheme_id
                          AND jsonb_exists(l.indicator_codes::jsonb, split_part(u.unit_key, ':', 2)))
  ) THEN
    RAISE EXCEPTION USING ERRCODE = 'TP001', MESSAGE =
      'precondition failed: expected orphan row missing or identity changed';
  END IF;
  SELECT count(*) INTO v_units FROM usage_units u
   WHERE u.user_id = v_uid AND u.period_type = 'calendar_month' AND u.period_key = '2026-10'
     AND NOT EXISTS (SELECT 1 FROM lesson_plans l
                      WHERE l.owner_id = u.user_id AND l.scheme_id = u.scheme_id
                        AND jsonb_exists(l.indicator_codes::jsonb, split_part(u.unit_key, ':', 2)));
  IF v_units <> 1 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP001', MESSAGE =
      'precondition failed: incident ledger has other unmatched units';
  END IF;
  SELECT count(*) INTO v_units FROM lesson_plans WHERE owner_id = v_uid;
  IF v_units <> 6 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP001', MESSAGE =
      'precondition failed: expected 6 persisted incident lessons';
  END IF;
  SELECT count(*) INTO v_units FROM lesson_plans
   WHERE owner_id = v_uid AND source_occurrence_id IN
     ('week1:0:B9.1.1.1.1','week2:0:B9.1.1.1.2','week2:1:B9.1.1.1.3',
      'week4:0:B9.1.2.1.1','week4:1:B9.1.2.1.2','week5:0:B9.1.2.1.3');
  IF v_units <> 6 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP001', MESSAGE =
      'precondition failed: incident lessons no longer carry the six verified occurrence ids';
  END IF;
  IF EXISTS (SELECT 1 FROM lesson_plans
              WHERE owner_id = v_uid AND jsonb_exists(indicator_codes::jsonb, 'B9.1.1.2.1')) THEN
    RAISE EXCEPTION USING ERRCODE = 'TP001', MESSAGE =
      'precondition failed: a persisted lesson now exists for the rejected code';
  END IF;
  SELECT count(DISTINCT job_id) INTO v_units FROM lesson_plans WHERE owner_id = v_uid;
  IF v_units <> 1 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP001', MESSAGE =
      'precondition failed: incident lessons no longer share a single job';
  END IF;
  IF EXISTS (SELECT 1 FROM lesson_plans l JOIN generation_jobs j ON j.id = l.job_id
              WHERE l.owner_id = v_uid AND j.status <> 'completed') THEN
    RAISE EXCEPTION USING ERRCODE = 'TP001', MESSAGE =
      'precondition failed: the shared incident job is not completed';
  END IF;
  SELECT count(*) INTO v_units FROM generation_jobs
   WHERE owner_id = v_uid AND status = 'failed' AND error_message = ''
     AND date_trunc('second', created_at)::time
         IN (time '00:21:16', time '00:22:19', time '00:36:41');
  IF v_units <> 3 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP001', MESSAGE =
      'precondition failed: the three verified failed jobs are not intact';
  END IF;
  SELECT count(*) INTO v_units FROM generation_jobs WHERE owner_id = v_uid AND status = 'failed';
  IF v_units <> 3 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP001', MESSAGE =
      'precondition failed: unexpected number of failed jobs';
  END IF;
  SELECT count(*) INTO v_units FROM generation_jobs WHERE owner_id = v_uid;
  IF v_units <> 10 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP001', MESSAGE =
      'precondition failed: incident job count changed (expected 10)';
  END IF;
  SELECT max(created_at) INTO v_ts FROM usage_units WHERE user_id = v_uid;
  IF v_ts IS DISTINCT FROM v_newest THEN
    RAISE EXCEPTION USING ERRCODE = 'TP001', MESSAGE =
      'precondition failed: ledger activity changed since investigation (newest unit moved)';
  END IF;
END $$;

-- Phase B: exact-row deletion + counter repair + enforced post-conditions.
DO $$
DECLARE
  v_uid     constant text      := 'c11bde4c-a9bb-4f41-b96a-921570cf856e';
  v_scheme  constant text      := 'ab28233d-f87c-4753-98c1-fbb94acead7f';
  v_key     constant text      := 'ab28233d-f87c-4753-98c1-fbb94acead7f:B9.1.1.2.1';
  v_created constant timestamp := timestamp '2026-10-09 00:21:16.294309';
  v_id    text;
  v_rows  int;
  v_ledger int;
  v_ts    timestamp := now();
  v_orig_ts timestamp;
BEGIN
  -- B1: delete exactly the verified orphan row.
  DELETE FROM usage_units u
   WHERE u.user_id = v_uid AND u.period_type = 'calendar_month' AND u.period_key = '2026-10'
     AND u.unit_kind = 'lesson_plan' AND u.unit_key = v_key AND u.scheme_id = v_scheme
     AND u.created_at = v_created
     AND NOT EXISTS (SELECT 1 FROM lesson_plans l
                      WHERE l.owner_id = u.user_id AND l.scheme_id = u.scheme_id
                        AND jsonb_exists(l.indicator_codes::jsonb, split_part(u.unit_key, ':', 2)))
  RETURNING u.id INTO v_id;
  GET DIAGNOSTICS v_rows = ROW_COUNT;
  IF v_rows <> 1 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP002', MESSAGE =
      format('orphan deletion affected %s row(s), expected exactly 1', v_rows);
  END IF;
  RAISE NOTICE 'DELETED_ORPHAN id=% key=% created_at=%', v_id, v_key, v_created;

  -- B2: repaired counter = post-deletion ledger count, which must be 6.
  SELECT count(*) INTO v_ledger FROM usage_units
   WHERE user_id = v_uid AND period_type = 'calendar_month' AND period_key = '2026-10';
  IF v_ledger <> 6 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP002', MESSAGE =
      format('post-deletion ledger is %s rows, expected 6 — aborting', v_ledger);
  END IF;
  -- Capture the exact original period timestamp BEFORE the counter update
  -- (the row is already locked from Phase A; this re-read is in-transaction).
  SELECT p.updated_at INTO v_orig_ts FROM usage_periods p
   WHERE p.user_id = v_uid AND p.period_type = 'calendar_month'
     AND p.period_key = '2026-10' FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION USING ERRCODE = 'TP002', MESSAGE =
      'period row vanished before the counter update — aborting';
  END IF;
  UPDATE usage_periods p
     SET units_used = v_ledger, updated_at = v_ts
   WHERE p.user_id = v_uid AND p.period_type = 'calendar_month'
     AND p.period_key = '2026-10' AND p.units_used = 0;
  GET DIAGNOSTICS v_rows = ROW_COUNT;
  IF v_rows <> 1 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP002', MESSAGE =
      format('counter update affected %s row(s), expected exactly 1', v_rows);
  END IF;
  RAISE NOTICE 'REPAIRED_TS %', v_ts;

  -- B3: enforced post-conditions (state must be exactly the approved result).
  SELECT count(*) INTO v_ledger FROM usage_units
   WHERE user_id = v_uid AND period_type = 'calendar_month' AND period_key = '2026-10';
  IF v_ledger <> 6 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP002', MESSAGE = 'post-condition failed: expected 6 ledger rows';
  END IF;
  SELECT count(*) INTO v_ledger FROM usage_units u
   WHERE u.user_id = v_uid AND u.period_type = 'calendar_month' AND u.period_key = '2026-10'
     AND EXISTS (SELECT 1 FROM lesson_plans l
                  WHERE l.owner_id = u.user_id AND l.scheme_id = u.scheme_id
                    AND jsonb_exists(l.indicator_codes::jsonb, split_part(u.unit_key, ':', 2)));
  IF v_ledger <> 6 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP002', MESSAGE = 'post-condition failed: all 6 remaining units must match lessons';
  END IF;
  SELECT units_used INTO v_ledger FROM usage_periods
   WHERE user_id = v_uid AND period_type = 'calendar_month' AND period_key = '2026-10';
  IF v_ledger <> 6 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP002', MESSAGE = 'post-condition failed: counter must be 6';
  END IF;
  IF EXISTS (SELECT 1 FROM usage_units WHERE user_id = v_uid AND unit_key = v_key) THEN
    RAISE EXCEPTION USING ERRCODE = 'TP002', MESSAGE = 'post-condition failed: orphan row still present';
  END IF;
  SELECT count(*) INTO v_ledger FROM lesson_plans WHERE owner_id = v_uid;
  IF v_ledger <> 6 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP002', MESSAGE = 'post-condition failed: accepted lessons must remain 6 and unchanged';
  END IF;
  -- B4: emit the original-period-timestamp packet only after every
  --     post-condition has passed (this is the last statement before the
  --     operator-review SELECTs and COMMIT).
  RAISE NOTICE 'P1_ORIGINAL_PERIOD user_id=% period_key=% updated_at=%',
    v_uid, '2026-10', v_orig_ts;
END $$;

-- Operator review only (cannot affect safety — checks above already passed):
SELECT units_used AS counter FROM usage_periods
 WHERE user_id = 'c11bde4c-a9bb-4f41-b96a-921570cf856e' AND period_key = '2026-10';
SELECT split_part(unit_key, ':', 2) AS code, created_at FROM usage_units
 WHERE user_id = 'c11bde4c-a9bb-4f41-b96a-921570cf856e' ORDER BY created_at;
COMMIT;
```

**Rollback (P1).** Permitted **only immediately after the repair and
before any account activity**, and only with the full packet captured
from the repair `NOTICE` lines (packet table in the Execution note
above). It is fully guarded: if the counter, ledger, or `updated_at`
differ from the repaired state (i.e. anything touched the account since
the repair), it **raises and refuses** — it never overwrites newer
accounting. On success it restores the orphan row **and** the period row
(`units_used = 0` and the **original** `updated_at` captured by the
repair) to their exact pre-repair values. Substitute `<ORPHAN_ID>`,
`<ORPHAN_CREATED_AT>` (from `DELETED_ORPHAN …`), `<REPAIRED_TS>` (from
`REPAIRED_TS …`) and `<ORIGINAL_PERIOD_TS>` (from `P1_ORIGINAL_PERIOD …`).
If any packet line is missing or the values cannot be established,
**stop and investigate read-only — do not attempt a best-effort
rollback.**

```sql
-- SCRIPT: P1-ROLLBACK
BEGIN;
SET LOCAL statement_timeout = '60s';
SET LOCAL lock_timeout = '10s';
DO $$
DECLARE
  v_uid     constant text := 'c11bde4c-a9bb-4f41-b96a-921570cf856e';
  v_scheme  constant text := 'ab28233d-f87c-4753-98c1-fbb94acead7f';
  v_key     constant text := 'ab28233d-f87c-4753-98c1-fbb94acead7f:B9.1.1.2.1';
  v_id      constant text := '<ORPHAN_ID>';
  v_created constant timestamp := timestamp '<ORPHAN_CREATED_AT>';
  v_ts      constant timestamp := timestamp '<REPAIRED_TS>';
  v_orig    constant timestamp := timestamp '<ORIGINAL_PERIOD_TS>';
  n int;
  v_check_ts timestamp;
BEGIN
  -- G1: still exactly the repaired state, untouched since the repair.
  SELECT p.units_used INTO n FROM usage_periods p
   WHERE p.user_id = v_uid AND p.period_type = 'calendar_month'
     AND p.period_key = '2026-10' FOR UPDATE;
  IF NOT FOUND OR n <> 6 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP003', MESSAGE =
      'rollback refused: counter is not the repaired value 6 (activity or drift since repair)';
  END IF;
  IF (SELECT p.updated_at FROM usage_periods p
       WHERE p.user_id = v_uid AND p.period_type = 'calendar_month'
         AND p.period_key = '2026-10') <> v_ts THEN
    RAISE EXCEPTION USING ERRCODE = 'TP003', MESSAGE =
      'rollback refused: period row changed after the repair (updated_at moved)';
  END IF;
  SELECT count(*) INTO n FROM usage_units
   WHERE user_id = v_uid AND period_type = 'calendar_month' AND period_key = '2026-10';
  IF n <> 6 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP003', MESSAGE =
      'rollback refused: ledger no longer the repaired 6 rows';
  END IF;
  IF (SELECT max(created_at) FROM usage_units WHERE user_id = v_uid)
     IS DISTINCT FROM timestamp '2026-10-09 00:22:52.201720' THEN
    RAISE EXCEPTION USING ERRCODE = 'TP003', MESSAGE =
      'rollback refused: newer ledger activity exists since the repair';
  END IF;
  SELECT count(*) INTO n FROM lesson_plans WHERE owner_id = v_uid;
  IF n <> 6 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP003', MESSAGE =
      'rollback refused: lesson set changed since the repair';
  END IF;
  -- G2: the captured row is truly absent (no double-restore).
  IF EXISTS (SELECT 1 FROM usage_units WHERE id = v_id)
     OR EXISTS (SELECT 1 FROM usage_units
                 WHERE user_id = v_uid AND period_type = 'calendar_month'
                   AND period_key = '2026-10' AND unit_kind = 'lesson_plan'
                   AND unit_key = v_key) THEN
    RAISE EXCEPTION USING ERRCODE = 'TP003', MESSAGE =
      'rollback refused: orphan row (id or key) already present';
  END IF;
  -- R1: restore the captured row faithfully (all original values).
  INSERT INTO usage_units (id, user_id, period_type, period_key,
                           unit_kind, unit_key, scheme_id, created_at)
  VALUES (v_id, v_uid, 'calendar_month', '2026-10',
          'lesson_plan', v_key, v_scheme, v_created);
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 1 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP003', MESSAGE = 'rollback failed: restore insert affected no rows';
  END IF;
  -- R2: restore the original counter 0 AND the original period timestamp
  --     (guarded: only from the repaired value/timestamp, never over
  --     anything newer).
  UPDATE usage_periods
     SET units_used = 0, updated_at = v_orig
   WHERE user_id = v_uid AND period_type = 'calendar_month'
     AND period_key = '2026-10' AND units_used = 6 AND updated_at = v_ts;
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 1 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP003', MESSAGE = 'rollback failed: counter restore affected no rows';
  END IF;
  -- Post: original state fully restored (counters AND timestamps AND rows).
  SELECT count(*) INTO n FROM usage_units
   WHERE user_id = v_uid AND period_type = 'calendar_month' AND period_key = '2026-10';
  IF n <> 7 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP003', MESSAGE = 'rollback post-check failed: expected 7 ledger rows';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM usage_units WHERE id = v_id
                  AND user_id = v_uid AND unit_key = v_key
                  AND scheme_id = v_scheme AND created_at = v_created) THEN
    RAISE EXCEPTION USING ERRCODE = 'TP003', MESSAGE =
      'rollback post-check failed: orphan row not restored with its captured values';
  END IF;
  SELECT units_used, updated_at INTO n, v_check_ts FROM usage_periods
   WHERE user_id = v_uid AND period_type = 'calendar_month' AND period_key = '2026-10';
  IF n <> 0 OR v_check_ts IS DISTINCT FROM v_orig THEN
    RAISE EXCEPTION USING ERRCODE = 'TP003', MESSAGE =
      'rollback post-check failed: period row must be counter 0 with the original updated_at';
  END IF;
END $$;
SELECT units_used AS restored_counter FROM usage_periods
 WHERE user_id = 'c11bde4c-a9bb-4f41-b96a-921570cf856e' AND period_key = '2026-10';
COMMIT;
```

**Safe recheck (read-only, optional, before attempting a rollback):**
the `G1`/`G2` guard queries above, without the `DO` block — if any value
differs from the repaired state, do not run the rollback; investigate
read-only instead.

**Expected post-correction state:** `units_used = 6` (limit 5) → new
distinct generations correctly **blocked until 2026-11-01**; free
regenerations of the six counted codes remain free (unit-key conflict →
`consumed=0`); the six accepted lessons remain saved (accepted-only
persistence is unaffected); every other account untouched (the full
all-account inventory from the 2026-10-16 probes is in §13f; correcting
the other 14 period rows is the separate Proposal 2 in §13g).

**Not executed.** Awaiting explicit owner approval; until applied, every
quota read for this account truthfully reports the still-broken stored
counter (`used=0`) even though the deployed code is correct — which is
why readiness stays NO-GO.

## 13f) Production read-only verification (2026-10-16 — zero writes, zero POSTs)

Method: Render API (service/deploy/env **names** only; no secret values
printed) plus three read-only database probes. Each probe ran inside a
single `BEGIN TRANSACTION READ ONLY` transaction with
`transaction_read_only = 'on'` asserted, `statement_timeout = 30s`, then
`ROLLBACK` — no `INSERT/UPDATE/DELETE/migration` was issued at any point.
No production HTTP write endpoint was called (the only HTTP requests were
`GET` on the Render API).

**Deployed-state re-verification:**
- Live deploy is still `dep-db8aftlg1s2s739kr47g` = commit `3ef1a41`
  (finished 2026-10-15T10:18:21Z); no newer deploy attempt exists.
  Local `main` = `217a32c` == `origin/main`, still NOT deployed (by design).
- Content verification (not just ancestry): `git show 3ef1a41:backend/
  src/usage_quota.py` contains the `RETURNING`-based `_insert_ignore`;
  `git diff --stat 3ef1a41..217a32c -- backend/src/usage_quota.py
  backend/src/entitlements.py` is empty → **the deployed quota code is
  byte-identical to the code verified by the local PostgreSQL gate (22
  passed)**.

**Incident account (`c11bde..856e`) — §13e re-validated against live rows:**
- 7 `usage_units` rows for 2026-10 (`B9.1.1.1.1/.2/.3`, `B9.1.1.2.1`,
  `B9.1.2.1.1/.2/.3`, created 00:10:34–00:22:52 on 2026-10-09); counter
  `units_used = 0`; entitlement `free / active / limit 5`.
- 6 persisted lessons, occurrence ids `week1:0`, `week2:0`, `week2:1`,
  `week4:0`, `week4:1`, `week5:0` — exactly the six chargeable units.
  All six lesson rows are currently linked to the final job `dc22da..47c1`
  (replacement re-homes survivors to the last run).
- Exactly 1 orphan: `ab28233d-f87c-4753-98c1-fbb94acead7f:B9.1.1.2.1`
  (created 00:21:16 by failed job `a95852..c0e7`; scheme still exists;
  never released because the broken path's `reserved_keys` was always
  empty — the §13e orphan).
- 3 failed jobs (`a95852`, `19fda9`, `571488`) all carry an **empty
  `error_message`** (evidence limitation: the gate-rejection reason is
  not recoverable from the job row; it is evidenced by the §4/§7-§8
  reproduction instead). The two later failures created no new unit rows
  (all-key conflicts → consumed 0).
- One §13e table nuance, recorded honestly: the idempotent free
  regeneration observed at occurrence level was `week1:0` (job
  `581355` at 00:15:46 re-generated it with no new unit row), not
  `week2:0` as the table line states. The line's accounting conclusion
  (0 charge, no new unit) is confirmed either way; the chargeable-units
  total of 6 is unaffected.
- Concurrency recheck at probe time: still 7 units, still 6 lessons,
  server clock 2026-10-16 (period still `2026-10`).

**Full production scope — every account (all rows, complete coverage):**
- 166 `usage_units` rows total, 15 `usage_periods` rows, 14 users with
  units; newest unit 2026-10-09 00:22:52; **0 generation jobs created
  after the 2026-10-15 deploy** (the fixed code has never been exercised
  by a real run).
- **All 15 period rows have `units_used = 0` while holding ledger rows —
  the defect was production-wide, not incident-only.** No counter
  without a ledger row exists (the reverse check is empty).
- Reconciliation unit→lesson across the whole ledger: **164 matched, 2
  orphans.** The second orphan (not in §13e's scope): user
  `1474a7..9ed9`, period 2026-09, `unit_kind=lesson_plan`, unit created
  2026-09-26 15:30:23 for scheme `8ffecf..b9db`, code
  `MID-TERM (05-11-2026 to 06-11-` — its job `5638bf..89b9` completed
  with `total_lessons = 0` (empty run), so nothing was persisted and the
  correct code would have released the row; the broken release path
  orphaned it. (The same user has a *matched* `MID-TERM` unit from an
  earlier 11:04 run whose job did persist a special-week lesson — special
  weeks that actually persist ARE chargeable, matched logic confirms it.)

| user (masked) | period | ledger rows | matched | orphans | expected counter |
|---|---|---|---|---|---|
| 1474a7..9ed9 | 2026-09 | 28 | 27 | 1 (MID-TERM empty run) | **27** |
| 1474a7..9ed9 | 2026-10 | 5 | 5 | 0 | **5** |
| 206f1b..f1b9 | 2026-09 | 5 | 5 | 0 | **5** |
| 2a9440..a3b5 | 2026-09 | 5 | 5 | 0 | **5** |
| 2dbf6e..a25f | 2026-09 | 5 | 5 | 0 | **5** |
| 2f62b5..320e | 2026-09 | 42 | 42 | 0 | **42** |
| 4995a6..6364 | 2026-10 | 34 | 34 | 0 | **34** |
| 5041ae..defd | 2026-09 | 5 | 5 | 0 | **5** |
| 762d46..0b28 | 2026-09 | 5 | 5 | 0 | **5** |
| b03ee7..1bf2 | 2026-09 | 5 | 5 | 0 | **5** |
| b2303e..3dce | 2026-10 | 5 | 5 | 0 | **5** |
| bdadee..b2d6 | 2026-09 | 5 | 5 | 0 | **5** |
| c11bde..856e | 2026-10 | 7 | 6 | 1 (gate rejection — §13e) | **6** |
| dbe010..68a9 | 2026-09 | 5 | 5 | 0 | **5** |
| f801cf..5efb | 2026-10 | 5 | 5 | 0 | **5** |

All 13 non-incident users are `free` tier, `limit 5` (one `revoked`
subscription — `2f62b5..320e`, limit still 5). September rows are
historical bookkeeping only (the API reads the current month); the
2026-10 rows of `1474a7..9ed9`, `4995a6..6364`, `b2303e..3dce` and
`f801cf..5efb` have **forward enforcement effect**: correcting them makes
those accounts exhaust/block in October exactly as Free Tier policy
describes (notably `4995a6..6364` at 34 units — already far over).

**Clarification (pre- vs post-repair counts).** The table above is the
**pre-deletion** picture: 166 total ledger rows = incident 7 +
non-incident 159, of which 164 match lessons and 2 are orphans. After
§13e+§13g run (each deletes its one zero-charge orphan), the ledger is
**164 rows, every one matched to a persisted lesson** (6 incident +
158 non-incident); the orphan columns of the table collapse to 0. The
chargeable-unit total of the surviving ledger (158 matched units) is
unchanged by the repair — the two deleted rows were never chargeable.

## 13g) Proposal 2 — all-accounts reconciliation (SEPARATE APPROVAL — NOT EXECUTED)

New evidence from §13f (the defect affected every account) widens the
historical-reconciliation control beyond §13e. This proposal is **not**
part of the §13e approval; it needs its own explicit owner decision.
**HARDENED 2026-10-16** with the same server-side enforcement model as
§13e (every precondition, row count and post-condition raises and aborts
before `COMMIT`; `ASSERT` is not relied upon).

**Identity of the target row.** The full `user_id`/`scheme_id` UUIDs of
the MID-TERM orphan were **masked in the recorded 2026-10-16 evidence**
and are not established anywhere in this repository — they are therefore
NOT invented here. The deletion is narrowed to every identity property
that *is* recorded, and the transaction verifies all of them plus
uniqueness: period `calendar_month`/`2026-09`, `unit_kind=lesson_plan`,
`created_at = 2026-09-26 15:30:23.633320` (globally unique in the
evidence), indicator code exactly `MID-TERM (05-11-2026 to 06-11-`,
`scheme_id` equal to the `unit_key` prefix, `unit_key` length 67, the
established zero-charge classification (`NOT EXISTS` a persisted lesson),
and exactly one such row. The repair `NOTICE` prints the full primary
key, `user_id` and `scheme_id` for the owner's review before `COMMIT`.

**Locking & concurrency.** Phase A locks all 14 non-incident
`usage_periods` rows `FOR UPDATE` in stable `(user_id, period_key)`
order. The deployed reservation/release paths update exactly one period
row per call, so they serialise against whichever row they touch;
`lock_timeout = '10s'` turns any wait into a clean abort. Assumptions:
no DDL; one session; the two proposals are NOT run simultaneously (they
are separate approvals — run them sequentially); any counter or ledger
change since the investigation trips a precondition.

```sql
-- SCRIPT: P2-REPAIR
-- PROPOSAL 2 (§13g) — all accounts EXCEPT c11bde4c-a9bb-4f41-b96a-921570cf856e.
-- Order-independent w.r.t. Proposal 1 (incident rows are snapshotted and
-- re-asserted untouched). NOT EXECUTED.
-- Scope: usage_units + usage_periods rows of the 13 other users.
-- No lesson/scheme/job/entitlement row is inserted, updated or deleted.
BEGIN;
SET LOCAL statement_timeout = '60s';
SET LOCAL lock_timeout = '10s';

-- Phase A: stable-order locks + preconditions (aborts on any mismatch).
DO $$
DECLARE
  v_inc   constant text := 'c11bde4c-a9bb-4f41-b96a-921570cf856e';
  v_code  constant text := 'MID-TERM (05-11-2026 to 06-11-';
  v_created constant timestamp := timestamp '2026-09-26 15:30:23.633320';
  r       record;
  n       int;
  v_inc_units  int;
  v_inc_counter int;
  v_inc_expected int;
  v_sept int[];
  v_oct  int[];
BEGIN
  -- A0: snapshot the incident account (order-independence w.r.t. §13e).
  SELECT count(*) INTO v_inc_units FROM usage_units WHERE user_id = v_inc;
  SELECT units_used INTO v_inc_counter FROM usage_periods
   WHERE user_id = v_inc AND period_type = 'calendar_month' AND period_key = '2026-10';
  -- (CASE computed into a variable: plpgsql's IF scanner would otherwise
  --  treat the CASE's own THEN as the end of the IF condition.)
  v_inc_expected := CASE WHEN v_inc_units = 7 THEN 0 ELSE 6 END;
  IF v_inc_units NOT IN (6, 7) OR v_inc_counter IS DISTINCT FROM v_inc_expected THEN
    RAISE EXCEPTION USING ERRCODE = 'TP001', MESSAGE =
      'precondition failed: incident account is not in a clean pre- or post-Proposal-1 state';
  END IF;

  -- A1: lock all 14 non-incident period rows in stable order; all counters 0.
  FOR r IN (SELECT user_id, units_used FROM usage_periods
             WHERE user_id <> v_inc
             ORDER BY user_id, period_key
             FOR UPDATE)
  LOOP
    IF r.units_used <> 0 THEN
      RAISE EXCEPTION USING ERRCODE = 'TP001', MESSAGE =
        'precondition failed: a non-incident counter is not 0';
    END IF;
  END LOOP;
  SELECT count(*) INTO n FROM usage_periods WHERE user_id <> v_inc;
  IF n <> 14 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP001', MESSAGE =
      'precondition failed: expected 14 non-incident period rows';
  END IF;

  -- A2: 159 non-incident ledger rows, with the recorded per-month shape.
  SELECT count(*) INTO n FROM usage_units WHERE user_id <> v_inc;
  IF n <> 159 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP001', MESSAGE =
      'precondition failed: expected 159 non-incident unit rows';
  END IF;
  SELECT array_agg(c ORDER BY c) INTO v_sept FROM (
    SELECT count(*)::int AS c FROM usage_units u
     WHERE u.user_id <> v_inc AND u.period_type = 'calendar_month'
       AND u.period_key = '2026-09' GROUP BY u.user_id) s;
  IF v_sept IS DISTINCT FROM ARRAY[5,5,5,5,5,5,5,5,28,42]::int[] THEN
    RAISE EXCEPTION USING ERRCODE = 'TP001', MESSAGE =
      'precondition failed: September non-incident ledger shape changed';
  END IF;
  SELECT array_agg(c ORDER BY c) INTO v_oct FROM (
    SELECT count(*)::int AS c FROM usage_units u
     WHERE u.user_id <> v_inc AND u.period_type = 'calendar_month'
       AND u.period_key = '2026-10' GROUP BY u.user_id) s;
  IF v_oct IS DISTINCT FROM ARRAY[5,5,5,34]::int[] THEN
    RAISE EXCEPTION USING ERRCODE = 'TP001', MESSAGE =
      'precondition failed: October non-incident ledger shape changed';
  END IF;

  -- A3: exactly one non-incident orphan, and it is the recorded MID-TERM row.
  SELECT count(*) INTO n FROM usage_units u
   WHERE u.user_id <> v_inc
     AND NOT EXISTS (SELECT 1 FROM lesson_plans l
                      WHERE l.owner_id = u.user_id AND l.scheme_id = u.scheme_id
                        AND jsonb_exists(l.indicator_codes::jsonb, split_part(u.unit_key, ':', 2)));
  IF n <> 1 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP001', MESSAGE =
      'precondition failed: expected exactly 1 non-incident orphan';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM usage_units u
     WHERE u.user_id <> v_inc
       AND u.period_type = 'calendar_month' AND u.period_key = '2026-09'
       AND u.unit_kind = 'lesson_plan'
       AND u.created_at = v_created
       AND split_part(u.unit_key, ':', 2) = v_code
       AND u.scheme_id = split_part(u.unit_key, ':', 1)
       AND length(u.unit_key) = 67
       AND NOT EXISTS (SELECT 1 FROM lesson_plans l
                        WHERE l.owner_id = u.user_id AND l.scheme_id = u.scheme_id
                          AND jsonb_exists(l.indicator_codes::jsonb, split_part(u.unit_key, ':', 2)))
  ) THEN
    RAISE EXCEPTION USING ERRCODE = 'TP001', MESSAGE =
      'precondition failed: the recorded MID-TERM orphan is missing or its identity changed';
  END IF;
  SELECT count(*) INTO n FROM usage_units WHERE created_at = v_created;
  IF n <> 1 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP001', MESSAGE =
      'precondition failed: the recorded orphan created_at is no longer globally unique';
  END IF;
END $$;

-- Phase B: exact-row deletion + 14-counter repair + enforced post-conditions.
DO $$
DECLARE
  v_inc   constant text := 'c11bde4c-a9bb-4f41-b96a-921570cf856e';
  v_code  constant text := 'MID-TERM (05-11-2026 to 06-11-';
  v_created constant timestamp := timestamp '2026-09-26 15:30:23.633320';
  v_ts    timestamp := now();
  v_id    text; v_user text; v_scheme text; v_key text;
  v_rows  int; n int;
  r       record;
  v_sept  int[]; v_oct int[];
  v_inc_units int; v_inc_counter int; v_inc_expected int;
BEGIN
  -- B1: delete exactly the recorded orphan row.
  DELETE FROM usage_units u
   WHERE u.user_id <> v_inc
     AND u.period_type = 'calendar_month' AND u.period_key = '2026-09'
     AND u.unit_kind = 'lesson_plan'
     AND u.created_at = v_created
     AND split_part(u.unit_key, ':', 2) = v_code
     AND u.scheme_id = split_part(u.unit_key, ':', 1)
     AND length(u.unit_key) = 67
     AND NOT EXISTS (SELECT 1 FROM lesson_plans l
                      WHERE l.owner_id = u.user_id AND l.scheme_id = u.scheme_id
                        AND jsonb_exists(l.indicator_codes::jsonb, split_part(u.unit_key, ':', 2)))
  RETURNING u.id, u.user_id, u.scheme_id, u.unit_key
  INTO v_id, v_user, v_scheme, v_key;
  GET DIAGNOSTICS v_rows = ROW_COUNT;
  IF v_rows <> 1 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP002', MESSAGE =
      format('orphan deletion affected %s row(s), expected exactly 1', v_rows);
  END IF;
  RAISE NOTICE 'DELETED_ORPHAN id=% user=% scheme=% key=% created_at=%',
    v_id, v_user, v_scheme, v_key, v_created;

  -- B1b: capture the exact original updated_at of every non-incident
  --      period row BEFORE the counter update (rows already locked in
  --      Phase A) and emit one parseable packet per row. The rollback
  --      script restores each row's own captured timestamp.
  n := 0;
  FOR r IN (SELECT user_id, period_type, period_key, updated_at
              FROM usage_periods
             WHERE user_id <> v_inc
             ORDER BY user_id, period_key
             FOR UPDATE)
  LOOP
    n := n + 1;
    RAISE NOTICE 'P2_ORIGINAL_PERIOD user_id=% period_type=% period_key=% updated_at=%',
      r.user_id, r.period_type, r.period_key, r.updated_at;
  END LOOP;
  IF n <> 14 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP002', MESSAGE =
      format('captured %s original period row(s), expected exactly 14', n);
  END IF;

  -- B2: recompute all 14 non-incident counters from their ledgers.
  UPDATE usage_periods p
     SET units_used = sub.matched, updated_at = v_ts
    FROM (
          SELECT u.user_id, u.period_type, u.period_key,
                 count(*) FILTER (
                   WHERE EXISTS (
                     SELECT 1 FROM lesson_plans l
                      WHERE l.owner_id = u.user_id AND l.scheme_id = u.scheme_id
                        AND jsonb_exists(l.indicator_codes::jsonb,
                                         split_part(u.unit_key, ':', 2)))
                 ) AS matched
            FROM usage_units u
           WHERE u.user_id <> v_inc
           GROUP BY u.user_id, u.period_type, u.period_key
         ) sub
   WHERE p.user_id = sub.user_id AND p.period_type = sub.period_type
     AND p.period_key = sub.period_key AND p.units_used = 0;
  GET DIAGNOSTICS v_rows = ROW_COUNT;
  IF v_rows <> 14 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP002', MESSAGE =
      format('counter update affected %s row(s), expected exactly 14', v_rows);
  END IF;
  RAISE NOTICE 'REPAIRED_TS %', v_ts;

  -- B3: enforced post-conditions — per-row and per-month, not just totals.
  SELECT count(*) INTO n FROM usage_units WHERE user_id <> v_inc;
  IF n <> 158 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP002', MESSAGE =
      format('post-deletion non-incident ledger is %s rows, expected 158', n);
  END IF;
  IF EXISTS (
    SELECT 1 FROM usage_units u
     WHERE u.user_id <> v_inc
       AND NOT EXISTS (SELECT 1 FROM lesson_plans l
                        WHERE l.owner_id = u.user_id AND l.scheme_id = u.scheme_id
                          AND jsonb_exists(l.indicator_codes::jsonb, split_part(u.unit_key, ':', 2)))
  ) THEN
    RAISE EXCEPTION USING ERRCODE = 'TP002', MESSAGE =
      'post-condition failed: unmatched non-incident units remain';
  END IF;
  -- Every counter equals its own recomputed ledger-matched count.
  IF EXISTS (
    SELECT 1 FROM usage_periods p
     WHERE p.user_id <> v_inc
       AND p.units_used <> (
         SELECT count(*) FROM usage_units u
          WHERE u.user_id = p.user_id AND u.period_type = p.period_type
            AND u.period_key = p.period_key
            AND EXISTS (SELECT 1 FROM lesson_plans l
                         WHERE l.owner_id = u.user_id AND l.scheme_id = u.scheme_id
                           AND jsonb_exists(l.indicator_codes::jsonb,
                                            split_part(u.unit_key, ':', 2))))
  ) THEN
    RAISE EXCEPTION USING ERRCODE = 'TP002', MESSAGE =
      'post-condition failed: a repaired counter does not equal its ledger-matched count';
  END IF;
  -- Exact per-month counter multisets (September distinct from October).
  SELECT array_agg(units_used ORDER BY units_used) INTO v_sept
    FROM usage_periods WHERE user_id <> v_inc AND period_key = '2026-09';
  IF v_sept IS DISTINCT FROM ARRAY[5,5,5,5,5,5,5,5,27,42]::int[] THEN
    RAISE EXCEPTION USING ERRCODE = 'TP002', MESSAGE =
      format('post-condition failed: September counters are %s, expected {5,5,5,5,5,5,5,5,27,42}', v_sept);
  END IF;
  SELECT array_agg(units_used ORDER BY units_used) INTO v_oct
    FROM usage_periods WHERE user_id <> v_inc AND period_key = '2026-10';
  IF v_oct IS DISTINCT FROM ARRAY[5,5,5,34]::int[] THEN
    RAISE EXCEPTION USING ERRCODE = 'TP002', MESSAGE =
      format('post-condition failed: October counters are %s, expected {5,5,5,34}', v_oct);
  END IF;
  SELECT sum(units_used) INTO n FROM usage_periods WHERE user_id <> v_inc;
  IF n <> 158 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP002', MESSAGE =
      'post-condition failed: repaired counters must total 158';
  END IF;
  -- Incident account untouched (snapshot from Phase A).
  SELECT count(*) INTO v_inc_units FROM usage_units WHERE user_id = v_inc;
  SELECT units_used INTO v_inc_counter FROM usage_periods
   WHERE user_id = v_inc AND period_type = 'calendar_month' AND period_key = '2026-10';
  v_inc_expected := CASE WHEN v_inc_units = 7 THEN 0 ELSE 6 END;
  IF v_inc_units NOT IN (6, 7) OR v_inc_counter IS DISTINCT FROM v_inc_expected THEN
    RAISE EXCEPTION USING ERRCODE = 'TP002', MESSAGE =
      'post-condition failed: incident account rows changed during Proposal 2';
  END IF;
END $$;

-- Operator review only (cannot affect safety — checks above already passed):
SELECT period_key, units_used FROM usage_periods
 WHERE user_id <> 'c11bde4c-a9bb-4f41-b96a-921570cf856e'
 ORDER BY period_key, units_used;
COMMIT;
```

**Rollback (P2).** Same window rule as P1: **only immediately after the
repair and before any account activity**, using the full packet from the
repair `NOTICE` lines:

| Packet | Emitted by | Fields |
|---|---|---|
| `DELETED_ORPHAN …` | P2-REPAIR B1 | `id`, `user`, `scheme`, `key`, `created_at` |
| `REPAIRED_TS …` | P2-REPAIR B2 | repair timestamp |
| `P2_ORIGINAL_PERIOD …` ×14 | P2-REPAIR B1b | `user_id`, `period_type`, `period_key`, `updated_at` (one line per affected period row, captured **before** the counter update) |

Fully guarded — refuses (raises) if any of the 14 rows moved off the
repaired state, or if the captured packet is incomplete. On success it
restores the orphan row **and** each of the 14 period rows to its exact
pre-repair state (`units_used = 0` and **that row's own** captured
`updated_at` — no shared or current timestamp is used). Substitute
`<ORPHAN_ID>`, `<ORPHAN_USER_ID>`, `<ORPHAN_SCHEME_ID>`,
`<ORPHAN_UNIT_KEY>`, `<ORPHAN_CREATED_AT>`, `<REPAIRED_TS>`, and build
`<P2_ORIGINAL_PERIODS>` as a SQL `VALUES` list from all 14
`P2_ORIGINAL_PERIOD` lines, e.g.
`('<user1>','calendar_month','2026-09','<ts1>'), ('<user2>',…)` — the
same placeholder text must be substituted at **every** occurrence in the
script. The rollback verifies the list has exactly 14 distinct
account-period identities, that every captured identity maps to a
current non-incident period row and vice versa, and restores each row
individually (row-count enforced per row). If any of the 14 lines is
missing, duplicated, or cannot be matched — **stop and investigate
read-only; do not attempt a best-effort rollback.**

```sql
-- SCRIPT: P2-ROLLBACK
BEGIN;
SET LOCAL statement_timeout = '60s';
SET LOCAL lock_timeout = '10s';
DO $$
DECLARE
  v_inc constant text := 'c11bde4c-a9bb-4f41-b96a-921570cf856e';
  v_id  constant text := '<ORPHAN_ID>';
  v_user constant text := '<ORPHAN_USER_ID>';
  v_scheme constant text := '<ORPHAN_SCHEME_ID>';
  v_key  constant text := '<ORPHAN_UNIT_KEY>';
  v_created constant timestamp := timestamp '<ORPHAN_CREATED_AT>';
  v_ts   constant timestamp := timestamp '<REPAIRED_TS>';
  r record; n int; m int; v_sept int[]; v_oct int[];
BEGIN
  -- V0: the captured original-period packet must be exactly 14 rows with
  --     14 distinct account-period identities (missing/duplicate refuse).
  SELECT count(*) INTO n
    FROM (VALUES <P2_ORIGINAL_PERIODS>)
         AS t(user_id, period_type, period_key, orig_ts);
  IF n <> 14 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP003', MESSAGE =
      format('rollback refused: captured original-period packet has %s row(s), expected 14', n);
  END IF;
  SELECT count(*) INTO n FROM (
    SELECT DISTINCT user_id, period_type, period_key
      FROM (VALUES <P2_ORIGINAL_PERIODS>)
           AS t(user_id, period_type, period_key, orig_ts)
  ) d;
  IF n <> 14 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP003', MESSAGE =
      'rollback refused: captured original-period packet has duplicate account-period identities';
  END IF;

  -- G1: lock all 14 rows (stable order); every row must still be exactly
  --     the repaired state (corrected value AND untouched repair
  --     timestamp) and must have a captured packet entry.
  FOR r IN (SELECT user_id, period_type, period_key, units_used, updated_at
              FROM usage_periods
             WHERE user_id <> v_inc
             ORDER BY user_id, period_key
             FOR UPDATE)
  LOOP
    IF r.updated_at <> v_ts THEN
      RAISE EXCEPTION USING ERRCODE = 'TP003', MESSAGE =
        format('rollback refused: period row %s/%s changed after the repair',
               r.user_id, r.period_key);
    END IF;
    IF r.units_used <> (
         SELECT count(*) FROM usage_units u
          WHERE u.user_id = r.user_id AND u.period_type = r.period_type
            AND u.period_key = r.period_key
            AND EXISTS (SELECT 1 FROM lesson_plans l
                         WHERE l.owner_id = u.user_id AND l.scheme_id = u.scheme_id
                           AND jsonb_exists(l.indicator_codes::jsonb,
                                            split_part(u.unit_key, ':', 2))))
    THEN
      RAISE EXCEPTION USING ERRCODE = 'TP003', MESSAGE =
        format('rollback refused: counter drift for user %s since the repair', r.user_id);
    END IF;
    IF NOT EXISTS (
      SELECT 1 FROM (VALUES <P2_ORIGINAL_PERIODS>)
           AS t(user_id, period_type, period_key, orig_ts)
       WHERE t.user_id = r.user_id AND t.period_type = r.period_type
         AND t.period_key = r.period_key
    ) THEN
      RAISE EXCEPTION USING ERRCODE = 'TP003', MESSAGE =
        format('rollback refused: no captured original timestamp for period %s/%s/%s',
               r.user_id, r.period_type, r.period_key);
    END IF;
  END LOOP;
  SELECT array_agg(units_used ORDER BY units_used) INTO v_sept
    FROM usage_periods WHERE user_id <> v_inc AND period_key = '2026-09';
  IF v_sept IS DISTINCT FROM ARRAY[5,5,5,5,5,5,5,5,27,42]::int[] THEN
    RAISE EXCEPTION USING ERRCODE = 'TP003', MESSAGE =
      'rollback refused: September counters are not the repaired values';
  END IF;
  SELECT array_agg(units_used ORDER BY units_used) INTO v_oct
    FROM usage_periods WHERE user_id <> v_inc AND period_key = '2026-10';
  IF v_oct IS DISTINCT FROM ARRAY[5,5,5,34]::int[] THEN
    RAISE EXCEPTION USING ERRCODE = 'TP003', MESSAGE =
      'rollback refused: October counters are not the repaired values';
  END IF;
  SELECT count(*) INTO n FROM usage_units WHERE user_id <> v_inc;
  IF n <> 158 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP003', MESSAGE =
      'rollback refused: non-incident ledger no longer the repaired 158 rows';
  END IF;
  -- G2: captured row truly absent (no double-restore).
  IF EXISTS (SELECT 1 FROM usage_units WHERE id = v_id) THEN
    RAISE EXCEPTION USING ERRCODE = 'TP003', MESSAGE =
      'rollback refused: a unit row with the captured id already exists';
  END IF;
  IF EXISTS (SELECT 1 FROM usage_units
              WHERE user_id = v_user AND period_type = 'calendar_month'
                AND period_key = '2026-09' AND unit_kind = 'lesson_plan'
                AND unit_key = v_key) THEN
    RAISE EXCEPTION USING ERRCODE = 'TP003', MESSAGE =
      'rollback refused: a unit row with the captured key already exists';
  END IF;
  -- R1: restore the captured row faithfully.
  INSERT INTO usage_units (id, user_id, period_type, period_key,
                           unit_kind, unit_key, scheme_id, created_at)
  VALUES (v_id, v_user, 'calendar_month', '2026-09',
          'lesson_plan', v_key, v_scheme, v_created);
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 1 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP003', MESSAGE =
      'rollback failed: restore insert affected no rows';
  END IF;
  -- R2: restore every counter to 0 WITH ITS OWN captured original
  --     timestamp (identity + repair-timestamp guarded, per-row
  --     row-count enforced; never one shared timestamp).
  n := 0;
  FOR r IN (SELECT t.user_id, t.period_type, t.period_key, t.orig_ts
              FROM (VALUES <P2_ORIGINAL_PERIODS>)
                   AS t(user_id, period_type, period_key, orig_ts)
             ORDER BY t.user_id, t.period_type, t.period_key)
  LOOP
    IF NOT EXISTS (SELECT 1 FROM usage_periods p
                    WHERE p.user_id = r.user_id AND p.period_type = r.period_type
                      AND p.period_key = r.period_key AND p.user_id <> v_inc) THEN
      RAISE EXCEPTION USING ERRCODE = 'TP003', MESSAGE =
        format('rollback refused: captured period %s/%s/%s has no matching period row',
               r.user_id, r.period_type, r.period_key);
    END IF;
    UPDATE usage_periods
       SET units_used = 0, updated_at = r.orig_ts::timestamp
     WHERE user_id = r.user_id AND period_type = r.period_type
       AND period_key = r.period_key AND user_id <> v_inc
       AND updated_at = v_ts;
    GET DIAGNOSTICS m = ROW_COUNT;
    IF m <> 1 THEN
      RAISE EXCEPTION USING ERRCODE = 'TP003', MESSAGE =
        format('rollback failed: restore for %s/%s/%s affected %s row(s), expected 1',
               r.user_id, r.period_type, r.period_key, m);
    END IF;
    n := n + 1;
  END LOOP;
  IF n <> 14 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP003', MESSAGE =
      format('rollback failed: restored %s row(s), expected 14', n);
  END IF;
  -- Post: original state fully restored — counters 0 AND each row carries
  --       its own captured original timestamp.
  FOR r IN (SELECT t.user_id, t.period_type, t.period_key, t.orig_ts
              FROM (VALUES <P2_ORIGINAL_PERIODS>)
                   AS t(user_id, period_type, period_key, orig_ts))
  LOOP
    IF NOT EXISTS (SELECT 1 FROM usage_periods p
                    WHERE p.user_id = r.user_id AND p.period_type = r.period_type
                      AND p.period_key = r.period_key AND p.user_id <> v_inc
                      AND p.units_used = 0
                      AND p.updated_at = r.orig_ts::timestamp) THEN
      RAISE EXCEPTION USING ERRCODE = 'TP003', MESSAGE =
        format('rollback post-check failed: %s/%s/%s must be counter 0 with its original updated_at',
               r.user_id, r.period_type, r.period_key);
    END IF;
  END LOOP;
  SELECT count(*) INTO n FROM usage_units WHERE user_id <> v_inc;
  IF n <> 159 THEN
    RAISE EXCEPTION USING ERRCODE = 'TP003', MESSAGE =
      'rollback post-check failed: expected 159 non-incident ledger rows';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM usage_units WHERE id = v_id
                  AND user_id = v_user AND unit_key = v_key
                  AND scheme_id = v_scheme AND created_at = v_created) THEN
    RAISE EXCEPTION USING ERRCODE = 'TP003', MESSAGE =
      'rollback post-check failed: orphan row not restored with its captured values';
  END IF;
END $$;
SELECT count(*) AS restored_nonincident_units FROM usage_units
 WHERE user_id <> 'c11bde4c-a9bb-4f41-b96a-921570cf856e';
COMMIT;
```

**Safe recheck (read-only, optional):** the `G1` guard queries without
the `DO` block — if any counter or `updated_at` differs from the repair
packet, do not roll back; investigate read-only instead.

### Verification of §13e/§13g SQL (disposable local PostgreSQL, synthetic data)

Both proposals and both rollback scripts were executed verbatim (extracted
from this document by their `-- SCRIPT:` markers) against a scratch
database on the local docker `postgres:16-alpine` instance
(`127.0.0.1:54329`), seeded with synthetic production-shaped data
(166 units / 15 period rows / 164 lessons / 14 users / 10 jobs matching
the §13f table's exact per-month ledger shapes and both orphan
identities; every period row now carries a deliberately **distinct**
original `updated_at`). The validator refuses non-loopback hosts and
creates+drops one scratch database per case.

Command:
`./venv/Scripts/python backend/validate_quota_repair_sql.py`

**Run 1 — 2026-10-16, commit `2782a8f` (superseded):** 10/10 cases
passed with a limited fingerprint (row counts, unit ids/keys, counter
sums, lesson/job counts) and rollbacks that restored counters but set
`usage_periods.updated_at` to the rollback time. That timestamp gap and
the fingerprint's column coverage are corrected in the current scripts
(captured original timestamps + full-row logical fingerprint below).

**Run 2 — 2026-10-16, current scripts: 11/11 cases passed.**

State comparison is a **full-row logical fingerprint** covering every
column of every table in the synthetic repair schema —
`usage_units` (`id`, `user_id`, `period_type`, `period_key`,
`unit_kind`, `unit_key`, `scheme_id`, `created_at`), `usage_periods`
(`id`, `user_id`, `period_type`, `period_key`, `units_used`,
`created_at`, `updated_at`), `lesson_plans` (`id`, `owner_id`,
`scheme_id`, `indicator_codes`, `source_occurrence_id`, `job_id`) and
`generation_jobs` (`id`, `owner_id`, `status`, `error_message`,
`created_at`) — complete `to_jsonb(row)` representations aggregated in
primary-key order and md5-hashed. It is a logical (row-content)
fingerprint, **not** a physical byte-for-byte database comparison. Case
11 confirms the fingerprint changes when a single previously-uncovered
field (`usage_units.created_at`, `usage_units.scheme_id` or
`usage_periods.updated_at`) changes while row counts and counter sums
stay identical.

| # | Case | Result |
|---|---|---|
| 1 | P1 repair valid; `DELETED_ORPHAN` + `REPAIRED_TS` + `P1_ORIGINAL_PERIOD` packets (original ts = seed value) | PASS |
| 2 | P1 rollback restores the **complete original full-row fingerprint**, incl. the original period `updated_at` | PASS |
| 3 | P2 repair valid; 14 distinct `P2_ORIGINAL_PERIOD` packets matching the 14 non-incident rows + captured values | PASS |
| 4 | P2 rollback restores the **complete original full-row fingerprint**, incl. each row's own `updated_at` | PASS |
| 5 | P1→P2 and P2→P1 orders converge to the same final state | PASS |
| 6 | Wrong counter / missing orphan / extra orphan / changed identity → TP001, full fingerprint unchanged after every abort | PASS |
| 7 | Tampered (extra DELETE mid-Phase-B, both proposals) → TP002, no partial commit, fingerprint unchanged | PASS |
| 8 | Rollback refuses after intervening activity (P1 and P2) → TP003, fingerprint unchanged | PASS |
| 9 | Rollback refuses after counter drift or repair-`updated_at` drift (P1 and P2) → TP003, fingerprint unchanged | PASS |
| 10 | Rollback refuses on a bad captured packet (P2: duplicated entry, missing entry, wrong identity) → TP003, fingerprint unchanged | PASS |
| 11 | Fingerprint changes when `usage_units.created_at`, `usage_units.scheme_id` or `usage_periods.updated_at` is altered (counts/sums identical) | PASS |

**Limitations (stated honestly):** the rollback scripts verify the
packet's internal consistency (restored state must equal the provided
values; all drift guards apply) but cannot detect a *mistyped but
plausible* packet value against external truth — the operator must copy
the raw `NOTICE` output verbatim and retain it. (`updated_at` is
informational for quota enforcement; only `units_used` drives gating.)
These synthetic tests validate the scripts' internal logic only — they
are **not** production verification. Production execution still requires
the explicit owner approvals described above (§13e and §13g remain
separate decisions), and remains **not executed**.

## 13h) Live enforcement test plan (APPROVAL REQUIRED — NOT EXECUTED)

Control: "enforcement is verified in the production runtime" — currently
**NOT TESTED** (no authorized POST has been issued since the deploy).

**Route & payload (minimal, `ai_mode` default is already `OFF`):**

```
POST {base}/api/generation/ab28233d-f87c-4753-98c1-fbb94acead7f/generate
Authorization: Bearer $TF_TEACHER_TOKEN        # token obtained/used by the OWNER locally
Content-Type: application/json

{
  "scheme_of_work_id": "ab28233d-f87c-4753-98c1-fbb94acead7f",
  "ai_mode": "OFF"
}
```

Empty `selected_indicator_codes` = full scheme → `requested_codes` =
every instructional indicator of the scheme (weeks 1–12 are `instruction`;
≥ 12 codes, upload-time extraction observed 20).

**Expected results:**
- **Variant A (possible now, before §13e):** HTTP **403** at the admission
  pre-check (`generation.py:817-830`), body
  `"This scheme contains {N} instructional indicators. You have 5 Free
  Tier lesson plans remaining this month. Select up to 5 indicators to
  generate now, or upgrade to Teacher Pro for unlimited generation."`
  (exact message built from the code; `remaining = 5`).
- **Variant B (authoritative, after Proposal 1/§13e):** same request →
  HTTP **403**, body `"... You have 0 Free Tier lesson plans remaining
  this month. Select up to 0 indicators to generate now, or upgrade to
  Teacher Pro for unlimited generation."` (`remaining = 0`, because
  `used = 6 > limit = 5`).
- **Zero side effects (both variants)** — asserted by a read-only probe
  after the call: no new `generation_jobs` row (count unchanged),
  `usage_units` count unchanged (6 after §13e), `units_used` unchanged,
  `lesson_plans` count unchanged.

**Side-effect analysis of the denial path (verified by reading the full
handler, `generation.py:624`–`850`):**
- The only DB write before the pre-check is a conditional
  `db.commit()` for teacher-confirmed class level (line ~686). It cannot
  fire: the test scheme has `class_level='Basic 9'`,
  `detection_status='single'` (probed).
- `require_ai_entitlement` is skipped (`ai_mode=OFF`); school/teacher
  name resolution, calendar/allocation and quota reads are read-only;
  `log_event` writes to stdout only (`logging_config.py:44`).
- The pre-check raises **before** `reserve_lesson_units` (line ~831) and
  `create_job` (line ~849) — nothing is reserved, created or counted.
- Auth = JWT verification + user read; no session/login write per request.

**What this test does NOT prove (stated honestly):** the atomic
reserve-path guard (race window: two requests passing the pre-check
simultaneously). That path is unreachable in a single denial test and
can only be exercised by local concurrency tests — `PG driver gate 22
passed (incl. threaded concurrency)` — plus, if ever needed, an approved
two-request race test. The RETURNING fix itself is proven on the
production driver stack locally, and §13f shows the deployed file is
byte-identical to the locally tested file.

**Execution mechanics (owner):** obtain a teacher JWT for the smoke
account from the owner's own authenticated session (browser DevTools
"Copy as cURL", or session storage) and run the request with the token in
a **local** environment variable — the token must never be pasted into
chat, issues, commits or logs. Approval requested: (1) POST of the
denial payload above (Variant A immediately; Variant B after §13e), and
(2) the §13e and §13g SQL transactions.

**Post-test verification (read-only):** re-run the probe queries of §13f
to confirm counts unchanged.

## 14) Residual risks / open items



- Deployment is DONE (§13d, 2026-10-15: `3ef1a41` live; §13f content-
  verified 2026-10-16). RED/NO-GO stands until the §13h live denial test
  passes AND the §13e reconciliation is approved and applied (plus an
  owner decision on Proposal 2/§13g).
- Owner decisions outstanding: §13e SQL, §13g SQL, §13h POST approval
  (token stays in the owner's local environment; never in chat/logs).
- Production-wide accounting state (§13f): all 15 period rows hold
  `units_used = 0` with ledger rows present — enforcement under-binds
  EVERY free account until §13e/§13g are applied.
- Pre-existing policy (unchanged): at exhaustion the 403 pre-check refuses
  **any** generate call, including free regenerations of already-counted
  codes; pinned as current behaviour in the journey test.
- AI allowance: guard path verified on PostgreSQL locally but not exercised
  in production (account generated 0 AI generations).
- No new product priority was started; P4/P1 semantics untouched.
