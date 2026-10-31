# SchemeKnit — Zero-Cost Infrastructure Assessment

Date: 2026-10-31  
Branch: `chore/zero-cost-pilot-20261031`  
Scope: friends-and-family pilot for 5–10 trusted teachers, no paid infrastructure, no live payments.

This assessment separates **platform hosting** from **AI usage**. Hosting can remain at GHS 0;
AI generation is not free merely because hosting is free.

## Evidence and limits

- Account state was read through existing authenticated access: GitHub CLI, Render API, and
  Cloudflare API. No passwords or secret values are reproduced here.
- Neon, DeepSeek, Groq, Paystack and Resend dashboards were **not** available from this
  environment. Their rows below distinguish configuration evidence from dashboard evidence.
- No live AI call, payment, database write, deployment or DNS change was made.
- Free-tier limits were checked against official documentation on 2026-10-31. Limits can
  change; re-check before inviting teachers.

## A. Existing account inventory

| Platform | Account access confirmed? | Existing resources | Free eligibility | Notes |
|---|---|---|---|---|
| GitHub | Yes — `gh` authenticated as `Delkay-byte` | Public repo `Delkay-byte/SchemeKnit`; one CI workflow; no repository secrets | FREE — sustainable (public repo standard runners) | Recent CI run `41170414139` succeeded; four jobs; ~10.5 minutes total. |
| Render | Yes — read-only API key | Six `free` web services in one Hobby workspace, including `schemeknit-frontend` and `schemeknit-api`; no Render Postgres, cron job or background worker | FREE — restricted | Both SchemeKnit services deploy `main`, region Oregon. No `render.yaml`; configuration is dashboard-only. |
| Neon | No — no API token or console access | Production `DATABASE_URL` points at a pooled Neon host in `us-east-2`, database `neondb` | FREE — restricted | Project plan, storage, compute usage and branch count are UNVERIFIED. |
| Cloudflare | Yes — API token verified, account active | R2 bucket `schemeknit` (Standard, WEUR, 0 objects, 0 bytes); no Pages projects; one unrelated Worker `dzidel-platform-staging` | R2: FREE — payment method required for the R2 subscription (already active); Workers/Pages: FREE — restricted | R2 is already configured in the Render backend. No Pages project exists. |
| DeepSeek | Credential present in Render backend; dashboard unverified | `DEEPSEEK_API_KEY` set; `ZELI_PROVIDER=deepseek`; `ZELI_MODEL=deepseek-flash` | PAID — no published free allowance | Balance, granted credit and spend limit are UNVERIFIED. No live call was made. |
| Groq | Credential present in Render backend; dashboard unverified | `GROQ_API_KEY` set; `GROQ_MODEL=openai/gpt-oss-120b`; fallback and Standard enrichment | FREE — restricted (rate limits) | Free-plan limits apply at organization level. Dashboard plan is UNVERIFIED. |
| Paystack | Configuration confirmed; dashboard unverified | Test-mode keys present; `PAYSTACK_ENABLED=false`; `PAYSTACK_MODE=test` | FREE while disabled/test | No live payments. Keep both values unchanged for the pilot. |
| Resend | Configuration confirmed; dashboard unverified | `RESEND_API_KEY` set; `EMAIL_FROM=onboarding@resend.dev`; `PREVIEW_MODE=true` | FREE — restricted | `resend.dev` can send only to the Resend account owner's address. External teacher email is blocked until a domain is verified. |
| Domain | No | No `schemeknit.com`; no DNS change | PAID later | Continue on `*.onrender.com` for the pilot. Do not purchase or configure DNS now. |

## B. Component-by-component cost assessment

