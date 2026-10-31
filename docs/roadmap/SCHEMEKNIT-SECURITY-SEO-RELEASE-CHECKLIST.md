# SchemeKnit Security, SEO and Release Checklist

Master progress ledger. Statuses: NOT STARTED, IN PROGRESS, PARTIAL, BLOCKED, DONE, DEFERRED.

DONE means implemented and locally tested unless explicitly marked staging-verified. Documentation alone is not DONE.

Branch: `hardening/remediation-staging-20261031`  
HEAD: `8b70d7f`  
Last updated: 2026-10-31

## A. Account and login protection

| Status | Item | Evidence |
|---|---|---|
| DONE | 5 failures / 15 min → 1-minute cooldown | `src/login_security.py`; `test_login_lockout.py` |
| DONE | Repeated lockout → 5/15/30/60 minutes | escalation test + configured steps |
| DONE | Successful auth/reset clears counters | `test_cooldown_expiry_and_success_reset` |
| DONE | Account counters across IPs | `test_account_counter_is_not_ip_scoped` |
| DONE | Independent IP throttling | `DbRateLimiter`; shared-store test |
| NOT STARTED | Automated bot challenge | No challenge provider configured |
| PARTIAL | Account enumeration protection | Login generic; registration 409 reveals existing email |
| PARTIAL | Lockout DoS load test | bounded cooldown + recovery; no distributed load test |

## B. Password and session security

| Status | Item | Evidence |
|---|---|---|
| DONE | Salted password hashing | bcrypt/Passlib |
| DONE | Existing hashes compatible | no forced reset |
| DONE | Reset tokens random/hashed/single-use/TTL | `routers/auth.py`; reset tests |
| DONE | Session expiration/logout revocation/pwv | auth tests |
| PARTIAL | Browser token handling | tab-scoped sessionStorage; CSP report-only |
| DONE | Privileged-user MFA backend | TOTP; `test_mfa.py` 3 passed |
| DONE | Recovery codes | 8 single-use bcrypt hashes |
| DONE | MFA frontend enrollment/status/recovery/disable | `mfa-settings-card.tsx`; `test_mfa_frontend_source.py` |
| PARTIAL | MFA browser end-to-end | no staging browser test |

## C. Authorization and API security

| Status | Item | Evidence |
|---|---|---|
| DONE | Route inventory + auth dependency test | `test_authorization_route_inventory.py` |
| DONE | Platform-admin role dependency test | same file |
| PARTIAL | Per-handler User A/User B negative matrix | existing IDOR/isolation tests; not exhaustive |
| PARTIAL | Property-level mass-assignment tests | representative |
| DONE | Shared IP rate limiting | `DbRateLimiter`; local test |
| PARTIAL | Trusted proxy configuration | interface + forged-header test; Render CIDRs unverified |
| PARTIAL | Request/resource limits | upload/generation bounds; broader audit pending |

## D. File and web security

| Status | Item | Evidence |
|---|---|---|
| DONE | File size/signature/DOCX archive/XML checks | `test_upload_security.py` 9 passed |
| DONE | Path traversal/macro/compression limits | same |
| DONE | CORS allow-list | CORS tests |
| PARTIAL | XSS protections | React escaping; CSP report-only |
| PARTIAL | CSP enforced | report-only; staging enforcement blocked |
| PARTIAL | HSTS | opt-in; no verified permanent domain |
| DONE | Security headers | `test_security_headers.py` |

## E. Database, AI and payment security

| Status | Item | Evidence |
|---|---|---|
| PARTIAL | SQL/ORM safety | ORM-heavy; no complete raw-SQL audit |
| BLOCKED | DB least privilege | no production/staging DB access |
| BLOCKED | Backup/restore verified | `DATABASE-BACKUP-AND-RESTORE-REPORT.md`; no restore |
| BLOCKED | Staging DB isolation | no staging |
| DONE | AI abuse controls | quotas, credits, bounded fallback, shared IP limits |
| DONE | Prompt-injection corpus | 14 passed; `CURRICULUM-AI-INPUT-SECURITY.md` |
| DONE | DeepSeek/Groq local verification | prior live runs; preserved |
| DONE | Credit/cache behaviour | fallback/quota tests |
| DONE | Webhook signature/replay/idempotency | payment tests |
| DONE | Payment disabled | `PAYSTACK_ENABLED=false`, `PAYSTACK_MODE=test` |

