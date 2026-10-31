# SchemeKnit — ASVS 5.0 and OWASP API Security Top 10 Gap Assessment

Date: 2026-10-31  
Assessment target: `Delkay-byte/SchemeKnit`, local branch `chore/zero-cost-pilot-20261031`
(based on the pre-rewrite history; production `main` was later rewritten for attribution only).  
Assessment type: evidence-based gap assessment. Not a certification and not a claim of full
OWASP compliance.

## 1. Executive assessment

SchemeKnit has a stronger than typical baseline for a small SaaS: server-side authorization
checks, database-backed rate limiting, progressive account lockout, bcrypt, JWT revocation,
password-version invalidation, TOTP MFA, upload container validation, CORS allow-listing,
payment signature/idempotency controls, structured security logs, and a substantial automated
test suite.

The application is **not yet ready for an unrestricted public launch or an unsupervised pilot**.
The confirmed lesson mass-assignment vulnerability was remediated on 2026-10-31. Four
high-priority gaps remain:

1. The real client IP behind Render is unverified; forwarding remains disabled, so all traffic
   may share one rate-limit bucket, while enabling it without correct CIDRs would allow spoofing.
2. Platform-admin MFA exists but is not required.
3. The Next.js frontend does not set CSP/HSTS/frame/referrer headers; the backend CSP is
   report-only and permits `unsafe-inline` and `unsafe-eval`.
4. There is no tested backup/restore or central alert delivery for the free-tier pilot design.

No critical vulnerability was confirmed from code review and local tests. The remaining highest
severity is **HIGH** for the combined session/header/MFA posture.

**Technical-readiness conclusion:** **CONDITIONAL — NOT READY** for public launch. A small,
invite-only friends-and-family pilot is acceptable only after the remaining high-priority fixes
in §10 and the pre-pilot tests in §11. Hosting and provider-dependent controls remain BLOCKED
until the owner verifies them.

## 2. Scope and assumptions

### In scope

- Next.js frontend (`frontend/`), FastAPI backend (`backend/src/`), PostgreSQL via SQLAlchemy.
- Teacher registration, login, MFA, password reset, sessions, uploads, curriculum review,
  generation, lesson editing, exports, credits, admin routes and Paystack test-mode code.
- Existing automated tests and local evidence.
- OWASP ASVS 5.0.0 stable release (`v5.0.0`) and OWASP API Security Top 10 (2023).

### Out of scope

- Pupil accounts, attendance, grades or student records. SchemeKnit is not an SIS/LMS.
- Live payment processing; Paystack is disabled and in test mode.
- Production database mutation, live AI calls, DNS, Render deployment or remote Git changes.
- Formal penetration testing, source-code certification, or compliance certification.
- Desktop/Electron packaging except where it shares the same auth/API code.

### Assumed deployment

- Render free web services for frontend and API, Neon PostgreSQL, Cloudflare R2 configured but
  not wired to upload/export persistence.
- DeepSeek primary, Groq one-attempt fallback, Paystack test mode disabled.
- 5–10 trusted teachers, low volume, owner-supervised.

### ASVS level

Target **ASVS Level 2** for the web application and API. Rationale: the product handles teacher
identities, uploaded documents, generated content and payment-adjacent records, but is not a
high-value financial or government system. Selected **Level 3** controls are expected for
platform-admin and payment flows because those actions can affect all tenants or real money.
This assessment does not certify Level 2 or Level 3.

### Status vocabulary

| Status | Meaning |
|---|---|
| VERIFIED | Code and local test/evidence confirm the control. |
| IMPLEMENTED BUT UNVERIFIED | Code exists; no local or infrastructure verification. |
| PARTIAL | Some controls exist; a material gap remains. |
| FAIL | Required control is absent or contradicted by code. |
| BLOCKED | Verification requires owner/infrastructure access not available here. |
| NOT APPLICABLE | Control does not apply to this architecture. |

## 3. ASVS 5.0 requirement traceability matrix

Eighty-four requirement rows were assessed: 83 applicable requirements and 1 N/A. V10
(OAuth/OIDC) and V17 (WebRTC) are not applicable; the app uses first-party JWT auth and no
WebSocket/WebRTC transport. Cookie-specific requirements are not applicable because sessions
are bearer tokens in tab-scoped `sessionStorage`, not cookies.

