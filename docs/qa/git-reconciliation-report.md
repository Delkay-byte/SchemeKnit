# Git Reconciliation Report

Date: 2026-10-30
Branch: `hardening/deepseek-groq-staging-20261030`

## Starting state

| Item | Value |
|---|---|
| Starting branch | `main` |
| Starting HEAD | `43bb266` |
| Latest `origin/main` | `0b3c292` |
| Local commits ahead / behind | `0` ahead / `5` behind |
| Worktree state | 106 modified tracked files + 41 untracked files |
| Staged changes | none |

The local branch was five commits behind `origin/main`. The working tree also
contained a large uncommitted DeepSeek verification tranche created before the
latest release work. No existing work was discarded.

## Safety protection

| Protection | Reference |
|---|---|
| Safety branch at starting HEAD | `safety/pre-deepseek-hardening-20261030` |
| Tracked-change snapshot commit | `71e8d2190b400745398102c3b46bf07ddeaa011f` |
| Backup ref | `refs/backups/pre-deepseek-hardening-20261030` |
| Untracked-file backup | `C:\Users\SAVIOUR\AppData\Local\Temp\opencode\teachflow-untracked-backup-20261030` (41 files) |
| Preservation commit on integration branch | `0cb4d8e` |
| Merge commit with `origin/main` | `0f054de` |

The backup commit contains every tracked change from the starting worktree. The
untracked backup contains every untracked file, including the new DeepSeek
tests and frontend artifacts. Recovery is possible without touching production.

## Integration strategy

1. Snapshotted the complete local worktree in one commit (`0cb4d8e`).
2. Merged `origin/main` into the snapshot (`0f054de`).
3. Resolved all 14 conflicts intentionally:
   - Release-owned files (`config.py`, `database.py`, `routers/auth.py`,
     `routers/generation.py`, release tests, landing page) took `origin/main`
     so the latest commercial/payment/webhook work is intact.
   - The four DeepSeek/Zeli files were merged manually:
     `generation_pipeline.py`, `generation_prompt.py`, `zeli_generation.py`,
     `docx_parser.py`.
4. Verified the four merged files differ from `origin/main` only by the
   intended DeepSeek changes.
5. Added the missing origin test modules. No test was deleted to make the
   count match.

## The 134-test discrepancy

The previous working tree collected 2,721 tests. `origin/main` collects 2,855.
The difference is explained exactly by ten test modules that existed on
`origin/main` but not in the previous tree, offset by the eight new
DeepSeek mapping tests already added locally.

| Missing module | Tests |
|---|---:|
| `tests/test_commercial_model.py` | 21 |
| `tests/test_credit_generation.py` | 7 |
| `tests/test_database_url.py` | 9 |
| `tests/test_paystack_live_readiness.py` | 12 |
| `tests/test_paystack_subscriptions.py` | 22 |
| `tests/test_prepaid_payments.py` | 41 |
| `tests/test_referrals.py` | 11 |
| `tests/test_webhook_sweeper.py` | 13 |
| `tests/test_webhook_sweeper_pg.py` | 1 |
| `tests/test_website_entitlement_integration.py` | 5 |
| **Total missing** | **142** |
| Less the 8 pre-existing new Zeli mapping tests | **-8** |
| **Net difference** | **134** |

No test-discovery failure remained after reconciliation. The new modules are
now present and collect normally. The two PG-only cases remain environment
skipped when no disposable PostgreSQL URL is configured; that is expected.

## Collection after reconciliation

- Previous tree: **2,721**
- `origin/main`: **2,855**
- Reconciled branch: **2,897 collected** (2,876 passed, 21 skipped)
- The extra 42 tests are 36 new tests in four added modules plus 6 new
  fallback-configuration tests in `test_zeli_deepseek_config.py`.

## Conflict / test corrections

- Four previously failing parser tests were fixed by correcting parser logic,
  not by changing expectations:
  - multi-code cell description bleed,
  - KG indicator range preservation,
  - duplicate-code `NameError` (two tests).
- The five stale download tests now match the real
  `export_docx_combined(..., context=None)` signature.
- Missing-credential authentication now returns `401` with a
  `WWW-Authenticate` challenge instead of FastAPI's default `403`.

## Remaining worktree notes

- `backend/.env` is intentionally untracked and not part of the repository.
  It was cleaned locally: one `AI_MODE=groq`, one
  `ZELI_FALLBACK_PROVIDER=groq`, `PAYSTACK_ENABLED=false`,
  `PAYSTACK_MODE=test`.
- No production database, credential, payment, balance or entitlement record
  was touched.
