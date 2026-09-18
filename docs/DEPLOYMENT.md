# SchemeKnit — Production Deployment Guide

Architecture:

```
DOMAIN (https://app.schemeknit.com)
  │
  ├── NEXT.JS FRONTEND (Vercel / container / static host)
  │     └── talks to ↓
  │
  ├── FASTAPI BACKEND (container / PaaS)
  │     ├── MANAGED POSTGRESQL (database)
  │     ├── OBJECT STORAGE (S3-compatible: files, exports)
  │     └── RESEND (transactional email)
  │
  └── [DESKTOP EXE — separate build, not part of cloud deployment]
```

The frontend and backend are independently deployable. The frontend never
connects to PostgreSQL or object storage directly — all data access goes
through the FastAPI backend.

## 1. Environment Configuration

Copy `backend/.env.example` to `backend/.env` and fill in production values.
The application **refuses to start** (DEBUG=false) when critical values are
missing or unsafe — see `config.py: validate_production()`.

Mandatory in production:

| Variable | Why |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string (SQLite rejected in prod) |
| `SECRET_KEY` | Session signing (must not be the dev default) |
| `JWT_SECRET_KEY` | JWT signing (must not be the dev default) |
| `PUBLIC_WEB_URL` | Frontend URL (no localhost) |
| `API_BASE_URL` | Backend URL (no localhost) |
| `CORS_ORIGINS` | Allowed origins (no localhost) |
| `RESEND_API_KEY` | Transactional email (password reset) |
| `EMAIL_FROM` | Verified sending domain (not resend.dev) |
| `STORAGE_BACKEND=s3` | Object storage for user files |
| `S3_BUCKET` / `S3_ACCESS_KEY` / `S3_SECRET_KEY` | Storage credentials |
| `PLATFORM_ADMIN_BOOTSTRAP_SECRET` | One-time first-admin setup |

## 2. Database

### Create the production database

```bash
# Point at the NEW production database (not the acceptance DB)
export DATABASE_URL="postgresql://user:pass@host:5432/schemeknit"

# Create schema + run all migrations + seed system config
python -m src.tools.production_reset --reset --confirm
```

The script verifies zero customer data (users, schools, licenses, payments,
lessons, exports all = 0) and prints a PASS/FAIL report.

### Tests must never touch production

Tests use `TEST_DATABASE_URL` (separate database). The reset script refuses
to operate on any URL containing "test".

### Backups

**PostgreSQL:**
- Enable automated daily backups on the managed instance (all major
  providers support this: RDS, Cloud SQL, Neon, Supabase, Railway).
- Minimum retention: 30 days.
- Practice a restore into a staging database before relying on it.
- A backup that has never been restored is not a backup.

**Object storage:**
- Enable bucket versioning (S3, R2, B2 all support it) so deleted or
  overwritten files can be recovered.
- Configure lifecycle rules to move older versions to cold storage.
- Do not rely on the application server's local disk as the sole copy of
  user documents — that is what object storage is for.

## 3. Storage

Set `STORAGE_BACKEND=s3` and configure the S3_* variables. Any
S3-compatible provider works (AWS S3, Cloudflare R2, Backblaze B2,
DigitalOcean Spaces, MinIO). No vendor is hard-coded — see `src/storage.py`.

The local backend (`STORAGE_BACKEND=local`) is for development and
single-server deployments only.

## 4. Email

Transactional email is sent through Resend (`src/email_service.py`).

- `RESEND_API_KEY` is **server-side only**. Never expose it to browser
  code. Never use `NEXT_PUBLIC_RESEND_API_KEY`.
- `EMAIL_FROM` must be a verified sending domain (e.g.
  `notify@schemeknit.com`). Do not use `resend.dev`.
- If email sending fails, the application logs a safe operational error
  (with the key redacted) and returns a generic user-facing message.
  The underlying account/reset state is preserved.

## 5. Health & Readiness

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Process alive (liveness) |
| `GET /api/ready` | DB + storage reachable (readiness). Returns 503 if a dependency is down. No secrets in the response. |

Use these for load-balancer health checks and deployment verification.

## 6. Observability

Structured JSON logging via `structlog`. All events include a timestamp,
level, and event name. Logs are safe to ship to any log aggregator.

**Logged:**
- Startup, readiness, shutdown
- Login failures (email + IP, never the password)
- Activation events, payment events
- Password resets (who/when, never the token)
- Generation failures, export failures
- AI failures, storage failures, email failures
- Unhandled exceptions (sanitized)

**Never logged:**
- Passwords (plaintext or hashes)
- API keys / secrets (redacted to first 6 + last 4 chars)
- JWTs
- Reset tokens
- Activation secrets

## 7. Security Checklist

| Control | Status |
|---|---|
| CORS allowlist (no localhost in prod) | Enforced at startup |
| HTTPS (terminate at reverse proxy / CDN) | Required |
| JWT session invalidation after password change | pwv claim |
| Rate limiting on auth endpoints | In-memory sliding window |
| IDOR / tenant isolation | School-scoped queries |
| File access authorization | Download tokens, scoped paths |
| Email reset links | One-time, expiring, hashed at rest |
| Activation codes | Single-use, expiring |
| Platform admin bootstrap | One-time, secret-gated, 410 after first admin |
| Secret validation at startup | `validate_production()` |
| No secrets in logs | Redaction + allowlist |

Do not loosen any of these to simplify deployment.

## 8. Deployment Sequence

1. Provision managed PostgreSQL.
2. Create the production database via `production_reset`.
3. Provision S3-compatible bucket; set `STORAGE_BACKEND=s3`.
4. Verify the Resend sending domain; set `RESEND_API_KEY` + `EMAIL_FROM`.
5. Set all `.env` values (see §1).
6. Deploy the backend. Verify `/api/ready` returns 200.
7. Deploy the frontend. Verify it loads.
8. Set `PLATFORM_ADMIN_BOOTSTRAP_SECRET` to a strong value.
9. Open `/setup/platform-admin`; create the first platform admin.
10. Remove or rotate the bootstrap secret.
11. Verify `/api/ready` still returns 200 and the admin can log in.

**Do not deploy publicly until the infrastructure credentials and domain
have been deliberately configured by the owner.**
