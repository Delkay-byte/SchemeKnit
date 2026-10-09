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

No Render access from this side — deployment is owner-side:

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

## 14) Residual risks / open items

- Deployment + owner verification (§12) outstanding — RED/NO-GO stands until
  the fixed build is deployed AND the counter is observed incrementing
  (or the backfilled `used=6` is observed).
- Owner evidence (logs, DB rows, deployed SHA) still requested (§4).
- Pre-existing policy (unchanged): at exhaustion the 403 pre-check refuses
  **any** generate call, including free regenerations of already-counted
  codes; pinned as current behaviour in the journey test.
- AI allowance: guard path verified on PostgreSQL locally but not exercised
  in production (account generated 0 AI generations).
- No new product priority was started; P4/P1 semantics untouched.
