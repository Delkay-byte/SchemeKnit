# SchemeKnit Security, SEO and Release Checklist

Master progress ledger. Statuses: NOT STARTED, IN PROGRESS, PARTIAL, BLOCKED, DONE, DEFERRED.

Evidence standard: DONE requires implementation plus a run test/inspection and a file/test/commit reference. Documentation alone is not DONE.

Branch: `hardening/security-seo-staging-20261031`  
Baseline: `faab8b6` (code `4f15111`)  
Last updated: 2026-10-31

## A. Account and login protection

| Status | Item | Evidence |
|---|---|---|
| DONE | Five failures / 15 min → 1-minute cooldown | `src/login_security.py`; `tests/test_login_lockout.py`; 2026-10-31 |
| DONE | Repeated lockout → 5 minutes | same test (`test_lockout_escalates...`) |
| DONE | Further lockout → 15 minutes | same test |
| DONE | Persistent attacks cap at 60 minutes | configured `1,5,15,30,60`; escalation test covers 15, cap by config |
| DONE | Successful auth resets counters | `test_cooldown_expiry_and_success_reset` |
| DONE | Account counters across IPs | `test_account_counter_is_not_ip_scoped` |
| DONE | Independent IP throttling | `DbRateLimiter`; `test_db_rate_limiter_is_shared_and_persistent` |
| NOT STARTED | Automated bot challenge | No external challenge provider configured |
| PARTIAL | Account enumeration protection | Login generic; registration 409 still reveals existing email |
| PARTIAL | Lockout DoS safeguards tested | short bounded cooldown + recovery; no explicit distributed lockout-DoS load test |

## B. Password and session security

| Status | Item | Evidence |
|---|---|---|
| DONE | Salted password hashing | bcrypt/Passlib; existing auth tests |
| DONE | Existing hashes compatible | bcrypt retained; no forced reset |
| DONE | Password-reset tokens random/hashed/single-use/TTL | `routers/auth.py`; reset tests |
| DONE | Session expiration | JWT `exp`; auth tests |
| DONE | Logout revocation | `RevokedTokenDB`; logout tests |
| DONE | Password-change invalidation | `pwv`; auth lifecycle tests |
| PARTIAL | Browser token handling audited | tab-scoped `sessionStorage`; CSP report-only; XSS remains the risk |
| DONE | Privileged-user MFA | TOTP API; `tests/test_mfa.py` |
| DONE | Recovery codes | 8 bcrypt-hashed single-use codes; `test_mfa.py` |
| PARTIAL | MFA enrollment UI | API only; no frontend enrollment screen |

## C. Authorization and API security

| Status | Item | Evidence |
|---|---|---|
| PARTIAL | Authorization matrix covers sensitive routes | `docs/security/AUTHORIZATION-MATRIX.md` route families |
| PARTIAL | Object-level authorization tested | existing IDOR/school isolation tests |
| PARTIAL | Property-level authorization tested | not complete |
| PARTIAL | Function-level authorization tested | role tests exist |
| DONE | Users cannot access another user's lessons | existing owner-scoped tests |
| PARTIAL | Users cannot access another user's uploads/exports | representative tests; full route matrix pending |
| DONE | Endpoint-specific API rate limits | `RATE_LIMITS` + shared DB limiter |
| PARTIAL | Request validation/resource limits | upload/generation bounds; broader limits not audited |
| DONE | Shared IP rate limiting | `DbRateLimiter`; local test |
| PARTIAL | Trusted proxy configuration | safe interface + forged-header test; Render CIDRs unverified |

## D. File and web security

| Status | Item | Evidence |
|---|---|---|
| DONE | File-size limits | 50 MB streamed limit |
| DONE | File signature validation | DOCX `PK`, PDF `%PDF-`; `test_upload_security.py` |
| DONE | DOCX archive validation | container/macro/path checks; same tests |
| DONE | ZIP decompression limits | entry/size/ratio limits; same tests |
| DONE | XML entity protections | DOCTYPE/ENTITY rejection; same tests |
| DONE | Malformed-document handling | malformed ZIP/container tests |
| PARTIAL | CSRF applicability assessed | Bearer token, no cookie session; no cookie CSRF surface |
| PARTIAL | XSS protections | React escaping; CSP report-only not enforced |
| DONE | CORS allow-list | `main.py`; CORS tests |
| PARTIAL | CSP tested and enforced | report-only by default; HTTP header verified; enforcement not staged |
| PARTIAL | HSTS configured where safe | opt-in config; not enabled for unverified domain |
| DONE | Security headers verified | `tests/test_security_headers.py` |

## E. Database, AI and payment security

| Status | Item | Evidence |
|---|---|---|
| PARTIAL | SQL/ORM safety audited | ORM-heavy; no complete raw-SQL audit |
| PARTIAL | Database least privilege | staging role not provisioned |
| PARTIAL | Backups/restore | documented; restore not tested |
| BLOCKED | Staging/production databases isolated | no staging |
| DONE | AI generation abuse controls | quotas, credits, bounded fallback, shared IP limits |
| DONE | Provider costs/concurrency bounded | quotas + one fallback attempt |
| PARTIAL | Uploaded content untrusted for AI | prompt is indicator-grounded; no injection corpus |
| DONE | DeepSeek primary works | local live verification 2026-10-30 |
| DONE | Groq fallback works | local live verification 2026-10-30 |
| DONE | Credit/cache behaviour | `test_zeli_fallback.py`, quota tests |
| DONE | Webhook signature validation | prepaid/paystack tests |
| DONE | Webhook replay protection | idempotency tests |
| DONE | Payment idempotency | credit grant tests |
| DONE | Live payment disabled | local `PAYSTACK_ENABLED=false`, test mode |