| ID | Requirement (short) | Status | Evidence / gap |
|---|---|---|---|
| 1.2.4 | Parameterized queries / ORM | VERIFIED | SQLAlchemy ORM; `text()` uses bound parameters. Migration DDL uses fixed identifiers. |
| 1.2.5 | OS command injection protection | IMPLEMENTED BUT UNVERIFIED | PDF conversion uses a subprocess path; no user shell string found, but no injection test. |
| 1.3.2 | No eval/dynamic code execution | VERIFIED | No `eval`/`new Function` in app source. |
| 1.3.6 | SSRF allow-list | VERIFIED | No user-controlled outbound URL. Provider, storage and email endpoints are configuration-only. |
| 1.5.1 | XXE-safe XML parsing | PARTIAL | DOCX archive rejects DOCTYPE/ENTITY; parser relies on library defaults. No explicit XXE regression file. |
| 2.1.1 | Documented input validation | PARTIAL | Pydantic and upload rules exist; no single validation specification per endpoint. |
| 2.2.1 | Input validation for business rules | VERIFIED | Pydantic models, service-layer checks, enum coercion. |
| 2.3.2 | Business-logic limits | VERIFIED | Quotas, credits, upload limits, generation locks; `test_monthly_quota.py`, `test_credit_generation.py`. |
| 2.3.4 | Locking for limited resources | VERIFIED | PostgreSQL advisory lock plus process lock; `test_wapef_generate_race_repro.py`. |
| 2.4.1 | Anti-automation controls | PARTIAL | Rate limits and account lockout; no bot challenge or device/behaviour signal. |
| 3.2.2 | Safe text rendering | VERIFIED | React escaping; only static JSON-LD uses `dangerouslySetInnerHTML`. |
| 3.3.1 | Secure cookies | NOT APPLICABLE | No cookie-based session. Bearer token in `sessionStorage`. |
| 3.4.1 | HSTS on all responses | PARTIAL | Frontend and backend now emit HSTS when enabled; production activation still requires `ENABLE_HSTS=true` and a verified HTTPS host. |
| 3.4.2 | CORS allow-list | VERIFIED | Exact origin list; `test_cors_registration_preflight.py`. |
| 3.4.3 | CSP | PARTIAL | Frontend enforces CSP without `unsafe-eval`; backend CSP is enforced when `CSP_REPORT_ONLY=false`. Production header verification pending. |
| 3.4.4 | `X-Content-Type-Options: nosniff` | VERIFIED | Frontend `headers()` and backend middleware set it; source test pins both. |
| 3.4.6 | Frame-ancestors protection | VERIFIED | Frontend CSP/XFO and backend CSP/XFO both set; source test pins it. |
| 4.1.1 | Correct response Content-Type | VERIFIED | FastAPI JSON/file responses; Next.js standard responses. |
| 4.1.3 | Trusted proxy header handling | BLOCKED | Parser hardened (right-to-left, bounded, IPv6/mapped, fail-closed) and 34 tests pass; Render peer address/CIDRs remain unverified. Trust stays disabled. |
| 4.1.4 | Explicit HTTP methods | VERIFIED | FastAPI route methods; TRACE not enabled. |
| 5.1.1 | Documented upload types/sizes | VERIFIED | `.docx/.pdf`, 50 MB, archive limits in `routers/documents.py`; docs describe them. |
| 5.2.1 | Processable file size | VERIFIED | 50 MB request cap; streaming size check. |
| 5.2.3 | Archive decompression limits | VERIFIED | 4,000 entries, 200 MB total, 50 MB entry, 200:1 ratio, 25 MB XML. |
| 5.2.4 | Per-user file quota | PARTIAL | Per-file limit only; no per-user storage/file-count quota. |
| 5.3.2 | Internally generated file paths | VERIFIED | UUID/timestamp filename; `safe_join` containment. |
| 5.4.3 | Malware scanning | FAIL | No antivirus/content-disarm scanner; uploads are parsed as untrusted data. |
| 6.1.1 | Authentication abuse documentation | PARTIAL | Lockout/rate-limit code and tests exist; no complete authentication runbook. |
| 6.2.1 | Minimum password length | VERIFIED | 8 characters; `validation.py`. |
| 6.2.3 | Current password on change | VERIFIED | `change-password` verifies current password; `test_auth_lifecycle.py`. |
| 6.2.4 | Breached-password check | FAIL | No breached-password or common-password list; only composition rules. |
| 6.3.1 | Brute-force / credential-stuffing controls | VERIFIED | Account lockout + DB rate limiter; `test_login_lockout.py` 7 passed. |
| 6.3.3 | MFA for privileged access | VERIFIED | Production platform-admin mutations require enrolled MFA; enrollment/status stay reachable. Tested. |
| 6.3.8 | No user enumeration on auth failure | VERIFIED | Generic 401; unknown-user timing equalisation; lockout keyed opaquely. |
| 6.4.1 | Secure reset/activation secrets | VERIFIED | `secrets.token_urlsafe`; hashed reset tokens; single use. |
| 6.4.3 | Forgotten-password process | PARTIAL | Reset invalidates sessions and is single-use; it does not require an existing MFA factor. |
| 6.5.1 | TOTP single use | VERIFIED | `mfa_last_step` replay rejection; `test_mfa.py`. |
| 7.1.1 | Session timeout documentation | PARTIAL | 24-hour JWT lifetime in config; no inactivity timeout or user-facing session policy. |
| 7.2.1 | Backend token verification | VERIFIED | JWT signature, expiry, user lookup, password version, JTI revocation. |
| 7.2.4 | New session token on login | VERIFIED | New `jti` every login/token creation. |
| 7.3.1 | Inactivity timeout | VERIFIED | Server-side `user_sessions.last_seen_at` enforces 30-minute idle expiry. |
| 7.3.2 | Absolute session lifetime | VERIFIED | 12-hour absolute server session expiry; 2-hour access token; documented in env example. |
| 7.4.1 | Logout invalidates session | VERIFIED | JTI inserted into `revoked_tokens`; `test_logout_revocation.py` 7 passed. |
| 7.5.2 | View/terminate all sessions | VERIFIED | `POST /api/auth/logout-all` revokes all server sessions; Settings exposes “Sign out all devices”. |
| 8.1.1 | Authorization documentation | VERIFIED | `docs/security/AUTHORIZATION-MATRIX.md`; route inventory test. |
| 8.2.1 | Function-level authorization | VERIFIED | 105 non-public handlers checked; privileged routes require role dependency. |
| 8.2.2 | Data-specific authorization | PARTIAL | Owner-scoped IDOR tests cover schemes, lessons, jobs, templates; not every ID type/export token. |
| 8.2.3 | Field-level authorization | VERIFIED | `normalize_lesson_updates` enforces an explicit editable allowlist before mutation; protected/unknown fields return 422. `test_lesson_update_mass_assignment.py` 31 passed. |
| 8.3.1 | Server-side enforcement | VERIFIED | Dependencies and service-layer owner filters; no client-trusted role. |
| 8.4.1 | Cross-tenant isolation | PARTIAL | Owner scoping is consistent; `school_id` is mutable through lesson updates, weakening tenant metadata. |
| 9.1.1 | Token signature verification | VERIFIED | PyJWT HS256 decode; tampered/expired tokens rejected. |
| 9.1.2 | Algorithm allow-list | VERIFIED | `algorithms=[settings.JWT_ALGORITHM]`, default HS256; no `none`. |
| 9.2.3 | Token audience validation | FAIL | No `aud` claim or audience check. |
| 9.2.4 | Audience separation | FAIL | Same JWT key/claims used for teacher, school-admin and platform-admin APIs. |
| 11.1.1 | Key-management policy | FAIL | No documented key lifecycle/rotation policy for JWT, HMAC, provider or storage keys. |
| 11.4.2 | Password hashing KDF | VERIFIED | bcrypt/Passlib; existing hashes compatible. |
| 11.5.1 | CSPRNG for secrets | VERIFIED | `secrets.token_urlsafe`, `uuid4`, TOTP secrets. |
| 11.3.1 | No insecure block modes | VERIFIED | No application-level symmetric encryption; relies on managed TLS/storage. |
| 12.1.1 | Modern TLS configuration | BLOCKED | Render/Neon TLS versions and ciphers not inspectable here. |
| 12.2.1 | TLS for external HTTP | VERIFIED | Production URLs are HTTPS; CORS uses HTTPS origin. |
| 12.3.1 | TLS for internal/outbound | PARTIAL | Provider/DB endpoints are HTTPS/SSL; not all connection strings verified. |
| 13.3.1 | Secrets management | PARTIAL | Secrets in Render env; no vault, rotation schedule or access review. |
| 13.4.2 | Debug disabled in production | VERIFIED | Render `DEBUG=false`; docs/OpenAPI disabled when not DEBUG. |
| 13.4.5 | Docs/monitoring endpoints not exposed | VERIFIED | `/api/docs` and `/api/openapi.json` are `None` in production. |
| 13.4.6 | No detailed version exposure | PARTIAL | `/api/health` returns service version `1.0.5`. |
| 13.4.7 | Restrict served file types | PARTIAL | Export endpoints are explicit; Next.js static serving is framework-controlled. |
| 14.1.1 | Data classification | PARTIAL | No formal classification of teacher PII, documents, payments and logs. |
| 14.2.1 | Sensitive data not in URL | VERIFIED | Passwords/reset tokens submitted in bodies; download tokens are path parameters by design. |
| 14.2.2 | No-store on sensitive API | VERIFIED | API `Cache-Control: no-store`; frontend HTML caching not verified. |
| 14.2.3 | No sensitive data to untrusted parties | PARTIAL | Curriculum text goes to DeepSeek/Groq; no tracker found, but provider DPA/retention not documented. |
| 14.2.7 | Retention/deletion | PARTIAL | No automated retention for uploads, exports, logs or revoked tokens. |
| 14.3.3 | Browser storage sensitivity | PARTIAL | JWT and user object in `sessionStorage`; XSS would expose the token. |
| 15.1.1 | Dependency remediation timeframes | PARTIAL | Remediation report exists; no formal SLA per severity. |
| 15.1.2 | SBOM/component inventory | FAIL | No SBOM generation in CI. |
| 15.2.1 | Components within remediation window | VERIFIED | CI runs `pip-audit` and `npm audit --omit=dev --audit-level=high`; recent run green. |
| 15.3.3 | Mass-assignment controls | VERIFIED | Lesson update rejects every field outside the explicit allowlist before mutation; regression tests cover ownership, school, subject, class, scheme, template and structural fields. |
| 15.3.4 | Trusted client IP propagation | PARTIAL | Trust remains off; explicit CIDR validation, right-to-left parsing, HMAC keys and per-user budgets implemented and locally tested. Live Render peer/CIDRs unverified. |
| 15.4.2 | State checks and actions atomic | VERIFIED | Quota update uses guarded SQL; generation uses advisory lock. |
| 16.1.1 | Logging inventory | PARTIAL | Structured logs exist; no complete log inventory/retention/access document. |
| 16.2.1 | Log metadata | VERIFIED | structlog timestamp, level, event, user/account context. |
| 16.3.1 | Authentication events logged | VERIFIED | Login success/failure, lockout, MFA, reset events. |
| 16.3.2 | Authorization failures logged | PARTIAL | Some security events logged; not every 403. |
| 16.4.2 | Log access/modification protection | PARTIAL | Render log access controlled by account; no immutability/WORM. |
| 16.4.3 | Central log/alert delivery | PARTIAL | Throttled webhook/owner-email fallback implemented; production recipient and one live alert not yet verified. |
| 16.5.1 | Generic error to consumer | VERIFIED | Global 500 handler returns generic message; details logged server-side. |