| Component | Current implementation | Existing service | Free option | Limits | Sustainable for pilot? |
|---|---|---|---|---|---|
| Frontend hosting | Next.js 16.4.3, SSR, route handlers, middleware | Render free web service `schemeknit-frontend` | Render free web service | 512 MB RAM, 0.1 CPU, sleeps after 15 min idle, ephemeral disk, 750 shared instance hours/workspace, 5 GB Hobby bandwidth, 500 build minutes | Yes, with cold starts and shared-hour risk |
| Backend hosting | FastAPI, Python 3.13, in-process background generation | Render free web service `schemeknit-api` | Render free web service | Same free limits; no persistent disk, no shell, no cron/worker on Free; service-initiated traffic can be suspended | Yes, with cold starts and restart risk |
| Database | PostgreSQL via SQLAlchemy; Neon pooled URL; DB-backed rate limits | Neon Free (plan unverified) | Neon Free | 100 projects, 10 branches/project, 100 CU-hours/project/month, 1 GB/project, 20 GB/account, 5 GB egress/project, autosuspend after 5 min, 6-hour restore window, 1 manual snapshot, no scheduled backups | Yes for 5–10 teachers; backup and compute headroom must be watched |
| File storage | Scheme originals on local disk (`~/teachflow_data/uploads`); exports under `exports/`; S3/R2 only used by `/api/ready` | Render ephemeral disk + Cloudflare R2 bucket | R2 Free: 10 GB-month, 1M Class A, 10M Class B, free egress | Local files lost on restart/sleep/redeploy. R2 is not wired into upload/export code today. | Partially: parsed curriculum persists in PostgreSQL; original upload and download cache do not |
| Background processing | FastAPI background tasks and in-process generation jobs with heartbeat/stale reclaim | Render web process | Same process | No separate worker on Free; process restart interrupts in-flight work; stale jobs are reclaimed after 60 min | Yes for low-frequency pilot, with retry expectation |
| Scheduled jobs | Paystack webhook sweeper exists as a one-shot CLI | None scheduled | GitHub Actions manual dispatch (public repo) | Actions schedule minimum 5 minutes, delays possible, scheduled workflows disabled after 60 days of repo inactivity; repo has no secrets configured | Yes manually; no automatic schedule until owner configures a pilot DB secret |
| Rate limiting | Database-backed shared counters (`RATE_LIMIT_BACKEND=db`) | Neon PostgreSQL | Neon Free | Uses DB rows; no Redis needed; connection pool default 5 + 10 overflow | Yes |
| Monitoring | Structured JSON logs, `/api/health`, `/api/ready`, optional alert webhook (unset) | Render logs, Neon metrics | Render Hobby logs (7 days), Neon Free metrics (1 day) | No HTTP request logs on Hobby; no central alert delivery; no Sentry | Yes with manual owner review; not proactive |
| Email | Resend password-reset and payment email | Resend Free | 3,000/month, 100/day, 3 domains | External recipients require a verified domain. `onboarding@resend.dev` only reaches the account owner. | No for external password resets; manual owner reset required |
| Security | HTTPS, CORS allow-list, JWT, bcrypt, MFA, DB rate limits, security headers | Render TLS + app controls | Included | HSTS disabled; CSP report-only; no WAF on Hobby; public repo | Acceptable for invited pilot, not a public launch |
| AI — primary | DeepSeek `deepseek-flash` via Zeli | DeepSeek API | None published | Paid per token; no free tier; 2,500 concurrency; balance unverified | Usage-based, not zero-cost |
| AI — fallback | Groq `openai/gpt-oss-120b`, one bounded attempt | Groq Free | 30 RPM, 1,000 RPD, 8,000 TPM, 200,000 TPD for this model | 429 on limits; one fallback attempt only | Yes for low volume, with 429 handling |
| CI | GitHub Actions: backend, frontend, PostgreSQL, Gitleaks | GitHub Free public repo | Standard runners free for public repos | Public repo only; no private-repo minute budget needed | Yes |
| Domain | Render subdomains | Render | Included `*.onrender.com` | No custom domain; SEO/canonical work deferred | Yes temporarily |

## C. Free-tier restrictions by provider

### Render

- Free web services: 0.1 CPU / 512 MB RAM; sleep after 15 minutes without inbound traffic;
  spin-up takes about one minute (measured cold start on 2026-10-31: API 82.96 s, web 23.95 s).
- 750 free instance hours per workspace per calendar month, shared by all free services.
  Six free services already exist. Keeping two SchemeKnit services warm 24/7 would consume
  about 1,460 hours and exhaust the allowance. Accept sleep.
- Ephemeral filesystem: uploads, local SQLite and generated files are lost on redeploy,
  restart or sleep. Free services cannot attach a persistent disk.
