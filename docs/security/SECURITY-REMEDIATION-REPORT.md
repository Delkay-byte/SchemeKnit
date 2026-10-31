# Security Remediation Report

Date: 2026-10-31  
Release candidate: `4f15111`  
Status: **NOT READY FOR PRODUCTION — staging and high-severity controls remain**

## Implemented and tested (prior work)

| Control | Status | Evidence |
|---|---|---|
| Missing credentials return 401 | Implemented | `backend/src/auth.py`; auth tests |
| JWT logout revocation | Implemented | `RevokedTokenDB`; logout tests |
| Password-change session invalidation | Implemented | `pwv` claim; session tests |
| Password reset token single-use/TTL | Implemented | hashed token rows; auth tests |
| Bearer-token authorization and owner checks | Implemented on existing routes | authorization/IDOR tests |
| DeepSeek/Groq bounded fallback | Implemented | fallback tests + live verification |
| AI credit/cache atomicity | Implemented | quota/concurrency tests |
| Payment webhook signature/idempotency | Implemented | prepaid/paystack tests |
| Baseline security headers | Implemented | `SecurityHeadersMiddleware` |
| Upload size/MIME checks | Implemented | documents router tests |

## Not implemented — blocking release

| Finding | Severity | Reason |
|---|---|---|
| Per-account progressive lockout | High | No staging; no schema/control added |
| Shared IP rate limiting | High | In-memory only; no Redis/PostgreSQL store |
| Trusted proxy client IP | High | No Render proxy model or tests |
| MFA for platform admins | High | No implementation |
| CI dependency/secret scanning | High | No workflows or scan evidence |
| CSP/HSTS | Medium | Not configured; staging origin unverified |
| DOCX/ZIP/XML resource limits | High | No archive-bomb/XXE tests |
| Staging isolation | Critical | No staging services/database |

## Required before production

1. Provision isolated staging frontend, backend and database.
2. Implement account lockout with a migration and concurrency tests.
3. Replace in-memory limiter with shared atomic storage.
4. Add trusted-proxy tests and Render topology configuration.
5. Add admin MFA or document a formally accepted exception.
6. Add ZIP/XML limits and malicious document fixtures.
7. Add CI: backend tests, frontend typecheck/build, dependency audit, secret
   scan.
8. Add CSP/HSTS after staging verification.
9. Run authorized OWASP ZAP baseline on staging.
10. Complete the staging smoke matrix.

## Security score

No percentage score is provided. No authorized penetration test or complete
ASVS assessment was performed, so a numeric score would be invented.