## 4. OWASP API Security Top 10 (2023) traceability

| Risk | Status | Evidence and impact |
|---|---|---|
| API1:2023 Broken Object Level Authorization | PARTIAL | Owner-scoped IDOR tests cover schemes, weeks, lessons, jobs and templates (`test_authorization_idor.py`, 14 passed). Not every export token/download path or all 105 handlers has an A/B negative test. |
| API2:2023 Broken Authentication | PARTIAL | Strong lockout, bcrypt, JWT expiry/JTI/revocation and password-version checks. Gaps: optional MFA, 24-hour token with no idle timeout, token in `sessionStorage`, no session list/terminate-all. |
| API3:2023 Broken Object Property Level Authorization | VERIFIED | `normalize_lesson_updates` rejects unknown/protected fields before mutation; the ordinary lesson save no longer uses a generic `setattr` loop. Tests cover school, ownership, subject/class/scheme relations, template, status and structural fields. |
| API4:2023 Unrestricted Resource Consumption | PARTIAL | 50 MB upload cap, IP rate limits, account lockout, per-user upload/generate/resume/export budgets, AI quotas, bounded retries/tokens. Still no per-user storage quota, no bot challenge, and reads bypass IP budgets. |
| API5:2023 Broken Function Level Authorization | VERIFIED | 105 non-public handlers checked; all declare an auth dependency; platform-admin handlers require `require_platform_admin`. |
| API6:2023 Unrestricted Access to Sensitive Business Flows | PARTIAL | Registration, generation and credits are bounded; no bot/velocity control on registration, referrals or repeated generation beyond quotas. Payments are disabled. |
| API7:2023 Server Side Request Forgery | VERIFIED | No user-controlled URL fetch. Provider/storage/email endpoints are server configuration. |
| API8:2023 Security Misconfiguration | PARTIAL | CORS allow-list, debug off, docs off. Gaps: frontend security headers, HSTS off, CSP report-only/unsafe directives, proxy trust unverified. |
| API9:2023 Improper Inventory Management | PARTIAL | Code-level route inventory exists; no published API inventory, versioning/deprecation policy or SBOM. |
| API10:2023 Unsafe Consumption of APIs | PARTIAL | AI output is parsed/validated and identity is reasserted; payment webhook is signed/idempotent. Gaps: no documented provider data-processing/retention review; no circuit breaker for provider failure beyond bounded retries. |

