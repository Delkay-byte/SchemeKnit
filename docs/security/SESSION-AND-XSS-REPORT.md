# Session and XSS Report

Date: 2026-10-31  
Status: **Bearer/sessionStorage retained; CSP report-only; staging enforcement blocked**

## Current session model

- JWT Bearer token, HS256, server-signed.
- `exp` enforced by PyJWT decode.
- `jti` logout revocation table.
- `pwv` password-version invalidation.
- Browser token stored in tab-scoped `sessionStorage`; `localStorage` legacy tokens are not migrated.
- Logout revokes the server-side token id and clears the tab session.
- Password change rotates the current token and invalidates other tokens through `pwv`.
- No refresh token, no cookie session, no pre-auth MFA challenge token.

## Cookie migration decision

Not migrated in this task. A secure HttpOnly cookie flow requires coordinated changes to:

- CORS credentials and exact origins,
- CSRF tokens for every state-changing route,
- SameSite/domain/path configuration,
- Paystack return flow,
- multi-tab and logout semantics,
- staging HTTPS verification.

Retaining `sessionStorage` is lower risk than an incomplete cookie migration. Residual XSS impact remains: any script execution can read the token.

## CSP

- Response header is `Content-Security-Policy-Report-Only` by default.
- Policy allows `'self'`, inline styles/scripts and `'unsafe-eval'` for Next.js compatibility.
- HSTS is opt-in and disabled until a verified HTTPS domain exists.
- Enforced CSP is **not** claimed; it requires staging violation collection and testing.

## XSS regression coverage

- React escapes rendered text by default.
- Lesson content is rendered as text, not `dangerouslySetInnerHTML`.
- Uploaded filenames are sanitized server-side.
- API errors are rendered as text.
- Security-header tests verify CSP/HSTS behavior.
- No dedicated browser/DOM XSS scanner was run.

## Residual risks

- `sessionStorage` is JavaScript-readable.
- CSP report-only does not block injection.
- No staging XSS/ZAP scan.
- No cookie/CSRF migration.
