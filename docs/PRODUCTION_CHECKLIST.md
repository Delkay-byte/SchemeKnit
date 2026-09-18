# SchemeKnit — Production Checklist: Human Inputs Required

The application is prepared for production. The following values must be
supplied by the owner before deployment. **Do not send passwords or API
keys through source files or chat messages** — set them directly in the
deployment environment.

## 1. Production domain
- The domain SchemeKnit will be served from (e.g. `schemeknit.com`).
- Frontend subdomain (e.g. `app.schemeknit.com`).
- API subdomain (e.g. `api.schemeknit.com`).
- Used for: `PUBLIC_WEB_URL`, `API_BASE_URL`, `CORS_ORIGINS`, `EMAIL_FROM`.

## 2. DNS provider / account
- Where the domain's A/CNAME records are managed.
- Needed to point the frontend and API subdomains at the hosting provider.

## 3. Hosting accounts
- Frontend hosting (Vercel, Netlify, Cloudflare Pages, or a container host).
- Backend hosting (container host, PaaS, or VM).
- The two are independently deployable.

## 4. Production DATABASE_URL
- Managed PostgreSQL connection string.
- Format: `postgresql://user:password@host:5432/schemeknit`
- Run `python -m src.tools.production_reset --reset --confirm` against it
  to create the schema + system configuration.
- Also set `TEST_DATABASE_URL` to a separate test database.

## 5. Production SECRET_KEY
- Used for session signing.
- Generate: `python -c "import secrets; print(secrets.token_urlsafe(48))"`

## 6. Platform Admin bootstrap secret
- A strong one-time secret for creating the FIRST platform admin at
  `/setup/platform-admin`.
- Generate: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
- After the first admin is created, remove or rotate this value.

## 7. Object storage credentials
- S3-compatible provider (AWS S3, Cloudflare R2, Backblaze B2, DO Spaces).
- `S3_ENDPOINT`, `S3_REGION`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`.
- Enable bucket versioning for file recovery.

## 8. RESEND_API_KEY
- Transactional email API key (server-side only).
- Never expose to browser code. Never use `NEXT_PUBLIC_RESEND_API_KEY`.

## 9. Email sender address
- `EMAIL_FROM` — must be on a verified sending domain.
- Recommended: `notify@schemeknit.com` (subdomain of the production domain).
- Do NOT use `resend.dev`.

## 10. Reply-to address
- `EMAIL_REPLY_TO` — where users reply for support.
- Recommended: `support@schemeknit.com`.

## 11. AI production configuration (if enabled)
- `AI_MODE` (currently OFF).
- If enabling AI generation: provider API key + production quotas.

## 12. Production payment details
- The payment configuration in the DB seed currently has mobile-money and
  bank-transfer details. Confirm or replace these with production values
  before accepting real payments.

## 13. Production legal / contact information
- Privacy policy, terms of service, support contact.
- Used in the frontend footer and legal pages.

---

## After deployment

1. Verify `/api/ready` returns HTTP 200.
2. Create the first platform admin at `/setup/platform-admin`.
3. Remove or rotate `PLATFORM_ADMIN_BOOTSTRAP_SECRET`.
4. Verify the admin can log in and see the console.
5. Run a test password change to confirm session invalidation works.
6. Confirm automated PostgreSQL backups are active and test a restore.