## 5. Existing implementation evidence

| Area | Code evidence |
|---|---|
| Password hashing | `backend/src/auth.py` — bcrypt/Passlib |
| JWT | `backend/src/auth.py:84-156` — signature, expiry, `pwv`, `jti`; `backend/src/config.py:74` 24h |
| Logout | `backend/src/routers/auth.py:774`; `RevokedTokenDB` |
| MFA | `backend/src/mfa.py`; `routers/auth.py` setup/verify/disable/recovery; replay check `mfa_last_step` |
| Lockout | `backend/src/login_security.py`; 5 failures, escalating cooldown |
| Rate limiting | `backend/src/security.py:49-78` rules; `DbRateLimiter` shared DB store |
| Client IP | `backend/src/security.py:244-258`; trusted-proxy CIDR interface, forwarding disabled by default |
| CORS | `backend/src/main.py:204` exact `CORS_ORIGINS` |
| Security headers | `backend/src/security.py:330-360`; CSP report-only; HSTS opt-in |
| Authorization | `backend/src/auth.py:181-260` role dependencies; `docs/security/AUTHORIZATION-MATRIX.md` |
| Upload validation | `backend/src/routers/documents.py:40-108,162-300` — size, signature, DOCX archive/XML/macro/path checks |
| Filename safety | `backend/src/security.py:24-78` — basename sanitize and `safe_join` |
| AI prompt boundary | `backend/src/curriculum/generation_prompt.py`; `docs/security/CURRICULUM-AI-INPUT-SECURITY.md` |
| AI quotas | `backend/src/ai_quota.py`; `backend/src/entitlements.py` — 2 lesson plans, 5 AI generations/month |
| Bounded fallback | `backend/src/engines/zeli_generation.py`; `ai_provider.py` — one Groq fallback, 2 retries, 2,000 max tokens |
| Paystack | `backend/src/paystack.py:503` HMAC-SHA512; `routers/paystack.py:548`; `webhook_sweeper.py` leases/idempotency |
| Error handling | `backend/src/main.py` global handler; no traceback to client |
| Logging | `backend/src/logging_config.py` structured JSON; optional webhook adapter |
| Frontend session | `frontend/src/lib/auth-context.tsx` tab-scoped `sessionStorage`; logout clears it |

