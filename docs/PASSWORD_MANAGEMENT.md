# Password Management

## Password Policy

All accounts (including platform admin) use the same policy:

- Minimum **8 characters**
- At least **one letter**
- At least **one number**
- At least **one symbol**

The authoritative policy is published by `GET /api/auth/setup/status` under `password_policy`. The frontend mirrors this exactly (see `lib/password-policy.ts`).

## Password Change (self-service)

An authenticated user who knows their current password can change it:

- **Endpoint:** `POST /api/auth/change-password`
- **Body:** `{ current_password, new_password }`
- The backend verifies the current password before accepting the change.
- The new password must satisfy the policy and must differ from the current one.
- On success, a fresh token is issued (stamped with the new password version). All other sessions for that user are invalidated.
- **UI:** Settings → Change Password (available for Teacher, School Admin, and Platform Admin).

## Password Reset (forgot password)

Reset is a **token-based, admin-initiated** flow — a user cannot reset their own password without authentication.

### Flow

1. An admin (school admin or platform admin) initiates a reset for a target user.
2. The backend generates a **one-time reset token** (`secrets.token_urlsafe(32)`).
3. Only the SHA-256 digest is stored in the database. The raw token is returned once to the initiating admin.
4. The admin delivers the token to the user out-of-band (the platform has no email delivery yet).
5. The user visits `/reset-password`, enters the token, and sets a new password.
6. The token is consumed (single-use) and all existing sessions are invalidated.

### Token Security

- **Cryptographically random:** `secrets.token_urlsafe(32)` (256 bits of entropy).
- **Hashed at rest:** only the SHA-256 digest is persisted.
- **Single-use:** consumed on first successful use; a second attempt returns 410.
- **Expiring:** 30-minute TTL (configurable via `PASSWORD_RESET_TOKEN_TTL_MINUTES`).
- **Bound to target:** a token cannot be used for a different account.
- **Never logged:** audit entries record who/when/what, never the token itself.

### Endpoints

| Endpoint | Auth | Purpose |
|---|---|---|
| `POST /api/auth/users/{id}/initiate-reset` | admin | Admin initiates reset, gets one-time token |
| `GET /api/auth/reset-token/validate?token=...` | none | Public token check (returns target email) |
| `POST /api/auth/confirm-password-reset` | none | Complete reset with token + new password |

## Session Invalidation

Every JWT is stamped with a `pwv` (password-version) claim — the microsecond timestamp of the user's last password change. On every authenticated request, the server compares the token's `pwv` with the user's current `password_changed_at`. A mismatch means the token was issued before the password changed, and the request is rejected with **401**.

This means:
- After a **password change**, all sessions except the current one are invalidated.
- After a **password reset**, all sessions are invalidated (the user must log in fresh).
- Legacy tokens without a `pwv` claim pass through unchecked (backward compatibility).

## Rate Limiting

Sensitive endpoints are rate-limited (in-memory sliding window):

| Endpoint group | Limit | Window |
|---|---|---|
| `/api/auth/login` | 20 | 60s |
| `/api/auth/setup-platform-admin` | 5 | 300s |
| `/api/auth/change-password` | 10 | 60s |
| `/api/auth/confirm-password-reset` | 10 | 300s |
| `/api/auth/reset-token/validate` | 20 | 300s |
| `/api/auth/users/` (initiate-reset) | 30 | 60s |

Multi-worker deployments must also rate-limit at the reverse proxy.

## Audit Logging

All password events are recorded in `platform_audit_logs`:

| Action | Trigger |
|---|---|
| `platform_admin_created` | Bootstrap or CLI admin creation |
| `password_changed` | Self-service password change |
| `password_reset_initiated` | Admin initiated a token-based reset |
| `password_reset_completed` | User completed a reset with a token |
| `teacher_password_reset` | School admin direct-set reset (legacy) |
| `platform_admin_password_reset_cli` | CLI break-glass recovery |

**Never audited:** plaintext passwords, reset tokens, password hashes.

## Role Boundaries for Resets

| Actor | Can reset |
|---|---|
| Teacher | Nobody (self-service change only) |
| School Admin | Teachers in their own school |
| Platform Admin | Any account (school admin, teacher, individual teacher, another platform admin) |

School admins cannot reset platform admins or teachers from other schools. These boundaries are enforced server-side, not just in the UI.