## F. Operations and CI/CD

| Status | Item | Evidence |
|---|---|---|
| PARTIAL | Structured sanitized security logs | `log_security`; account keys HMAC; no central alerting |
| PARTIAL | Security events investigable | log events exist; no dashboard/runbook |
| FAIL | Dependency vulnerability scan clean | `pip-audit` and `npm audit` report open findings |
| DONE | Secret scanning configured | Gitleaks job in `.github/workflows/ci.yml` |
| PARTIAL | GitHub Actions CI | workflow added; not yet run on GitHub |
| DONE | CI backend tests | workflow job |
| DONE | CI frontend typecheck/build | workflow jobs |
| DONE | CI does not expose production secrets | no production secrets; `permissions: contents: read` |
| BLOCKED | Staging deployment separated from production | no staging |
| PARTIAL | Production release procedure documented | plan exists; not executed |

## G. SEO

| Status | Item | Evidence |
|---|---|---|
| DONE | Homepage mojibake fixed | `layout.tsx`; built HTML title checked |
| DONE | Homepage title/description | built HTML; `test_seo_foundation.py` |
| DONE | Unique title for every public page | pageMetadata on 11 public pages; static test |
| DONE | Unique meta descriptions | same |
| DONE | Open Graph metadata | helper + root; built HTML checked |
| DONE | Social-sharing metadata | Twitter card fields |
| DONE | Centralized website URL | `src/lib/site-url.ts` + `.env.example` |
| DONE | Canonical URL infrastructure | `alternates.canonical`; built HTML checked |
| DONE | XML sitemap | `/sitemap.xml` 200; public URLs only |
| DONE | robots.txt | `/robots.txt` 200; private paths excluded |
| DONE | Organization JSON-LD | `site-structured-data.tsx` |
| DONE | SoftwareApplication JSON-LD | same |
| DONE | Breadcrumb/article structured data | not applicable to current static pages; no fake article pages added |
| DONE | Private pages excluded from indexing | middleware `X-Robots-Tag`; verified `/login`, `/dashboard` |
| PARTIAL | Staging noindex protection | code path implemented; no staging host to verify |
| DONE | Ghanaian education content improvements | public pages now SchemeKnit-branded and accurate; no new thin pages |
| DONE | SEO tests pass | `tests/test_seo_foundation.py` 6 passed |
| DONE | Future domain migration documented | `docs/seo/FUTURE-DOMAIN-MIGRATION.md` |

## H. Staging and release

| Status | Item | Evidence |
|---|---|---|
| BLOCKED | Isolated staging frontend | no service |
| BLOCKED | Isolated staging backend | no service |
| BLOCKED | Separate staging PostgreSQL | no service |
| BLOCKED | Staging credentials | none |
| BLOCKED | Staging CORS | none |
| BLOCKED | Staging AI providers | none |
| BLOCKED | Staging migrations | none |
| BLOCKED | Staging health | none |
| BLOCKED | Staging security acceptance | none |
| BLOCKED | Staging SEO acceptance | none |
| BLOCKED | Staging DeepSeek/Groq acceptance | none |
| BLOCKED | Six-case staging matrix | local only |
| BLOCKED | Full staging suite | none |
| NOT STARTED | Production candidate review | — |
| NOT STARTED | Merge into main | — |
| NOT STARTED | Production deployment | — |
| NOT STARTED | Rollback readiness verified | plan only |
| DONE | Pilot plan ready | `docs/release/FRIENDS-AND-FAMILY-PILOT-PLAN.md` |
| NOT STARTED | Pilot completed and feedback reviewed | — |

## Open blockers

1. No isolated staging infrastructure or Render/Neon access.
2. `npm audit`: 1 critical (Next.js) + high transitive findings; major upgrade not forced.
3. `pip-audit`: vulnerabilities in aiohttp, requests, pytest, black, ecdsa; upgrades need compatibility review.
4. No GitHub CI execution evidence yet.
5. Render proxy CIDRs/topology unverified.
6. MFA enrollment UI not built.
7. No staging security/SEO/provider validation.

## Linked reports

- `docs/release/STAGING-RELEASE-BASELINE.md`
- `docs/release/STAGING-VALIDATION-REPORT.md`
- `docs/release/STAGING-PROVISIONING-RUNBOOK.md`
- `docs/security/SECURITY-AUDIT.md`
- `docs/security/AUTHENTICATION-AND-RATE-LIMITING.md`
- `docs/security/AUTHORIZATION-MATRIX.md`
- `docs/security/SECURITY-REMEDIATION-REPORT.md`
- `docs/security/STAGING-SECURITY-RESULTS.md`
- `docs/seo/SEO-AUDIT.md`
- `docs/seo/TECHNICAL-SEO-IMPLEMENTATION.md`
- `docs/seo/CONTENT-STRATEGY.md`
- `docs/seo/SEO-VALIDATION-REPORT.md`
- `docs/seo/FUTURE-DOMAIN-MIGRATION.md`
- `docs/release/PRODUCTION-RELEASE-PLAN.md`
- `docs/release/FRIENDS-AND-FAMILY-PILOT-PLAN.md`