## 6. Existing automated test evidence

| Suite | Result |
|---|---|
| Full backend suite (local, after proxy/mass-assignment fixes) | **3010 passed, 22 skipped, 0 failed** |
| Targeted security suites | **177 passed, 0 failed** |
| Lesson mass-assignment regression | **31 passed** |
| Proxy/client-IP and spoofing regression | **34 passed** |
| Auth lifecycle | 42 tests |
| Logout/revocation | 7 tests |
| Login lockout | 7 tests |
| MFA | 3 tests |
| Authorization IDOR | 14 tests |
| Route inventory | 2 tests; **105 non-public handlers checked, 0 missing** |
| Upload security | 9 tests |
| Security hardening | 39 tests |
| Security headers | 2 tests |
| Security monitoring | 3 tests |
| Paystack subscriptions | 22 tests |
| Webhook sweeper | 13 tests |
| Prompt-injection corpus | 14 tests (12 cases + malformed output + identity override) |
| Frontend typecheck/build | Passed (46 static pages) |

Command used:

```bash
cd backend
python -m pytest -q
```

The targeted run covered all suites listed above and completed with 177 passed.

## 7. Critical and high-risk findings

### H1 — Mass assignment in lesson update (HIGH) — REMEDIATED 2026-10-31

- **ID:** API3:2023; ASVS 8.2.3, 15.3.3.
- **Original evidence:** `data_service.update_lesson_plan` iterated every submitted key and
  called `setattr` on any existing model attribute except a short denylist. A local probe
  changed `school_id` and `subject`.