- Hobby bandwidth: 5 GB/month included; overage is $0.15/GB if a payment method exists,
  otherwise free services are suspended for the rest of the month.
- Build pipeline: 500 minutes/month; overage $5 per 1,000 minutes or builds disabled without
  a payment method.
- Free services cannot run cron jobs, background workers, one-off jobs or shell access.
  Cron jobs have a $1/month minimum on paid compute.
- Free services can be restarted at any time and may be suspended for unusually high
  service-initiated traffic (database, AI, object storage).
- Outbound SMTP ports 25/465/587 are blocked. Resend uses HTTPS, so this does not block email.
- Free Postgres exists but is not used and is unsuitable: 1 GB, expires after 30 days, no backups.

### Neon

- Free plan is permanent and requires no credit card.
- 100 projects, 10 branches per project, 100 CU-hours per project per month.
- 1 GB PostgreSQL storage per project, 20 GB total per account; 5 GB public egress per project.
- Compute autosuspends after 5 minutes idle; it cannot be disabled on Free.
- 6-hour instant-restore window capped at 1 GB of changes; one manual snapshot; no scheduled
  backups on Free.
- Connection pooling is included (PgBouncer, transaction mode). Use the pooled URL for the
  app; use a direct URL for `pg_dump`/`pg_restore`.
- Exceeding CU-hours or egress suspends compute until the next period; exceeding storage
  blocks writes. Limits do not delete data.

### Cloudflare

- **R2:** 10 GB-month storage, 1M Class A operations, 10M Class B operations, free egress.
  R2 requires an R2 subscription checkout and normally a payment method; the account already
  has an active bucket, so do not create another subscription. The bucket is empty.
- **Workers Free:** 100,000 requests/day, 10 ms CPU per request, 128 MB memory, 50 subrequests,
  64 environment variables, 5 cron triggers. These limits make a Next.js SSR + 50 MB upload
  workload a poor fit. OpenNext supports Next.js 16, but CPU and memory limits remain the
  blocker. Do not migrate the frontend or backend for the pilot.
- **Pages Free:** 500 builds/month, 20,000 files, 25 MiB per file, 100 projects. Static Pages
  cannot host the authenticated SSR application as-is.

### GitHub Actions

- Standard GitHub-hosted runners are free for public repositories. This repository is public.
- Scheduled workflows: shortest interval is 5 minutes; runs may be delayed; scheduled
  workflows are disabled automatically after 60 days without repository activity.
- No repository secrets are configured. A manual recovery workflow is prepared but inactive.
- Keep `permissions: contents: read`; do not put database URLs or API keys in YAML.

### Resend

- Free: 3,000 emails/month, 100/day, 3 domains, 30-day data retention.
- A verified domain is required to send to other people. `onboarding@resend.dev` is restricted
  to the Resend account owner's address. External teacher password resets will fail with 403
  until a domain is verified.
- Registration does not require email verification, so the pilot can create accounts without
  email. Use owner-side password resets during the pilot.

### DeepSeek and Groq

- DeepSeek has no published free tier. `deepseek-flash` is billed per token; the account
  balance and any granted credit are unverified.
- Groq Free has organisation-level limits. For `openai/gpt-oss-120b`: 30 RPM, 1,000 RPD,
  8,000 TPM, 200,000 TPD. A 429 is handled by one bounded fallback attempt.
- Existing credentials do not imply free usage. Monitor provider dashboards; do not enable
  billing or change API plans for this assessment.

### Paystack

- Test mode is free and takes no real money. `PAYSTACK_ENABLED=false` and
  `PAYSTACK_MODE=test` are confirmed in the Render backend. Keep them.
- Live Paystack fees are a future commercial cost, not a pilot infrastructure cost.

### AI cost protection already in the code

- Free accounts have a monthly lesson-plan allowance and a separate AI-generation
  allowance; the AI ledger is calendar-month and server-clock based
  (`src/ai_quota.py`).
- One successful AI-assisted request consumes one unit; provider failures,
  malformed output and quality-gate failures consume zero.
- `ZELI_MAX_TOKENS=2000` bounds completion size; retries are bounded to transient
  failures; fallback is one attempt to Groq.
