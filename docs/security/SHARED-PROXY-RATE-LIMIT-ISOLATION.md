# Shared Proxy Rate-Limit Isolation

Status: **IMPLEMENTED AND LOCALLY VERIFIED**. Live Render proxy
differentiation remains **UNVERIFIED**: production keeps
`TRUST_PROXY_HEADERS=false`, and no real request through the Render ingress was
observed from this workstation.

## 1. The risk

Render may present several unrelated teachers through one direct peer address.
A restrictive per-IP counter would then let one teacher's uploads, generations
or exports exhaust another teacher's opportunity to work. SchemeKnit therefore
treats the IP address as a broad abuse signal only. Authenticated operations are
identified and limited by the authenticated account (`user.id` from the access
token). The direct-peer parser never trusts `X-Forwarded-For` unless the socket
peer is in an explicitly configured trusted CIDR; no Render CIDR is invented.

`TRUST_PROXY_HEADERS=false` remains the production value. If the Render topology
is later verified, enabling header trust is a separate owner action.

## 2. Complete IP-limit inventory

These are broad aggregate ceilings applied by the shared middleware to the
direct peer. They are not teacher quotas.

| Path prefix | Limit / window | Notes |
|---|---:|---|
| `/api/auth/login` | 200 / 60 s | Account lockout and Turnstile are primary |
| `/api/auth/setup` | 10 / 300 s | First-run bootstrap |
| `/api/auth/activation/validate` | 120 / 300 s | Activation-code checks |
| `/api/auth/setup-school-admin` | 10 / 300 s | School-admin bootstrap |
| `/api/auth/users/` | 120 / 60 s | Authenticated admin user management |
| `/api/auth/setup-platform-admin` | 5 / 300 s | Very strict one-time bootstrap |
| `/api/auth/change-password` | 60 / 60 s | Authenticated |
| `/api/auth/confirm-password-reset` | 60 / 300 s | Public, single-use reset token + Turnstile |
| `/api/auth/reset-token/validate` | 120 / 300 s | Public, token validation only |
| `/api/platform-admin/activate` | 120 / 300 s | Platform admin only |
| `/api/documents/upload` | 120 / 300 s | Account budget is primary |
| `/api/templates/analyze` | 120 / 300 s | Authenticated |
| `/api/templates/upload` | 120 / 300 s | Authenticated |
| `/api/generation/` | 300 / 60 s | Account budgets, credits and provider budget are primary |

Loopback is exempt only when `DEBUG=true`. Production never exempts a real peer
because a proxy presents it as localhost.

## 3. Authenticated account budgets

`security.AUTHENTICATED_BUDGETS`, keyed by the authenticated `user.id` and
shared through the DB-backed limiter:

| Operation | Budget | Primary identity | Endpoints |
|---|---:|---|---|
| Upload | 30 / 15 min | `user.id` | `POST /api/documents/upload` |
| Generate | 30 / 10 min | `user.id` | `POST /api/generation/{scheme}/generate` |
| Resume | 20 / 10 min | `user.id` | `POST /api/generation/{scheme}/generate/resume` |
| Export | 60 / 10 min | `user.id` | DOCX, PDF, XLSX, ZIP, download-url |

These values were deliberately raised from the previous 10/20/10/30:

- 30 uploads / 15 min allows several subjects, corrections, re-uploads and
  browser retries in one planning session.
- 30 generations / 10 min is above normal multi-indicator work; actual billable
  generation is still bounded by credits and the provider budget.
- 20 resumes / 10 min allows interrupted jobs to be retried without opening a
  runaway loop.
- 60 exports / 10 min covers exporting many lessons and retrying a download.

The account budget remains restrictive for the individual account that exceeds
its own limit; it does not block a different teacher.

## 4. Other identities

| Control | Identity | Behaviour |
|---|---|---|
| Login failures | HMAC of normalized email (`login_security.account_key`) | Progressive cooldown, independent per account |
| Registration | Email uniqueness + invitation code + Turnstile `register` | Direct API calls cannot skip the challenge |
| Password-reset completion | Single-use reset token + Turnstile `password_reset` | Token and challenge are both required when enabled |
| Job resume | Authenticated `user.id` + job/scheme ownership | Another owner gets 404/403 |
| Upload/read/delete document | Authenticated `user.id` + scheme ownership | Another owner cannot inspect or delete |
| Cached AI generation | Cache key + job id | No provider call, no duplicate credit |

Email-derived login throttling is account-scoped, not IP-scoped. Account lockout
is the primary defence against credential stuffing; the broad login IP ceiling
exists only to stop a single peer from flooding the endpoint.

## 5. Shared store and fail-closed behaviour

`RateLimitCounterDB` (migration `v044`) stores fixed-window counters in the
shared database, so workers and restarts see the same state. High-risk
operations retain their documented fail-closed handling when the shared store is
unavailable. HTTP 429 responses carry `Retry-After`.

## 6. Ten-teacher shared-peer evidence

`backend/tests/test_shared_proxy_isolation.py`:

- ten teachers using one peer can each perform uploads, generations and exports
  without exhausting another teacher's allowance;
- one account's generation abuse produces 429 for that account only;
- one account's failed login does not lock another account;
- ordinary combined usage (10 teachers × 20 generations = 200) stays below the
  300/min broad IP ceiling;
- sustained abuse still trips the IP breaker;
- two different peers keep separate IP buckets;
- forged forwarded headers cannot create a new identity;
- shared DB counters remain correct across limiter instances and concurrent
  calls.

`backend/tests/test_integrated_release_security.py` adds a ten-teacher
same-peer scenario that combines account budgets, storage reservations and a
single abusive account. The abusive account is blocked at its own 429 while an
honest teacher continues.

Targeted Part 1 run: **89 passed**. The complete backend suite result is in the
release report.

## 7. Remaining live limitation

The actual Render ingress topology has not been observed. Production keeps
`TRUST_PROXY_HEADERS=false`; if Render presents a shared peer, all teachers share
the broad IP buckets above. The deliberate ceilings and per-account primary
controls are the mitigation. Do not enable header trust or invent a proxy CIDR
without a real request to verify the chain.