- **Fix:** `backend/src/service.py` now validates the complete payload through
  `normalize_lesson_updates` before any mutation. `LESSON_EDITABLE_FIELDS` is an explicit
  teacher-content allowlist; ownership, school, subject/class, scheme/job, template, status,
  provenance, curriculum indicators and structural fields are rejected with HTTP 422.
- **Tests:** `backend/tests/test_lesson_update_mass_assignment.py` (31 tests) covers permitted
  edits, protected fields, unknown fields, no partial mutation, A/B isolation, persistence,
  reload and DOCX export. Existing save/reload and IDOR suites remain green.
- **Residual:** other endpoints that accept dictionaries were reviewed; the lesson-review
  draft path has its own allowlist, and preferences/templates use typed or explicit fields.
  No second generic model-`setattr` path was found.

### H2 — Render client-IP and rate-limit topology unverified (HIGH for pilot)

- **ID:** API4; ASVS 4.1.3, 15.3.4.
- **Evidence:** `TRUST_PROXY_HEADERS=false`; `client_ip()` uses the direct peer unless the peer
  is in `TRUSTED_PROXY_CIDRS`. No verified Render CIDRs. Render documents TLS termination and
  HTTP forwarding but publishes no inbound proxy CIDRs or XFF contract.
- **Impact:** with forwarding off, the API may see Render's proxy address, collapsing all
  teachers into one rate-limit key. Enabling forwarding without correct CIDRs lets a client
  forge `X-Forwarded-For` and evade limits.
- **Code remediation:** `client_ip()` now walks right-to-left, rejects malformed/oversized
  chains, normalizes IPv4-mapped IPv6, and only trusts the direct peer when explicitly
  allowlisted. Configuration rejects empty/invalid/wildcard CIDRs. Per-account budgets reduce
  dependence on IP identity. 34 proxy tests pass.
- **Remaining blocker:** runtime peer/CIDR verification requires isolated staging or Render
  support evidence. Trust remains disabled.
- **See:** `docs/security/RENDER-PROXY-AND-CLIENT-IP-VERIFICATION.md`.

### H3 — Platform-admin MFA enforcement (HIGH) — REMEDIATED 2026-10-31

- **ID:** API2; ASVS 6.3.3.
- **Fix applied:** production platform-admin mutations now require `mfa_enabled`; enrollment and
  status remain reachable without MFA; recovery/TOTP replay tests pass.
- **Remaining:** step-up for every sensitive read is not implemented; mutations are enforced.

### H4 — Frontend/backend security headers (HIGH) — CODE IMPLEMENTED, DEPLOYMENT VERIFICATION PENDING

- **ID:** API8; ASVS 3.4.1, 3.4.3, 3.4.4, 3.4.6.
- **Evidence:** `frontend/next.config.js` has no `headers()`; `frontend/src/middleware.ts` sets
  only `X-Robots-Tag`. Backend CSP is `Report-Only` by default and allows
  `'unsafe-inline'`/`'unsafe-eval'`; HSTS is opt-in.
- **Impact:** the HTML origin lacks baseline browser protections; a future XSS has weaker
  containment, and HSTS is not guaranteed.
- **Fix:** add headers at the frontend/CDN, remove unsafe CSP directives after nonce/hash
  migration, enforce CSP, enable HSTS on a verified HTTPS host.

### H5 — Session lifetime and token exposure (HIGH) — CODE REMEDIATED, DEPLOYMENT VERIFICATION PENDING

- **ID:** API2; ASVS 7.3.1, 7.3.2, 14.3.3.
- **Fix applied:** 2-hour JWT, 30-minute server-verified idle timeout, 12-hour absolute
  session, logout-all API/UI, password-change/reset revocation. Token remains in
  `sessionStorage`; no refresh-token rotation was introduced.
- **Remaining:** XSS containment still depends on CSP and frontend code quality.

### H6 — No tested backup/restore or central alerting (HIGH operational)

- **ID:** ASVS 14.2.7, 16.4.3; API4/API8 operational.
- **Evidence:** Neon Free has a 6-hour restore window and one manual snapshot; no restore has
  been executed. Render logs are the only central record; `SECURITY_ALERT_WEBHOOK_URL` is unset.
- **Impact:** data loss or a security event may be discovered late and cannot be recovered from
  a verified backup.
- **Fix:** execute the runbook against an isolated pilot DB, record restore evidence, configure
  a free alert channel, and document incident response ownership.

### H7 — Resource-consumption controls are incomplete (HIGH/MEDIUM)