- Generation is serialised per owner+scheme by a process lock and a PostgreSQL
  advisory lock, so duplicate concurrent requests cannot double-charge.
- Missing: a provider-side spend limit and an owner alert. Set those in the
  DeepSeek dashboard before inviting teachers.

## Repository and secret hygiene

- Repository is public. Gitleaks was run against all 198 commits and the working
  tree (32.15 MB scanned) with redaction.
- 11 findings were reported, all false positives:
  - 10 `sk_live_placeholder` / `sk_test_placeholder` strings in
    `backend/tests/test_paystack_live_readiness.py` (11 characters after the
    prefix; test fixtures, not live keys).
  - 1 UUID in a stored CORS test-result line
    (`frontend/e2e/curriculum-workspace-acceptance/results.txt`) matched the
    generic API-key rule.
- No active credential exposure was identified. No value was printed and no Git
  history was rewritten.
- `.env` files are ignored; `.env.example` contains placeholders only. No
  repository Actions secrets are configured.
- Do not put `PILOT_INVITE_CODE`, database URLs or API keys in source, workflow
  YAML, screenshots or chat.

## D. Recommended temporary architecture

### Primary zero-cost architecture

```
Teacher browser
  │ HTTPS
  ▼
Render free web service: schemeknit-pilot-web (Next.js 16, SSR)
  │  NEXT_PUBLIC_API_URL
  ▼
Render free web service: schemeknit-pilot-api (FastAPI, Python 3.13)
  ├── Neon Free project: schemeknit-pilot (PostgreSQL, pooled URL)
  ├── Cloudflare R2 bucket: schemeknit (prefix `pilot/`, prepared but not wired)
  ├── DeepSeek API (paid usage; primary Zeli)
  ├── Groq API (free tier; one fallback attempt)
  └── Resend (owner-only test sender; manual password resets)
GitHub Actions (manual only) ──► one bounded webhook sweep against pilot DB
```

This is a **new, isolated** pilot stack. Do not point the existing production services at the
pilot database, and do not point the pilot at the production database.

### Fallback architecture

If two additional Render free services would exhaust the workspace's 750 hours:

1. Run the pilot on one Render free web service serving only the API, and host the frontend
   locally for the owner's supervised sessions; or
2. Defer the pilot until the workspace has fewer active free services; or
3. Use the owner's local Docker stack over a private network for a hands-on demonstration,
   with no external teacher access.

Do not migrate to Cloudflare Workers Free to avoid Render hours. The 10 ms CPU limit is not
compatible with this SSR + upload + parsing workload.

### Component status

| Component | Status | Notes |
|---|---|---|
| Frontend hosting | Already available / free to activate | New Render free service requires owner creation |
| Backend hosting | Already available / free to activate | New Render free service requires owner creation |
| PostgreSQL | Free to activate | New Neon Free project; do not branch production data |
| Uploaded file storage | Free but not wired | R2 bucket exists; current upload code uses ephemeral local disk |
| Generated exports | Free | Regenerated on demand from PostgreSQL lessons |
| AI primary | Requires usage budget | DeepSeek is paid per token |
| AI fallback | Free but restricted | Groq Free rate limits |
| Rate limiting | Already available | Database-backed; no Redis |
| Logging | Already available | Render logs + structured JSON |
| Backups | Free but manual | Neon snapshot + `pg_dump`; no scheduled backups |
| Webhook recovery | Prepared | Manual GitHub workflow; no schedule |
| Teacher access control | Prepared | `REGISTRATION_MODE=invite_only` + invite code |
| Custom domain | Future payment | Stay on `*.onrender.com` |

### Required configuration changes (pilot only)

Backend:

