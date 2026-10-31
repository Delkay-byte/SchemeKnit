# CI Validation Report

Date: 2026-10-31  
Workflow: `.github/workflows/ci.yml`  
Branch: `hardening/remediation-staging-20261031`

## Actual GitHub Actions run

- Run URL: `https://github.com/Delkay-byte/SchemeKnit/actions/runs/41168965791`
- Commit: `8b70d7f`
- Overall conclusion: **success**

| Job | Result |
|---|---|
| Backend tests and compile | success |
| Frontend typecheck and build | success |
| PostgreSQL migration harness | success |
| Secret scan (Gitleaks) | success |

A prior run on `b752983` failed only because tests used a local Windows
document path and an unavailable PDF converter. Those tests were made portable
or explicitly skipped when the external tool/database is absent; security checks
were not weakened.

## Local-equivalent checks

- Full deterministic backend suite: 2,920 passed, 21 skipped, 5 live deselected.
- Live provider suite: 1 passed, 4 skipped (Groq/Gemini transient throttling).
- Frontend `tsc --noEmit`: passed.
- Frontend `npm run build`: passed.
- `pip-audit -r requirements.txt`: 0 vulnerabilities.
- `npm audit --omit=dev`: 0 vulnerabilities.
- Full `npm audit`: 16 moderate dev-tool findings only.
- `git diff --check`: passed.

## CI security properties

- `permissions: contents: read`.
- No production secrets.
- No automatic deployment.
- PostgreSQL service isolated to the job.
- Concurrency cancels superseded runs.
- Gitleaks scans full history.
- Dependency audits are blocking for production dependencies.
