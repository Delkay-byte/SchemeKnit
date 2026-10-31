# Authentication and Rate Limiting

Date: 2026-10-31  
Status: **Implemented locally — staging validation blocked by infrastructure**

## Implemented account policy

- 5 failed attempts in a rolling 15-minute window trigger a 1-minute cooldown.
- Repeated lockouts within 24 hours escalate 5 → 15 → 30 → 60 minutes.
- No permanent lockout.
- Counters keyed by HMAC of the normalized account identifier, not IP.
- Successful login and successful password reset clear failure state.
- Generic `401 Invalid email or password` for wrong credentials.
- `429` with `Retry-After` for cooldown.
- Unknown accounts perform a dummy bcrypt verification to reduce timing leakage.
- Recovery through the password-reset channel remains available.

Files: `backend/src/login_security.py`, `backend/src/routers/auth.py`,
migration `v044_security_counters`.

## Implemented shared IP policy

- `DbRateLimiter` stores fixed-window counters in `rate_limit_counters`.
- Atomic `INSERT ... ON CONFLICT ... count = count + 1` updates.
- Shared across workers and restarts; old buckets cleaned up.
- `RATE_LIMIT_BACKEND=db` is required for non-SQLite production.
- High-risk routes return `503` if the shared store is unavailable; they never
  silently become unrestricted.
- Covered by `tests/test_login_lockout.py`.

## Trusted proxy handling

`client_ip()` trusts `X-Forwarded-For` only when `TRUST_PROXY_HEADERS=true` and
the direct peer matches `TRUSTED_PROXY_CIDRS`. Empty CIDRs trusts no proxy.
Forged headers from an untrusted peer are ignored and tested.

**Still required:** verify Render's actual proxy CIDRs/topology in staging before
enabling `TRUST_PROXY_HEADERS`.

## MFA

TOTP MFA is implemented for platform administrators:

- enrollment through `/api/auth/mfa/setup` and `/api/auth/mfa/verify-setup`,
- 6-digit RFC 6238 TOTP, 30-second step,
- replay protection via `mfa_last_step`,
- 8 single-use bcrypt-hashed recovery codes,
- disable requires password + TOTP/recovery code,
- login requires MFA when enabled,
- failures use the same account cooldown path.

Tests: `tests/test_mfa.py`.

**No frontend enrollment UI was added in this task.** Admin enrollment is API
only. Do not force enrollment for existing admins until a UI and recovery process
are reviewed.
