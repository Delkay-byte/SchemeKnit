# Staging Validation Report

Date: 2026-10-31  
Status: **BLOCKED — STAGING INFRASTRUCTURE UNAVAILABLE**

## Finding

No genuine staging environment exists in the repository, deployment
configuration, or documented infrastructure.

Evidence:

- No `render.yaml`, `render.yml`, or `.render.yaml` in the repository.
- No `.github/workflows` directory; no automated deployment pipeline.
- No staging frontend, backend, database, or Redis service is documented.
- The only documented Render services are production preview services:
  - `https://schemeknit-api.onrender.com`
  - `https://schemeknit-frontend.onrender.com`
- No `RENDER_API_KEY` or Render dashboard access is present in the environment.
- Repository documentation repeatedly records that production deployment is
  owner-side because no deploy hook or dashboard access is available.
- There is no separate staging `DATABASE_URL`, no staging frontend origin, and
  no staging test account.

Using the Render preview services as “staging” would violate the task rules:
they are the production-equivalent services and use the production database and
secrets.

## Decision

Staging deployment and staging acceptance are stopped. No production service
was used as a substitute. No staging or production deployment was attempted.

## Required staging infrastructure

| Component | Required |
|---|---|
| Frontend | New Render Static/Web Service, e.g. `schemeknit-staging-frontend`, isolated from production |
| Backend | New Render Web Service, e.g. `schemeknit-staging-api`, isolated from production |
| Database | New PostgreSQL instance, staging-only credentials, never production `DATABASE_URL` |
| Redis | Optional; required only if a distributed rate limiter is introduced |
| DNS/URL | Staging-only origin recorded in `CORS_ORIGINS` and frontend API base URL |
| Secrets | Staging-only `SECRET_KEY`, `JWT_SECRET_KEY`, `DEEPSEEK_API_KEY`, `GROQ_API_KEY`, `RESEND_API_KEY` |
| Payment | `PAYSTACK_ENABLED=false`, `PAYSTACK_MODE=test` |
| Logging | Staging log drain or dashboard access, no secrets in logs |
| Account | Synthetic staging teacher and admin accounts |
| Access | Owner-authorized Render access or deploy hook |

## Required provider configuration

```env
ZELI_ENABLED=true
ZELI_PROVIDER=deepseek
ZELI_FALLBACK_PROVIDER=groq
ZELI_MODEL=deepseek-flash
DEEPSEEK_API_KEY=<staging secret>
GROQ_API_KEY=<staging secret>
GROQ_MODEL=openai/gpt-oss-120b
AI_MODE=groq
PAYSTACK_ENABLED=false
PAYSTACK_MODE=test
```

Do not commit secrets. Do not reuse production secrets in staging without an
explicit owner decision.

## What was not done

- No staging deployment.
- No staging database creation.
- No staging smoke tests.
- No security-header/CSP behavior against a live staging origin.
- No staging `noindex` verification.
- No live provider test against staging.
- No OWASP ZAP scan against staging.

## Next action

Owner must provision the isolated services and provide authorized access. Then
the next task can deploy the candidate, run the full staging checklist, and
return `READY FOR PRODUCTION RELEASE REVIEW` or a specific blocker.
