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
   distinct lessons this month (self-heals 2026-11-01). Recommended: make
   the ledger reflect what was actually accepted:
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

**Proposed correction** (semantics unchanged from §12.5; now with hard
preconditions, `RETURNING` evidence, exact scope and a rollback path —
re-verified against production state on 2026-10-16, see §13f):

```sql
-- PROPOSAL 1 (§13e) — incident account ONLY. NOT EXECUTED as of 2026-10-16.
-- Scope: rows of user c11bde4c-a9bb-4f41-b96a-921570cf856e, period 2026-10.
BEGIN;

-- Hard preconditions (assertions match the 2026-10-16 read-only probes;
-- if ANY assert fails, the transaction aborts — re-probe, re-approve).
DO $$
DECLARE n int;
BEGIN
  SELECT units_used INTO n FROM usage_periods
   WHERE user_id = 'c11bde4c-a9bb-4f41-b96a-921570cf856e'
     AND period_type = 'calendar_month' AND period_key = '2026-10'
     FOR UPDATE;                      -- row lock: blocks concurrent reservation
  ASSERT n = 0, 'precondition failed: counter is not 0';
  SELECT count(*) INTO n FROM usage_units
   WHERE user_id = 'c11bde4c-a9bb-4f41-b96a-921570cf856e'
     AND period_type = 'calendar_month' AND period_key = '2026-10';
  ASSERT n = 7, 'precondition failed: expected 7 unit rows';
  SELECT count(*) INTO n FROM usage_units u
   WHERE u.user_id = 'c11bde4c-a9bb-4f41-b96a-921570cf856e'
     AND u.period_type = 'calendar_month' AND u.period_key = '2026-10'
     AND EXISTS (SELECT 1 FROM lesson_plans l
                  WHERE l.owner_id = u.user_id AND l.scheme_id = u.scheme_id
                    AND jsonb_exists(l.indicator_codes::jsonb,
                                     split_part(u.unit_key, ':', 2)));
  ASSERT n = 6, 'precondition failed: expected 6 matched units';
  SELECT count(*) INTO n FROM lesson_plans
   WHERE owner_id = 'c11bde4c-a9bb-4f41-b96a-921570cf856e';
  ASSERT n = 6, 'precondition failed: expected 6 persisted lessons';
  SELECT count(*) INTO n FROM generation_jobs
   WHERE owner_id = 'c11bde4c-a9bb-4f41-b96a-921570cf856e' AND status = 'failed';
  ASSERT n = 3, 'precondition failed: expected 3 failed jobs';
END $$;

-- S1: delete the orphan unit row (work never persisted = zero charge).
--     CAPTURE the RETURNING output — the id is required for the rollback path.
DELETE FROM usage_units u
 WHERE u.user_id = 'c11bde4c-a9bb-4f41-b96a-921570cf856e'
   AND u.period_type = 'calendar_month' AND u.period_key = '2026-10'
   AND NOT EXISTS (
     SELECT 1 FROM lesson_plans l
      WHERE l.owner_id = u.user_id AND l.scheme_id = u.scheme_id
        AND jsonb_exists(l.indicator_codes::jsonb, split_part(u.unit_key, ':', 2)))
 RETURNING u.id, u.unit_key, u.created_at;
-- Expected: EXACTLY 1 row,
--   unit_key = ab28233d-f87c-4753-98c1-fbb94acead7f:B9.1.1.2.1

-- S2: recompute the counter from the corrected ledger.
UPDATE usage_periods p
   SET units_used = (
         SELECT count(*) FROM usage_units u
          WHERE u.user_id = p.user_id AND u.period_type = p.period_type
            AND u.period_key = p.period_key),
       updated_at = now()
 WHERE p.user_id = 'c11bde4c-a9bb-4f41-b96a-921570cf856e'
   AND p.period_type = 'calendar_month' AND p.period_key = '2026-10'
   AND p.units_used = 0
 RETURNING p.units_used;
-- Expected: EXACTLY 1 row, units_used = 6

-- Guard: if S1 or S2 returned anything other than the expected rows,
-- ROLL BACK instead of committing (psql: \rollback, else ROLLBACK;).
COMMIT;

-- Post-correction verification (read-only):
SELECT units_used FROM usage_periods
 WHERE user_id = 'c11bde4c-a9bb-4f41-b96a-921570cf856e' AND period_key = '2026-10';
-- Expected: 6
SELECT count(*) FROM usage_units
 WHERE user_id = 'c11bde4c-a9bb-4f41-b96a-921570cf856e' AND period_key = '2026-10';
-- Expected: 6
```

**Rollback** (only if the executed change must be reverted later; uses the
`S1` `RETURNING` values captured at execution time):

