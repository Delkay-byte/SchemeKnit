# Authentication and Rate Limiting

Date: 2026-10-31  
Status: **Design only — not implemented in this task**  
Reason: staging infrastructure is unavailable; security controls cannot be
staging-qualified.

## Current behaviour

- `POST /api/auth/login` verifies bcrypt password.
- Bad credentials return a generic `401 Invalid email or password`.
- No per-account failure counter exists.
- `backend/src/security.py` has an in-memory sliding-window limiter:
  - login: 20 requests / 60 seconds per IP
  - registration-related setup: 5–10 / 300 seconds
  - upload: 10 / 300 seconds
  - generation: 30 / 60 seconds
- Safe methods bypass budgets.
- Localhost is exempt.
- The limiter is a process-local dictionary; no restart or multi-worker sharing.

## Required account policy

Initial policy to implement and usability-test:

| Condition | Action |
|---|---|
| 5 failed attempts within 15 minutes | 1-minute cooldown |
| Next lockout within rolling 24 hours | 5-minute cooldown |
| Further repeated lockout | 15-minute cooldown |
| Persistent repeated lockouts | maximum 60-minute cooldown |

Rules:

- No permanent lockout from password failures.
- Counters keyed by normalized account identifier, across all IPs.
- Atomic database updates; no read-modify-write race.
- `locked_until` stored in UTC server time.
- `Retry-After` on 429/423 response.
- Generic public message; never reveal account existence.
- Successful login and successful reset clear the current failure counter.
- Escalation history remains for the rolling 24-hour window.
- Account recovery remains available through the separate reset channel.
- Audit events for every cooldown and every failed attempt aggregate.
- Do not use CAPTCHA as the only control; add step-up verification if abuse
  continues.

## Required IP policy

Endpoint-specific budgets, per IP and per account:

| Endpoint | Proposed IP budget | Proposed account budget |
|---|---|---|
| Login | 20 / 10 min | 5 / 15 min |
| Registration | 5 / hour | 3 / hour per email |
| Password reset request | 5 / hour | 3 / hour per email |
| Reset-token validation | 20 / hour | — |
| OTP/verification | 10 / 10 min | 5 / 10 min |
| AI generation | 10 / 10 min | plan quota |
| Upload/analyze | 10 / 10 min | 20 / hour |
| Export | 20 / 10 min | 40 / hour |

Requirements:

- Shared store across workers: PostgreSQL table with atomic UPSERT, or existing
  Redis if provisioned.
- Cleanup old rows by expiry.
- Trusted-proxy extraction only; never blindly trust `X-Forwarded-For`.
- Fairness for school NAT: account-level control must be primary; IP limit must
  not lock an entire school because one user abuses it.
- 429 with `Retry-After`.
- Security log event without passwords/tokens/lesson content.

## Trusted proxy design

Render forwards requests through its edge proxy. The backend must:

1. Accept a configured trusted proxy CIDR/host set.
2. Only read forwarding headers when the direct peer is trusted.
3. Define whether the left-most or right-most address is the client, based on
   Render's actual documented behavior.
4. Reject or ignore forged headers from untrusted peers.
5. Be covered by tests that spoof `X-Forwarded-For` and assert the limit key does
   not change.

## What was not changed

No lockout schema, migration, middleware, or tests were added because the
staging environment required to validate them does not exist. The existing
authentication checks were not weakened.
