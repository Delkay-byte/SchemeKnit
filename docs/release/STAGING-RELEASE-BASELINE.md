# Staging Release Baseline

Date: 2026-10-31  
Release candidate branch: `hardening/deepseek-groq-staging-20261030`  
Release candidate SHA: `4f15111`

## Git state

| Item | Value |
|---|---|
| Current branch | `hardening/deepseek-groq-staging-20261030` |
| Current HEAD | `4f15111` |
| `4f15111` exists | Yes |
| Reconciliation merge | `0f054de` |
| Preservation commit | `0cb4d8e` |
| Latest `origin/main` | `0b3c292` |
| Branch ahead / behind origin | `3` ahead / `0` behind |
| Working tree at baseline | clean |
| Safety branch | `safety/pre-deepseek-hardening-20261030-2200` |
| Backup ref | `refs/backups/pre-deepseek-hardening-20261030-2200` (`71e8d21`) |
| Untracked backup | `C:\Users\SAVIOUR\AppData\Local\Temp\opencode\teachflow-untracked-backup-20261030` |

No push, merge into `main`, or deployment was performed.

## Verified candidate evidence

The hardening report recorded:

- Full backend suite: **2,876 passed, 21 skipped, 0 failed, 0 errors**
- Collected: **2,897**
- Real DeepSeek generation: verified
- Real Groq fallback: verified
- Six-case KG/primary/JHS matrix: all gate-accepted
- DOCX/PDF persistence and export: verified
- Frontend TypeScript check: pass
- Frontend production build: pass
- `git diff --check`: pass

## Baseline failure reconciliation

The seven previously reported failures are resolved:

- Missing-credential auth now returns 401 with `WWW-Authenticate`.
- Five one-time-download tests use the real `context` parameter.

The 134-test collection gap is resolved: the ten missing `origin/main` modules
(142 tests) are present; the net difference was the eight pre-existing new Zeli
tests. Current total is 2,897 after additional hardening tests.

## Staging preconditions

The candidate is ready to be deployed only to a **separate staging environment**
with:

- separate frontend service,
- separate backend service,
- separate PostgreSQL database,
- staging-only secrets,
- staging-only CORS origin,
- staging-only test account,
- payment disabled.

Those services do not currently exist. See
`docs/release/STAGING-VALIDATION-REPORT.md`.