- **ID:** API4; ASVS 5.2.4, 2.4.1.
- **Evidence:** 50 MB per upload, 10 uploads/5 min/IP, 30 generation requests/min/IP, AI quotas.
  No per-user storage quota, no bot challenge, read requests bypass rate limits, and PDF/export
  work is CPU-heavy.
- **Impact:** an invited or leaked account can exhaust free-tier CPU/bandwidth or storage.
- **Fix:** per-user upload/storage/export quotas, bounded concurrent exports, challenge or
  approval for registration, and monitoring of usage.

## 8. Medium and lower-risk findings

| ID | Finding | Impact | Fix |
|---|---|---|---|
| M1 | Uploaded originals are on ephemeral disk; R2 not wired | Restart can break multi-subject confirmation; original file lost | Persist originals to R2 and read back for confirmation |
| M2 | No antivirus/content-disarm scanning | Malicious PDF/DOCX may reach parser | Add a free scanner or quarantine workflow; document residual risk |
| M3 | No SBOM or dependency remediation SLA | Supply-chain visibility and patch timing unclear | Generate CycloneDX SBOM in CI; publish severity SLAs |
| M4 | Logs can contain user filenames | Filenames may contain pupil names or school data | Redact/truncate filenames; document log data classification |
| M5 | No cryptographic key inventory/rotation policy | Key compromise recovery is ad hoc | Inventory JWT/HMAC/provider/storage keys; define rotation |
| M6 | JWT has no `aud`/`typ` claim | Token confusion across API surfaces | Add `aud`/`typ`, validate both |
| M7 | No “sign out all sessions” | Lost device cannot be fully revoked | Session table + revoke-all endpoint/UI |
| M8 | No breached-password check | Weak but policy-compliant passwords | Add k-anonymity breached-password check |
| M9 | DB least privilege/SSL not verified | Over-privileged app role; TLS unverified | Owner verifies role grants and `sslmode=require` |
| M10 | No retention automation | Old uploads/exports/logs accumulate | Define retention and cleanup job |
| M11 | Reset email blocked by `resend.dev` | Teachers cannot self-reset during pilot | Verify domain or owner-side resets |
| M12 | No published API inventory/versioning | Deprecated endpoints may linger | Generate inventory from OpenAPI in staging; document lifecycle |
| M13 | Health endpoint exposes version | Minor fingerprinting | Return version only to admins or omit |
| M14 | `school_id` in user response | Minor tenant metadata exposure | Return only fields the UI needs |
| M15 | No DB migration restore rehearsal | Migration failure recovery untested | Test migrations + rollback on a Neon branch |

## 9. Infrastructure-dependent blockers

| Blocker | Why it blocks verification | Owner action |
|---|---|---|
| Neon console/API access | Plan, storage, compute, role grants, SSL and snapshot state unverified | Provide read-only console/API access or record screenshots |
| Render proxy CIDRs | Cannot verify `client_ip()` or safely enable forwarding | Inspect request peer addresses and configure CIDRs |
| Render dashboard | Cannot verify TLS/HSTS/header behavior at the edge | Owner checks service settings and response headers |
| Backup/restore | No isolated pilot DB or restore test | Create empty pilot DB; execute runbook; record evidence |
| Central alerting | No webhook/alert account configured | Configure a free webhook or accept manual monitoring |
| Staging | No isolated staging host | Use local Docker/CI plus owner-approved pilot stack |
| Email domain | `onboarding@resend.dev` cannot reach teachers | Verify a domain or use owner-side resets |
| Database least privilege | Production role/grants unverified | Inspect Neon role and restrict DDL/runtime rights |
| WAF/bot challenge | No provider configured | Evaluate a free challenge only after privacy/accessibility review |

## 10. Ordered remediation plan