```sql
BEGIN;
INSERT INTO usage_units
  (id, user_id, period_type, period_key, unit_kind, unit_key, scheme_id, created_at)
VALUES
  ('<captured id>', 'c11bde4c-a9bb-4f41-b96a-921570cf856e', 'calendar_month', '2026-10',
   'lesson_plan', 'ab28233d-f87c-4753-98c1-fbb94acead7f:B9.1.1.2.1',
   'ab28233d-f87c-4753-98c1-fbb94acead7f', '<captured created_at>');
UPDATE usage_periods
   SET units_used = 0, updated_at = now()
 WHERE user_id = 'c11bde4c-a9bb-4f41-b96a-921570cf856e'
   AND period_type = 'calendar_month' AND period_key = '2026-10'
   AND units_used = 6;
COMMIT;
```

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

## 13g) Proposal 2 — all-accounts reconciliation (SEPARATE APPROVAL — NOT EXECUTED)

New evidence from §13f (the defect affected every account) widens the
historical-reconciliation control beyond §13e. This proposal is **not**
part of the §13e approval; it needs its own explicit owner decision.
Semantics: delete every ledger row whose work was never persisted (2 rows
if run before Proposal 1… — scoped here to the 1 non-incident orphan), then
recompute each non-incident period counter from its ledger.

```sql
-- PROPOSAL 2 — all accounts EXCEPT c11bde..856e (that account is §13e/Proposal 1).
-- Order-independent: can run before or after Proposal 1.
-- NOT EXECUTED as of 2026-10-16.
BEGIN;

DO $$
DECLARE n int;
BEGIN
  -- 14 non-incident period rows, all still counter 0
  SELECT count(*) INTO n FROM usage_periods
   WHERE user_id <> 'c11bde4c-a9bb-4f41-b96a-921570cf856e';
  ASSERT n = 14, 'precondition failed: expected 14 non-incident period rows';
  SELECT count(*) INTO n FROM usage_periods
   WHERE user_id <> 'c11bde4c-a9bb-4f41-b96a-921570cf856e' AND units_used <> 0;
  ASSERT n = 0, 'precondition failed: a non-incident counter is not 0';
  -- 159 non-incident ledger rows (166 total − incident 7)
  SELECT count(*) INTO n FROM usage_units
   WHERE user_id <> 'c11bde4c-a9bb-4f41-b96a-921570cf856e';
  ASSERT n = 159, 'precondition failed: expected 159 non-incident unit rows';
  -- exactly 1 non-incident orphan (the MID-TERM empty-run row)
  SELECT count(*) INTO n FROM usage_units u
   WHERE u.user_id <> 'c11bde4c-a9bb-4f41-b96a-921570cf856e'
     AND NOT EXISTS (
       SELECT 1 FROM lesson_plans l
        WHERE l.owner_id = u.user_id AND l.scheme_id = u.scheme_id
          AND jsonb_exists(l.indicator_codes::jsonb, split_part(u.unit_key, ':', 2)));
  ASSERT n = 1, 'precondition failed: expected exactly 1 non-incident orphan';
END $$;

-- S1: delete the non-incident orphan; CAPTURE RETURNING for rollback.
DELETE FROM usage_units u
 WHERE u.user_id <> 'c11bde4c-a9bb-4f41-b96a-921570cf856e'
   AND NOT EXISTS (
     SELECT 1 FROM lesson_plans l
      WHERE l.owner_id = u.user_id AND l.scheme_id = u.scheme_id
        AND jsonb_exists(l.indicator_codes::jsonb, split_part(u.unit_key, ':', 2)))
 RETURNING u.id, u.user_id, u.period_key, u.unit_key, u.created_at;
-- Expected: EXACTLY 1 row — user 1474a7..(full id), period 2026-09,
--   code 'MID-TERM (05-11-2026 to 06-11-', created 2026-09-26 15:30:23.633320

-- S2: recompute every non-incident counter from its ledger.
UPDATE usage_periods p
   SET units_used = sub.matched, updated_at = now()
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
         WHERE u.user_id <> 'c11bde4c-a9bb-4f41-b96a-921570cf856e'
         GROUP BY u.user_id, u.period_type, u.period_key
       ) sub
 WHERE p.user_id = sub.user_id
   AND p.period_type = sub.period_type
   AND p.period_key = sub.period_key
   AND p.units_used = 0
 RETURNING p.user_id, p.period_key, p.units_used;
-- Expected: EXACTLY 14 rows with values from the §13f table
--   (27, 5, 5, 5, 5, 42, 34, 5, 5, 5, 5, 5, 5, 5).
-- NOTE: S2's SET assigns sub.matched directly (filtered count), so the
--   expected values are the §13f "matched" column regardless of delete order.

-- Guard: if S1/S2 row counts differ from expected, ROLL BACK.
COMMIT;
```

**Consequence the owner should accept explicitly:** after Proposal 2,
`4995a6..6364` (34), `1474a7..9ed9` (5 in 2026-10) and two other
October accounts sit at/over the Free Tier limit of 5 and will receive
403s for new distinct generation until 2026-11-01 — correct Free Tier
behaviour, but a user-visible change for those accounts.

**Rollback:** captured `S1 RETURNING` row re-inserted with the same
columns (as in §13e's rollback block) plus `UPDATE usage_periods SET
units_used = 0 … WHERE user_id = <id> AND units_used = <returned value>`
for the 14 rows (values listed in the §13f table).

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
