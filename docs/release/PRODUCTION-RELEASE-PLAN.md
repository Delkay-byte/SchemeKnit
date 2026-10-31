# Production Release Plan

Date: 2026-10-31  
Status: **NOT AUTHORIZED — staging infrastructure unavailable**

## Release candidate

| Item | Value |
|---|---|
| Source branch | `hardening/deepseek-groq-staging-20261030` |
| Candidate commit | `4f15111` |
| Reconciliation merge | `0f054de` |
| Target branch | `main` |
| Target remote | `origin` |
| Merge method | reviewed merge commit; no squash without owner approval |
| Migrations | none added by this hardening |
| Push | **not authorized now** |

## Production environment variables required

Names only; values are owner-managed in Render and must never be committed:

- `DEEPSEEK_API_KEY`
- `ZELI_PROVIDER=deepseek`
- `ZELI_FALLBACK_PROVIDER=groq`
- `ZELI_MODEL=deepseek-flash`
- `GROQ_API_KEY`
- `GROQ_MODEL=openai/gpt-oss-120b`
- `AI_MODE=groq`
- `PAYSTACK_ENABLED=false`
- `PAYSTACK_MODE=test`

Existing production variables (`DATABASE_URL`, `SECRET_KEY`,
`JWT_SECRET_KEY`, CORS origins) are not changed by this plan.

## Required sequence after owner authorization

1. Confirm staging acceptance with isolated services/database.
2. Freeze `main`; confirm no conflicting owner commits.
3. Create a release PR from the candidate branch to `main`.
4. Require CI: backend tests, frontend typecheck/build, dependency/secret scan.
5. Review the diff and the QA reports.
6. Merge the approved commit.
7. Record the exact merge SHA.
8. Deploy backend first; wait for health.
9. Deploy frontend; verify the staging/production origin mapping.
10. Run post-deploy checks:
    - `/api/health`,
    - login/logout/revocation,
    - DeepSeek generation,
    - controlled Groq fallback,
    - cache/credit behaviour,
    - DOCX/PDF export,
    - payment-disabled check.
11. Monitor logs and provider errors.

## Rollback

- Redeploy the prior production commit/SHA.
- No migration downgrade is required for this hardening.
- Preserve database backups; do not delete lesson/credit rows.
- Restore previous provider environment values only if they were changed.
- Investigate before retrying.

## Approval gates

Owner must explicitly approve:

- staging infrastructure creation,
- staging credentials,
- release branch push,
- PR merge to `main`,
- production environment changes,
- production deployment,
- any migration.

No approval is implied by this document.
