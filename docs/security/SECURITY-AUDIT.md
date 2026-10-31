# Security Audit

Date: 2026-10-31  
Framework: OWASP ASVS 5.0 areas + OWASP API Security Top 10  
Scope: read-only audit of the release candidate `4f15111`  
Status: staging-qualified security testing **BLOCKED — STAGING INFRASTRUCTURE UNAVAILABLE**

This is an internal code and configuration audit. It is **not** a penetration
test. No authorized penetration test was performed.

## Control matrix

| Area | Existing implementation | Evidence | Test coverage | Severity | Implemented now | Remaining risk |
|---|---|---|---|---|---|---|
| Password hashing | Passlib bcrypt through `CryptContext`; hashes only | `backend/src/auth.py` | auth tests | Medium | No change | bcrypt work factor not explicitly reviewed; Argon2id not adopted |
| Password reset tokens | `secrets.token_urlsafe(32)`, hashed at rest, single-use, TTL | `backend/src/routers/auth.py` (`_issue_reset_token`, `_consume_reset_token`) | auth lifecycle tests | Low | No change | Reset request throttling is IP-only/in-memory |
| Session revocation | JWT `jti` revocation table; `pwv` invalidates on password change | `backend/src/auth.py` | logout/revocation tests | Low | No change | JWT is Bearer, not cookie; no idle timeout separate from `exp` |
| Missing credentials | Now returns 401 + `WWW-Authenticate` | `backend/src/auth.py` `_BearerUnauthorized` | auth tests | Low | Fixed previously | None known |
| Account enumeration | Login message generic; registration returns 409 for existing email | `backend/src/routers/auth.py` | auth entry tests | Medium | No change | Registration/reset can confirm an existing address |
| Per-account failed-login lockout | **Absent** | No failure-counter model or logic | None | **High** | No | Unlimited password guessing per account except shared IP limiter |
| Progressive lockout | **Absent** | No policy implementation | None | **High** | No | Required by owner |
| Per-IP auth rate limiting | In-memory sliding window, 20 login attempts/min | `backend/src/security.py` | limited | High | No | Process-local; resets on restart; not shared across workers |
| Distributed rate limiting | **Absent** | `RateLimiter.hits` is a process dict | None | **High** | No | Multi-worker bypass; no Redis/PostgreSQL store |
| Trusted proxy IP | **Absent** | Uses `request.client.host`; no `X-Forwarded-For` handling | None | **High** | No | Render proxy topology not modeled; no forwarding-header trust policy |
| Combined account+IP throttling | **Absent** | No combined control | None | High | No | Distributed guessing and school NAT fairness unresolved |
| MFA for admins | **Absent** | No TOTP/WebAuthn fields, routes or tests | None | **High** | No | Privileged accounts rely on password only |
| Authorization/IDOR | Owner checks exist across many routes; tests cover several | route code + `test_authorization*`, `test_school_isolation` | partial | Medium | No change | No complete route-by-route matrix |
| CSRF | Bearer token auth, not cookie sessions; CORS allow-list | `backend/src/main.py` | CORS tests | Low/Medium | No change | If cookies are introduced, CSRF protection must be added |
| Security headers | nosniff, Referrer-Policy, X-Frame-Options, Permissions-Policy, no-store | `SecurityHeadersMiddleware` | none found | Medium | No change | No HSTS, no CSP, no `frame-ancestors` CSP |
| CORS | Explicit allow-list, credentials enabled | `backend/src/main.py` | CORS tests | Low | No change | Must use exact staging origin |
| Upload size | 50 MB streamed limit | `backend/src/routers/documents.py` | upload tests | Low | No change | No magic-byte validation documented |
| Upload type | Extension + MIME allow-list | `backend/src/routers/documents.py` | upload tests | Medium | No change | `application/octet-stream` accepted; no DOCX ZIP structure validation |
| Archive bombs/XXE | Not evidenced | No explicit decompression/XML limits found | None | **High** | No | Malicious DOCX/ZIP may exhaust parser resources |
| Path traversal | Filename sanitizer + `safe_join` | `backend/src/security.py` | security tests | Low | No change | Verify every upload/export path uses it |
| AI abuse | Quotas, credits, bounded retry/fallback, timeouts | `zeli_generation.py`, `generation_pipeline.py`, `usage_quota.py` | extensive | Medium | No change | IP limiter is in-memory; no staging load test |
| Payment/webhook | Signature verification, idempotency, replay protection | `src/paystack.py`, `test_prepaid_payments.py` | extensive | Low | No change | Payment stays disabled; no live test |
| Security logging | Structured `log_security` events | `logging_config.py`, auth routes | partial | Medium | No change | No central alerting or monitoring integration |
| Dependency/supply chain | requirements/package files present | repository | **not run this task** | Unknown | No | No `pip-audit`/`npm audit`/secret scan evidence |
| CI/CD | **Absent** | No `.github/workflows` | None | High | No | No automated tests, typecheck, audit or secret scan on push |
| Staging isolation | **Absent** | See staging report | None | **Critical for release** | No | Production cannot be used as staging |

## Key findings

1. **RESOLVED locally — account lockout.** Progressive 1/5/15/30/60-minute
   cooldowns, account-scoped HMAC counters, atomic DB updates, `Retry-After`,
   reset on success/recovery. `src/login_security.py`, `test_login_lockout.py`.
2. **RESOLVED locally — distributed rate limiting.** PostgreSQL/SQLite-backed
   fixed-window counters; production requires `RATE_LIMIT_BACKEND=db`;
   high-risk endpoints fail closed if the store is unavailable.
3. **PARTIAL — trusted proxy.** Safe trust interface and forged-header tests
   exist; Render's actual proxy CIDRs must be verified in staging.
4. **RESOLVED locally — MFA.** TOTP for platform admins, replay protection,
   hashed single-use recovery codes, rate-limited failures. API only; no
   enrollment UI yet.
5. **RESOLVED locally — upload archive validation.** Magic bytes, DOCX container
   checks, entry/size/compression limits, macro rejection, XML entity rejection.
6. **RESOLVED locally — CSP/HSTS controls.** Report-only CSP default, opt-in
   HSTS. Enforcement/domain verification remains staging work.
7. **OPEN — dependency risk.** `pip-audit` reports vulnerabilities in
   `aiohttp`, `requests`, `pytest`, `black`, `ecdsa`; `npm audit` reports a
   critical Next.js advisory plus high transitive advisories. Upgrading Next is
   a major-version change and was not forced.
8. **OPEN — staging.** No isolated staging environment; no security control has
   been qualified against a production-like deployment.
9. **PARTIAL — CI.** GitHub Actions workflow added, but it has not run on GitHub
   yet; dependency audits will fail until the open advisories are resolved or
   formally accepted.
10. **OPEN — authorization matrix completeness.** Route-family matrix documented;
    per-handler negative tests still need expansion.

## What is not claimed

- No PASS for account lockout, distributed IP rate limiting, trusted proxy
  handling, MFA, CI security scanning, or archive-bomb protection.
- No penetration test.
- No staging security test.
- No claim that passing unit tests proves the application is immune to attack.

## Recommended implementation order

1. Provision staging and isolated database.
2. Add DB-backed account failure tracking + progressive cooldown.
3. Replace in-memory limiter with PostgreSQL/Redis-backed shared store and
   trusted-proxy IP extraction.
4. Add MFA for platform admins.
5. Add CSP/HSTS after staging origin verification.
6. Harden DOCX/ZIP/XML parser limits with malicious fixtures.
7. Add CI dependency/secret scanning and security regression tests.