| Order | Action | Addresses | Effort |
|---|---|---|---|
| 1 | **DONE** — Replace lesson-update `setattr` loop with an explicit editable-field allowlist; reject immutable/provenance fields | H1, API3, ASVS 8.2.3/15.3.3 | Small |
| 2 | **CODE DONE / LIVE BLOCKED** — Harden proxy parsing, validate CIDRs, add forged-XFF and per-user budget tests; verify Render peer/CIDRs on isolated staging before enabling trust | H2, API4, ASVS 4.1.3 | Medium |
| 3 | Require MFA for platform admins; add step-up for activation/reset/maintenance | H3, API2, ASVS 6.3.3 | Medium |
| 4 | Add frontend CSP/HSTS/XFO/referrer/nosniff; remove `unsafe-inline`/`unsafe-eval`; enforce CSP | H4, API8, ASVS 3.4.x | Medium |
| 5 | Shorten access token, add refresh rotation/idle timeout, session list/revoke-all | H5, API2, ASVS 7.3/7.5 | Medium |
| 6 | Execute backup/restore runbook; configure free alert delivery; document incident response | H6, ASVS 14.2.7/16.4.3 | Medium |
| 7 | Add per-user upload/storage/export quotas and bounded export concurrency | H7, API4 | Medium |
| 8 | Wire uploads to R2; add retention/cleanup; consider AV scanning | M1/M2/M10 | Medium |
| 9 | Add SBOM, dependency SLA, key inventory/rotation, JWT `aud`/`typ` | M3/M5/M6, ASVS 9/11/15 | Medium |
| 10 | Add breached-password check, log redaction, API inventory/versioning | M4/M8/M12 | Small–Medium |

Do not treat a “green CI” as closure of these items. Each needs a test or owner evidence.

## 11. Exact tests required before the friends-and-family pilot

### Must pass before inviting teachers

1. **A/B authorization matrix** across scheme, week, lesson, job, template, export-token and
   download-token IDs: read, update, delete, export, regenerate as User B. Expect 403/404 and
   no victim mutation.
2. **Mass-assignment negative tests**: submit `owner_id`, `school_id`, `job_id`, `scheme_id`,
   `subject`, `class_level`, `indicator_codes`, `teacher_edited`, `status`, `created_at`;
   expect rejection or no change.
3. **Forged proxy tests**: `X-Forwarded-For` from untrusted peer ignored; from configured trusted
   peer uses first hop; two different clients do not share a lockout bucket.
4. **MFA enforcement test**: platform admin without MFA cannot reach privileged mutations;
   enrollment/step-up required; recovery code single-use.
5. **Session tests**: expiry, password change invalidation, logout revocation, revoke-all,
   idle timeout, token replay.
6. **Header tests**: frontend and API responses contain CSP, HSTS (on HTTPS host), nosniff,
   frame-ancestors, referrer policy; CSP has no `unsafe-eval` and no unnecessary
   `unsafe-inline`.
7. **Upload tests**: ZIP traversal, bomb, malformed archive, macro, XML entity, wrong MIME,
   oversized file, failed-upload cleanup, restart-before-confirm behavior.
8. **AI tests**: max input/output, one fallback, no duplicate credit on provider failure,
   prompt-injection corpus 14/14, no secret in provider error/log.
9. **Payment tests**: invalid signature, duplicate event, wrong amount/currency, replay,
   wrong customer, disabled mode. Keep test mode; no live charge.
10. **Backup/restore rehearsal**: dump pilot DB, restore to empty pilot DB, verify counts,
    login, lesson edit, DOCX/PDF export.
11. **Rate/resource abuse**: upload/generate/export bursts, per-user quota, 429 behavior,
    read endpoints not creating a denial-of-service for normal polling.
12. **Frontend browser test**: sessionStorage cleared on logout, no token in URL/log, CSP
    violations monitored, mobile upload notice still visible.

### Commands

```bash
cd backend
python -m pytest -q tests/test_authorization_idor.py tests/test_authorization_route_inventory.py
python -m pytest -q tests/test_auth_lifecycle.py tests/test_logout_revocation.py tests/test_mfa.py
python -m pytest -q tests/test_upload_security.py tests/security/test_curriculum_prompt_injection.py
python -m pytest -q tests/test_paystack_subscriptions.py tests/test_webhook_sweeper.py

cd frontend
npx tsc --noEmit
npm run build
```

## 12. Explicit technical-readiness conclusion

**Status: CONDITIONAL — NOT READY for public launch or unsupervised pilot.**

- The core auth, ownership, upload and payment-test controls are credible and locally tested.
- The lesson mass-assignment flaw (H1) is fixed and covered by 31 regression tests.
- Optional admin MFA, unverified proxy topology, missing frontend headers and the 24-hour token
  remain material enough to block an open pilot.
- A **small, invite-only, owner-supervised pilot** may proceed after H2–H5 are fixed and the
  §11 must-pass tests are green.
- Production/staging verification of TLS, proxy CIDRs, backups, alerting, database privileges
  and email remains BLOCKED. Those must be recorded as owner evidence before calling the pilot
  “security-ready”.
- This document does not certify ASVS Level 2 or OWASP compliance. It records the current
  evidence and gaps.