```dotenv
DEBUG=false
DATABASE_URL=<pilot Neon pooled URL>
PUBLIC_WEB_URL=https://<pilot-web>.onrender.com
API_BASE_URL=https://<pilot-api>.onrender.com
CORS_ORIGINS=["https://<pilot-web>.onrender.com"]
STORAGE_BACKEND=s3
S3_ENDPOINT=<existing R2 endpoint>
S3_REGION=auto
S3_BUCKET=schemeknit
S3_ACCESS_KEY=<owner-supplied>
S3_SECRET_KEY=<owner-supplied>
PAYSTACK_ENABLED=false
PAYSTACK_MODE=test
REGISTRATION_MODE=invite_only
PILOT_INVITE_CODE=<owner-supplied secret>
ZELI_ENABLED=true
ZELI_PROVIDER=deepseek
ZELI_FALLBACK_PROVIDER=groq
ZELI_MAX_TOKENS=2000
```

Frontend:

```dotenv
NEXT_PUBLIC_SITE_URL=https://<pilot-web>.onrender.com
NEXT_PUBLIC_API_URL=https://<pilot-api>.onrender.com
NEXT_PUBLIC_STAGING=true
NEXT_PUBLIC_PILOT_INVITE_REQUIRED=true
```

`NEXT_PUBLIC_STAGING=true` emits noindex protections on the pilot host. Do not put the invite
code or any API key in a `NEXT_PUBLIC_*` variable.

### Expected limitations

- First request after idle can take 1–2 minutes. Tell testers before they start.
- Services can restart at any time. In-flight generation may fail and must be retried.
- Multi-subject original files may disappear after a restart before the teacher confirms a
  subject. Parsed curriculum and lessons remain in PostgreSQL; exports regenerate.
- No automatic database backup. The owner must take a manual snapshot/dump before the pilot
  and periodically during it.
- External password-reset email will fail until a domain is verified. Use owner-side resets.
- No central alerting. Check Render and Neon dashboards manually.
- AI generation has a per-token cost and can hit Groq rate limits.

### Owner-side setup instructions

1. Create a **new Neon Free project** named `schemeknit-pilot`. Do not branch or copy the
   production database; real teacher accounts must not enter the pilot database.
2. Record the pooled URL (application) and direct URL (manual backup). Do not paste either
   into chat or source control.
3. Create two new Render **Free** web services from this repository/branch:
   - `schemeknit-pilot-api`: `cd backend && pip install -r requirements.txt`;
     `cd backend && python -m uvicorn src.main:app --host 0.0.0.0 --port $PORT`.
   - `schemeknit-pilot-web`: `cd frontend && npm install && npm run build:web`;
     `cd frontend && npx next start -p $PORT`.
4. Set the environment values above in the Render dashboard. Do not copy the local `.env`
   wholesale; it contains local-only settings.
5. Generate fresh `SECRET_KEY`, `JWT_SECRET_KEY`, `SECURITY_HMAC_KEY` and
   `PLATFORM_ADMIN_BOOTSTRAP_SECRET` for the pilot. Do not reuse production values.
6. Deploy and verify `GET /api/health` returns 200 and `GET /api/ready` returns 200.
7. Create the first platform admin through the bootstrap flow, then remove or rotate the
   bootstrap secret.
8. Create one pilot teacher account and run the workflow once. Then create or invite the
   remaining 4–9 teachers.
9. Keep `PAYSTACK_ENABLED=false` and `PAYSTACK_MODE=test`.
10. Take a manual Neon snapshot/dump before the first teacher and weekly thereafter.
11. Put only the **pilot** direct database URL in the `PILOT_DATABASE_URL` GitHub secret if
    manual webhook recovery is needed. Do not add a schedule yet.

## E. Monthly cost estimate

| Cost line | Expected cost | Notes |
|---|---|---|
| Render hosting | $0 | Two free web services; 750 shared hours; cold starts |
| Neon database | $0 | Free plan; 100 CU-hours/project; 1 GB/project |
| Cloudflare R2 storage | $0 | 10 GB-month free; current usage 0 bytes |
| Scheduled jobs | $0 | Manual GitHub Actions dispatch only |
| Email | $0 | Resend Free; external delivery blocked without a verified domain |
| Monitoring | $0 | Render/Neon included logs and metrics |
| Domain | $0 now | No purchase; Render subdomain |
| GitHub Actions | $0 | Public repository, standard runners |
| **Infrastructure total** | **GHS 0 additional recurring** | No paid resource is required |
| AI usage — DeepSeek | Not zero | Paid per token; see estimate below |
| AI usage — Groq fallback | $0 within free limits | 429 beyond limits |

