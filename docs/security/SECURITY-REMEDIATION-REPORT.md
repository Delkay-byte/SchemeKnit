# Security Remediation Report

Date: 2026-10-31  
Release candidate: `faab8b6` + local hardening
Status: **LOCAL HARDENING COMPLETE — STAGING AND DEPENDENCY ITEMS BLOCK RELEASE**

## Implemented locally in this task

| Control | Status | Evidence |
|---|---|---|
| Progressive account lockout | Implemented | `src/login_security.py`; `test_login_lockout.py` |
| Account counters across IPs | Implemented | HMAC account key; same test |
| Shared DB rate limiting | Implemented | `DbRateLimiter`; `test_login_lockout.py` |
| Trusted-proxy interface | Implemented | `client_ip`; forged-header test |
| TOTP MFA for platform admins | Implemented | `src/mfa.py`; `test_mfa.py` |
| Recovery codes | Implemented | bcrypt hashes, single-use; `test_mfa.py` |
| Upload magic/archive/XML checks | Implemented | `documents.py`; `test_upload_security.py` |
| CSP report-only + opt-in HSTS | Implemented | `test_security_headers.py` |
| GitHub Actions CI | Implemented, not yet run | `.github/workflows/ci.yml` |
| SEO foundation | Implemented | `test_seo_foundation.py`; built HTTP checks |

## Open blockers

| Finding | Severity | Status |
|---|---|---|
| No isolated staging environment | Critical for release | BLOCKED |
| `npm audit` critical Next.js advisory | Critical | OPEN — major upgrade not forced |
| `npm audit` high transitive advisories | High | OPEN |
| `pip-audit` vulnerable Python packages | High/unknown | OPEN — compatibility review needed |
| Render proxy CIDRs unverified | High | STAGING REQUIRED |
| MFA enrollment UI absent | Medium | PARTIAL |
| Authorization matrix not per-handler | Medium | PARTIAL |

No security score is provided. No penetration test was performed.
