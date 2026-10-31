# Staging Security Results

Date: 2026-10-31  
Status: **NOT RUN — staging infrastructure unavailable**

## Local evidence

| Control | Local result | Test |
|---|---|---|
| Progressive account lockout | PASS | `tests/test_login_lockout.py` |
| Shared DB rate limiting | PASS | `DbRateLimiter` test |
| Trusted proxy interface | PASS (forged header ignored) | `tests/test_login_lockout.py` |
| MFA TOTP enrollment/login/recovery | PASS | `tests/test_mfa.py` |
| Security headers/CSP/HSTS opt-in | PASS | `tests/test_security_headers.py` |
| DOCX/PDF upload container validation | PASS | `tests/test_upload_security.py` |
| SEO noindex/robots/sitemap | PASS locally | `tests/test_seo_foundation.py` + HTTP checks |

## Not run

- Staging brute-force test across real proxy topology.
- Staging OWASP ZAP baseline.
- Staging CORS/proxy verification.
- Staging MFA enrollment over the deployed frontend.
- Staging dependency scan in CI.
- Staging provider security tests.

No staging security claim is made.