## F. Operations and CI/CD

| Status | Item | Evidence |
|---|---|---|
| DONE | Structured sanitized security logs | `log_security`; HMAC account keys |
| DONE | Optional alert adapter | `alert_security`; `test_security_monitoring.py` 3 passed |
| BLOCKED | Central alert delivery | no configured monitoring account/webhook |
| DONE | Dependency high/critical audit | pip-audit 0; npm prod audit 0 |
| PARTIAL | Moderate findings | 16 dev-only ESLint/Type tooling findings documented |
| DONE | GitHub Actions CI | run 41168965791; all 4 jobs success |
| DONE | PostgreSQL harness in CI | success |
| DONE | Secret scan in CI | Gitleaks success |
| BLOCKED | Staging deployment separate | no staging infrastructure |
| PARTIAL | Production release procedure | plan documented; not executed |

## G. SEO

| Status | Item | Evidence |
|---|---|---|
| DONE | Homepage title/mojibake/description | built HTML verified |
| DONE | Unique metadata for public pages | `test_seo_foundation.py` 6 passed |
| DONE | Canonical/Open Graph/Twitter | helper + built HTML |
| DONE | Centralized site URL | `site-url.ts` + `.env.example` |
| DONE | XML sitemap | `/sitemap.xml` 200 public-only |
| DONE | robots.txt | `/robots.txt` 200 private exclusions |
| DONE | Organization/WebSite/SoftwareApplication JSON-LD | `site-structured-data.tsx` |
| DONE | Private/staging noindex code | middleware verified locally |
| BLOCKED | Staging noindex verification | no staging host |
| DONE | Future domain migration doc | `FUTURE-DOMAIN-MIGRATION.md` |
| PARTIAL | Search Console/indexing/CWV | no domain/account evidence |

## H. Staging and release

| Status | Item | Evidence |
|---|---|---|
| BLOCKED | Isolated staging frontend/backend/database | no services/access |
| BLOCKED | Staging credentials/CORS/providers | none |
| BLOCKED | Staging security/SEO/AI acceptance | none |
| BLOCKED | Staging rollback test | none |
| NOT STARTED | Production merge/deploy | no authorization |
| DONE | Friends-and-family pilot plan | `FRIENDS-AND-FAMILY-PILOT-PLAN.md` |
| NOT STARTED | Pilot execution | requires release |

## Open blockers

1. No isolated staging infrastructure or Render/Neon access.
2. No production/staging database role or restore verification.
3. No central alert delivery configured.
4. Render proxy CIDRs unverified; forwarding remains disabled.
5. CSP is report-only; no staging enforcement.
6. Handler-level negative tests are not exhaustive.
7. 16 moderate dev-only frontend audit findings documented.

## Linked reports

- `docs/release/CI-VALIDATION-REPORT.md`
- `docs/release/STAGING-VALIDATION-REPORT.md`
- `docs/release/STAGING-PROVISIONING-RUNBOOK.md`
- `docs/security/DEPENDENCY-REMEDIATION-REPORT.md`
- `docs/security/MFA-IMPLEMENTATION-REPORT.md`
- `docs/security/AUTHORIZATION-MATRIX.md`
- `docs/security/AUTHORIZATION-TEST-REPORT.md`
- `docs/security/SESSION-AND-XSS-REPORT.md`
- `docs/security/CURRICULUM-AI-INPUT-SECURITY.md`
- `docs/security/STAGING-SECURITY-RESULTS.md`
- `docs/operations/DATABASE-BACKUP-AND-RESTORE-REPORT.md`
- `docs/operations/SECURITY-MONITORING-AND-INCIDENT-RESPONSE.md`
- `docs/seo/SEO-VALIDATION-REPORT.md`
- `docs/seo/FUTURE-DOMAIN-MIGRATION.md`