### AI cost estimate (assumption, not a provider quote)

No actual token usage was recorded in the repository. Use a conservative planning assumption
for one Zeli whole-lesson request:

- 10,000 input tokens (cache miss), 2,000 output tokens, `deepseek-flash`.
- Peak: `10,000 × $0.30/1M + 2,000 × $1.20/1M = $0.0054` per request.
- Off-peak: half the peak rate, about `$0.0027`.
- 50 requests/month (10 teachers × 5): about **$0.14–$0.27/month**.
- 100 requests/month: about **$0.27–$0.54/month**.

These are estimates, not measured usage. Standard deterministic generation needs no provider.
Confirm the DeepSeek balance and set a provider-side spend limit before the pilot. Groq
fallback uses the free tier but is rate-limited.

**Card/billing requirements:** Neon Free and GitHub public Actions need no card. Render Hobby
does not require a card for free services, but overages without a card suspend services.
R2 already has an active subscription and may have a payment method on file; do not add a new
one. Resend Free does not require a paid plan. DeepSeek requires a funded balance for paid
usage.

## F. Future paid activation plan

Activate only after the pilot validates demand and funds are available.

| Service | Why | Free limitation | Paid capability | Approx. price (verified) | Free workaround | Priority |
|---|---|---|---|---|---|---|
| Render Starter web instances | Remove cold starts, stable generation | Sleep after 15 min; 0.1 CPU/512 MB | 0.5 CPU/512 MB per service | $7/month per service | Accept 1–2 min cold starts | High |
| Render Cron Job | Automatic webhook sweeper | Cron not available on Free | Scheduled one-shot command | From $1/month minimum | Manual GitHub workflow | Medium |
| Neon Launch | Longer PITR, scheduled backups, more compute | 6-hour restore; 1 snapshot; 100 CU-hours | 7-day PITR, scheduled backups, higher limits | Usage-based; no monthly minimum | Manual `pg_dump` + snapshot | High |
| Cloudflare R2 overage | Durable uploads beyond 10 GB | 10 GB-month | $0.015/GB-month storage; operations | Usage-based | Keep pilot files small | Medium |
| Resend Pro | External transactional email at volume | 100/day, shared domain restrictions | 50,000/month, no daily cap | $20/month | Verify a domain on Free (3 domains) and stay under 100/day | High |
| `schemeknit.com` domain | Brand, canonical URL, email domain | Render subdomain only | Custom domain | At-cost via Cloudflare; owner to confirm current price | Continue on `*.onrender.com` | High |
| DeepSeek top-up / spend limit | Paid primary generation | No free tier | Prepaid token balance | Per-token pricing above | Use deterministic generation; Groq fallback only | High |
| Monitoring/alerting | Proactive error alerts | No central delivery | Sentry/healthcheck service | Free tiers may exist; not evaluated | Manual dashboard checks | Medium |

Do not activate any of these during the pilot assessment.

## G. Decision

**ZERO-COST PILOT PARTIALLY FEASIBLE — OWNER ACTION REQUIRED**

The hosting, database, object storage, CI and monitoring path can run at GHS 0 additional
recurring infrastructure cost using existing accounts and free allowances. The pilot cannot
start safely until the owner:

1. creates an isolated Neon Free database and two Render Free pilot services;
2. decides how to handle external password-reset email (manual resets or a verified domain);
3. accepts that DeepSeek generation is usage-billed and sets a spend limit;
4. accepts cold starts, shared 750-hour limits and manual backups.

No paid upgrade is required to begin. No paid resource was created during this assessment.

## H. Local validation performed

| Check | Result |
|---|---|
| Backend suite (`python -m pytest -q`) | 2934 passed, 21 skipped, 0 failed |
| Frontend typecheck (`npx tsc --noEmit`) | Passed |
| Frontend production build (`npm run build`) | Passed; 46 static pages generated |
| Upload privacy notice browser gate | 13/13 passed at 1440×900 and 390×844 |
| Gitleaks full history + working tree | 11 findings, all false positives (see above) |
| YAML parse for CI and manual recovery workflow | Passed |

No test sent live AI requests, took a payment, wrote to the production database or deployed a service.
