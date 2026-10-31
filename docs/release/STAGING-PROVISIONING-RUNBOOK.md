# Staging Provisioning Runbook

Date: 2026-10-31  
Status: **BLOCKED — no staging infrastructure or Render/Neon access**

## Required architecture

| Component | Requirement |
|---|---|
| Frontend | Separate Render service, e.g. `schemeknit-staging-frontend` |
| Backend | Separate Render service, e.g. `schemeknit-staging-api` |
| Database | Separate PostgreSQL database / Neon branch with staging role |
| Frontend origin | Exact staging origin, e.g. `https://schemeknit-staging-frontend.onrender.com` |
| Backend origin | Exact staging API origin |
| CORS | Only the staging frontend origin |
| Secrets | Staging-only `SECRET_KEY`, `JWT_SECRET_KEY`, `SECURITY_HMAC_KEY`, provider keys |
| Payments | `PAYSTACK_ENABLED=false`, `PAYSTACK_MODE=test` |
| Logs | Staging log access; no secrets |
| Account | Synthetic teacher/admin accounts |

Do not use production `DATABASE_URL`, `DIRECT_URL`, secrets or users.

## Owner actions required

1. Confirm Render account access and whether free-tier staging services are
   available without new charges.
2. Confirm Neon access and create a separate staging database/branch.
3. Create the two staging services from the release branch.
4. Set the environment variables listed in `docs/release/STAGING-VALIDATION-REPORT.md`.
5. Provide authorized deploy access or trigger the deploy owner-side.
6. Confirm the exact frontend/backend URLs for CORS and SEO.
7. Confirm staging test account creation method.

## Validation after provisioning

- Health and version endpoints.
- Database migrations and seed.
- Frontend-to-backend connectivity and CORS.
- Login, lockout, MFA enrollment, logout.
- DeepSeek generation and Groq fallback.
- Credits/cache.
- DOCX/PDF exports.
- SEO metadata, robots, sitemap and noindex.
- Security headers.
- No production data.

## Cost rule

Do not create paid resources or recurring charges without explicit owner
approval. If free-tier staging is not genuinely available, stop and report the
cost decision rather than using production.
